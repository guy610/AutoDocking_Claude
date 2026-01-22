---
phase: 04-epo-patent-search-and-filtering
plan: 01
subsystem: patent-search
tags: [epo, oauth, cql, legal-status, inpadoc, xml-parsing]

dependency-graph:
  requires: [phase-03-complete]
  provides: [epo-client, legal-status-parser, cosmetic-cpc-filtering]
  affects: [04-02-epo-worker, 04-03-integration]

tech-stack:
  added:
    - python-epo-ops-client@4.2.1
    - lxml@6.0.2
    - defusedxml@0.7.1
  patterns:
    - oauth-token-management
    - cql-query-building
    - xml-namespace-parsing
    - legal-status-analysis

key-files:
  created:
    - src/fto_agent/services/epo.py
    - src/fto_agent/services/legal_status.py
  modified:
    - pyproject.toml
    - src/fto_agent/services/__init__.py

decisions:
  - id: epo-ops-client-library
    choice: python-epo-ops-client
    why: Handles OAuth token refresh and API throttling automatically

metrics:
  duration: 6m
  completed: 2026-01-22
---

# Phase 4 Plan 1: EPO OPS Client and Legal Status Summary

**One-liner:** EPO OPS client with OAuth authentication, CQL cosmetic patent search (A61K8/A61Q), and INPADOC legal status parsing

## What Was Built

### EPOClient Class (`src/fto_agent/services/epo.py`)

Created EPO OPS API client following the USPTOClient pattern:

- **OAuth Authentication**: Uses `python-epo-ops-client` which handles token management and throttling automatically
- **CQL Query Building**: Builds CQL queries combining keywords with cosmetic CPC classifications (A61K8, A61Q)
- **XML Response Parsing**: Uses `lxml` with proper namespace handling to parse EPO OPS XML responses
- **Context Manager**: Supports `with` statement for clean resource management

Key exports:
- `EPOClient`: Main client class for EPO OPS API
- `EPOPatent`: Pydantic model for patent data (publication_number, title, abstract, applicants, cpc_classifications)
- `EPOSearchResponse`: Pydantic model for search results (patents, count, total_hits)
- `EPOSearchError`: Exception for API errors with optional status_code

### Legal Status Parser (`src/fto_agent/services/legal_status.py`)

Created INPADOC legal status parsing utilities:

- **PatentStatus Enum**: ACTIVE, EXPIRED, LAPSED, WITHDRAWN, PENDING, UNKNOWN
- **Keyword-Based Analysis**: Searches legal event text for indicators of inactive status (lapse, expired, withdrawn, etc.)
- **Conservative Filtering**: `is_patent_active()` returns True for ACTIVE, PENDING, and UNKNOWN (err on side of caution for FTO)

Key exports:
- `PatentStatus`: Enum for patent legal status
- `get_patent_status(legal_xml: bytes) -> PatentStatus`: Parse INPADOC XML to determine status
- `is_patent_active(status: PatentStatus) -> bool`: Check if patent should be included in FTO analysis
- `filter_active_patents(patents, get_legal_xml_func) -> list`: Utility for batch filtering

## Commits

| Hash | Type | Description |
|------|------|-------------|
| efd8949 | chore | Add EPO OPS client dependencies (python-epo-ops-client, lxml, defusedxml) |
| 5fc2faf | feat | Add EPO OPS client and legal status parser |

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| OAuth library | python-epo-ops-client | Handles token refresh and API throttling automatically |
| XML parsing | lxml with namespaces | Robust namespace handling required for EPO responses |
| Secure XML | defusedxml available | Prevents XXE attacks (imported for security) |
| CPC codes | A61K8, A61Q | Specific to cosmetics (not broader A61K which includes pharma) |
| Status caution | Include UNKNOWN as active | Err on side of caution for FTO analysis |

## Files Changed

**Created:**
- `src/fto_agent/services/epo.py` (295 lines) - EPOClient, EPOPatent, EPOSearchResponse, EPOSearchError
- `src/fto_agent/services/legal_status.py` (243 lines) - PatentStatus, get_patent_status, is_patent_active

**Modified:**
- `pyproject.toml` - Added 3 new dependencies
- `src/fto_agent/services/__init__.py` - Export EPO and legal status APIs

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All success criteria met:
- [x] python-epo-ops-client, lxml, defusedxml dependencies added and installed
- [x] EPOClient class with OAuth authentication
- [x] search_patents method builds CQL with cosmetic CPC codes
- [x] Legal status parsing extracts INPADOC events
- [x] All public APIs exported from services package
- [x] No runtime errors on import

Existing test suite: 81 tests passing (no regressions)

## Usage Example

```python
from fto_agent.services import EPOClient, PatentStatus, get_patent_status, is_patent_active

# Search for cosmetic patents
with EPOClient() as client:
    # CQL: ta="peptide collagen" AND (cpc=A61K8 OR cpc=A61Q)
    response = client.search_patents(["peptide", "collagen"])
    print(f"Found {response.total_hits} patents")

    for patent in response.patents:
        # Check legal status
        legal_xml = client.get_legal_status(patent.publication_number)
        status = get_patent_status(legal_xml)

        if is_patent_active(status):
            print(f"{patent.publication_number}: {patent.title}")
```

## Next Phase Readiness

Ready for Plan 04-02 (EPO Search Worker):
- EPOClient API mirrors USPTOClient pattern
- Can create `perform_epo_search` function following `perform_uspto_search` pattern
- Legal status filtering can be integrated for SRCH-05 requirement

**Environment variables needed before testing EPO search:**
- `EPO_OPS_CONSUMER_KEY` - From EPO developer portal
- `EPO_OPS_CONSUMER_SECRET` - From EPO developer portal
