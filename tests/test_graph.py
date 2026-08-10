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


def test_history_is_passed_through_to_router_and_generation():
    history = [{"role": "user", "content": "My name is Jeevan."}, {"role": "assistant", "content": "Nice to meet you!"}]

    with (
        patch("app.graph.route_query", return_value="general") as mock_route,
        patch("app.graph.retrieve_relevant_chunks"),
        patch("app.graph.generate_answer", return_value="Your name is Jeevan.") as mock_generate,
        patch("app.graph.validate_answer", return_value=(True, "Your name is Jeevan.")),
    ):
        run_agent_pipeline("What is my name?", uuid.uuid4(), history)

    mock_route.assert_called_once_with("What is my name?", history)
    mock_generate.assert_called_once_with("What is my name?", [], "general", history)


def test_no_history_defaults_to_empty_list():
    with (
        patch("app.graph.route_query", return_value="general") as mock_route,
        patch("app.graph.generate_answer", return_value="Hi!"),
        patch("app.graph.validate_answer", return_value=(True, "Hi!")),
    ):
        run_agent_pipeline("Hello!", uuid.uuid4())

    mock_route.assert_called_once_with("Hello!", [])


def test_retrieval_query_with_no_matching_chunks_has_correct_source():
    with (
        patch("app.graph.route_query", return_value="retrieval"),
        patch("app.graph.retrieve_relevant_chunks", return_value=[]),
        patch("app.graph.generate_answer", return_value="I don't have enough information."),
        patch("app.graph.validate_answer", return_value=(True, "I don't have enough information.")),
    ):
        result = run_agent_pipeline("Something not in any document", uuid.uuid4())

    assert result["source"] == "no_relevant_documents"
