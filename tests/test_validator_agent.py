from unittest.mock import patch

from app.agents.validator import validate_answer


def test_validate_answer_passes_through_when_grounded():
    chunks = [{"text": "Revenue grew by 15% in Q3."}]

    with patch("app.agents.validator.get_completion", return_value="YES"):
        is_valid, final_answer = validate_answer("Revenue grew by 15%.", chunks)

    assert is_valid is True
    assert final_answer == "Revenue grew by 15%."


def test_validate_answer_flags_ungrounded_claim_with_fallback():
    chunks = [{"text": "Revenue grew by 15% in Q3."}]

    with patch("app.agents.validator.get_completion", return_value="NO"):
        is_valid, final_answer = validate_answer("Revenue grew by 50%.", chunks)

    assert is_valid is False
    assert "couldn't confidently verify" in final_answer
    assert "Revenue grew by 50%." in final_answer


def test_validate_answer_skips_validation_when_no_chunks():
    with patch("app.agents.validator.get_completion") as mock_completion:
        is_valid, final_answer = validate_answer("Hello there!", [])

    mock_completion.assert_not_called()
    assert is_valid is True
    assert final_answer == "Hello there!"


def test_validate_answer_uses_zero_temperature_for_consistent_verdicts():
    chunks = [{"text": "Revenue grew by 15% in Q3."}]

    with patch("app.agents.validator.get_completion", return_value="YES") as mock_completion:
        validate_answer("Revenue grew by 15%.", chunks)

    assert mock_completion.call_args.kwargs["temperature"] == 0.0
