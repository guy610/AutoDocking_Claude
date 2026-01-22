# Project State: Cosmetic FTO Search Agent

**Core Value:** Quickly determine if a proposed cosmetic active/solution has freedom to operate in target markets

**Current Focus:** Phase 4 - EPO Patent Search and Filtering (Plan 1 of 3 complete)

---

## Current Position

**Phase:** 4 of 8 (EPO Patent Search and Filtering)
**Plan:** 1 of 3 in phase (04-01 complete)
**Status:** In progress

```
[########################------------------------------------------------] 45%
```

**Next Action:** Plan 04-02 - EPO Search Worker and Integration

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 9 |
| Plans failed | 0 |
| Success rate | 100% |
| Total phases | 8 |
| Phases complete | 3 |

---

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase |
|----------|-----------|-------|
| PySide6 for GUI | LGPL license, professional appearance, QtAsyncio for responsive UI | Research |
| USPTO + EPO only (v1) | Free APIs, no subscription cost, covers US and EU markets | Research |
| Claude for claim analysis | Best reasoning for legal text interpretation | Research |
| 8-phase structure | Comprehensive depth, natural delivery boundaries | Roadmap |
| Hatchling build backend | Modern, PEP 517 compliant, supports src-layout natively | 01-01 |
| Worker passes callbacks | Target functions receive is_cancelled and progress_callback kwargs | 01-01 |
| Cooperative cancellation | Never QThread.terminate(); workers check is_cancelled() flag | 01-01 |
| 500ms QTimer delay | Prevents progress bar flickering for fast operations | 01-02 |
| Status bar permanent widgets | Progress bar and cancel button in status bar right side | 01-02 |
| pytest with pytest-qt | Standard Python testing with Qt-specific fixtures | 01-03 |
| Synchronous worker testing | Call worker.run() directly for deterministic unit tests | 01-03 |
| RDKit for SMILES validation | Industry standard cheminformatics library | 02-01 |
| Empty SMILES valid | SMILES field is optional; empty should not block submission | 02-01 |
| Real-time SMILES validation | RDKit is fast; immediate feedback improves UX | 02-01 |
| Validation stylesheet in app | Centralized styling ensures consistent validation feedback | 02-02 |
| httpx over requests | Better async support, type hints, modern API | 03-01 |
| Pydantic for API validation | Automatic validation, clear errors, handles optional fields | 03-01 |
| Simple keyword extraction | KeyBERT/YAKE add heavy dependencies; simple approach sufficient for v1 | 03-01 |
| 4-step progress reporting | Granular feedback for keyword extraction, query building, search, completion | 03-02 |
| Empty response on cancel | Consistent return type, UI can handle gracefully | 03-02 |
| Abstract tooltip truncation | 300 char limit prevents tooltip overflow while showing context | 03-02 |
| QSplitter for panel layout | Allows user to resize InputPanel/ResultsPanel; 50/50 default | 03-03 |
| Env var check before search | Fail fast with clear message rather than after worker starts | 03-03 |
| Country validation for API | USPTO API only returns US patents; prevents confusing empty results | 03-03 |
| python-epo-ops-client | Handles OAuth token refresh and API throttling automatically | 04-01 |
| Conservative legal status | Include UNKNOWN as active to err on side of caution for FTO | 04-01 |
| A61K8/A61Q CPC codes | Specific cosmetics codes, not broader A61K which includes pharma | 04-01 |

### Technical Todos

- [x] Set up Python package structure with PySide6 dependency
- [x] Implement Worker/WorkerSignals pattern for background operations
- [x] Implement ProgressManager with 500ms delayed display
- [x] Create MainWindow with async operation support
- [x] Create unit tests for Worker pattern
- [x] Install RDKit for SMILES validation
- [x] Create InputPanel widget with form validation
- [x] Integrate InputPanel into MainWindow
- [x] Create unit tests for SMILES validator and InputPanel
- [x] Add httpx and pydantic dependencies
- [x] Create USPTOClient for PatentsView API
- [x] Create keyword extractor for search terms
- [x] Create USPTO search worker
- [x] Create ResultsPanel widget
- [x] Integrate USPTO search with MainWindow
- [x] Create unit tests for Phase 3 services and worker
- [x] Add python-epo-ops-client, lxml, defusedxml dependencies
- [x] Create EPOClient for EPO OPS API
- [x] Create legal status parser for INPADOC data
- [ ] Create EPO search worker
- [ ] Integrate EPO search with MainWindow
- [ ] Create unit tests for Phase 4 services and worker
- [ ] Register for EPO OPS API access (get consumer key/secret)
- [ ] Set up Anthropic API key for Claude
- [ ] Budget for code signing certificate ($200-500/year)
- [ ] Obtain PatentsView API key

### Blockers

None currently.

### Warnings

- AI hallucination rates 17-58% on legal queries -- always show confidence scores and citations
- Unsigned executables blocked by Windows SmartScreen -- code signing required for Phase 8
- EPO OPS registration may take time -- start early in Phase 4
- PatentsView API key required for USPTO search -- request from PatentsView support portal

---

## Phase 4 Summary (IN PROGRESS)

Phase 4 adds EPO OPS API support for European patent search.

