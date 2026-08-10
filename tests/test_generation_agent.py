from unittest.mock import patch

from app.agents.generation import generate_answer


def test_generate_answer_includes_retrieved_context_in_prompt():
    chunks = [{"text": "Revenue grew by 15% in Q3."}]

    with patch("app.agents.generation.get_completion", return_value="Revenue grew by 15%.") as mock_completion:
        result = generate_answer("What was Q3 revenue growth?", chunks, route="retrieval")

    assert result == "Revenue grew by 15%."
    prompt_used = mock_completion.call_args.args[0]
    assert "Revenue grew by 15% in Q3." in prompt_used
    assert "What was Q3 revenue growth?" in prompt_used


def test_retrieval_route_with_no_chunks_says_not_enough_info():
    # a real document question where nothing relevant enough was found —
    # different from general chat, and should stay in "grounded" mode
    with patch("app.agents.generation.get_completion", return_value="I don't have enough information.") as mock_completion:
        result = generate_answer("What was Q3 revenue?", [], route="retrieval")

    assert result == "I don't have enough information."
    prompt_used = mock_completion.call_args.args[0]
    assert "No relevant document content was found" in prompt_used


def test_general_route_has_normal_conversation_not_document_prompt():
    with patch("app.agents.generation.get_completion", return_value="I'm doing well, thanks!") as mock_completion:
        result = generate_answer("Hi, how are you?", [], route="general")

    assert result == "I'm doing well, thanks!"
    prompt_used = mock_completion.call_args.args[0]
    system_prompt_used = mock_completion.call_args.kwargs["system_prompt"]
    # the raw question is sent as-is — no fake "context" wrapper, no document restriction
    assert prompt_used == "Hi, how are you?"
    assert "document" not in system_prompt_used.lower()


def test_generate_answer_passes_history_through_for_conversational_context():
    history = [{"role": "user", "content": "My name is Jeevan."}, {"role": "assistant", "content": "Nice to meet you!"}]

    with patch("app.agents.generation.get_completion", return_value="Your name is Jeevan.") as mock_completion:
        generate_answer("What is my name?", [], route="general", history=history)

    assert mock_completion.call_args.kwargs["history"] == history
