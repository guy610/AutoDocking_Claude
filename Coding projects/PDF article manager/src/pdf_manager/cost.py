"""Cost estimation for Claude API classification calls."""

from __future__ import annotations

from .models import PDFRecord

# Haiku 4.5 Batch API pricing (per million tokens)
HAIKU_BATCH_INPUT_PER_MTOK = 0.50
HAIKU_BATCH_OUTPUT_PER_MTOK = 2.50

# Haiku 4.5 standard (non-batch) pricing
HAIKU_STD_INPUT_PER_MTOK = 1.00
HAIKU_STD_OUTPUT_PER_MTOK = 5.00

CHARS_PER_TOKEN = 4.0
SYSTEM_PROMPT_CHARS = 700  # approximate size of classification prompt
OUTPUT_TOKENS_PER_REQUEST = 30  # short JSON response


def estimate_cost(
    records: list[PDFRecord],
    use_batch: bool = True,
) -> dict:
    """Estimate the API cost for classifying *records*.

    Returns a dict with token counts and USD estimates.
    """
    input_price = HAIKU_BATCH_INPUT_PER_MTOK if use_batch else HAIKU_STD_INPUT_PER_MTOK
    output_price = HAIKU_BATCH_OUTPUT_PER_MTOK if use_batch else HAIKU_STD_OUTPUT_PER_MTOK

    total_input_chars = 0
    for rec in records:
        text_len = len(rec.extracted_text_preview or "")
        total_input_chars += SYSTEM_PROMPT_CHARS + len(rec.filename) + text_len

    total_input_tokens = int(total_input_chars / CHARS_PER_TOKEN)
    total_output_tokens = len(records) * OUTPUT_TOKENS_PER_REQUEST

    input_cost = (total_input_tokens / 1_000_000) * input_price
    output_cost = (total_output_tokens / 1_000_000) * output_price

    return {
        "num_pdfs": len(records),
        "est_input_tokens": total_input_tokens,
        "est_output_tokens": total_output_tokens,
        "input_cost_usd": round(input_cost, 4),
        "output_cost_usd": round(output_cost, 4),
        "total_cost_usd": round(input_cost + output_cost, 4),
        "batch_mode": use_batch,
    }
