from fastapi import FastAPI

from app.config import get_settings
from app.routers import auth, chat, documents

app = FastAPI(title="Document Intelligence Platform")
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "groq_model": settings.groq_model,
        "storage_backend": settings.storage_backend,
    }
