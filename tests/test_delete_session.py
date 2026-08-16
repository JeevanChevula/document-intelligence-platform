import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ChatSession, Message, User


@pytest.fixture
def two_users_with_chats():
    """Two real users, each with a chat containing messages.

    Hits the real database rather than mocking it, because the property under
    test — that deleting a session cascades to its messages and stops at the
    owner's boundary — is enforced by the schema, not by our Python.
    """
    db = SessionLocal()
    owner = User(email=f"owner-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    stranger = User(email=f"stranger-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db.add_all([owner, stranger])
    db.flush()

    owned = ChatSession(user_id=owner.id, title="owned chat")
    keep = ChatSession(user_id=owner.id, title="the other one")
    strangers = ChatSession(user_id=stranger.id, title="not yours")
    db.add_all([owned, keep, strangers])
    db.flush()

    db.add_all(
        [
            Message(session_id=owned.id, role="user", content="hello"),
            Message(session_id=owned.id, role="assistant", content="hi", source="general_knowledge"),
            Message(session_id=keep.id, role="user", content="still here"),
        ]
    )
    db.commit()

    data = {"owner": owner.id, "owned": owned.id, "keep": keep.id, "strangers": strangers.id}
    yield db, data

    for user_id in (owner.id, stranger.id):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            db.delete(user)  # cascades to sessions and messages
    db.commit()
    db.close()


def _client_for(user_id: uuid.UUID) -> TestClient:
    from app.dependencies import get_current_user

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_deleting_a_chat_removes_its_messages_too(two_users_with_chats):
    db, data = two_users_with_chats
    client = _client_for(data["owner"])

    response = client.delete(f"/chat/sessions/{data['owned']}")

    assert response.status_code == 204
    db.expire_all()
    assert db.query(ChatSession).filter(ChatSession.id == data["owned"]).first() is None
    # the cascade is the point: an orphaned message row would still hold whatever
    # the assistant said in a conversation the user asked to be rid of
    assert db.query(Message).filter(Message.session_id == data["owned"]).count() == 0
    app.dependency_overrides.clear()


def test_deleting_one_chat_leaves_the_users_others_alone(two_users_with_chats):
    db, data = two_users_with_chats
    client = _client_for(data["owner"])

    client.delete(f"/chat/sessions/{data['owned']}")

    db.expire_all()
    assert db.query(ChatSession).filter(ChatSession.id == data["keep"]).first() is not None
    assert db.query(Message).filter(Message.session_id == data["keep"]).count() == 1
    app.dependency_overrides.clear()


def test_cannot_delete_another_users_chat(two_users_with_chats):
    db, data = two_users_with_chats
    client = _client_for(data["owner"])

    response = client.delete(f"/chat/sessions/{data['strangers']}")

    # 404 rather than 403: the API never reveals that a chat it won't serve exists
    assert response.status_code == 404
    db.expire_all()
    assert db.query(ChatSession).filter(ChatSession.id == data["strangers"]).first() is not None
    app.dependency_overrides.clear()


def test_deleting_a_chat_that_does_not_exist_is_a_404(two_users_with_chats):
    _, data = two_users_with_chats
    client = _client_for(data["owner"])

    assert client.delete(f"/chat/sessions/{uuid.uuid4()}").status_code == 404
    app.dependency_overrides.clear()
