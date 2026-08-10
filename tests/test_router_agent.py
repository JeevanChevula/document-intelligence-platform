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


def test_route_query_passes_history_through_for_context_dependent_followups():
    history = [{"role": "user", "content": "What was our Q3 revenue?"}, {"role": "assistant", "content": "15%."}]

    with patch("app.agents.router.get_completion", return_value="retrieval") as mock_completion:
        route_query("check that again", history)

    assert mock_completion.call_args.kwargs["history"] == history
