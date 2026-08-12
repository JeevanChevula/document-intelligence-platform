"""How an answer's origin is described in the UI.

Kept out of app.py deliberately: this is pure logic with no Streamlit import,
so it can be tested directly without executing the whole page script.
"""

SOURCE_LABELS = {
    "documents": "📄 From your documents",
    "general_knowledge": "🧠 General knowledge",
    "no_relevant_documents": "⚠️ No relevant documents found",
    "error": "❌ Error generating response",
}

UNVERIFIED_NOTE = " · ⚠️ parts not verified against them"


def source_caption(message: dict) -> str:
    """Where the answer came from, plus — separately — whether it checked out.

    Two independent facts: an answer can genuinely come from the user's
    documents while extrapolating beyond them (e.g. "what roles should I apply
    for based on my resume?"), so provenance and verification get their own say.
    Collapsing them previously made document-grounded answers display as
    "no relevant documents found", which was simply untrue.
    """
    label = SOURCE_LABELS.get(message["source"], message["source"])
    if message.get("is_verified") is False:
        label += UNVERIFIED_NOTE
    return label
