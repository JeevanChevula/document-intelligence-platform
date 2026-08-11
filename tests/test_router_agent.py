from unittest.mock import patch

from app.agents.router import route_query


def test_route_query_returns_retrieval_when_llm_says_so():
    with patch("app.agents.router.get_completion", return_value="retrieval"):
        assert route_query("What was our Q3 revenue?") == "retrieval"


def test_route_query_returns_general_when_llm_says_so():
    with patch("app.agents.router.get_completion", return_value="general"):
        assert route_query("Hi, how are you?") == "general"


def test_route_query_defaults_to_general_on_unexpected_response():
    with patch("app.agents.router.get_completion", return_value="I'm not sure what you mean"):
        assert route_query("???") == "general"


def test_route_query_uses_zero_temperature_for_consistent_decisions():
    with patch("app.agents.router.get_completion", return_value="general") as mock_completion:
        route_query("Hi!")

    assert mock_completion.call_args.kwargs["temperature"] == 0.0


def test_route_query_does_not_use_conversation_history():
    # deliberate: history previously caused topic-bleed (unrelated recent chat
    # biasing the classification of an unrelated new question) — the Router
    # now classifies from the current message alone
    with patch("app.agents.router.get_completion", return_value="retrieval") as mock_completion:
        route_query("list all career gaps")

    assert "history" not in mock_completion.call_args.kwargs
