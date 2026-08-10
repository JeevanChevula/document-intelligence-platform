from app.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_returns_a_single_chunk():
    result = chunk_text("This is a short sentence.", chunk_size=1000, chunk_overlap=200)

    assert result == ["This is a short sentence."]


def test_long_text_splits_into_multiple_chunks():
    # 300 words, each "word0" "word1" ... — long enough to force multiple chunks
    words = [f"word{i}" for i in range(300)]
    text = " ".join(words)

    result = chunk_text(text, chunk_size=200, chunk_overlap=50)

    assert len(result) > 1
    # every chunk should stay reasonably close to the requested size (off by
    # at most 1 char, since the trailing word has no joining space after it)
    for chunk in result[:-1]:  # last chunk is allowed to be shorter
        assert len(chunk) >= 199


def test_consecutive_chunks_actually_overlap():
    words = [f"word{i}" for i in range(300)]
    text = " ".join(words)

    result = chunk_text(text, chunk_size=200, chunk_overlap=50)

    first_chunk_words = result[0].split()
    second_chunk_words = result[1].split()

    # the tail of chunk 1 should reappear at the head of chunk 2
    shared = set(first_chunk_words) & set(second_chunk_words)
    assert len(shared) > 0


def test_no_word_is_split_or_lost():
    words = [f"word{i}" for i in range(300)]
    text = " ".join(words)

    result = chunk_text(text, chunk_size=200, chunk_overlap=50)

    all_words_seen = set()
    for chunk in result:
        all_words_seen.update(chunk.split())

    assert all_words_seen == set(words)
