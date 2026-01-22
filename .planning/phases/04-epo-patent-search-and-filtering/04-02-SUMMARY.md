---
phase: 04-epo-patent-search-and-filtering
plan: 02
subsystem: patent-search
tags: [epo, worker, unified-model, legal-status-filtering, progress-reporting]

dependency-graph:
  requires: [04-01-complete]
  provides: [epo-search-worker, unified-patent-model]
  affects: [04-03-tests, 05-mainwindow-integration]

tech-stack:
  added: []
  patterns:
    - worker-pattern-for-epo
    - unified-model-conversion
    - legal-status-filtering

key-files:
  created:
    - src/fto_agent/services/models.py
    - src/fto_agent/workers/epo_worker.py
  modified:
    - src/fto_agent/services/__init__.py
    - src/fto_agent/workers/__init__.py

decisions:
  - id: unified-patent-model
    choice: UnifiedPatent with from_uspto and from_epo converters
    why: Normalizes multi-source patents for unified display in results panel

  - id: epo-worker-progress-steps
    choice: 5 steps (extract, query, search, filter, complete)
    why: Granular progress feedback; filtering step only shown when filter_active_only=True

  - id: legal-status-per-patent
    choice: Query INPADOC per patent during filtering step
    why: Required for accurate active-only filtering; warn on >50 patents

metrics:
  duration: 5m
  completed: 2026-01-22
---

# Phase 4 Plan 2: EPO Search Worker and Unified Model Summary

**One-liner:** Unified patent model with source converters, EPO search worker with 5-step progress and legal status filtering

## What Was Built

### UnifiedPatent Model (`src/fto_agent/services/models.py`)

Created unified patent representation for multi-source display:

- **PatentSource Enum**: USPTO and EPO values for source tracking
- **UnifiedPatent Pydantic Model**: Normalized fields (id, title, abstract, date, source, url, status, cpc_codes)
- **from_uspto Converter**: Converts USPTO Patent to UnifiedPatent with Google Patents URL
- **from_epo Converter**: Converts EPOPatent to UnifiedPatent with Espacenet URL

Key exports:
- `PatentSource`: Enum for USPTO/EPO source identification
- `UnifiedPatent`: Model with `from_uspto()` and `from_epo()` class methods

### EPO Search Worker (`src/fto_agent/workers/epo_worker.py`)

Created EPO search worker following USPTO worker pattern:

- **5-Step Progress Reporting**:
  1. "Extracting keywords..." (20%)
  2. "Building EPO query..." (40%)
  3. "Searching EPO patents..." (60%)
  4. "Filtering active patents..." (80%) - only when filter_active_only=True
  5. "Search complete" (100%)

- **Legal Status Filtering**: Queries INPADOC for each patent and filters to active-only
- **Cooperative Cancellation**: Checks `is_cancelled()` between each step
- **Warning on Large Sets**: Logs warning when filtering >50 patents

Key exports:
- `perform_epo_search`: Main worker function with filter_active_only parameter
- `create_epo_search_worker`: Factory function for InputPanel data

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 06d6679 | feat | Add unified patent model for multi-source display |
| 2e0fdbf | feat | Add EPO search worker with legal status filtering |

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Unified model | Pydantic with converters | Type-safe conversion, validates at creation time |
| URL patterns | Google Patents (USPTO), Espacenet (EPO) | Official/authoritative sources for each region |
| Filtering approach | Per-patent INPADOC query | Required for accurate status; warn on performance |
| Progress steps | 5 steps with filter | Consistent granularity with USPTO's 4 steps plus filtering |

## Files Changed

**Created:**
- `src/fto_agent/services/models.py` (141 lines) - PatentSource, UnifiedPatent with converters
- `src/fto_agent/workers/epo_worker.py` (200 lines) - perform_epo_search, create_epo_search_worker

**Modified:**
- `src/fto_agent/services/__init__.py` - Export PatentSource, UnifiedPatent
- `src/fto_agent/workers/__init__.py` - Export perform_epo_search, create_epo_search_worker

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All success criteria met:
- [x] UnifiedPatent model with from_uspto and from_epo class methods
- [x] PatentSource enum with USPTO and EPO values
- [x] EPO worker with 5-step progress reporting
- [x] Legal status filtering removes expired/lapsed/withdrawn patents
- [x] Cancellation returns empty response (no errors)
- [x] All public APIs exported from packages

Existing test suite: 81 tests passing (no regressions)

## Usage Example

```python
from fto_agent.services import Patent, EPOPatent, UnifiedPatent, PatentSource

# Convert USPTO patent to unified
uspto = Patent(patent_id="12345678", patent_title="Test Patent")
unified = UnifiedPatent.from_uspto(uspto)
print(unified.id)      # "US12345678"
print(unified.url)     # "https://patents.google.com/patent/US12345678"
print(unified.source)  # PatentSource.USPTO

# Convert EPO patent to unified with status
from fto_agent.services import PatentStatus
epo = EPOPatent(publication_number="EP1000000A1", title="EPO Patent")
unified = UnifiedPatent.from_epo(epo, status=PatentStatus.ACTIVE)
print(unified.url)     # "https://worldwide.espacenet.com/patent/search?q=pn%3DEP1000000A1"

# Create EPO search worker
from fto_agent.workers import create_epo_search_worker
data = {"problem": "skin aging", "solution": "GHK peptide", "constraints": ""}
worker = create_epo_search_worker(data, consumer_key, consumer_secret)
worker.signals.result.connect(on_complete)
QThreadPool.globalInstance().start(worker)
```

## Next Phase Readiness

Ready for Plan 04-03 (Unit Tests and Verification):
- UnifiedPatent can be tested for conversion accuracy
- EPO worker can be tested with mocked EPOClient
- Legal status filtering can be tested with mock INPADOC responses

**For MainWindow integration (Phase 5):**
- ResultsPanel can display UnifiedPatent from either source
- MainWindow can run parallel USPTO + EPO workers when both US and EU selected
