from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Contract every storage implementation (local disk, S3, ...) must follow.

    Business logic depends only on this interface, never on a concrete
    implementation — so swapping local disk for S3 later means writing a
    new class here, not touching any code that uploads/downloads files.
    """

    @abstractmethod
    def save(self, file_bytes: bytes, filename: str) -> str:
        """Persist file_bytes and return a storage_path that identifies it later."""

    @abstractmethod
    def get(self, storage_path: str) -> bytes:
        """Return the raw bytes previously saved at storage_path."""

    @abstractmethod
    def delete(self, storage_path: str) -> None:
        """Remove the file at storage_path, if it exists."""

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Return whether a file exists at storage_path."""
