# Project Research Summary

**Project:** Cosmetic FTO Search Agent
**Domain:** Desktop patent freedom-to-operate search tool (Cosmetic Industry)
**Researched:** 2026-01-20
**Confidence:** HIGH

## Executive Summary

Building an FTO search agent for cosmetic chemists requires a pure Python desktop stack with PySide6 for GUI, RDKit for chemical structure processing, and official patent APIs (USPTO PatentsView, EPO OPS) for data access. The LLM (Claude) serves as an analysis engine for claim interpretation and risk scoring, but must never provide legal conclusions. This architecture was chosen because chemists already know Python, RDKit is the industry standard for cheminformatics, and official patent APIs avoid the legal risks of web scraping.

The critical success factor is positioning: this tool provides patent information retrieval and preliminary screening, NOT legal advice. Every output must include disclaimers, citations to source documents, and recommendations to consult patent counsel. AI hallucination rates in legal contexts run 17-58%, so all AI-generated analysis must be traceable to actual patent text. The tool helps chemists identify potentially relevant patents quickly; it does not replace attorney review.

Key risks include: (1) AI hallucinations leading to wrong business decisions, (2) unauthorized practice of law exposure if the tool provides definitive conclusions, (3) patent database access violations if scraping instead of using official APIs, and (4) desktop distribution failures if executables are unsigned. Mitigation requires building legal disclaimers into the architecture from day one, using only official APIs with rate limiting, and budgeting for code signing certificates.

## Key Findings

### Recommended Stack

Python 3.12 with PySide6 provides a professional desktop GUI that chemists can install and use without technical setup. RDKit handles all chemical structure operations (SMILES parsing, rendering, similarity search). Patent data comes from official APIs: USPTO PatentsView (free, generous rate limits), EPO OPS (free with registration), and Playwright for Google Patents only if absolutely necessary. Reports are generated with ReportLab (PDF) and XlsxWriter (Excel). The application is packaged as a Windows executable using PyInstaller.

**Core technologies:**
- **Python 3.12 + PySide6**: Desktop GUI framework -- LGPL licensed, professional appearance, QtAsyncio for responsive UI
- **RDKit 2025.09.4**: Chemical structure processing -- industry standard, SMILES parsing, 2D rendering, similarity search
- **USPTO PatentsView API**: US patent search -- free, 45 requests/minute, modern JSON API
- **EPO OPS + python-epo-ops-client**: Global patent search -- free tier with registration, 4GB/month
- **Claude API (Anthropic)**: Claim analysis -- best reasoning for legal text interpretation
- **ReportLab 4.4.9**: PDF generation -- precise control for professional FTO reports
- **XlsxWriter 3.2.9**: Excel generation -- fast write-only performance for patent data exports
- **PyInstaller 6.18.0**: Executable packaging -- mature, supports PySide6 + RDKit

### Expected Features

**Must have (table stakes):**
- Natural language problem/solution input -- chemists describe in plain language
- Target country selection -- FTO is jurisdiction-specific
- Multi-jurisdiction patent search (USPTO, EPO at minimum)
- Keyword + CPC classification search (A61K 8/00, A61Q)
- Legal status filtering -- only active patents matter
- Per-patent risk indicator (High/Medium/Low)
- Per-country risk summary (Clear/Caution/Blocked)
- PDF summary report -- executive summary for stakeholders
- Excel detailed export -- all patent data for review

**Should have (competitive, Phase 2+):**
- SMILES structure input with chemical structure search
- Semantic/conceptual search via AI
- Claim element mapping to proposed solution
- Patent family aggregation to reduce duplicate analysis
- Confidence levels on AI assessments

**Defer (v2+):**
- Chemical structure drawing tool
- Non-patent literature integration
- Design-around suggestions (legal sensitivity)
- Real-time monitoring alerts
- WIPO PATENTSCOPE API (paid)

### Architecture Approach

