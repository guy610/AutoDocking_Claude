---
phase: 03
plan: 01
subsystem: patent-search-services
tags:
  - httpx
  - pydantic
  - patentsview-api
  - keyword-extraction

dependency-graph:
  requires:
    - 01-01 (Worker pattern for future USPTO worker)
    - 02-02 (InputPanel provides data for search terms)
  provides:
    - USPTOClient for USPTO PatentsView API
    - Patent and PatentSearchResponse Pydantic models
    - build_keyword_query for query construction
    - extract_keywords and extract_search_terms utilities
  affects:
    - 03-02 (USPTO worker will use USPTOClient)
    - 03-03 (Results display will use PatentSearchResponse)
    - 04-xx (EPO client will follow similar patterns)

tech-stack:
  added:
    - httpx>=0.27
    - pydantic>=2.0
  patterns:
    - Context manager pattern for HTTP client lifecycle
    - Pydantic models for API response validation
    - Simple tokenization for keyword extraction
    - Stop word filtering for search term quality

key-files:
  created:
    - src/fto_agent/services/__init__.py
    - src/fto_agent/services/uspto.py
    - src/fto_agent/services/keyword_extractor.py
  modified:
    - pyproject.toml

decisions:
  - id: httpx-over-requests
    description: Used httpx instead of requests for HTTP client
    rationale: Better async support, type hints, connection pooling
  - id: pydantic-for-validation
    description: Used Pydantic models for API response parsing
    rationale: Automatic validation, clear error messages, extra="ignore" for API stability
  - id: simple-keyword-extraction
    description: Used simple tokenization instead of KeyBERT/YAKE
    rationale: No heavy NLP dependencies needed for v1; simple approach sufficient

metrics:
  duration: 10m
  completed: 2026-01-22
---

# Phase 3 Plan 1: USPTO Client and Keyword Extractor Summary

**One-liner:** USPTO PatentsView API client with httpx/pydantic and simple keyword extraction for search query construction.

## What Was Built

### 1. Dependencies (pyproject.toml)
Added httpx>=0.27 and pydantic>=2.0 to project dependencies.

### 2. USPTO Client Module (src/fto_agent/services/uspto.py)

**Classes:**
- `Patent`: Pydantic model for single patent with fields: patent_id, patent_title, patent_abstract, patent_date, patent_type
- `PatentSearchResponse`: Pydantic model for search results with patents list, count, total_hits
- `USPTOSearchError`: Custom exception with message and status_code
- `USPTOClient`: HTTP client for PatentsView API with:
  - BASE_URL = "https://search.patentsview.org/api/v1"
  - DEFAULT_FIELDS for common patent attributes
  - API key from parameter or PATENTSVIEW_API_KEY env var
  - `search_patents()` method with query, fields, size, sort parameters
  - Rate limit (429) handling with Retry-After header
  - Context manager support (__enter__, __exit__)

**Functions:**
- `build_keyword_query(keywords)`: Builds PatentsView query dict with _or operator searching patent_title and patent_abstract using _text_any

### 3. Keyword Extractor Module (src/fto_agent/services/keyword_extractor.py)

**Constants:**
- `STOP_WORDS`: Set of ~100 common English stop words

**Functions:**
- `extract_keywords(text, max_keywords=10)`: Tokenizes text, filters stop words, returns unique keywords preserving order
- `extract_search_terms(problem, solution, constraints=None, max_total=15)`: Combines keywords from solution (8 max), problem (6 max), constraints (4 max) with solution-first priority

### 4. Services Package (src/fto_agent/services/__init__.py)
Exports all public APIs from both modules.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| httpx over requests | Better async support, type hints, modern API |
| Pydantic for response parsing | Automatic validation, clear errors, handles optional fields |
| Simple tokenization for keywords | KeyBERT/YAKE add heavy dependencies; simple approach sufficient for v1 |
| Solution-first keyword priority | Active ingredient/solution is most relevant for patent search |
| extra="ignore" on Pydantic models | API may add fields; ignore unknown fields for stability |

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All verification commands passed:
- `python -c "from fto_agent.services import ..."` - All imports OK
- `extract_search_terms('improve skin health via collagen', 'GHK peptide')` - Returns ['ghk', 'peptide', 'improve', 'skin', 'health', 'via', 'collagen']
- `build_keyword_query(['peptide', 'collagen'])` - Returns correct PatentsView query structure
- `USPTOClient()` without API key - Raises USPTOSearchError with "API key" message

## Next Phase Readiness

**Ready for Phase 3 Plan 2:**
- USPTOClient ready to be used in Worker pattern
- Keyword extraction ready to process InputPanel data
- PatentSearchResponse ready for results display

**Remaining Phase 3 work:**
- Create USPTO search worker using Worker pattern
- Integrate with MainWindow submit action
- Create results display panel (or defer to Phase 5)

**Prerequisites for live testing:**
- PATENTSVIEW_API_KEY environment variable must be set
- API key obtained from: https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18
