"""Command-line interface for the PDF article manager."""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from . import config
from .batch_client import BatchClassifier
from .cost import estimate_cost
from .extractor import extract_first_page_text
from .heuristics import score_article_likelihood
from .models import ClassificationResult, ScanState
from .organizer import organize_articles
from .scanner import scan_for_pdfs
from .state import load_state, save_state
from .utils import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-manager",
        description="Scan for scientific article PDFs and organize by subject",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run the full scan-classify-organize pipeline")
    run_p.add_argument(
        "--root",
        type=str,
        default=str(config.DEFAULT_SCAN_ROOT),
        help="Root directory to scan (default: C:/)",
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Phase 1 only — scan + heuristics, show cost estimate, don't call API",
    )
    run_p.add_argument(
        "--no-batch",
        action="store_true",
        help="Use synchronous API calls instead of Batch API (2x more expensive)",
    )
    run_p.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last saved checkpoint",
    )
    run_p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    sub.add_parser("status", help="Show current scan state and progress")

    return parser


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    setup_logging(verbose=args.verbose)

    # --- Resume or start fresh -----------------------------------------
    state: ScanState | None = None
    if args.resume:
        state = load_state(config.STATE_FILE)

    if state is None:
        state = ScanState(
            scan_id=uuid.uuid4().hex[:12],
            started_at=datetime.now(timezone.utc),
        )

    root = Path(args.root)

    # --- Phase 1a: Scan -----------------------------------------------
    if not state.scan_complete:
        print(f"\n=== Phase 1a: Scanning {root} for PDFs ===")
        state.records = scan_for_pdfs(root, config.SKIP_DIRS)
        state.total_pdfs_found = len(state.records)
        state.scan_complete = True
        save_state(state, config.STATE_FILE)
        print(f"Found {state.total_pdfs_found} PDFs\n")
    else:
        print(f"Scan already done — {state.total_pdfs_found} PDFs on file\n")

    # --- Phase 1b: Extract text ---------------------------------------
    if not state.extraction_complete:
        print("=== Phase 1b: Extracting first-page text ===")
        to_extract = [r for r in state.records if r.extracted_text_preview is None and r.heuristic_result is None]
        for rec in tqdm(to_extract, desc="Extracting text", unit="pdf"):
            rec.extracted_text_preview = extract_first_page_text(rec.path)
        state.pdfs_extracted = sum(1 for r in state.records if r.extracted_text_preview)
        state.extraction_complete = True
        save_state(state, config.STATE_FILE)
        print(f"Extracted text from {state.pdfs_extracted}/{state.total_pdfs_found} PDFs\n")
    else:
        print(f"Extraction already done — {state.pdfs_extracted} PDFs with text\n")

    # --- Phase 1c: Heuristic scoring ----------------------------------
    if not state.heuristics_complete:
        print("=== Phase 1c: Heuristic scoring ===")
        for rec in state.records:
            if rec.heuristic_result is None:
                rec.heuristic_result, rec.heuristic_score = score_article_likelihood(rec)
        state.heuristics_complete = True
        save_state(state, config.STATE_FILE)

    articles = [r for r in state.records if r.heuristic_result == ClassificationResult.SCIENTIFIC_ARTICLE]
    ambiguous = [r for r in state.records if r.heuristic_result == ClassificationResult.AMBIGUOUS]
    not_articles = [r for r in state.records if r.heuristic_result == ClassificationResult.NOT_ARTICLE]

    print(f"  Likely articles (skip API):  {len(articles)}")
    print(f"  Ambiguous (need API):        {len(ambiguous)}")
    print(f"  Not articles (skip API):     {len(not_articles)}")

    # --- Cost estimate ------------------------------------------------
    est = estimate_cost(ambiguous, use_batch=not args.no_batch)
    print(f"\n  Estimated API cost: ${est['total_cost_usd']:.4f}")
    print(f"  ({est['num_pdfs']} PDFs, ~{est['est_input_tokens']:,} input tokens)")
    state.estimated_cost_usd = est["total_cost_usd"]
    save_state(state, config.STATE_FILE)

    if args.dry_run:
        print("\n--dry-run flag set. Stopping before API calls.")
        print(f"State saved to {config.STATE_FILE}")
        return

    # --- Phase 2: Claude API classification ---------------------------
    if not state.classification_complete:
        if not ambiguous:
            print("\nNo ambiguous PDFs — skipping API phase.")
        else:
            print(f"\n=== Phase 2: Classifying {len(ambiguous)} PDFs with Claude ===")
            if not config.ANTHROPIC_API_KEY:
                print("ERROR: ANTHROPIC_API_KEY not set.")
                print("Copy .env.example to .env and add your key.")
                print("Get a key at https://console.anthropic.com/")
                return

            answer = input(f"Proceed? Estimated cost: ${est['total_cost_usd']:.4f} [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("Aborted. State saved — use --resume to continue later.")
                return

            classifier = BatchClassifier()
            if args.no_batch:
                classifier.classify_sync(ambiguous)
            else:
                classifier.classify_batch(ambiguous)

        state.pdfs_classified = len(ambiguous)
        state.classification_complete = True
        save_state(state, config.STATE_FILE)

    # --- Collect subjects ---------------------------------------------
    all_articles = [
        r for r in state.records
        if r.api_result == ClassificationResult.SCIENTIFIC_ARTICLE
        or (r.heuristic_result == ClassificationResult.SCIENTIFIC_ARTICLE and r.api_result is None)
    ]
    # For heuristic-only articles, we need subjects from the API.
    # Give them a generic subject based on the strongest signal.
    for rec in all_articles:
        if rec.subject is None:
            rec.subject = "Uncategorized"

    subjects = sorted({r.subject for r in all_articles if r.subject})
    state.subjects_discovered = subjects
    print(f"\nDiscovered {len(subjects)} subject categories: {', '.join(subjects)}")

    # --- Phase 3: Organize files --------------------------------------
    if not state.organization_complete:
        print(f"\n=== Phase 3: Organizing {len(all_articles)} articles ===")
        copied = organize_articles(state.records, config.OUTPUT_DIR)
        state.pdfs_copied = copied
        state.organization_complete = True
        save_state(state, config.STATE_FILE)
        print(f"\nDone! {copied} articles copied to {config.OUTPUT_DIR}")
    else:
        print(f"Already organized — {state.pdfs_copied} articles in {config.OUTPUT_DIR}")


def cmd_status(args: argparse.Namespace) -> None:
    setup_logging()
    state = load_state(config.STATE_FILE)
    if state is None:
        print("No scan state found. Run 'pdf-manager run' to start.")
        return

    print(f"Scan ID:       {state.scan_id}")
    print(f"Started:       {state.started_at}")
    print(f"PDFs found:    {state.total_pdfs_found}")
    print(f"Text extracted:{state.pdfs_extracted}")
    print(f"Classified:    {state.pdfs_classified}")
    print(f"Copied:        {state.pdfs_copied}")
    print(f"Est. cost:     ${state.estimated_cost_usd:.4f}")
    print()
    print(f"Scan complete:          {state.scan_complete}")
    print(f"Extraction complete:    {state.extraction_complete}")
    print(f"Heuristics complete:    {state.heuristics_complete}")
    print(f"Classification complete:{state.classification_complete}")
    print(f"Organization complete:  {state.organization_complete}")
    if state.subjects_discovered:
        print(f"\nSubjects: {', '.join(state.subjects_discovered)}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
