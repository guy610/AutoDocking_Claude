"""Phase 1a: Walk the filesystem and find all PDF files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from tqdm import tqdm

from .models import PDFRecord

logger = logging.getLogger("pdf_manager")


def scan_for_pdfs(
    root: Path,
    skip_dirs: set[str],
) -> list[PDFRecord]:
    """Walk *root* recursively, collecting all .pdf files.

    Directories whose name appears in *skip_dirs* are pruned entirely.
    Permission errors and encoding issues are logged and skipped.
    """
    records: list[PDFRecord] = []
    dirs_scanned = 0

    def _on_error(err: OSError) -> None:
        logger.debug("Skipped (OS error): %s", err)

    progress = tqdm(desc="Scanning directories", unit=" dirs", dynamic_ncols=True)

    for dirpath, dirnames, filenames in os.walk(
        str(root), onerror=_on_error
    ):
        # Prune skip_dirs in-place so os.walk won't descend into them
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        dirs_scanned += 1
        if dirs_scanned % 200 == 0:
            progress.update(200)
            progress.set_postfix(pdfs=len(records), refresh=True)

        for fname in filenames:
            if not fname.lower().endswith(".pdf"):
                continue
            full_path = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(full_path)
                records.append(
                    PDFRecord(
                        path=full_path,
                        size_bytes=size,
                        filename=fname,
                    )
                )
            except OSError as exc:
                logger.debug("Cannot stat %s: %s", full_path, exc)

    progress.update(dirs_scanned % 200)
    progress.set_postfix(pdfs=len(records))
    progress.close()

    logger.info("Scan complete: %d PDFs found in %d directories", len(records), dirs_scanned)
    return records
