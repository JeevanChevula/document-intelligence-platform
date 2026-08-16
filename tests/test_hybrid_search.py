import uuid

import pytest

from app.vector_store import (
    collection_has_sparse_vectors,
    get_qdrant_client,
    search_chunks,
    upsert_chunks,
)


@pytest.fixture
def indexed_identifiers():
    """Chunks containing identifiers, which dense embeddings handle badly.

    Real Qdrant rather than a mock: fusion behaviour is a property of the search
    engine, so mocking it would only test our own assumptions back at us.
    """
    user = uuid.uuid4()
    other_user = uuid.uuid4()
    target = uuid.uuid4()
    filler = uuid.uuid4()
    other = uuid.uuid4()

    upsert_chunks(target, user, ["Permanent Account Number: ZZQPX8817K issued to the account holder."])
    upsert_chunks(
        filler,
        user,
        [
            "The quarterly revenue grew by fifteen percent compared with last year.",
            "The office relocated to the third floor of the building in March.",
        ],
    )
    upsert_chunks(other, other_user, ["Permanent Account Number: ZZQPX8817K issued to the account holder."])

    yield {"user": user, "other_user": other_user, "target": target, "other": other}

    client = get_qdrant_client()
    for doc, count in ((target, 1), (filler, 2), (other, 1)):
        client.delete(
            collection_name="document_chunks",
            points_selector=[str(uuid.uuid5(doc, str(i))) for i in range(count)],
        )


def test_collection_is_configured_for_hybrid_search():
    assert collection_has_sparse_vectors()


def test_an_identifier_is_found_by_exact_token_match(indexed_identifiers):
    # the reason hybrid search exists: "ZZQPX8817K" carries no meaning, so there
    # is nothing for a dense embedding to be semantically similar *to*. BM25
    # matches the token directly.
    results = search_chunks("ZZQPX8817K", indexed_identifiers["user"], limit=3)

    assert results, "no chunks returned for an identifier present in the corpus"
    assert results[0]["document_id"] == str(indexed_identifiers["target"])
    assert "ZZQPX8817K" in results[0]["text"]


def test_paraphrased_questions_still_work(indexed_identifiers):
    # the other arm must keep working: BM25 alone cannot connect "how much did
    # revenue grow" to "revenue grew by fifteen percent" beyond the shared word
    results = search_chunks("how much did the company grow last year?", indexed_identifiers["user"], limit=3)

    assert any("fifteen percent" in r["text"] for r in results)


def test_hybrid_search_never_crosses_users(indexed_identifiers):
    # the security property, re-asserted for hybrid: each arm of the search runs
    # independently, so the user filter has to be applied to *both* prefetches —
    # an unfiltered arm would pull another user's chunks into the fusion pool
    results = search_chunks("ZZQPX8817K", indexed_identifiers["other_user"], limit=5)

    returned = {r["document_id"] for r in results}
    assert str(indexed_identifiers["target"]) not in returned
    assert returned <= {str(indexed_identifiers["other"])}
