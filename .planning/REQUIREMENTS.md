# Requirements: Cosmetic FTO Search Agent

**Defined:** 2026-01-20
**Core Value:** Quickly determine if a proposed cosmetic active/solution has freedom to operate in target markets

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Input & User Interface

- [ ] **INP-01**: User can describe cosmetic problem in natural language
- [ ] **INP-02**: User can describe proposed solution/active in natural language
- [ ] **INP-03**: User can specify constraints (cosmetic grade, leave-on, etc.) in natural language
- [ ] **INP-04**: User can paste chemical structure in SMILES notation (optional)
- [ ] **INP-05**: User can select target countries for FTO check (multi-select)

### Patent Search

- [ ] **SRCH-01**: System searches USPTO via PatentsView API
- [ ] **SRCH-02**: System searches EPO via OPS API
- [ ] **SRCH-03**: System performs keyword-based patent search
- [ ] **SRCH-04**: System performs CPC classification search (A61K 8/00, A61Q for cosmetics)
- [ ] **SRCH-05**: System filters results to active/enforced patents only (excludes expired)
- [ ] **SRCH-06**: System performs semantic/AI-powered concept search beyond keywords

### Analysis & Risk Assessment

- [ ] **ANLS-01**: System assigns risk indicator per patent (High/Medium/Low)
- [ ] **ANLS-02**: System provides per-country summary (Clear/Caution/Blocked)
- [ ] **ANLS-03**: System extracts and displays relevant claim text from patents
- [ ] **ANLS-04**: System maps claim elements to user's proposed solution
- [ ] **ANLS-05**: System provides confidence scores on AI assessments
- [ ] **ANLS-06**: System converts Markush structures from patent claims to SMILES for comparison

### Output & Reports

- [ ] **OUT-01**: System generates PDF summary report with per-country verdicts and key findings
- [ ] **OUT-02**: System generates Excel breakdown with patent numbers, titles, claims, risk ratings
- [ ] **OUT-03**: Reports include hyperlinks to original patent sources

### Application & Distribution

- [ ] **APP-01**: Application launches via clickable desktop executable (.exe)
- [ ] **APP-02**: Application displays progress indicators during search and analysis operations

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Input

- **INP-06**: Chemical structure drawing tool (draw instead of paste SMILES)
- **INP-07**: Saved search templates for common queries
- **INP-08**: Auto-suggest for CPC classifications

### Enhanced Search

- **SRCH-07**: WIPO PATENTSCOPE integration (paid API)
- **SRCH-08**: Chemical structure similarity search
- **SRCH-09**: Patent family aggregation to reduce duplicates
- **SRCH-10**: Google Patents fallback search

### Enhanced Output

- **OUT-04**: Embedded chemical structure images in reports
- **OUT-05**: Executive summary variant for non-technical stakeholders
- **OUT-06**: Export to PowerPoint format

### Enhanced Application

- **APP-03**: Legal disclaimers (not legal advice messaging)
- **APP-04**: Auto-update mechanism
- **APP-05**: Offline mode with cached data
- **APP-06**: Code signing certificate for Windows SmartScreen

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Legal advice/opinions | Tool provides information retrieval, not legal counsel — UPL risk |
| Expired patent searches | Separate IP search agent planned by user |
| Design-around suggestions | Legally sensitive, requires attorney input |
| Real-time monitoring alerts | v2+ feature, not core FTO workflow |
| Multi-user license management | Single-user tool for now |
| Non-patent literature search | Out of scope for FTO focus |

## Test Cases

Validation cases provided by user for testing the complete workflow.

### Case 1: GHK Peptide (Expected: Clear)

| Field | Value |
|-------|-------|
| **Problem** | Improve skin health (TWEL, flexibility) via collagen synthesis |
| **Proposed active** | GHK peptide (Gly-His-Lys) |
| **SMILES** | `NCC(=O)NC(Cc1cnc[nH]1)C(=O)NC(CCCCN)C(=O)O` |
| **Countries** | US, EU |
| **Expected result** | ✓ Clear — natural peptide, no active restricting patents |

### Case 2: Palmitoyl-GHK (Expected: Clear)

| Field | Value |
|-------|-------|
| **Problem** | Improve skin health (TWEL, flexibility) via collagen synthesis — GHK not permeable |
| **Proposed active** | Palmitoyl-GHK (Pal-GHK / Palmitoyl Tripeptide-1) |
| **SMILES** | `CCCCCCCCCCCCCCCC(=O)NCC(=O)NC(Cc1cnc[nH]1)C(=O)NC(CCCCN)C(=O)O` |
| **Countries** | US, EU |
| **Expected result** | ✓ Clear — no enforced patents on palmitoyl-modified peptides for cosmetic use |

### Case 3: Syn-Ake (Expected: Blocked)

| Field | Value |
|-------|-------|
| **Problem** | Reduce wrinkles in skin |
| **Proposed active** | Syn-Ake (dipeptide diaminobutyroyl benzylamide diacetate) |
| **Countries** | US, EU |
| **Expected result** | ✗ Blocked — patents WO2006047900 / US7964630B2 |
| **Known blocking patents** | WO2006047900, US7964630B2 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INP-01 | TBD | Pending |
| INP-02 | TBD | Pending |
| INP-03 | TBD | Pending |
| INP-04 | TBD | Pending |
| INP-05 | TBD | Pending |
| SRCH-01 | TBD | Pending |
| SRCH-02 | TBD | Pending |
| SRCH-03 | TBD | Pending |
| SRCH-04 | TBD | Pending |
| SRCH-05 | TBD | Pending |
| SRCH-06 | TBD | Pending |
| ANLS-01 | TBD | Pending |
| ANLS-02 | TBD | Pending |
| ANLS-03 | TBD | Pending |
| ANLS-04 | TBD | Pending |
| ANLS-05 | TBD | Pending |
| ANLS-06 | TBD | Pending |
| OUT-01 | TBD | Pending |
| OUT-02 | TBD | Pending |
| OUT-03 | TBD | Pending |
| APP-01 | TBD | Pending |
| APP-02 | TBD | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 0
- Unmapped: 22 ⚠️

---
*Requirements defined: 2026-01-20*
*Last updated: 2026-01-20 after initial definition*
