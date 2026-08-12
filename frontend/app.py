import streamlit as st

from api_client import (
    ApiError,
    create_session,
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

    st.dataframe(
        [
            {
                "Filename": doc["filename"],
                "Pages": doc["num_pages"],
                "Scanned": doc["is_scanned"],
                "OCR used": doc["ocr_used"],
                "Indexed": doc["is_indexed"],
                "Uploaded at": doc["uploaded_at"],
            }
            for doc in documents
        ],
        use_container_width=True,
        hide_index=True,
    )


def _chat_tab(token: str) -> None:
    try:
        sessions = list_sessions(token)
    except ApiError as e:
        st.error(f"Could not load chat sessions: {e}")
        return

    session_labels = {s["id"]: (s["title"] or "Untitled chat") for s in sessions}

    col1, col2 = st.columns([3, 1])
    with col1:
        options = list(session_labels.keys())
        current = st.session_state["current_session_id"]
        index = options.index(current) if current in options else 0 if options else None
        selected = st.selectbox(
            "Chat session",
            options=options,
            index=index,
            format_func=lambda sid: session_labels[sid],
        ) if options else None
        if selected is not None:
            st.session_state["current_session_id"] = selected
    with col2:
        new_title = st.text_input("New chat title", placeholder="optional", label_visibility="collapsed")
        if st.button("+ New chat"):
            try:
                new_session = create_session(token, new_title or None)
                st.session_state["current_session_id"] = new_session["id"]
                st.rerun()
            except ApiError as e:
                st.error(f"Could not create chat session: {e}")

    session_id = st.session_state["current_session_id"]
    if session_id is None:
        st.info("Create a chat session to get started.")
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
