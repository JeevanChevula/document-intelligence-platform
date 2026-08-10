from app.llm import get_completion

GROUNDED_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions using ONLY the provided context from the "
    "user's documents. If the answer is not contained in the context, say you don't have enough "
    "information rather than guessing."
)

GENERAL_SYSTEM_PROMPT = "You are a friendly, helpful assistant having a normal conversation. Respond naturally."


def generate_answer(query: str, chunks: list[dict], route: str, history: list[dict] | None = None) -> str:
    """The Answer Generation agent.

    `route` (from the Router agent) — not just "are chunks empty?" — decides
    the behavior, because empty chunks means two different things: general
    chat (no documents needed at all) vs. a document question where nothing
    relevant enough was found. Those need different responses.

    `history` (prior turns in this chat session) is passed to the LLM so
    follow-up questions like "check that again" or "what about him" can be
    understood in context, instead of every message being answered in isolation.
    """
    if route == "general":
        return get_completion(query, system_prompt=GENERAL_SYSTEM_PROMPT, history=history)

    if not chunks:
        context = "No relevant document content was found."
    else:
        context = "\n\n".join(f"[Source {i + 1}]: {chunk['text']}" for i, chunk in enumerate(chunks))

    prompt = f"Context:\n{context}\n\nQuestion: {query}"
    return get_completion(prompt, system_prompt=GROUNDED_SYSTEM_PROMPT, history=history)
