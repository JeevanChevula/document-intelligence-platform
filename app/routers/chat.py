import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.graph import run_agent_pipeline
from app.models import ChatSession, Message, User
from app.schemas import ChatSessionCreate, ChatSessionOut, MessageCreate, MessageOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# how many prior turns to feed back to the LLM as conversation memory. Kept small
# deliberately: assistant answers are long, so replaying many of them on every
# single call was a large share of token usage (enough to hit Groq's free-tier
# rate limit during testing) while only genuinely mattering for short-range
# follow-ups like "check that again".
MAX_HISTORY_MESSAGES = 4


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

    user_message = Message(session_id=session.id, role="user", content=message_in.content)
    db.add(user_message)
    db.commit()

    try:
        result = run_agent_pipeline(message_in.content, current_user.id, history)
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
