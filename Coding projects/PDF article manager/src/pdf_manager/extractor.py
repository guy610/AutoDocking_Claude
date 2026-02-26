"""Phase 1b: Extract text from the first page of each PDF using PyMuPDF."""

from __future__ import annotations

import logging

import fitz  # PyMuPDF

from .config import FIRST_PAGE_CHAR_LIMIT
from .utils import ensure_long_path

logger = logging.getLogger("pdf_manager")


def extract_first_page_text(
    pdf_path: str,
    char_limit: int = FIRST_PAGE_CHAR_LIMIT,
) -> str | None:
    """Extract text from the first page of *pdf_path*.

    Returns ``None`` if the PDF cannot be opened, has no pages, or
    contains no extractable text (e.g. scanned-image PDFs).
    """
    try:
        safe_path = ensure_long_path(pdf_path)
        doc = fitz.open(safe_path)
        try:
            if doc.page_count == 0:
                return None
            text = doc[0].get_text("text")
            if not text or not text.strip():
                return None
            return text[:char_limit]
        finally:
            doc.close()
    except Exception as exc:
        logger.debug("Cannot extract text from %s: %s", pdf_path, exc)
        return None
