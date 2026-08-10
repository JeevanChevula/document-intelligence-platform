import fitz

from app.ocr import run_ocr


def make_text_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=20)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_ocr_reads_text_from_rendered_page():
    result = run_ocr(make_text_pdf("Tesseract OCR pipeline verification."))

    assert "Tesseract OCR pipeline verification" in result


def test_ocr_on_blank_page_returns_empty_or_whitespace():
    result = run_ocr(make_text_pdf(""))

    assert result.strip() == ""