The application uses a layered architecture with MVVM for the GUI, an orchestration layer for workflow management, and separate services for search, analysis, and reporting. The LLM acts as an analysis engine only -- it interprets claims and assesses risk but never controls application flow. All external APIs are abstracted behind interfaces enabling parallel queries, isolated failure handling, and easy addition of new patent sources. Async patterns are used throughout to keep the GUI responsive during long patent searches and AI analysis calls.

**Major components:**
1. **Presentation Layer (PySide6 MVVM)** -- User input/output, progress display, results visualization
2. **Orchestration Layer** -- Workflow state machine (IDLE -> VALIDATING -> SEARCHING -> ANALYZING -> GENERATING -> COMPLETE)
3. **Search Service** -- Patent API adapters, query building, result parsing and deduplication
4. **Analysis Service** -- LLM client, claim parsing, risk assessment with confidence scores
5. **Chemistry Service** -- SMILES validation via RDKit, structure rendering, similarity search
6. **Report Service** -- PDF generation with ReportLab, Excel with XlsxWriter, templates

### Critical Pitfalls

1. **AI Hallucinations** -- LLMs hallucinate 17-58% on legal queries. Mitigation: Never present AI output as legal conclusion; require citations to actual patent text; include confidence scores; mandatory disclaimer on every screen.

2. **Unauthorized Practice of Law** -- Providing "opinions" or "advice" constitutes UPL. Mitigation: Frame outputs as "information for discussion with patent counsel"; avoid words like "safe," "recommend," "should"; require users acknowledge they have access to patent counsel.

3. **Patent Database Access Violations** -- Scraping violates ToS and risks IP blocks. Mitigation: Use only official APIs (USPTO, EPO OPS); implement robust rate limiting (20% below published limits); cache aggressively; never scrape Google Patents directly.

4. **Desktop Distribution Failures** -- Unsigned executables blocked by Windows SmartScreen; PyInstaller packaging is fragile. Mitigation: Budget for OV/EV code signing certificate ($200-500/year); use --onedir not --onefile; build on Windows for Windows; test on clean machines.

5. **GUI Freezes** -- Synchronous API calls freeze the UI for 30+ seconds. Mitigation: All network/AI calls in worker threads via QThread; progress indicators for any operation >500ms; cancel buttons for long operations.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation and Core Architecture
**Rationale:** Data models define contracts for all components; must establish legal disclaimer framework from day one; threading architecture must be designed early
**Delivers:** Domain models (Patent, Claim, RiskAssessment), PySide6 application shell with async infrastructure, legal disclaimer framework
**Addresses:** Input collection UI, basic application structure
**Avoids:** Deprecated framework pitfall, GUI freeze pitfall, UPL exposure pitfall
**Stack:** Python 3.12, PySide6, RDKit (for SMILES validation)

### Phase 2: Patent Database Integration
**Rationale:** Search functionality is core value; must validate API access and rate limiting before building analysis features
**Delivers:** Working patent search across USPTO and EPO, keyword + classification search, legal status filtering, basic results display
**Addresses:** Multi-jurisdiction search, legal status filtering, classification search
**Avoids:** ToS violations, wrong classification strategy, scope miscommunication
**Stack:** USPTO PatentsView API, python-epo-ops-client, aiohttp

### Phase 3: AI-Powered Claim Analysis
**Rationale:** LLM analysis is the differentiator but requires stable data models and search results to analyze
**Delivers:** Claim parsing, risk assessment with confidence scores, citation-backed analysis
**Addresses:** Per-patent risk rating, claim element mapping (basic), per-country summary
**Avoids:** Hallucination pitfall, claim interpretation overreach, UPL exposure
**Stack:** Claude API (Sonnet for volume, Opus for synthesis)

### Phase 4: Report Generation
**Rationale:** Reports are output-only and require complete analysis pipeline; safe to build last
**Delivers:** Professional PDF summary reports, detailed Excel exports, embedded chemical structures
**Addresses:** PDF summary report, Excel breakdown, hyperlinks to sources
**Avoids:** Memory issues on large reports, rendering problems
**Stack:** ReportLab, XlsxWriter

