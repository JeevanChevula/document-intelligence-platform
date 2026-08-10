import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import get_settings
from app.embeddings import embed_texts


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant_client()

    if not client.collection_exists(settings.qdrant_collection_name):
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=settings.embedding_dimension, distance=Distance.COSINE),
        )


def upsert_chunks(document_id: uuid.UUID, user_id: uuid.UUID, chunks: list[str]) -> int:
    if not chunks:
        return 0

    settings = get_settings()
    ensure_collection()

    vectors = embed_texts(chunks)

    points = [
        PointStruct(
            id=str(uuid.uuid5(document_id, str(index))),
            vector=vector,
            payload={
                "document_id": str(document_id),
                "user_id": str(user_id),
                "chunk_index": index,
                "text": chunk,
            },
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    get_qdrant_client().upsert(collection_name=settings.qdrant_collection_name, points=points)
    return len(points)


def search_chunks(query: str, user_id: uuid.UUID, limit: int = 5) -> list[dict]:
    settings = get_settings()
    ensure_collection()

    query_vector = embed_texts([query])[0]

    results = get_qdrant_client().query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]),
        limit=limit,
        score_threshold=settings.retrieval_score_threshold,
    )

    return [
        {
            "text": point.payload["text"],
            "document_id": point.payload["document_id"],
            "chunk_index": point.payload["chunk_index"],
            "score": point.score,
        }
        for point in results.points
    ]
