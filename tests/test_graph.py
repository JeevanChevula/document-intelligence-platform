import uuid
from unittest.mock import patch

from app.graph import _determine_source, run_agent_pipeline


def test_determine_source_general_route():
    assert _determine_source("general", []) == "general_knowledge"


def test_determine_source_retrieval_with_chunks():
    chunks = [{"text": "some chunk"}]
    assert _determine_source("retrieval", chunks) == "documents"


def test_determine_source_retrieval_with_no_chunks():
    assert _determine_source("retrieval", []) == "no_relevant_documents"


def test_general_query_skips_retrieval_node():
    with (
        patch("app.graph.route_query", return_value="general") as mock_route,
        patch("app.graph.retrieve_relevant_chunks") as mock_retrieve,
        patch("app.graph.generate_answer", return_value="Hi there!") as mock_generate,
        patch("app.graph.validate_answer", return_value=(True, "Hi there!")),
    ):
        result = run_agent_pipeline("Hello!", uuid.uuid4())

    mock_route.assert_called_once()
    mock_retrieve.assert_not_called()  # the whole point of routing: skip retrieval for general chat
    mock_generate.assert_called_once_with("Hello!", [], "general", [])
    assert result["answer"] == "Hi there!"
    assert result["route"] == "general"
    assert result["source"] == "general_knowledge"


def test_retrieval_query_runs_full_pipeline():
    fake_chunks = [{"text": "Revenue grew 15%.", "document_id": "abc", "chunk_index": 0, "score": 0.9}]

    with (
        patch("app.graph.route_query", return_value="retrieval"),
        patch("app.graph.retrieve_relevant_chunks", return_value=fake_chunks) as mock_retrieve,
        patch("app.graph.generate_answer", return_value="Revenue grew by 15%.") as mock_generate,
        patch("app.graph.validate_answer", return_value=(True, "Revenue grew by 15%.")) as mock_validate,
    ):
        result = run_agent_pipeline("What was revenue growth?", uuid.uuid4())

    mock_retrieve.assert_called_once()
    mock_generate.assert_called_once_with("What was revenue growth?", fake_chunks, "retrieval", [])
    mock_validate.assert_called_once()
    assert result["answer"] == "Revenue grew by 15%."
    assert result["route"] == "retrieval"
    assert result["chunks"] == fake_chunks
    assert result["source"] == "documents"


def test_history_reaches_generation_but_not_router():
    history = [{"role": "user", "content": "My name is Jeevan."}, {"role": "assistant", "content": "Nice to meet you!"}]

    with (
        patch("app.graph.route_query", return_value="general") as mock_route,
        patch("app.graph.retrieve_relevant_chunks"),
        patch("app.graph.generate_answer", return_value="Your name is Jeevan.") as mock_generate,
        patch("app.graph.validate_answer", return_value=(True, "Your name is Jeevan.")),
    ):
        run_agent_pipeline("What is my name?", uuid.uuid4(), history)

    # deliberate: the Router classifies from the current message alone (history
    # previously caused topic-bleed from unrelated recent chat); Generation still
    # gets full history, since that's where conversational memory actually matters
    mock_route.assert_called_once_with("What is my name?")
    mock_generate.assert_called_once_with("What is my name?", [], "general", history)


def test_no_history_defaults_to_empty_list():
    with (
        patch("app.graph.route_query", return_value="general") as mock_route,
        patch("app.graph.generate_answer", return_value="Hi!"),
        patch("app.graph.validate_answer", return_value=(True, "Hi!")),
    ):
        run_agent_pipeline("Hello!", uuid.uuid4())

    mock_route.assert_called_once_with("Hello!")


def test_retrieval_query_with_no_matching_chunks_has_correct_source():
    with (
        patch("app.graph.route_query", return_value="retrieval"),
        patch("app.graph.retrieve_relevant_chunks", return_value=[]),
        patch("app.graph.generate_answer", return_value="I don't have enough information."),
        patch("app.graph.validate_answer", return_value=(True, "I don't have enough information.")),
    ):
        result = run_agent_pipeline("Something not in any document", uuid.uuid4())

    assert result["source"] == "no_relevant_documents"


def test_failed_validation_does_not_change_where_the_answer_came_from():
    # the regression this guards: an advisory question ("what roles should I apply
    # for based on my resume?") legitimately extrapolates beyond the documents, so
    # the Validator rejects it — but it genuinely *did* come from the user's
    # documents, and was previously mislabelled "no_relevant_documents"
    fake_chunks = [{"text": "resume chunk", "document_id": "abc", "chunk_index": 0, "score": 0.5}]
    fallback_answer = "I couldn't confidently verify this answer against your documents: apply for X."

    with (
        patch("app.graph.route_query", return_value="retrieval"),
        patch("app.graph.retrieve_relevant_chunks", return_value=fake_chunks),
        patch("app.graph.generate_answer", return_value="apply for X."),
        patch("app.graph.validate_answer", return_value=(False, fallback_answer)),
    ):
        result = run_agent_pipeline("what roles should I apply for?", uuid.uuid4())

    # provenance and verification are reported independently
    assert result["source"] == "documents"
    assert result["is_valid"] is False