**Plan 04-01: EPO OPS Client and Legal Status Parser (COMPLETE)**
- python-epo-ops-client, lxml, defusedxml dependencies added
- EPOClient class with OAuth authentication
- CQL query building with cosmetic CPC codes (A61K8, A61Q)
- EPOPatent and EPOSearchResponse Pydantic models
- PatentStatus enum and legal status parsing from INPADOC
- is_patent_active helper for FTO analysis filtering

**Plan 04-02: EPO Search Worker and Integration (PENDING)**
- Create perform_epo_search function following USPTO worker pattern
- Integrate EPO search when EU selected in countries
- Handle parallel USPTO + EPO searches

**Plan 04-03: Unit Tests and Verification (PENDING)**
- Unit tests for EPO client and worker
- Integration tests for multi-source search

**Key artifacts created in 04-01:**
- `src/fto_agent/services/epo.py` - EPO OPS API client
- `src/fto_agent/services/legal_status.py` - INPADOC legal status parser

**Requirements in progress:**
- SRCH-02: EPO OPS search for EP/WO patents
- SRCH-04: CPC classification filtering (A61K8, A61Q for cosmetics)
- SRCH-05: Legal status filtering (active patents only)

---

## Phase 3 Summary (COMPLETE)

Phase 3 delivered complete USPTO patent search functionality:

**Plan 03-01: USPTO Client and Keyword Extractor**
- httpx>=0.27 and pydantic>=2.0 dependencies added
- USPTOClient class with search_patents method
- Patent and PatentSearchResponse Pydantic models
- build_keyword_query for query construction
- extract_keywords and extract_search_terms utilities

**Plan 03-02: USPTO Search Worker and Results Panel**
- perform_uspto_search function with 4-step progress
- create_uspto_search_worker factory for InputPanel data
- ResultsPanel widget with patentSelected signal
- Color-coded status feedback (green/blue/red)

**Plan 03-03: MainWindow Integration and Unit Tests**
- QSplitter layout with InputPanel (left) and ResultsPanel (right)
- Complete search flow wired from submit to results display
- API key and country validation before search starts
- 40 new unit tests (81 total in suite)
- Human verification passed for all features

**Key artifacts:**
- `src/fto_agent/services/__init__.py` - Services package exports
- `src/fto_agent/services/uspto.py` - USPTO PatentsView API client
- `src/fto_agent/services/keyword_extractor.py` - Keyword extraction utilities
- `src/fto_agent/workers/uspto_worker.py` - USPTO search worker
- `src/fto_agent/widgets/results_panel.py` - Results display panel
- `tests/test_keyword_extractor.py` - Keyword extractor tests
- `tests/test_uspto_client.py` - USPTO client tests
- `tests/test_uspto_worker.py` - USPTO worker tests

**Requirements satisfied:**
- SRCH-01: Async patent search (USPTO)
- SRCH-03: Progress bar with cancel capability

---

## Phase 2 Summary (COMPLETE)

Phase 2 delivered the complete input collection UI for FTO queries:

**Plan 02-01:**
- SMILES validator with RDKit integration
- InputPanel widget with 5 input sections
- Form validation for problem, solution, countries required
- Real-time SMILES validation feedback

**Plan 02-02:**
- MainWindow integration with InputPanel
- VALIDATION_STYLESHEET for visual feedback
- 33 unit tests (12 SMILES validator, 21 InputPanel)
- Human verification of UI functionality

**Key artifacts:**
- `src/fto_agent/validators/smiles.py` - SMILES validation
- `src/fto_agent/widgets/input_panel.py` - InputPanel widget
- `src/fto_agent/main_window.py` - MainWindow with InputPanel
- `src/fto_agent/app.py` - App factory with validation stylesheet
- `tests/test_smiles_validator.py` - SMILES validation tests
- `tests/test_input_panel.py` - InputPanel widget tests

**Requirements satisfied:**
- INP-01: Problem description field
- INP-02: Solution/active field
- INP-03: Constraints field
- INP-04: SMILES with real-time validation
- INP-05: Country multi-select (US, EU, CN, JP)

---

## Session Continuity

### Last Session

**Date:** 2026-01-22
**Activity:** Complete plan 04-01 (EPO OPS Client and Legal Status Parser)
**Outcome:** Plan complete, all verifications passed

### Handoff Notes

Plan 04-01 complete. Ready for Plan 04-02 (EPO Search Worker and Integration).

Current application state:
- User can enter FTO query in InputPanel
- Click Submit triggers USPTO search (if US selected, API key set)
- Progress bar and cancel button appear during search
- Results display in ResultsPanel with patent titles
- Status bar shows patent count or error message
- 81 unit tests passing

EPO client ready for integration:
- EPOClient class mirrors USPTOClient pattern
- CQL query building includes cosmetic CPC codes
- Legal status parsing ready for active patent filtering

Next steps for 04-02:
1. Create perform_epo_search function (follow USPTO worker pattern)
2. Create create_epo_search_worker factory
3. Integrate EPO search when EU selected
4. Handle parallel USPTO + EPO searches

**Environment variables needed for EPO testing:**
- `EPO_OPS_CONSUMER_KEY` - From https://developers.epo.org
- `EPO_OPS_CONSUMER_SECRET` - From https://developers.epo.org

---
*State initialized: 2026-01-21*
*Last updated: 2026-01-22*
