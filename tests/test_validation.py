from app.validation import is_valid_pdf


def test_valid_pdf_bytes_accepted():
    assert is_valid_pdf(b"%PDF-1.4\n...")


def test_non_pdf_bytes_rejected():
    assert not is_valid_pdf(b"not a pdf at all")


def test_renamed_file_with_pdf_extension_but_wrong_content_rejected():
    fake_pdf = b"MZ\x90\x00...this is actually an exe"  # real .exe files start with "MZ"
    assert not is_valid_pdf(fake_pdf)
