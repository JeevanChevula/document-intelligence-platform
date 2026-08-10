import os

import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


class ApiError(Exception):
    """Raised when the backend returns a non-2xx response, carrying its detail message."""


def _raise_for_status(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise ApiError(detail)


def register(email: str, password: str) -> dict:
    response = requests.post(f"{API_BASE_URL}/auth/register", json={"email": email, "password": password})
    _raise_for_status(response)
    return response.json()


def login(email: str, password: str) -> str:
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        data={"username": email, "password": password},
    )
    _raise_for_status(response)
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def list_documents(token: str) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/documents", headers=_auth_headers(token))
    _raise_for_status(response)
    return response.json()


def upload_document(token: str, filename: str, file_bytes: bytes) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/documents/upload",
        headers=_auth_headers(token),
        files={"file": (filename, file_bytes, "application/pdf")},
    )
    _raise_for_status(response)
    return response.json()


def list_sessions(token: str) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/chat/sessions", headers=_auth_headers(token))
    _raise_for_status(response)
    return response.json()


def create_session(token: str, title: str | None) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/chat/sessions", headers=_auth_headers(token), json={"title": title}
    )
    _raise_for_status(response)
    return response.json()


def list_messages(token: str, session_id: str) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/chat/sessions/{session_id}/messages", headers=_auth_headers(token))
    _raise_for_status(response)
    return response.json()


def send_message(token: str, session_id: str, content: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/chat/sessions/{session_id}/messages",
        headers=_auth_headers(token),
        json={"content": content},
    )
    _raise_for_status(response)
    return response.json()
