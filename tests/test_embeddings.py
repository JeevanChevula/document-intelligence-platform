from app.embeddings import embed_texts


def test_embed_texts_returns_one_vector_per_input():
    vectors = embed_texts(["first chunk", "second chunk", "third chunk"])

    assert len(vectors) == 3


def test_embed_texts_returns_correct_dimension():
    vectors = embed_texts(["some text"])

    assert len(vectors[0]) == 384


def test_similar_texts_produce_more_similar_vectors_than_unrelated_ones():
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    vectors = embed_texts([
        "The cat sat on the mat.",
        "A cat was sitting on a mat.",
        "Quarterly financial revenue report for the fiscal year.",
    ])

    similar_pair_score = cosine_similarity(vectors[0], vectors[1])
    unrelated_pair_score = cosine_similarity(vectors[0], vectors[2])

    assert similar_pair_score > unrelated_pair_score
