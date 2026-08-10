from app.llm import get_completion

ROUTER_SYSTEM_PROMPT = (
    "You are a router in a document Q&A assistant. Decide how to handle the user's latest message, "
    "using the conversation so far as context if it helps (e.g. a follow-up like 'check again'). "
    "Reply with exactly one word:\n"
    "'retrieval' if the message is a question that likely needs looking up information from the "
    "user's uploaded documents.\n"
    "'general' if it's a greeting, small talk, or a question unrelated to any documents."
)


def route_query(query: str, history: list[dict] | None = None) -> str:
    """The Router agent: returns 'retrieval' or 'general'."""
    # low temperature: this is a classification decision, not creative writing —
    # we want the same question to reliably route the same way every time
    response = get_completion(
        query, system_prompt=ROUTER_SYSTEM_PROMPT, temperature=0.0, history=history
    ).strip().lower()
    return "retrieval" if "retrieval" in response else "general"
