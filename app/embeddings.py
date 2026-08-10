from functools import lru_cache

from fastembed import TextEmbedding

from app.config import get_settings


@lru_cache
def _get_embedding_model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(model_name=settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    return [vector.tolist() for vector in model.embed(texts)]
