from pathlib import Path

import pymupdf as fitz
import pytest

from engo_pdf_ops import merge_pdfs


def _make_pdf(path: Path, text: str, pages: int = 1):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_merge_pdfs_combines_pages_and_preserves_input_files(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "combined.pdf"
    _make_pdf(first, "first", 2)
    _make_pdf(second, "second", 3)

    result = merge_pdfs([first, second], output)

    assert result == str(output.resolve())
    with fitz.open(output) as merged:
        assert merged.page_count == 5
        assert "first" in merged[0].get_text()
        assert "second" in merged[2].get_text()
    with fitz.open(first) as original:
        assert original.page_count == 2
    with fitz.open(second) as original:
        assert original.page_count == 3


def test_merge_pdfs_rejects_single_input_and_output_collision(tmp_path):
    source = tmp_path / "source.pdf"
    _make_pdf(source, "source")
    with pytest.raises(ValueError, match="at least two"):
        merge_pdfs([source], tmp_path / "out.pdf")
    with pytest.raises(ValueError, match="different"):
        merge_pdfs([source, source], source)


def test_merge_pdfs_rejects_encrypted_input(tmp_path):
    source = tmp_path / "protected.pdf"
    protected = fitz.open()
    protected.new_page()
    protected.save(source, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    protected.close()
    other = tmp_path / "other.pdf"
    _make_pdf(other, "other")
    with pytest.raises(ValueError, match="Password-protected"):
        merge_pdfs([source, other], tmp_path / "result.pdf")
