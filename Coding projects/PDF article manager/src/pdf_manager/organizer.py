"""Phase 3: Copy classified articles into subject subfolders."""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from .models import ClassificationResult, PDFRecord
from .utils import make_unique_path, sanitize_folder_name

logger = logging.getLogger("pdf_manager")

# Merge similar subject names returned by Claude
SUBJECT_ALIASES: dict[str, str] = {
    "hair biology": "Hair Science",
    "hair research": "Hair Science",
    "trichology": "Hair Science",
    "skin biology": "Dermatology",
    "skin science": "Dermatology",
    "cosmetics": "Cosmetic Science",
    "cosmetic chemistry": "Cosmetic Science",
    "peptide chemistry": "Biochemistry",
    "protein chemistry": "Biochemistry",
    "polymer science": "Materials Science",
    "polymer chemistry": "Materials Science",
    "drug discovery": "Pharmacology",
    "drug delivery": "Pharmacology",
    "cancer biology": "Oncology",
    "cancer research": "Oncology",
    "genomics": "Genetics",
    "bioinformatics": "Genetics",
}

# Subjects with fewer articles than this get merged into "Other"
MIN_ARTICLES_PER_SUBJECT = 2


def normalize_subject(raw: str | None) -> str:
    """Map *raw* subject to a canonical folder name."""
    if not raw:
        return "Uncategorized"
    lower = raw.lower().strip()
    return SUBJECT_ALIASES.get(lower, raw.strip().title())


def _article_records(records: list[PDFRecord]) -> list[PDFRecord]:
    """Return records that are confirmed scientific articles."""
    return [
        r
        for r in records
        if r.api_result == ClassificationResult.SCIENTIFIC_ARTICLE
        or (
            r.heuristic_result == ClassificationResult.SCIENTIFIC_ARTICLE
            and r.api_result is None  # wasn't sent to API
        )
    ]


def organize_articles(
    records: list[PDFRecord],
    output_dir: Path,
) -> int:
    """Copy scientific articles into *output_dir*/{subject}/.

    Returns the number of files copied.
    """
    articles = _article_records(records)
    if not articles:
        logger.info("No scientific articles found to organize.")
        return 0

    # Normalize subjects
    for rec in articles:
        rec.subject = normalize_subject(rec.subject)

    # Merge rare subjects into "Other"
    counts = Counter(rec.subject for rec in articles)
    rare = {subj for subj, n in counts.items() if n < MIN_ARTICLES_PER_SUBJECT}
    if rare:
        for rec in articles:
            if rec.subject in rare:
                rec.subject = "Other"

    output_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for rec in tqdm(articles, desc="Copying articles", unit="file"):
        subject_dir = output_dir / sanitize_folder_name(rec.subject or "Uncategorized")
        subject_dir.mkdir(parents=True, exist_ok=True)

        dest = make_unique_path(subject_dir / rec.filename)
        try:
            shutil.copy2(rec.path, dest)
            rec.copied_to = str(dest)
            copied += 1
        except OSError as exc:
            logger.warning("Failed to copy %s: %s", rec.path, exc)
            rec.error_message = str(exc)

    logger.info("Copied %d articles into %s", copied, output_dir)
    return copied
