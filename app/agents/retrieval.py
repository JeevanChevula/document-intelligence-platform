import uuid

from app.vector_store import search_chunks


def retrieve_relevant_chunks(query: str, user_id: uuid.UUID, limit: int = 5) -> list[dict]:
    """The Retrieval agent: given a user's question, find their most relevant document chunks."""
    return search_chunks(query, user_id, limit=limit)
