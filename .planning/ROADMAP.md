# Roadmap: Cosmetic FTO Search Agent

**Created:** 2026-01-21
**Depth:** Comprehensive
**Phases:** 8
**Requirements:** 22 v1 requirements mapped

## Overview

This roadmap delivers a desktop FTO search agent for cosmetic chemists in 8 phases. The structure follows the natural dependency chain: foundation and async patterns first, then input collection, patent search across two jurisdictions (USPTO, EPO), AI-powered claim analysis, risk assessment synthesis, report generation, and finally executable packaging. Each phase delivers a verifiable capability that enables subsequent phases.

---

## Phase 1: Foundation and Async Infrastructure

**Goal:** Application shell with responsive async architecture that displays progress during long operations

**Dependencies:** None (starting point)

**Requirements:**
- APP-02: Application displays progress indicators during search and analysis operations

**Success Criteria:**
1. User can launch the application and see a responsive main window
2. User sees progress indicators when any operation exceeds 500ms
3. User can cancel long-running operations via a cancel button
4. Application remains responsive (no freezes) during background operations

**Rationale:** Progress indicators require async infrastructure (QThread, signals/slots). Building this foundation first prevents retrofitting later. Legal disclaimers also integrated at this stage per research recommendations.

**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md -- Project scaffold and worker infrastructure
- [x] 01-02-PLAN.md -- Progress widgets and main window integration
- [x] 01-03-PLAN.md -- Unit tests and human verification

---

## Phase 2: Input Collection UI

**Goal:** Users can describe their FTO query through a complete input panel

**Dependencies:** Phase 1 (application shell exists)

**Requirements:**
- INP-01: User can describe cosmetic problem in natural language
- INP-02: User can describe proposed solution/active in natural language
- INP-03: User can specify constraints (cosmetic grade, leave-on, etc.) in natural language
- INP-04: User can paste chemical structure in SMILES notation (optional)
- INP-05: User can select target countries for FTO check (multi-select)

**Success Criteria:**
1. User can enter problem description in a multi-line text field
2. User can enter solution/active description in a multi-line text field
3. User can enter constraints in a text field
4. User can paste SMILES notation and see validation feedback (valid/invalid)
5. User can select multiple target countries from a checkbox list (at minimum: US, EU, CN, JP)

**Rationale:** All input requirements are naturally grouped as they form the complete query interface. SMILES validation uses RDKit which must be integrated early.

---

## Phase 3: USPTO Patent Search

**Goal:** Users can search US patents via USPTO PatentsView API

**Dependencies:** Phase 2 (query inputs exist to drive search)

**Requirements:**
- SRCH-01: System searches USPTO via PatentsView API
- SRCH-03: System performs keyword-based patent search

**Success Criteria:**
1. User can initiate a patent search and see USPTO results returned
2. User sees patent results including title, patent number, and abstract
3. Search uses keywords derived from problem and solution descriptions
4. User can see result count and basic result list within 30 seconds for typical queries

**Rationale:** USPTO PatentsView is the most accessible API (free, no registration). Starting here validates the search architecture before adding EPO complexity.

---

## Phase 4: EPO Patent Search and Filtering

**Goal:** Users can search global patents via EPO OPS with classification and legal status filtering

**Dependencies:** Phase 3 (search architecture established)

**Requirements:**
- SRCH-02: System searches EPO via OPS API
- SRCH-04: System performs CPC classification search (A61K 8/00, A61Q for cosmetics)
- SRCH-05: System filters results to active/enforced patents only (excludes expired)

**Success Criteria:**
1. User can search EPO and see European/international patent results
2. User sees only active/enforced patents (expired patents filtered out)
3. Search includes cosmetic-relevant CPC classifications (A61K 8/00, A61Q) automatically
4. User can see combined results from both USPTO and EPO in unified view

**Rationale:** EPO OPS provides broader coverage (EP, WO, and national patents). CPC classification and legal status filtering require EPO's richer metadata. This phase completes the search foundation.

---

## Phase 5: AI Claim Extraction and Mapping

**Goal:** Users can see relevant claim text extracted and mapped to their proposed solution

**Dependencies:** Phase 4 (patent results with full text available)

**Requirements:**
- ANLS-03: System extracts and displays relevant claim text from patents
- ANLS-04: System maps claim elements to user's proposed solution

