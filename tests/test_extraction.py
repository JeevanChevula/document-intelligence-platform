import fitz
import pytest

from app.extraction import extract_text


def make_searchable_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is a searchable PDF with plenty of real extractable text for testing.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_blank_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page()  # no text inserted — simulates a scanned page with no text layer
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_searchable_pdf_detected_correctly():
    result = extract_text(make_searchable_pdf())

    assert result.num_pages == 1
    assert "searchable PDF" in result.text
    assert result.is_scanned is False


def test_blank_pdf_detected_as_scanned():
    result = extract_text(make_blank_pdf())

    assert result.num_pages == 1
    assert result.text.strip() == ""
    assert result.is_scanned is True


def test_corrupt_pdf_raises():
    with pytest.raises(Exception):
        extract_text(b"%PDF-1.4\nnot a real pdf structure at all")
