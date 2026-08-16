import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.graph import run_agent_pipeline
from app.models import ChatSession, DocumentMetadata, Message, User
from app.schemas import ChatSessionCreate, ChatSessionOut, MessageCreate, MessageOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# how many prior turns to feed back to the LLM as conversation memory. Kept small
# deliberately: assistant answers are long, so replaying many of them on every
# single call was a large share of token usage (enough to hit Groq's free-tier
# rate limit during testing) while only genuinely mattering for short-range
# follow-ups like "check that again".
MAX_HISTORY_MESSAGES = 4

# how much of the first message becomes the chat's title
TITLE_MAX_LENGTH = 50


def _title_from(message: str) -> str:
    """Derive a chat title from its first message.

    Deliberately not an LLM call: a summarised title would cost tokens on every
    new chat against a limited daily budget, and the user's own opening words
    identify the conversation perfectly well. Untitled chats all rendered as
    "Untitled chat", which made the session list unusable once there were a few.
    """
    title = " ".join(message.split())  # collapse newlines/runs of spaces
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    # trim at a word boundary where there is one reasonably near the end,
    # so titles don't break mid-word
    trimmed = title[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0]
    return f"{trimmed or title[:TITLE_MAX_LENGTH]}…"


def _get_owned_session(session_id: uuid.UUID, db: Session, current_user: User) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    session_in: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(user_id=current_user.id, title=session_in.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat and everything said in it.

    Simpler than deleting a document, which spans Qdrant, disk and Postgres: a
    chat lives only in Postgres, and ChatSession.messages cascades, so removing
    the session removes its messages in the same transaction.

    Note this deletes the conversation, not the documents it discussed — and
    conversely, deleting a document never rewrites chats that already quoted it.
    """
    session = _get_owned_session(session_id, db, current_user)
    db.delete(session)
    db.commit()


@router.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    session_id: uuid.UUID,
    message_in: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(session_id, db, current_user)

    prior_messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(prior_messages)]

    # name the chat after its opening message. Guarded on the session having no
    # title rather than on the history being empty, so an explicitly-chosen title
    # is never overwritten and a chat whose first turn errored still gets named.
    if not session.title:
        session.title = _title_from(message_in.content)

    user_message = Message(session_id=session.id, role="user", content=message_in.content)
    db.add(user_message)
    db.commit()

    # fetched here rather than inside the pipeline so app/graph.py keeps no
    # database dependency of its own — same pattern as `history` above
    document_names = [
        name for (name,) in db.query(DocumentMetadata.filename).filter(DocumentMetadata.user_id == current_user.id)
    ]

    try:
        result = run_agent_pipeline(message_in.content, current_user.id, history, document_names)
        answer = result["answer"]
        source = result["source"]
        # only meaningful when there were chunks to validate against; stays NULL
        # for general chat and for document questions that retrieved nothing
        is_verified = result["is_valid"] if source == "documents" else None
    except Exception:
        # never leave the user's question without a reply, even if the pipeline
        # itself failed (Groq outage, rate limit, network error, etc.) — but do
        # log the real error, otherwise production failures are undiagnosable
        logger.exception("Agent pipeline failed for session %s", session.id)
        answer = "Sorry, something went wrong while generating a response. Please try again."
        source = "error"
        is_verified = None

    assistant_message = Message(
        session_id=session.id, role="assistant", content=answer, source=source, is_verified=is_verified
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return assistant_message


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(session_id, db, current_user)
    return db.query(Message).filter(Message.session_id == session.id).order_by(Message.created_at).all()
