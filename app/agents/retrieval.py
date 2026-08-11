import uuid

from app.vector_store import search_chunks


def retrieve_relevant_chunks(query: str, user_id: uuid.UUID, limit: int = 20) -> list[dict]:
    """The Retrieval agent: given a user's question, find their most relevant document chunks.

    limit is deliberately far wider than the usual top-3/top-5. Measured on real
    data: an irrelevant query ("how do I fix my car engine") scored 0.495 while a
    genuinely relevant one ("what are my employment dates") scored 0.455 against
    the correct chunk — this embedding model's similarity ranking simply doesn't
    separate relevant from irrelevant at this scale, so a tight cutoff drops real
    answers. With a handful of personal documents per user (~14 chunks), this
    amounts to "retrieve everything, let the LLM in Generation/Validator do the
    real relevance filtering", which it does far better than cosine similarity.

    This does NOT scale to large corpora: at hundreds of chunks it would retrieve
    a small fraction anyway and cost far more tokens. That case needs a stronger
    embedding model or a reranking step, not a bigger number here.
    """
    return search_chunks(query, user_id, limit=limit)
