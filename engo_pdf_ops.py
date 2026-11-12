"""Small local PDF utilities built on Engo's existing PyMuPDF dependency."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

import pymupdf as fitz


def merge_pdfs(input_paths: Iterable[str | os.PathLike[str]], output_path: str | os.PathLike[str]) -> str:
    """Merge at least two PDFs into ``output_path`` and replace it atomically.

    Inputs are read-only. A temporary file is written beside the destination so
    ``os.replace`` remains atomic on the same volume. Password-protected PDFs
    are refused rather than silently omitting pages.
    """
    sources = [Path(path).expanduser().resolve() for path in input_paths]
    if len(sources) < 2:
        raise ValueError("Select at least two PDF files to merge")
    if any(not path.is_file() for path in sources):
        missing = next(path for path in sources if not path.is_file())
        raise FileNotFoundError(f"PDF input file was not found: {missing}")
    if any(path.suffix.lower() != ".pdf" for path in sources):
        raise ValueError("All input files must be PDFs")

    destination = Path(output_path).expanduser().resolve()
    if destination in sources:
        raise ValueError("The output file must be different from every input file")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("The output file must use the .pdf extension")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output folder does not exist: {destination.parent}")

    fd, temp_name = tempfile.mkstemp(prefix=".engo-merge-", suffix=".pdf", dir=str(destination.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        # PyMuPDF expects to create the new target itself; remove the empty
        # mkstemp placeholder while retaining its unique path.
        temp_path.unlink(missing_ok=True)
        with fitz.open() as merged:
            first_metadata = None
            for source_path in sources:
                with fitz.open(str(source_path)) as source:
                    if source.needs_pass:
                        raise ValueError(f"Password-protected PDF cannot be merged without a password: {source_path.name}")
                    if source.page_count < 1:
                        continue
                    if first_metadata is None:
                        metadata = source.metadata or {}
                        allowed = ("title", "author", "subject", "keywords", "creator", "producer",
                                   "creationDate", "modDate", "trapped")
                        first_metadata = {key: metadata[key] for key in allowed if metadata.get(key) is not None}
                    merged.insert_pdf(source, links=True, annots=True, show_progress=0)
            if merged.page_count < 1:
                raise ValueError("The selected PDFs contain no pages")
            if first_metadata:
                merged.set_metadata(first_metadata)
            merged.save(str(temp_path), garbage=4, deflate=True)
        os.replace(temp_path, destination)
        return str(destination)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


__all__ = ["merge_pdfs"]
