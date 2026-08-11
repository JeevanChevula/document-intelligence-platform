from app.llm import get_completion

ROUTER_SYSTEM_PROMPT = (
    "You are a router in a document Q&A assistant. Decide how to handle the user's message. "
    "Reply with exactly one word:\n"
    "'retrieval' if the message is a question that likely needs looking up information from the "
    "user's uploaded documents.\n"
    "'general' if it's a greeting, small talk, or a question unrelated to any documents."
)


def route_query(query: str) -> str:
    """The Router agent: returns 'retrieval' or 'general'.

    Deliberately classifies from the current message alone, with no conversation
    history — history previously caused topic-bleed (e.g. casual chat about an
    unrelated subject right before a real document question would bias this
    classification toward the unrelated topic). Conversational continuity is
    still fully preserved where it actually matters: Generation keeps history.
    """
    # low temperature: this is a classification decision, not creative writing —
    # we want the same question to reliably route the same way every time
    response = get_completion(query, system_prompt=ROUTER_SYSTEM_PROMPT, temperature=0.0).strip().lower()
    return "retrieval" if "retrieval" in response else "general"
