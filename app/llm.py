import logging
import time
from functools import lru_cache

from groq import Groq, RateLimitError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Retries are for the *per-minute* ceiling, which clears on its own within a
# rolling 60-second window. Kept deliberately short: a user is waiting on this
# request, and a minute of silent retrying is worse than an honest failure.
MAX_RATE_LIMIT_ATTEMPTS = 3
MAX_WAIT_SECONDS = 8.0


class DailyQuotaExceeded(Exception):
    """The daily token budget is gone — retrying cannot help until it resets."""


@lru_cache
def get_groq_client() -> Groq:
    settings = get_settings()
    return Groq(api_key=settings.groq_api_key)


def _is_daily_limit(error: RateLimitError) -> bool:
    """Whether a 429 is the daily budget rather than the per-minute one.

    The two are the same HTTP status but need opposite handling: a per-minute
    limit clears in seconds, while a daily one lasts until it resets. Retrying
    the daily case just makes the user wait before failing anyway.
    """
    message = str(error).lower()
    return "per day" in message or "tpd" in message or "rpd" in message


def _wait_seconds(error: RateLimitError, attempt: int) -> float:
    """How long to wait — the server's own Retry-After if it sent one."""
    retry_after = getattr(getattr(error, "response", None), "headers", {}) or {}
    try:
        suggested = float(retry_after.get("retry-after", ""))
    except (TypeError, ValueError):
        suggested = 2.0 * attempt  # otherwise back off: 2s, 4s
    return min(suggested, MAX_WAIT_SECONDS)


def get_completion(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    history: list[dict] | None = None,
) -> str:
    settings = get_settings()
    client = get_groq_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    for attempt in range(1, MAX_RATE_LIMIT_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except RateLimitError as error:
            if _is_daily_limit(error):
                # nothing to wait for — surface it so the user gets told why,
                # instead of a generic failure after a pointless delay
                logger.warning("Groq daily token budget exhausted: %s", error)
                raise DailyQuotaExceeded(str(error)) from error
            if attempt == MAX_RATE_LIMIT_ATTEMPTS:
                logger.warning("Groq rate limit still hit after %s attempts", attempt)
                raise
            wait = _wait_seconds(error, attempt)
            logger.info("Groq rate limited, retrying in %.1fs (attempt %s)", wait, attempt)
            time.sleep(wait)

    raise RuntimeError("unreachable")  # loop either returns or raises
