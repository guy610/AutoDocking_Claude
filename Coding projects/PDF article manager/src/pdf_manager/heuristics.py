"""Phase 1c: Rule-based pre-classification to minimise API calls.

Scores each PDF on likelihood of being a scientific article using text
patterns from the first page.  PDFs with high or low scores are classified
without touching the API; only ambiguous ones are forwarded to Claude.
"""

from __future__ import annotations

import re

from .config import (
    ARTICLE_THRESHOLD,
    MAX_PDF_SIZE_BYTES,
    MIN_PDF_SIZE_BYTES,
    NOT_ARTICLE_THRESHOLD,
)
from .models import ClassificationResult, PDFRecord

# ---------------------------------------------------------------------------
# Positive signals
# ---------------------------------------------------------------------------
DOI_PATTERN = re.compile(r"10\.\d{4,}/[^\s]+", re.IGNORECASE)
ABSTRACT_PATTERN = re.compile(r"\babstract\b", re.IGNORECASE)
KEYWORDS_PATTERN = re.compile(r"\bkeywords?\s*:", re.IGNORECASE)
ISSN_PATTERN = re.compile(r"ISSN[\s:]*\d{4}-\d{3}[\dX]", re.IGNORECASE)
RECEIVED_ACCEPTED = re.compile(
    r"\b(received|accepted|revised|submitted)\s*:", re.IGNORECASE
)

JOURNAL_INDICATORS = [
    "journal of",
    "proceedings of",
    "et al.",
    "vol.",
    "pp.",
    "published by",
    "elsevier",
    "springer",
    "wiley",
    "nature",
    "science",
    "cell press",
    "acs publications",
    "royal society",
    "academic press",
    "taylor & francis",
    "mdpi",
    "frontiers in",
    "plos",
    "bmc ",
    "peer-reviewed",
    "open access",
]

# ---------------------------------------------------------------------------
# Negative signals (definitely NOT a scientific article)
# ---------------------------------------------------------------------------
NEGATIVE_KEYWORDS = [
    "invoice",
    "receipt",
    "payslip",
    "pay slip",
    "salary",
    "contract",
    "agreement",
    "non-disclosure",
    "nda",
    "standard operating procedure",
    "sop",
    "material safety data sheet",
    "msds",
    "safety data sheet",
    "sds",
    "certificate of analysis",
    "coa",
    "quotation",
    "purchase order",
    "shipping label",
    "tracking number",
    "user manual",
    "installation guide",
    "curriculum vitae",
    "resume",
]

# Filename-based quick rejections
SOP_FILENAME = re.compile(r"^\d{3}[-_].*SOP", re.IGNORECASE)
INSTRUMENT_OUTPUT = re.compile(r"~Prvw\d+\.pdf$", re.IGNORECASE)


def score_article_likelihood(
    record: PDFRecord,
) -> tuple[ClassificationResult, float]:
    """Score *record* on how likely it is to be a scientific article.

    Returns ``(classification, score)`` where score is in [0, 1].
    """
    text = (record.extracted_text_preview or "").lower()
    filename = record.filename

    # --- Filename-based hard rejections --------------------------------
    if SOP_FILENAME.match(filename):
        return ClassificationResult.NOT_ARTICLE, 0.05
    if INSTRUMENT_OUTPUT.search(filename):
        return ClassificationResult.NOT_ARTICLE, 0.02

    # --- Size-based quick decisions ------------------------------------
    if record.size_bytes < MIN_PDF_SIZE_BYTES:
        return ClassificationResult.NOT_ARTICLE, 0.10
    if not text:
        # No extractable text (scanned image or empty) — can't classify
        return ClassificationResult.NOT_ARTICLE, 0.15

    score = 0.50  # Start neutral

    # Large files less likely to be single articles
    if record.size_bytes > MAX_PDF_SIZE_BYTES:
        score -= 0.15

    # --- Negative text signals -----------------------------------------
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if neg_count >= 2:
        return ClassificationResult.NOT_ARTICLE, 0.05
    score -= neg_count * 0.15

    # --- Positive text signals -----------------------------------------
    if DOI_PATTERN.search(text) or DOI_PATTERN.search(filename.lower()):
        score += 0.25
        record.has_doi = True

    if ABSTRACT_PATTERN.search(text):
        score += 0.15
        record.has_abstract = True

    if KEYWORDS_PATTERN.search(text):
        score += 0.10

    if ISSN_PATTERN.search(text):
        score += 0.20

    if RECEIVED_ACCEPTED.search(text):
        score += 0.10

    journal_hits = sum(1 for j in JOURNAL_INDICATORS if j in text)
    score += min(journal_hits * 0.08, 0.30)

    # --- Clamp and classify --------------------------------------------
    score = max(0.0, min(1.0, score))

    if score >= ARTICLE_THRESHOLD:
        return ClassificationResult.SCIENTIFIC_ARTICLE, score
    if score <= NOT_ARTICLE_THRESHOLD:
        return ClassificationResult.NOT_ARTICLE, score
    return ClassificationResult.AMBIGUOUS, score
