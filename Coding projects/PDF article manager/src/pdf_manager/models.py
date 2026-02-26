"""Pydantic data models for the PDF classification pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ClassificationResult(str, Enum):
    SCIENTIFIC_ARTICLE = "scientific_article"
    NOT_ARTICLE = "not_article"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


class PDFRecord(BaseModel):
    """Represents one PDF found during scanning."""

    path: str
    size_bytes: int
    filename: str

    # Phase 1 results
    heuristic_result: ClassificationResult | None = None
    heuristic_score: float | None = None
    extracted_text_preview: str | None = None
    has_doi: bool = False
    has_abstract: bool = False

    # Phase 2 results
    api_result: ClassificationResult | None = None
    subject: str | None = None
    api_confidence: float | None = None

    # Phase 3 results
    copied_to: str | None = None

    # Metadata
    error_message: str | None = None
    processed_at: datetime | None = None


class ScanState(BaseModel):
    """Checkpoint state for resume capability."""

    scan_id: str
    started_at: datetime
    scan_complete: bool = False
    extraction_complete: bool = False
    heuristics_complete: bool = False
    classification_complete: bool = False
    organization_complete: bool = False

    total_pdfs_found: int = 0
    pdfs_extracted: int = 0
    pdfs_classified: int = 0
    pdfs_copied: int = 0

    records: list[PDFRecord] = []
    subjects_discovered: list[str] = []
    estimated_cost_usd: float = 0.0
    batch_id: str | None = None
