import sys
from pathlib import Path

# frontend/ isn't a package (Streamlit runs app.py directly, with its own directory
# on sys.path), so point at it explicitly. Importing `labels` rather than the
# Streamlit script keeps this free of both the app/ name collision and any
# page-rendering side effects.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from labels import source_caption  # noqa: E402  (needs the sys.path line above)


def test_verified_document_answer_shows_only_provenance():
    caption = source_caption({"source": "documents", "is_verified": True})

    assert caption == "📄 From your documents"


def test_unverified_document_answer_keeps_provenance_and_adds_a_caveat():
    # the regression this guards: this used to be labelled "no relevant documents
    # found" even though the answer genuinely came from the user's documents
    caption = source_caption({"source": "documents", "is_verified": False})

    assert caption.startswith("📄 From your documents")
    assert "not verified" in caption


def test_general_chat_has_no_verification_note():
    # nothing was retrieved, so there is nothing to verify against
    caption = source_caption({"source": "general_knowledge", "is_verified": None})

    assert caption == "🧠 General knowledge"


def test_unknown_source_falls_back_to_the_raw_value():
    caption = source_caption({"source": "something_new", "is_verified": None})

    assert caption == "something_new"
