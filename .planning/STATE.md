# Project State: Cosmetic FTO Search Agent

**Core Value:** Quickly determine if a proposed cosmetic active/solution has freedom to operate in target markets

**Current Focus:** Phase 3 In Progress - USPTO Patent Search Backend

---

## Current Position

**Phase:** 3 of 8 (USPTO Patent Search)
**Plan:** 1 of 3 in phase (03-01 complete)
**Status:** In progress

```
[##########--------------------------------------------------------------] 30%
```

**Next Action:** Continue Phase 3 - Create USPTO search worker (03-02)

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Plans completed | 6 |
| Plans failed | 0 |
| Success rate | 100% |
| Total phases | 8 |
| Phases complete | 2 |

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
- [ ] Create USPTO search worker
- [ ] Integrate USPTO search with MainWindow
- [ ] Set up Python 3.12 virtual environment
- [ ] Install ReportLab, XlsxWriter
- [ ] Register for EPO OPS API access
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

## Phase 3 Progress

**Plan 03-01: USPTO Client and Keyword Extractor (COMPLETE)**
- httpx>=0.27 and pydantic>=2.0 dependencies added
- USPTOClient class with search_patents method
- Patent and PatentSearchResponse Pydantic models
- USPTOSearchError for error handling
- build_keyword_query for query construction
- extract_keywords and extract_search_terms utilities

**Key artifacts created:**
- `src/fto_agent/services/__init__.py` - Services package exports
- `src/fto_agent/services/uspto.py` - USPTO PatentsView API client
- `src/fto_agent/services/keyword_extractor.py` - Keyword extraction utilities

**Next:** Plan 03-02 - USPTO search worker integration

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
**Activity:** Execute plan 03-01 (USPTO client and keyword extractor)
**Outcome:** Plan complete, all verifications pass, 3 commits

### Handoff Notes

Phase 3 Plan 1 complete. Ready for Plan 03-02 (USPTO search worker).

Data flow established:
- InputPanel.get_data() provides problem, solution, constraints, smiles, countries
- extract_search_terms() converts to keyword list
- build_keyword_query() creates PatentsView query
- USPTOClient.search_patents() executes search
- PatentSearchResponse provides typed results

Next steps:
1. Create USPTO search worker using Worker pattern
2. Connect MainWindow submit to USPTO worker
3. Display results in UI

---
*State initialized: 2026-01-21*
*Last updated: 2026-01-22*
