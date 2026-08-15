import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.chunking import chunk_text
from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.extraction import extract_text
from app.models import DocumentMetadata, User
from app.ocr import run_ocr
from app.schemas import DocumentOut
from app.storage import get_storage
from app.validation import is_valid_pdf
from app.vector_store import delete_document_chunks, upsert_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(DocumentMetadata)
        .filter(DocumentMetadata.user_id == current_user.id)
        .order_by(DocumentMetadata.uploaded_at.desc())
        .all()
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a document from all three places it lives: Qdrant, disk, Postgres.

    Ordering is deliberate. Chunks go first, because the worst possible outcome
    is a document that looks deleted but still feeds answers into the RAG
    pipeline — invisible and still active. Removing chunks first means a partial
    failure leaves the document *visible but inert*: the user can see it in their
    list and retry. Fail toward the state the user can observe and fix.

    404 rather than 403 for someone else's document, matching the chat router:
    the API never reveals whether a resource it won't serve exists.
    """
    document = (
        db.query(DocumentMetadata)
        .filter(DocumentMetadata.id == document_id, DocumentMetadata.user_id == current_user.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        delete_document_chunks(document_id, current_user.id)
    except Exception:
        # the one failure worth refusing on: leaving searchable chunks behind
        # would mean a "deleted" document silently keeps answering questions
        logger.exception("Could not delete chunks for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete the document's indexed content — nothing was deleted. Please try again.",
        )

    try:
        get_storage().delete(document.storage_path)
    except Exception:
        # an orphaned file wastes disk but can't affect any answer, so it must
        # not block removing the row the user actually asked to be rid of
        logger.exception("Could not delete stored file for document %s", document_id)

    db.delete(document)
    db.commit()


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are accepted")

    file_bytes = await file.read()

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB limit",
        )

    if not is_valid_pdf(file_bytes):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is not a valid PDF")

    try:
        extraction = extract_text(file_bytes)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read PDF file — it may be corrupted")

    ocr_used = False
    raw_text = extraction.text
    if extraction.is_scanned:
        try:
            raw_text = run_ocr(file_bytes)
            ocr_used = True
        except Exception:
            # OCR failing shouldn't block the upload — the file and its metadata
            # are still valid and useful; it just stays flagged as not-yet-OCR'd.
            raw_text = ""
            ocr_used = False

    storage_path = get_storage().save(file_bytes, file.filename)

    document_id = uuid.uuid4()
    chunks = chunk_text(raw_text, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)

    is_indexed = False
    if chunks:
        try:
            upsert_chunks(document_id, current_user.id, chunks)
            is_indexed = True
        except Exception:
            # same principle as OCR above: indexing failing shouldn't block the
            # upload — the document is still saved, just not yet searchable.
            is_indexed = False

    document = DocumentMetadata(
        id=document_id,
        user_id=current_user.id,
        filename=file.filename,
        storage_path=storage_path,
        content_type=file.content_type,
        num_pages=extraction.num_pages,
        is_scanned=extraction.is_scanned,
        ocr_used=ocr_used,
        is_indexed=is_indexed,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return document
