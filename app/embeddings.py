from functools import lru_cache

from fastembed import SparseTextEmbedding, TextEmbedding

from app.config import get_settings


@lru_cache
def _get_embedding_model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(model_name=settings.embedding_model_name)


@lru_cache
def _get_sparse_embedding_model() -> SparseTextEmbedding:
    settings = get_settings()
    return SparseTextEmbedding(model_name=settings.sparse_embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Dense embeddings — meaning-based, for semantic similarity."""
    model = _get_embedding_model()
    return [vector.tolist() for vector in model.embed(texts)]


def embed_texts_sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Sparse BM25 embeddings — token-based, for exact keyword matching.

    Returned as (indices, values) pairs: a sparse vector stores only the tokens
    that actually appear, rather than a fixed-width array of floats.

    BM25 is statistical rather than neural — roughly 10MB, versus 532MB for
    SPLADE — which is what makes it viable on a 2GB instance. It exists to catch
    what dense embeddings are structurally bad at: identifiers, codes and dates.
    A PAN like "ABCDE1234F" carries no meaning to embed, so semantic similarity
    has nothing to work with, while exact token matching finds it immediately.
    """
    model = _get_sparse_embedding_model()
    return [(vector.indices.tolist(), vector.values.tolist()) for vector in model.embed(texts)]
