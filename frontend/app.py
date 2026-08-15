from datetime import datetime

import streamlit as st

from api_client import (
    ApiError,
    create_session,
    delete_document,
    list_documents,
    list_messages,
    list_sessions,
    login,
    register,
    send_message,
    upload_document,
)
from labels import source_caption

st.set_page_config(page_title="Document Intelligence Platform", layout="wide")


def _init_session_state() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("email", None)
    st.session_state.setdefault("current_session_id", None)
    st.session_state.setdefault("pending_delete", None)


def _login_and_register_screen() -> None:
    st.title("Document Intelligence Platform")
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            try:
                token = login(email, password)
                st.session_state["token"] = token
                st.session_state["email"] = email
                st.rerun()
            except ApiError as e:
                st.error(f"Login failed: {e}")

    with register_tab:
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password (min 8 characters)", type="password", key="register_password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                register(email, password)
                st.success("Account created — you can now log in.")
            except ApiError as e:
                st.error(f"Registration failed: {e}")


def _format_uploaded_at(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return raw


def _document_row(token: str, doc: dict) -> None:
    """One document, with a two-step delete.

    Deletion is irreversible — the PDF and its embedded chunks both go — so the
    first click only arms it, and the confirm button is the one that acts.
    """
    name_col, meta_col, action_col = st.columns([5, 3, 2])

    with name_col:
        st.write(f"**{doc['filename']}**")
        st.caption(_format_uploaded_at(doc["uploaded_at"]))

    with meta_col:
        pages = doc["num_pages"] or "?"
        details = [f"{pages} pages"]
        if doc["ocr_used"]:
            details.append("OCR")
        if not doc["is_indexed"]:
            details.append("⚠️ not searchable")
        st.caption(" · ".join(details))

    with action_col:
        if st.session_state.get("pending_delete") == doc["id"]:
            if st.button("Confirm", key=f"confirm_{doc['id']}", type="primary"):
                try:
                    delete_document(token, doc["id"])
                    st.session_state["pending_delete"] = None
                    st.rerun()
                except ApiError as e:
                    st.error(f"Delete failed: {e}")
            if st.button("Cancel", key=f"cancel_{doc['id']}"):
                st.session_state["pending_delete"] = None
                st.rerun()
        elif st.button("🗑", key=f"delete_{doc['id']}", help="Delete this document"):
            st.session_state["pending_delete"] = doc["id"]
            st.rerun()


def _documents_tab(token: str) -> None:
    st.subheader("Upload a PDF")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if uploaded_file is not None and st.button("Upload"):
        try:
            upload_document(token, uploaded_file.name, uploaded_file.getvalue())
            st.success(f"Uploaded {uploaded_file.name}")
            st.rerun()
        except ApiError as e:
            st.error(f"Upload failed: {e}")

    st.subheader("Your documents")
    try:
        documents = list_documents(token)
    except ApiError as e:
        st.error(f"Could not load documents: {e}")
        return

    if not documents:
        st.info("No documents uploaded yet.")
        return

    if st.session_state.get("pending_delete"):
        st.warning("Deleting a document also removes it from search — answers can no longer cite it.")

    for doc in documents:
        _document_row(token, doc)
        st.divider()


def _chat_tab(token: str) -> None:
    try:
        sessions = list_sessions(token)
    except ApiError as e:
        st.error(f"Could not load chat sessions: {e}")
        return

    # chats are named after their first message by the backend, so there is no
    # title to ask for up front. Older chats predating that may still be unnamed.
    session_labels = {s["id"]: (s["title"] or "Untitled chat") for s in sessions}
    options = list(session_labels.keys())
    current = st.session_state["current_session_id"]

    picker_col, new_col = st.columns([4, 1])
    with picker_col:
        # index=None so opening the tab never drops the user into an old
        # conversation — landing on a stale chat read as "it lost my place"
        selected = st.selectbox(
            "Previous chats",
            options=options,
            index=options.index(current) if current in options else None,
            format_func=lambda sid: session_labels[sid],
            placeholder="Select a previous chat…" if options else "No previous chats yet",
        )
        if selected is not None and selected != current:
            st.session_state["current_session_id"] = selected
            st.rerun()
    with new_col:
        st.write("")  # nudges the button down into line with the selectbox
        if st.button("＋ New chat", use_container_width=True):
            try:
                new_session = create_session(token, None)
                st.session_state["current_session_id"] = new_session["id"]
                st.rerun()
            except ApiError as e:
                st.error(f"Could not create chat session: {e}")

    session_id = st.session_state["current_session_id"]
    if session_id is None:
        st.info("Pick a previous chat above, or start a new one.")
        return

    try:
        messages = list_messages(token, session_id)
    except ApiError as e:
        st.error(f"Could not load messages: {e}")
        return

    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if message["role"] == "assistant" and message.get("source"):
                st.caption(source_caption(message))

    prompt = st.chat_input("Ask a question about your documents, or just say hi")
    if prompt:
        try:
            with st.spinner("Thinking..."):
                send_message(token, session_id, prompt)
            st.rerun()
        except ApiError as e:
            st.error(f"Could not send message: {e}")


def _main_app() -> None:
    with st.sidebar:
        st.write(f"Logged in as **{st.session_state['email']}**")
        if st.button("Log out"):
            st.session_state["token"] = None
            st.session_state["email"] = None
            st.session_state["current_session_id"] = None
            st.session_state["pending_delete"] = None
            st.rerun()

    documents_tab, chat_tab = st.tabs(["Documents", "Chat"])
    with documents_tab:
        _documents_tab(st.session_state["token"])
    with chat_tab:
        _chat_tab(st.session_state["token"])


def main() -> None:
    _init_session_state()
    if st.session_state["token"] is None:
        _login_and_register_screen()
    else:
        _main_app()


main()
