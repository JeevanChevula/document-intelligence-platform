from app.llm import get_completion

VALIDATOR_SYSTEM_PROMPT = (
    "You are a strict fact-checker. Given a context and an answer, reply with exactly one word: "
    "'YES' if the answer is well supported by the context, or 'NO' if it makes claims not found in "
    "the context."
)


def validate_answer(answer: str, chunks: list[dict]) -> tuple[bool, str]:
    """The Validator agent: checks the answer is grounded in the retrieved chunks.

    Returns (is_valid, final_answer) — final_answer is replaced with a safe
    fallback if validation fails, so an ungrounded claim is never shown as fact.
    """
    if not chunks:
        # nothing to validate against — either general chat, or a document
        # question where nothing relevant enough was found; either way there's
        # no retrieved content to fact-check the answer against
        return True, answer

    context = "\n\n".join(chunk["text"] for chunk in chunks)
    prompt = f"Context:\n{context}\n\nAnswer:\n{answer}\n\nIs the answer supported by the context?"
    # low temperature: fact-checking should be consistent, not creative
    verdict = get_completion(prompt, system_prompt=VALIDATOR_SYSTEM_PROMPT, temperature=0.0).strip().upper()

    is_valid = "YES" in verdict
    if is_valid:
        return True, answer

    fallback = "I couldn't confidently verify this answer against your documents: " + answer
    return False, fallback
