"""State persistence: JSON checkpoint/resume for interrupted runs."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import ScanState

logger = logging.getLogger("pdf_manager")


def save_state(state: ScanState, path: Path) -> None:
    """Atomically write *state* to a JSON file at *path*."""
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.replace(path)  # atomic rename on same drive
    logger.debug("State saved to %s", path)


def load_state(path: Path) -> ScanState | None:
    """Load a previous checkpoint, or return ``None`` if none exists."""
    if not path.exists():
        return None
    try:
        data = path.read_text(encoding="utf-8")
        state = ScanState.model_validate_json(data)
        logger.info(
            "Resumed from checkpoint: %d PDFs, scan=%s, extract=%s, heuristics=%s, classify=%s",
            state.total_pdfs_found,
            state.scan_complete,
            state.extraction_complete,
            state.heuristics_complete,
            state.classification_complete,
        )
        return state
    except Exception as exc:
        logger.warning("Could not load state from %s: %s", path, exc)
        return None
