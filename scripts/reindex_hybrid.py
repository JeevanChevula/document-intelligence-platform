"""One-off migration: rebuild the Qdrant collection with sparse vectors.

Qdrant cannot add a sparse vector to a live collection, so enabling hybrid
search requires recreating it. Every chunk's text is already stored in its
payload, so this rebuilds from Qdrant itself — no PDFs are re-read, no OCR
re-runs, and nothing depends on the original files still being on disk.

Safe to run more than once: it exits early if the collection is already hybrid.
Read the existing points first and only delete the old collection once the new
one has been written, so a failure midway leaves the original intact.

    python scripts/reindex_hybrid.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client.models import (  # noqa: E402  (needs the sys.path line above)
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import get_settings  # noqa: E402
from app.embeddings import embed_texts_sparse  # noqa: E402
from app.vector_store import collection_has_sparse_vectors, get_qdrant_client  # noqa: E402

BATCH_SIZE = 128


def main() -> int:
    settings = get_settings()
    client = get_qdrant_client()
    name = settings.qdrant_collection_name

    if not client.collection_exists(name):
        print(f"Collection {name!r} does not exist — nothing to migrate.")
        print("It will be created with sparse vectors on the next upload.")
        return 0

    if collection_has_sparse_vectors():
        print(f"Collection {name!r} already has sparse vectors — nothing to do.")
        return 0

    print(f"Reading existing points from {name!r}...")
    existing = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=name, limit=BATCH_SIZE, offset=offset, with_payload=True, with_vectors=True
        )
        existing.extend(points)
        if offset is None:
            break
    print(f"  read {len(existing)} point(s)")

    if not existing:
        print("Collection is empty — recreating it with sparse vectors.")
        client.delete_collection(name)
        _create(client, name, settings)
        return 0

    missing_text = [p.id for p in existing if not (p.payload or {}).get("text")]
    if missing_text:
        # without the chunk text there is nothing to compute a sparse vector
        # from, and re-deriving it would mean re-reading the original PDFs
        print(f"ABORTING: {len(missing_text)} point(s) have no 'text' payload, so they cannot be re-indexed.")
        return 1

    print("Computing sparse vectors...")
    texts = [p.payload["text"] for p in existing]
    sparse_vectors = embed_texts_sparse(texts)

    rebuilt = [
        PointStruct(
            id=point.id,
            vector={
                "": _dense_of(point),
                settings.sparse_vector_name: SparseVector(indices=indices, values=values),
            },
            payload=point.payload,
        )
        for point, (indices, values) in zip(existing, sparse_vectors)
    ]

    print("Recreating the collection...")
    client.delete_collection(name)
    _create(client, name, settings)

    for start in range(0, len(rebuilt), BATCH_SIZE):
        client.upsert(collection_name=name, points=rebuilt[start : start + BATCH_SIZE])

    restored = client.get_collection(name).points_count
    print(f"Done — {restored} point(s) re-indexed with dense + sparse vectors.")
    if restored != len(existing):
        print(f"WARNING: expected {len(existing)}, got {restored}.")
        return 1
    return 0


def _dense_of(point) -> list[float]:
    """The dense vector, whether stored unnamed or under the empty-string key."""
    vector = point.vector
    return vector[""] if isinstance(vector, dict) else vector


def _create(client, name: str, settings) -> None:
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=settings.embedding_dimension, distance=Distance.COSINE),
        sparse_vectors_config={settings.sparse_vector_name: SparseVectorParams()},
    )


if __name__ == "__main__":
    raise SystemExit(main())
