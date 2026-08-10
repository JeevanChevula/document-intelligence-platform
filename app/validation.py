PDF_MAGIC_BYTES = b"%PDF"


def is_valid_pdf(file_bytes: bytes) -> bool:
    return file_bytes.startswith(PDF_MAGIC_BYTES)
