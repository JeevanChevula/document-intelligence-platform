def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks, breaking on word boundaries.

    chunk_size/chunk_overlap are character counts, not exact — chunks stop
    at the nearest word boundary rather than mid-word.
    """
    text = text.strip()
    if not text:
        return []

    words = text.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for word in words:
        current_words.append(word)
        current_len += len(word) + 1  # +1 accounts for the joining space

        if current_len >= chunk_size:
            chunks.append(" ".join(current_words))
            current_words, current_len = _take_overlap(current_words, chunk_overlap)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def _take_overlap(words: list[str], overlap_chars: int) -> tuple[list[str], int]:
    """Return the trailing words (and their char count) to carry into the next chunk."""
    overlap_words: list[str] = []
    overlap_len = 0

    for word in reversed(words):
        overlap_len += len(word) + 1
        overlap_words.insert(0, word)
        if overlap_len >= overlap_chars:
            break

    return overlap_words, overlap_len