**Success Criteria:**
1. User can view relevant claim text for each patent result
2. User sees claim elements highlighted or listed separately
3. User sees visual mapping between claim elements and their proposed solution components
4. Claim extraction completes within 60 seconds for typical result sets (10-50 patents)

**Rationale:** Claim extraction and mapping are prerequisite to risk assessment. This phase establishes Claude API integration and prompt patterns for legal text analysis.

---

## Phase 6: Risk Assessment and Semantic Search

**Goal:** Users receive AI-powered risk ratings with confidence scores and per-country summaries

**Dependencies:** Phase 5 (claim analysis infrastructure exists)

**Requirements:**
- ANLS-01: System assigns risk indicator per patent (High/Medium/Low)
- ANLS-02: System provides per-country summary (Clear/Caution/Blocked)
- ANLS-05: System provides confidence scores on AI assessments
- ANLS-06: System converts Markush structures from patent claims to SMILES for comparison
- SRCH-06: System performs semantic/AI-powered concept search beyond keywords

**Success Criteria:**
1. User sees High/Medium/Low risk indicator for each patent
2. User sees Clear/Caution/Blocked summary for each target country
3. User sees confidence percentage (e.g., 85%) alongside each AI assessment
4. User sees Markush structures converted to SMILES where applicable
5. User can discover conceptually related patents even without exact keyword matches

**Rationale:** Risk assessment synthesizes all prior analysis into actionable output. Semantic search improves recall for patents using different terminology. Confidence scores address AI hallucination risk identified in research.

---

## Phase 7: Report Generation

**Goal:** Users can export professional PDF summary and detailed Excel breakdown

**Dependencies:** Phase 6 (complete analysis results to report)

**Requirements:**
- OUT-01: System generates PDF summary report with per-country verdicts and key findings
- OUT-02: System generates Excel breakdown with patent numbers, titles, claims, risk ratings
- OUT-03: Reports include hyperlinks to original patent sources

**Success Criteria:**
1. User can generate a PDF report with per-country Clear/Caution/Blocked verdicts
2. User can generate an Excel file with all patents, claims, and risk ratings
3. User can click hyperlinks in reports to open original patent pages in browser
4. Reports include legal disclaimers and timestamp of analysis
5. PDF is suitable for sharing with stakeholders (professional appearance)

**Rationale:** Reports are the deliverable output users share with management and legal counsel. Both formats serve different needs: PDF for executive summary, Excel for detailed review.

---

## Phase 8: Packaging and Distribution

**Goal:** Users can install and run the application via a clickable Windows executable

**Dependencies:** Phase 7 (complete application to package)

**Requirements:**
- APP-01: Application launches via clickable desktop executable (.exe)

**Success Criteria:**
1. User can download a single installer or executable package
2. User can double-click to launch without installing Python or dependencies
3. Application runs on a clean Windows 10/11 machine without errors
4. Windows SmartScreen does not block the application (code signing applied)

**Rationale:** Packaging is deferred until the application is feature-complete. PyInstaller with RDKit requires specific configuration that should only be done once.

---

## Progress

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 1 | Foundation and Async Infrastructure | APP-02 | Complete |
| 2 | Input Collection UI | INP-01, INP-02, INP-03, INP-04, INP-05 | Pending |
| 3 | USPTO Patent Search | SRCH-01, SRCH-03 | Pending |
| 4 | EPO Patent Search and Filtering | SRCH-02, SRCH-04, SRCH-05 | Pending |
| 5 | AI Claim Extraction and Mapping | ANLS-03, ANLS-04 | Pending |
| 6 | Risk Assessment and Semantic Search | ANLS-01, ANLS-02, ANLS-05, ANLS-06, SRCH-06 | Pending |
| 7 | Report Generation | OUT-01, OUT-02, OUT-03 | Pending |
| 8 | Packaging and Distribution | APP-01 | Pending |

**Coverage:** 22/22 v1 requirements mapped

---

## Dependency Graph

```
Phase 1 (Foundation)
    |
    v
Phase 2 (Input UI)
    |
    v
Phase 3 (USPTO Search)
    |
    v
Phase 4 (EPO Search + Filtering)
    |
    v
Phase 5 (Claim Analysis)
    |
    v
Phase 6 (Risk Assessment)
    |
    v
Phase 7 (Reports)
    |
    v
Phase 8 (Packaging)
```

All phases are sequential. Each depends on the prior phase completing.

---
*Roadmap created: 2026-01-21*
*Phase 1 complete: 2026-01-21*
