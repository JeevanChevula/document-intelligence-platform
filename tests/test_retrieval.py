import uuid

import pytest

from app.agents.retrieval import retrieve_relevant_chunks
from app.vector_store import get_qdrant_client, upsert_chunks


@pytest.fixture
def indexed_test_data():
    """Upserts real chunks into the real local Qdrant for two different users, then cleans up."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()

    upsert_chunks(doc_a, user_a, ["The company's quarterly revenue grew by fifteen percent this year."])
    upsert_chunks(doc_b, user_b, ["The recipe requires two cups of flour and one teaspoon of salt."])

    yield {"user_a": user_a, "user_b": user_b, "doc_a": doc_a, "doc_b": doc_b}

    client = get_qdrant_client()
    client.delete(collection_name="document_chunks", points_selector=[str(uuid.uuid5(doc_a, "0"))])
    client.delete(collection_name="document_chunks", points_selector=[str(uuid.uuid5(doc_b, "0"))])


def test_retrieval_finds_relevant_chunk_for_that_users_own_document(indexed_test_data):
    results = retrieve_relevant_chunks("How much did revenue grow?", indexed_test_data["user_a"])

    assert len(results) >= 1
    assert "revenue" in results[0]["text"]
    assert results[0]["document_id"] == str(indexed_test_data["doc_a"])


def test_retrieval_never_returns_another_users_chunks(indexed_test_data):
    # user_b searching with a query that would only semantically match user_a's document
    results = retrieve_relevant_chunks("How much did revenue grow?", indexed_test_data["user_b"])

    returned_doc_ids = {r["document_id"] for r in results}
    assert str(indexed_test_data["doc_a"]) not in returned_doc_ids
