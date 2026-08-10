import fitz
import pytesseract
from PIL import Image

# render at a higher resolution than the PDF default (72 dpi) — OCR accuracy
# drops sharply on low-resolution/blurry text
OCR_RENDER_DPI = 300


def run_ocr(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        page_texts = []
        for page in doc:
            pix = page.get_pixmap(dpi=OCR_RENDER_DPI)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            page_texts.append(pytesseract.image_to_string(image))
    finally:
        doc.close()

    return "\n".join(page_texts)
