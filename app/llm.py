from functools import lru_cache

from groq import Groq

from app.config import get_settings


@lru_cache
def get_groq_client() -> Groq:
    settings = get_settings()
    return Groq(api_key=settings.groq_api_key)


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

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content
