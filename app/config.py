from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Groq)
    groq_api_key: str
    # llama-3.3-70b-versatile was retired by Groq on 2026-08-16. gpt-oss-120b is the
    # closest replacement on the free tier and doubles the daily token budget
    # (100K -> 200K TPD), at the cost of a slightly tighter per-minute ceiling (12K -> 8K TPM).
    groq_model: str = "openai/gpt-oss-120b"

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "document_chunks"
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # File storage
    storage_backend: str = "local"
    storage_local_path: str = "./storage"
    max_upload_size_mb: int = 20

    # Chunking (character counts, not tokens — see app/chunking.py)
    chunk_size: int = 1000
    chunk_overlap: int = 200

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
