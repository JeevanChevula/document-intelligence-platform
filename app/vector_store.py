import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import get_settings
from app.embeddings import embed_texts, embed_texts_sparse

# how many candidates each arm of the hybrid search contributes before fusion.
# Generous on purpose: the two arms rank very differently, and fusion can only
# reorder what it is given.
PREFETCH_LIMIT = 40


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection() -> None:
    """Create the collection with both a dense and a sparse vector, if missing.

    The dense vector stays unnamed for backward compatibility with points
    written before hybrid search existed; the sparse one is named. Qdrant does
    not allow adding a sparse vector to a live collection, so switching to
    hybrid requires recreating it — see scripts/reindex_hybrid.py, which rebuilds
    from the chunk text already stored in each point's payload rather than
    re-reading any PDFs.
    """
    settings = get_settings()
    client = get_qdrant_client()

    if not client.collection_exists(settings.qdrant_collection_name):
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=settings.embedding_dimension, distance=Distance.COSINE),
            sparse_vectors_config={settings.sparse_vector_name: SparseVectorParams()},
        )


def collection_has_sparse_vectors() -> bool:
    """Whether the live collection was created with a sparse vector configured.

    A collection built before hybrid search has dense vectors only, and querying
    a sparse vector it doesn't have is an error rather than an empty result — so
    search falls back to dense-only until the reindex script has been run.
    """
    settings = get_settings()
    client = get_qdrant_client()

    if not client.collection_exists(settings.qdrant_collection_name):
        return False
    sparse_config = client.get_collection(settings.qdrant_collection_name).config.params.sparse_vectors
    return bool(sparse_config) and settings.sparse_vector_name in sparse_config


def upsert_chunks(document_id: uuid.UUID, user_id: uuid.UUID, chunks: list[str]) -> int:
    if not chunks:
        return 0

    settings = get_settings()
    ensure_collection()

    vectors = embed_texts(chunks)

    # writing a sparse vector to a collection that has none is a hard error, so
    # a deploy that hasn't run scripts/reindex_hybrid.py yet degrades to
    # dense-only indexing rather than failing every upload. Consistent with how
    # OCR and indexing failures are handled: never block the upload outright.
    hybrid = collection_has_sparse_vectors()
    sparse_vectors = embed_texts_sparse(chunks) if hybrid else [None] * len(chunks)

    def _vector(dense: list[float], sparse) -> dict | list[float]:
        if sparse is None:
            return dense
        indices, values = sparse
        return {
            "": dense,  # unnamed dense vector, as written before hybrid search
            settings.sparse_vector_name: SparseVector(indices=indices, values=values),
        }

    points = [
        PointStruct(
            id=str(uuid.uuid5(document_id, str(index))),
            vector=_vector(vector, sparse),
            payload={
                "document_id": str(document_id),
                "user_id": str(user_id),
                "chunk_index": index,
                "text": chunk,
            },
        )
        for index, (chunk, vector, sparse) in enumerate(zip(chunks, vectors, sparse_vectors))
    ]

    get_qdrant_client().upsert(collection_name=settings.qdrant_collection_name, points=points)
    return len(points)


def delete_document_chunks(document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Remove every chunk belonging to one document.

    Filters on user_id as well as document_id for the same reason search_chunks
    does: the caller's document id is never trusted on its own, so even a
    mismatched id can only ever delete the caller's own data.
    """
    settings = get_settings()
    ensure_collection()

    get_qdrant_client().delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id))),
                FieldCondition(key="user_id", match=MatchValue(value=str(user_id))),
            ]
        ),
    )


def search_chunks(query: str, user_id: uuid.UUID, limit: int = 5) -> list[dict]:
    """Hybrid search: dense semantic similarity fused with BM25 keyword matching.

    The two arms fail in opposite directions, which is the point of running both.
    Dense embeddings capture meaning but are blind to identifiers — "ABCDE1234F"
    or a date has no semantic content to encode, so there is nothing for cosine
    similarity to be similar *to*. BM25 matches those exactly, but is blind to
    paraphrase: it cannot connect "where do I work" to "employed at".

    Results are combined with Reciprocal Rank Fusion, which merges on *rank*
    rather than score. That matters because the two scales aren't comparable —
    cosine similarity sits in 0-1 while BM25 is unbounded, so averaging them
    would let BM25 silently dominate.

    Deliberately no score_threshold: real testing showed cosine similarity from
    this embedding model doesn't cleanly separate relevant from irrelevant
    content (an irrelevant query scored higher than a genuinely relevant one) —
    so relevance judgment is left to the LLM in Generation/Validator instead,
    which understands meaning far better than a raw similarity cutoff can.
    """
    settings = get_settings()
    ensure_collection()

    query_vector = embed_texts([query])[0]
    user_filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))])
    client = get_qdrant_client()

    if not collection_has_sparse_vectors():
        # collection predates hybrid search — dense-only until reindexed
        results = client.query_points(
            collection_name=settings.qdrant_collection_name,
            query=query_vector,
            query_filter=user_filter,
            limit=limit,
        )
        return _to_chunks(results)

    indices, values = embed_texts_sparse([query])[0]

    results = client.query_points(
        collection_name=settings.qdrant_collection_name,
        prefetch=[
            # the user filter goes on BOTH arms, not just the outer query: each
            # arm searches independently, so an unfiltered arm would rank another
            # user's chunks into the candidate set before fusion ever runs
            Prefetch(query=query_vector, using="", filter=user_filter, limit=PREFETCH_LIMIT),
            Prefetch(
                query=SparseVector(indices=indices, values=values),
                using=settings.sparse_vector_name,
                filter=user_filter,
                limit=PREFETCH_LIMIT,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        query_filter=user_filter,
        limit=limit,
    )

    return _to_chunks(results)


def _to_chunks(results) -> list[dict]:
    return [
        {
            "text": point.payload["text"],
            "document_id": point.payload["document_id"],
            "chunk_index": point.payload["chunk_index"],
            "score": point.score,
        }
        for point in results.points
    ]
