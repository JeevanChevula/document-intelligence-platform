from unittest.mock import MagicMock, patch

from app.llm import get_completion


def _mock_client_returning(text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = text

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_get_completion_with_system_prompt_builds_correct_messages():
    mock_client = _mock_client_returning("mocked answer")

    with patch("app.llm.get_groq_client", return_value=mock_client):
        result = get_completion("What is 2+2?", system_prompt="You are a helpful assistant.")

    assert result == "mocked answer"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
    ]


def test_get_completion_without_system_prompt_omits_it():
    mock_client = _mock_client_returning("mocked answer")

    with patch("app.llm.get_groq_client", return_value=mock_client):
        get_completion("What is 2+2?")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]


def test_get_completion_includes_history_between_system_and_prompt():
    mock_client = _mock_client_returning("mocked answer")
    history = [
        {"role": "user", "content": "My name is Jeevan."},
        {"role": "assistant", "content": "Nice to meet you, Jeevan!"},
    ]

    with patch("app.llm.get_groq_client", return_value=mock_client):
        get_completion("What is my name?", system_prompt="You are a helpful assistant.", history=history)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "My name is Jeevan."},
        {"role": "assistant", "content": "Nice to meet you, Jeevan!"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_get_completion_without_history_does_not_add_extra_messages():
    mock_client = _mock_client_returning("mocked answer")

    with patch("app.llm.get_groq_client", return_value=mock_client):
        get_completion("What is 2+2?", history=[])

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]
