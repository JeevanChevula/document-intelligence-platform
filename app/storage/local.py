import uuid
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, file_bytes: bytes, filename: str) -> str:
        # generate a random name so two uploads of "invoice.pdf" never collide,
        # and so a malicious filename (e.g. "../../etc/passwd") can't escape base_path
        extension = Path(filename).suffix
        storage_path = f"{uuid.uuid4()}{extension}"
        (self.base_path / storage_path).write_bytes(file_bytes)
        return storage_path

    def get(self, storage_path: str) -> bytes:
        return (self.base_path / storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        (self.base_path / storage_path).unlink(missing_ok=True)

    def exists(self, storage_path: str) -> bool:
        return (self.base_path / storage_path).exists()
