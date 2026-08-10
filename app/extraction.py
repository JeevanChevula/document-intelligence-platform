from dataclasses import dataclass

import fitz  # PyMuPDF

# Below this average amount of extractable text per page, we treat the PDF
# as scanned (image-only) rather than genuinely searchable.
MIN_CHARS_PER_PAGE_FOR_SEARCHABLE = 20


@dataclass
class ExtractionResult:
    num_pages: int
    text: str
    is_scanned: bool


def extract_text(file_bytes: bytes) -> ExtractionResult:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        num_pages = doc.page_count
        page_texts = [page.get_text() for page in doc]
    finally:
        doc.close()

    text = "\n".join(page_texts)
    avg_chars_per_page = len(text.strip()) / num_pages if num_pages else 0
    is_scanned = avg_chars_per_page < MIN_CHARS_PER_PAGE_FOR_SEARCHABLE

    return ExtractionResult(num_pages=num_pages, text=text, is_scanned=is_scanned)
