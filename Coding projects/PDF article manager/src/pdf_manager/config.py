"""Configuration constants and environment loading."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_DIR / ".env")

# --- Paths ---
PROJECT_DIR = _PROJECT_DIR
OUTPUT_DIR = PROJECT_DIR / "Scientific Articles"
STATE_FILE = PROJECT_DIR / "scan_state.json"
LOG_FILE = PROJECT_DIR / "scan.log"
DEFAULT_SCAN_ROOT = Path("C:/")

# --- Directories to skip during scanning ---
SKIP_DIRS = {
    # Windows system
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "$Recycle.Bin",
    "System Volume Information",
    "$WinREAgent",
    "Recovery",
    "PerfLogs",
    # Dev / cache
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    # Application data (mostly caches, not user files)
    "AppData",
}

# --- Claude API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS_CLASSIFY = 128
FIRST_PAGE_CHAR_LIMIT = 3000

# --- Batch API polling ---
BATCH_POLL_INTERVAL_SECONDS = 30

# --- Heuristic thresholds ---
ARTICLE_THRESHOLD = 0.7
NOT_ARTICLE_THRESHOLD = 0.2
MIN_PDF_SIZE_BYTES = 10_000        # < 10 KB almost certainly not an article
MAX_PDF_SIZE_BYTES = 100_000_000   # > 100 MB probably a book or scan dump
