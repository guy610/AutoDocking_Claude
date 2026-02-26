"""Phase 2: Claude API classification and subject tagging."""

from __future__ import annotations

import json
import logging

from .models import ClassificationResult, PDFRecord

logger = logging.getLogger("pdf_manager")

SYSTEM_PROMPT = """\
You are a scientific literature classifier. Given the first page text of a \
PDF document, determine:
1. Whether this is a peer-reviewed scientific research article published in a \
journal (research paper, review article, or conference paper).
2. If it IS a scientific article, classify its primary subject area.

The following are NOT scientific articles: patents, SOPs/protocols, data \
sheets/MSDS, theses/dissertations, textbook chapters, commercial/market \
reports, invoices, personal documents, presentation slides, instrument \
output files, certificates of analysis, quotations.

Respond in EXACTLY this JSON format (no markdown fences, no extra text):
{"is_article": true, "subject": "Subject Area", "confidence": 0.95}
or
{"is_article": false, "subject": null, "confidence": 0.95}

Use broad subject categories such as: Biochemistry, Cell Biology, \
Dermatology, Materials Science, Pharmacology, Analytical Chemistry, \
Molecular Biology, Neuroscience, Immunology, Organic Chemistry, \
Biophysics, Cosmetic Science, Hair Science, Nanotechnology, \
Plant Biology, Microbiology, Genetics, Proteomics, Biotechnology, \
Chemical Engineering, Environmental Science, Food Science."""


def build_user_message(record: PDFRecord) -> str:
    """Build the user message content for a single classification request."""
    return f"Filename: {record.filename}\n\nFirst page text:\n{record.extracted_text_preview}"


def parse_api_response(raw_text: str) -> dict:
    """Parse the JSON response from Claude into a dict.

    Returns a dict with keys 'is_article', 'subject', 'confidence'.
    On parse failure returns a fallback dict.
    """
    text = raw_text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        return {
            "is_article": bool(data.get("is_article", False)),
            "subject": data.get("subject"),
            "confidence": float(data.get("confidence", 0.5)),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse API response: %s — raw: %s", exc, raw_text[:200])
        return {"is_article": False, "subject": None, "confidence": 0.0}


def apply_api_result(record: PDFRecord, parsed: dict) -> None:
    """Update *record* in-place with the parsed API response."""
    if parsed["is_article"]:
        record.api_result = ClassificationResult.SCIENTIFIC_ARTICLE
        record.subject = parsed.get("subject") or "Uncategorized"
    else:
        record.api_result = ClassificationResult.NOT_ARTICLE
    record.api_confidence = parsed.get("confidence")
