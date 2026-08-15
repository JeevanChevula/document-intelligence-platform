from app.routers.chat import TITLE_MAX_LENGTH, _title_from


def test_short_message_becomes_the_title_verbatim():
    assert _title_from("which model are you") == "which model are you"


def test_long_message_is_trimmed_with_an_ellipsis():
    message = "so my skin swells when I go out in severe winter wind, does my IgE level explain that"

    title = _title_from(message)

    assert len(title) <= TITLE_MAX_LENGTH + 1  # +1 for the ellipsis character
    assert title.endswith("…")
    assert message.startswith(title.rstrip("…"))


def test_trimming_does_not_break_mid_word():
    title = _title_from("antidisestablishmentarianism " * 5)

    assert "…" in title
    # every whole word kept must be the complete word, never a fragment
    assert all(word == "antidisestablishmentarianism" for word in title.rstrip("…").split())


def test_a_single_very_long_word_still_produces_a_title():
    # no space to trim at — must not return an empty or ellipsis-only title
    title = _title_from("a" * 200)

    assert title.rstrip("…") == "a" * TITLE_MAX_LENGTH


def test_newlines_and_extra_spacing_are_collapsed():
    # a pasted multi-line question shouldn't render as a broken dropdown label
    assert _title_from("check   this\n\ndoc  please") == "check this doc please"
