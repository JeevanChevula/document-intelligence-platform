import uuid

import pytest

from app.agents.retrieval import retrieve_relevant_chunks
from app.vector_store import delete_document_chunks, get_qdrant_client, upsert_chunks


@pytest.fixture
def two_indexed_documents():
    """Two documents for the same user, plus one for a different user.

    Uses the real local Qdrant rather than a mock, for the same reason the
    retrieval tests do: deleting the right points and no others is a data-safety
    property, and a mock would happily confirm whatever we asserted.
    """
    owner = uuid.uuid4()
    other_user = uuid.uuid4()
    doc_to_delete = uuid.uuid4()
    doc_to_keep = uuid.uuid4()
    other_users_doc = uuid.uuid4()

    upsert_chunks(doc_to_delete, owner, ["The quarterly revenue grew by fifteen percent."])
    upsert_chunks(doc_to_keep, owner, ["The office relocated to the third floor in March."])
    upsert_chunks(other_users_doc, other_user, ["The quarterly revenue grew by fifteen percent."])

    yield {
        "owner": owner,
        "other_user": other_user,
        "doc_to_delete": doc_to_delete,
        "doc_to_keep": doc_to_keep,
        "other_users_doc": other_users_doc,
    }

    client = get_qdrant_client()
    for doc in (doc_to_delete, doc_to_keep, other_users_doc):
        client.delete(collection_name="document_chunks", points_selector=[str(uuid.uuid5(doc, "0"))])


def test_deleting_a_document_removes_it_from_search(two_indexed_documents):
    owner = two_indexed_documents["owner"]
    deleted = str(two_indexed_documents["doc_to_delete"])

    assert deleted in {r["document_id"] for r in retrieve_relevant_chunks("revenue growth", owner)}

    delete_document_chunks(two_indexed_documents["doc_to_delete"], owner)

    # the point of deleting: a removed document can never feed an answer again
    assert deleted not in {r["document_id"] for r in retrieve_relevant_chunks("revenue growth", owner)}


def test_deleting_one_document_leaves_the_users_others_alone(two_indexed_documents):
    owner = two_indexed_documents["owner"]

    delete_document_chunks(two_indexed_documents["doc_to_delete"], owner)

    kept = {r["document_id"] for r in retrieve_relevant_chunks("where is the office", owner)}
    assert str(two_indexed_documents["doc_to_keep"]) in kept


def test_deleting_cannot_touch_another_users_document(two_indexed_documents):
    # the security property: passing someone else's document id must be inert,
    # because the delete filters on user_id as well as document_id
    other_users_doc = two_indexed_documents["other_users_doc"]

    delete_document_chunks(other_users_doc, two_indexed_documents["owner"])

    still_there = retrieve_relevant_chunks("revenue growth", two_indexed_documents["other_user"])
    assert str(other_users_doc) in {r["document_id"] for r in still_there}