### Phase 5: Packaging and Distribution
**Rationale:** Must work on development machine before packaging for distribution; packaging has known issues with RDKit
**Delivers:** Signed Windows executable, installer, tested on clean machines
**Addresses:** Desktop installation, non-technical user deployment
**Avoids:** Unsigned exe blocking, packaging failures, antivirus false positives
**Stack:** PyInstaller, code signing certificate

### Phase Ordering Rationale

- **Foundation first:** Data models and async patterns must be established before building on top. Legal disclaimer framework is foundational to avoid retrofitting.
- **Search before analysis:** Cannot analyze patents that have not been retrieved. Search validates API integration patterns.
- **Analysis before reports:** Reports aggregate analysis results. Building reports early would mean rebuilding when analysis data structures change.
- **Distribution last:** Packaging is fragile and time-consuming. Only package once core functionality is stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Patent Search):** API-specific rate limits and quotas need validation; EPO OPS registration process needs walkthrough; Google Patents fallback strategy may need adjustment
- **Phase 3 (AI Analysis):** Prompt engineering for claim analysis is iterative; cost estimation needs real usage data

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** PySide6 MVVM is well-documented; async patterns are standard
- **Phase 4 (Reports):** ReportLab and XlsxWriter have excellent documentation
- **Phase 5 (Packaging):** PyInstaller documentation covers RDKit packaging

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All components verified via official PyPI, current versions confirmed |
| Features | HIGH | FTO workflow well-documented across multiple industry sources |
| Architecture | MEDIUM | Patterns verified but specific integration (QtAsyncio + RDKit + Claude) needs validation |
| Pitfalls | HIGH | Multiple authoritative sources including Stanford HAI research on AI hallucinations |

**Overall confidence:** HIGH

### Gaps to Address

- **WIPO PATENTSCOPE access:** Deferred due to cost (2,000-3,900 CHF/year) but may be needed for comprehensive global coverage -- revisit based on user feedback
- **Chinese/Japanese/Korean patent search:** EPO OPS provides coverage but translation quality unclear -- test during Phase 2
- **LLM cost estimation:** Depends on actual search volumes and claim complexity -- monitor during Phase 3 development
- **Espacenet registration:** Exact requirements and timeline need confirmation during Phase 2 setup
- **RDKit + PyInstaller spec file:** Hidden imports documented but specific spec file contents need testing during Phase 5

## Sources

### Primary (HIGH confidence)
- [RDKit Documentation](https://www.rdkit.org/docs/GettingStartedInPython.html) -- SMILES parsing, chemical informatics
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/) -- Qt for Python, LGPL licensing
- [PyInstaller Documentation](https://www.pyinstaller.org/) -- packaging patterns, common issues
- [USPTO PatentsView API](https://patentsview.org/apis/purpose) -- US patent search
- [EPO Open Patent Services](https://pypi.org/project/python-epo-ops-client/) -- python-epo-ops-client library
- [Stanford HAI: Hallucinating Law](https://hai.stanford.edu/news/hallucinating-law-legal-mistakes-large-language-models-are-pervasive) -- AI hallucination rates 17-58%

### Secondary (MEDIUM confidence)
- [IPRally FTO Search](https://www.iprally.com/use-cases/freedom-to-operate) -- FTO workflow expectations
- [PatSnap FTO Guide](https://www.patsnap.com/resources/blog/articles/freedom-to-operate-fto-analysis-guide-2025/) -- industry practices
- [PythonGUIs Framework Comparison](https://www.pythonguis.com/faq/which-python-gui-library/) -- GUI framework selection
- [Playwright vs Selenium Comparison](https://www.browserless.io/blog/playwright-vs-selenium-2025-browser-automation-comparison) -- web automation selection

### Tertiary (LOW confidence)
- LLM cost estimates (~$1-5/search) -- depends on actual usage patterns
- Specific API rate limits -- check official docs before implementation
- Espacenet registration timeline -- verify current process

---
*Research completed: 2026-01-20*
*Ready for roadmap: yes*
