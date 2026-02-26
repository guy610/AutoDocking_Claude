"""Anthropic Message Batches API wrapper for bulk classification."""

from __future__ import annotations

import hashlib
import logging
import time

from anthropic import Anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from tqdm import tqdm

from . import config
from .classifier import SYSTEM_PROMPT, apply_api_result, build_user_message, parse_api_response
from .models import ClassificationResult, PDFRecord

logger = logging.getLogger("pdf_manager")


def _custom_id(record: PDFRecord) -> str:
    """Deterministic short ID derived from the file path."""
    return hashlib.md5(record.path.encode("utf-8")).hexdigest()[:16]


class BatchClassifier:
    """Submit, poll, and retrieve classification results via the Batch API."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or config.ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. "
                "Copy .env.example to .env and paste your key."
            )
        self.client = Anthropic(api_key=key)

    # ------------------------------------------------------------------
    # Batch API path (50 % cheaper)
    # ------------------------------------------------------------------

    def submit_batch(self, records: list[PDFRecord]) -> str:
        """Submit a batch of PDFs for classification. Returns the batch ID."""
        requests = [
            Request(
                custom_id=_custom_id(rec),
                params=MessageCreateParamsNonStreaming(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS_CLASSIFY,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": build_user_message(rec)}],
                ),
            )
            for rec in records
        ]
        batch = self.client.messages.batches.create(requests=requests)
        logger.info("Batch submitted: %s (%d requests)", batch.id, len(requests))
        return batch.id

    def poll_until_complete(
        self,
        batch_id: str,
        interval: int = config.BATCH_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Block until the batch reaches ``ended`` status."""
        progress = tqdm(desc="Waiting for batch", unit="s", dynamic_ncols=True)
        while True:
            batch = self.client.messages.batches.retrieve(batch_id)
            progress.set_postfix(status=batch.processing_status)
            if batch.processing_status == "ended":
                progress.close()
                logger.info("Batch %s completed", batch_id)
                return
            time.sleep(interval)
            progress.update(interval)

    def retrieve_results(self, batch_id: str) -> dict[str, dict]:
        """Stream batch results and return {custom_id: parsed_response}."""
        results: dict[str, dict] = {}
        for entry in self.client.messages.batches.results(batch_id):
            cid = entry.custom_id
            if entry.result.type == "succeeded":
                raw = entry.result.message.content[0].text
                results[cid] = parse_api_response(raw)
            else:
                logger.warning("Batch item %s failed: %s", cid, entry.result.type)
                results[cid] = {"is_article": False, "subject": None, "confidence": 0.0}
        return results

    def classify_batch(self, records: list[PDFRecord]) -> None:
        """End-to-end: submit → poll → apply results to *records*."""
        if not records:
            return

        batch_id = self.submit_batch(records)
        self.poll_until_complete(batch_id)
        results = self.retrieve_results(batch_id)

        id_to_record = {_custom_id(r): r for r in records}
        for cid, parsed in results.items():
            rec = id_to_record.get(cid)
            if rec:
                apply_api_result(rec, parsed)

    # ------------------------------------------------------------------
    # Synchronous path (real-time progress, no batch discount)
    # ------------------------------------------------------------------

    def classify_sync(self, records: list[PDFRecord]) -> None:
        """Classify each record one by one with a progress bar."""
        for rec in tqdm(records, desc="Classifying PDFs", unit="pdf"):
            try:
                response = self.client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS_CLASSIFY,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": build_user_message(rec)}],
                )
                raw = response.content[0].text
                parsed = parse_api_response(raw)
                apply_api_result(rec, parsed)
            except Exception as exc:
                logger.warning("API error for %s: %s", rec.filename, exc)
                rec.api_result = ClassificationResult.ERROR
                rec.error_message = str(exc)
