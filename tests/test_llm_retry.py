from unittest.mock import MagicMock, patch

import httpx
import pytest
from groq import RateLimitError

from app.llm import MAX_RATE_LIMIT_ATTEMPTS, DailyQuotaExceeded, get_completion


def _rate_limit_error(message: str, retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(
        429, headers=headers, request=httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
    )
    return RateLimitError(message, response=response, body=None)


def _client_raising(*errors, then: str = "recovered") -> MagicMock:
    """A client that raises the given errors in order, then succeeds."""
    ok = MagicMock()
    ok.choices[0].message.content = then

    client = MagicMock()
    client.chat.completions.create.side_effect = [*errors, ok]
    return client


# real error text from Groq, so the daily/minute distinction is tested against
# what the API actually sends rather than what we imagine it sends
PER_MINUTE = "Rate limit reached ... Limit 8000, Used 7900, Requested 300. Please try again in 3.2s"
PER_DAY = "Rate limit reached for model ... on tokens per day (TPD): Limit 200000, Used 199000, Requested 3627"


def test_a_per_minute_limit_is_retried_and_succeeds():
    client = _client_raising(_rate_limit_error(PER_MINUTE))

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep") as sleep:
        result = get_completion("hello")

    assert result == "recovered"
    assert client.chat.completions.create.call_count == 2
    sleep.assert_called_once()  # it waited rather than hammering


def test_a_daily_limit_is_not_retried():
    # retrying is pointless: the budget is gone until it resets, so waiting
    # only delays the same failure while a user sits watching a spinner
    client = _client_raising(_rate_limit_error(PER_DAY))

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep") as sleep:
        with pytest.raises(DailyQuotaExceeded):
            get_completion("hello")

    assert client.chat.completions.create.call_count == 1
    sleep.assert_not_called()


def test_retries_give_up_rather_than_looping_forever():
    errors = [_rate_limit_error(PER_MINUTE) for _ in range(MAX_RATE_LIMIT_ATTEMPTS)]
    client = _client_raising(*errors)

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep"):
        with pytest.raises(RateLimitError):
            get_completion("hello")

    assert client.chat.completions.create.call_count == MAX_RATE_LIMIT_ATTEMPTS


def test_the_servers_retry_after_header_is_respected():
    client = _client_raising(_rate_limit_error(PER_MINUTE, retry_after="5"))

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep") as sleep:
        get_completion("hello")

    assert sleep.call_args.args[0] == 5.0


def test_an_absurd_retry_after_is_capped():
    # a user is waiting on this request — honouring a 300s hint would hang the
    # page far longer than simply failing
    client = _client_raising(_rate_limit_error(PER_MINUTE, retry_after="300"))

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep") as sleep:
        get_completion("hello")

    assert sleep.call_args.args[0] <= 8.0


def test_a_successful_call_never_sleeps():
    ok = MagicMock()
    ok.choices[0].message.content = "fine"
    client = MagicMock()
    client.chat.completions.create.return_value = ok

    with patch("app.llm.get_groq_client", return_value=client), patch("app.llm.time.sleep") as sleep:
        assert get_completion("hello") == "fine"

    sleep.assert_not_called()
