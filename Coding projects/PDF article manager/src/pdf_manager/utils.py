"""Cross-cutting utilities: logging, long-path handling, UTF-8 setup."""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

from . import config

logger = logging.getLogger("pdf_manager")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with UTF-8 encoding for Windows compatibility."""
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger("pdf_manager")
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def ensure_long_path(path: str) -> str:
    """Prefix with \\\\?\\ for Windows long path support (>260 chars)."""
    if sys.platform == "win32" and len(path) > 240 and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def make_unique_path(dest: Path) -> Path:
    """If dest exists, append _2, _3, etc. before the extension."""
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def sanitize_folder_name(name: str) -> str:
    """Remove characters invalid for Windows folder names."""
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join(c for c in name if c not in invalid_chars)
    return sanitized.strip(". ") or "Uncategorized"
