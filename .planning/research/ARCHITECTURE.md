# Architecture Patterns: Cosmetic FTO Search Agent

**Domain:** Desktop patent FTO search application with LLM-powered analysis
**Researched:** 2026-01-20
**Confidence:** MEDIUM (Architecture patterns verified via multiple sources; specific implementation details need validation during development)

---

## Recommended Architecture

### High-Level Overview

The application follows a **layered architecture with service separation**, combining the MVVM pattern for GUI management with an async service layer for backend operations. The LLM acts as an intelligent analysis engine, not as a controller.

```
+------------------------------------------------------------------+
|                          PRESENTATION LAYER                       |
|  +------------------------------------------------------------+  |
|  |                    PySide6 GUI (MVVM)                       |  |
|  |  +------------------+  +------------------+  +------------+ |  |
|  |  | Question Panel   |  | Results Display  |  | Status Bar | |  |
|  |  | (ViewModel)      |  | (ViewModel)      |  |            | |  |
|  |  +------------------+  +------------------+  +------------+ |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
                              |
                              | Qt Signals / async Queue
                              v
+------------------------------------------------------------------+
|                        ORCHESTRATION LAYER                        |
|  +------------------------------------------------------------+  |
|  |                   SearchOrchestrator                        |  |
|  |  - Coordinates search workflow                              |  |
|  |  - Manages state transitions                                |  |
|  |  - Aggregates results from services                         |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
+------------------+  +------------------+  +------------------+
|  SEARCH SERVICE  |  | ANALYSIS SERVICE |  | REPORT SERVICE   |
|                  |  |                  |  |                  |
| - Patent APIs    |  | - LLM Client     |  | - PDF Generator  |
| - Query Builder  |  | - Claim Parser   |  | - Excel Writer   |
| - Result Parser  |  | - Risk Assessor  |  | - Template Mgr   |
+------------------+  +------------------+  +------------------+
          |                   |                   |
          v                   v                   v
+------------------------------------------------------------------+
|                          DATA LAYER                               |
|  +------------------------------------------------------------+  |
|  |                   Domain Models                             |  |
|  |  Patent | Claim | ChemicalStructure | RiskAssessment | Report |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
          |
          v
+------------------------------------------------------------------+
|                       INFRASTRUCTURE                              |
|  +------------------+  +------------------+  +------------------+ |
|  | Patent DB APIs   |  | Anthropic API    |  | File System      | |
|  | - USPTO          |  | (Claude)         |  | - Output files   | |
|  | - Espacenet      |  |                  |  | - Cache          | |
|  | - Google Patents |  |                  |  |                  | |
|  +------------------+  +------------------+  +------------------+ |
+------------------------------------------------------------------+
```

---

## Component Boundaries

### Layer Responsibilities

| Layer | Responsibility | What It Does NOT Do |
|-------|----------------|---------------------|
| **Presentation** | User input/output, display state | Business logic, API calls, file I/O |
| **Orchestration** | Workflow coordination, state management | Direct API calls, UI updates |
| **Services** | Business logic, external integrations | State persistence, UI concerns |
| **Data** | Domain models, data validation | Network calls, persistence |
| **Infrastructure** | External system communication | Business decisions |

### Component Details

#### 1. GUI Layer (Presentation)

**Pattern:** MVVM (Model-View-ViewModel)
**Technology:** PySide6 (recommended over PyQt6 for LGPL licensing)
**Rationale:** Clear separation enables testing ViewModels without GUI, async-friendly with QtAsyncio

```
GUI/
  views/
    main_window.py        # Main application window
    question_panel.py     # Input form for FTO query
    results_panel.py      # Patent results display
    risk_dashboard.py     # Risk assessment visualization

  viewmodels/
    question_vm.py        # Manages question form state
    search_vm.py          # Manages search progress/results
    analysis_vm.py        # Manages risk analysis state

  widgets/
    smiles_input.py       # Chemical structure input with preview
    country_selector.py   # Multi-country selection
    progress_indicator.py # Search progress display
```

**Key Interfaces:**
- ViewModels expose `pyqtSignal` for state changes
- Views bind to ViewModel signals
- ViewModels call Orchestrator methods (async)

#### 2. Orchestration Layer

**Pattern:** Coordinator/Mediator
**Responsibility:** Workflow management, service coordination

```
orchestration/
  search_orchestrator.py  # Main workflow controller
  workflow_state.py       # State machine for search workflow
  result_aggregator.py    # Combines results from multiple sources
```

**Search Workflow States:**
```
IDLE --> VALIDATING --> SEARCHING --> PARSING --> ANALYZING --> GENERATING --> COMPLETE
   \                       |             |           |             |
    `----------------------+-------------+-----------+-------------+--> ERROR
```

**Key Responsibilities:**
- Validate input (SMILES structure, country codes)
- Coordinate parallel patent database queries
- Aggregate and deduplicate results
- Sequence analysis steps
- Trigger report generation

#### 3. Search Service

**Responsibility:** Patent database querying and result parsing

```
services/search/
  patent_search_service.py    # Main search interface

  adapters/
    uspto_adapter.py          # USPTO PatentsView API
    espacenet_adapter.py      # EPO Open Patent Services
    google_patents_adapter.py # Google Patents (via SerpAPI)

  query/
    query_builder.py          # Constructs search queries
    keyword_extractor.py      # Extracts searchable terms

  parsers/
    patent_parser.py          # Normalizes patent data
    claim_extractor.py        # Extracts claims from full text
```

**Data Sources (in priority order):**

| Source | API | Coverage | Rate Limits | Notes |
|--------|-----|----------|-------------|-------|
| USPTO PatentsView | REST JSON | US only | Generous | Best for US FTO |
| EPO Open Patent Services | REST XML | Global | 4GB/month free | Requires registration |
| Google Patents | SerpAPI | Global | Paid tier | Fallback for coverage |

**Key Design Decision:** Abstract each patent source behind a common interface (`PatentSearchAdapter`) to enable:
- Parallel querying
- Source-specific retry logic
- Easy addition of new sources

#### 4. Chemical Structure Service

**Responsibility:** SMILES parsing, structure validation, similarity search

```
services/chemistry/
  structure_service.py     # Main interface
  smiles_parser.py         # SMILES validation and canonicalization
  structure_renderer.py    # 2D structure image generation
  similarity_search.py     # Structure-based patent search
```

**Technology:** RDKit (industry standard, well-documented)

**Key Functions:**
- `validate_smiles(smiles: str) -> bool` - Check SMILES validity
- `canonicalize(smiles: str) -> str` - Normalize SMILES representation
- `render_2d(smiles: str) -> bytes` - Generate PNG for display
- `get_fingerprint(smiles: str) -> BitVector` - For similarity matching

**Source:** [RDKit Documentation](https://www.rdkit.org/docs/GettingStartedInPython.html) - Verified HIGH confidence

#### 5. Analysis Service (LLM-Powered)

**Responsibility:** Claim interpretation, risk assessment, FTO opinion generation

```
services/analysis/
  analysis_service.py      # Main interface
  llm_client.py           # Anthropic API wrapper
  claim_analyzer.py       # Claim parsing and interpretation
  risk_assessor.py        # Risk scoring and rationale

  prompts/
    claim_interpretation.py   # Prompt templates for claim analysis
    risk_assessment.py        # Prompt templates for risk scoring
    fto_summary.py           # Prompt templates for opinion generation
```

**LLM Integration Pattern:**

```python
# Simplified flow
class AnalysisService:
    async def analyze_patent(self, patent: Patent, product: ProductDescription) -> Analysis:
        # 1. Parse claims into structured form
        claims = await self.claim_analyzer.parse_claims(patent.claims)

        # 2. For each claim, assess relevance to product
        claim_analyses = []
        for claim in claims:
            analysis = await self.llm_client.analyze(
                prompt=ClaimInterpretationPrompt(claim, product),
                model="claude-sonnet-4-20250514"  # Balance of speed/quality
            )
            claim_analyses.append(analysis)

        # 3. Aggregate into overall risk assessment
        risk = await self.risk_assessor.assess(claim_analyses, product)

        return Analysis(claims=claim_analyses, risk=risk)
```

**Risk Categories:**
- **HIGH:** Claims appear to read on product; infringement likely
- **MEDIUM:** Claims may read on product; further review recommended
- **LOW:** Claims unlikely to cover product; minimal risk
- **NONE:** Patent clearly does not apply

**Key Design Decisions:**
1. Use Claude Sonnet for claim analysis (good balance of speed/cost/quality)
2. Use Claude Opus for complex risk synthesis (highest reasoning capability)
3. Include confidence scores with all assessments
4. Cache analysis results keyed by patent ID + product hash
5. Always include disclaimer that this is not legal advice

**Source:** [Anthropic API Documentation](https://github.com/anthropics/anthropic-sdk-python) - HIGH confidence

#### 6. Report Service

**Responsibility:** PDF and Excel report generation

```
services/report/
  report_service.py        # Main interface
  pdf_generator.py         # PDF report creation
  excel_generator.py       # Excel breakdown creation
  template_manager.py      # Report templates

  templates/
    fto_summary.html       # Jinja2 template for PDF
    patent_details.html    # Patent detail section
    risk_matrix.html       # Risk visualization
```

**PDF Generation:** WeasyPrint (HTML/CSS to PDF)
- **Rationale:** Easier to design with HTML/CSS than ReportLab's programmatic API
- **Trade-off:** Slightly less control than ReportLab, but faster development

**Excel Generation:** XlsxWriter via Pandas
- **Rationale:** Pandas integration for data export, XlsxWriter for formatting
- **Output:** Detailed patent list, claim analysis, risk breakdown

**Report Structure:**

```
FTO_Report_[Product]_[Date].pdf
  1. Executive Summary
     - Product description
     - Key findings (HIGH/MEDIUM/LOW risk counts)
     - Recommended actions

  2. Methodology
     - Databases searched
     - Search queries used
     - Analysis approach

  3. Patent Analysis
     - For each relevant patent:
       - Patent details
       - Relevant claims
       - Interpretation
       - Risk assessment

  4. Risk Matrix
     - Visual risk summary
     - By country
     - By claim type

  5. Appendix
     - Full search results
     - Disclaimers

FTO_Details_[Product]_[Date].xlsx
  Sheet 1: Summary
  Sheet 2: Patent List
  Sheet 3: Claim Analysis
  Sheet 4: Risk Breakdown
```

**Sources:**
- [WeasyPrint](https://weasyprint.org/) - MEDIUM confidence
- [XlsxWriter + Pandas](https://xlsxwriter.readthedocs.io/working_with_pandas.html) - HIGH confidence

---

## Data Flow

### Complete Search Flow

```
User Input                          System Processing                        Output
-----------                         -----------------                        ------

1. Question Panel
   - Problem statement    -------> 2. Input Validation
   - Proposed solution              - SMILES validation (RDKit)
   - SMILES structure               - Country code validation
   - Target countries               - Required fields check
   - Constraints                            |
                                           v
                                    3. Query Construction
                                       - Extract keywords from problem/solution
                                       - Build patent-specific queries
                                       - Prepare structure search queries
                                            |
                                            v
                                    4. Parallel Patent Search
                                       +---> USPTO API --------+
                                       +---> Espacenet API ----+---> Aggregator
                                       +---> Google Patents ---+
                                            |
                                            v
                                    5. Result Deduplication
                                       - Match by patent number
                                       - Merge data from multiple sources
                                       - Filter by target countries
                                            |
                                            v
                                    6. Initial Screening (LLM)
                                       - Quick relevance check
                                       - Filter obviously irrelevant patents
                                            |
                                            v
                                    7. Deep Analysis (LLM)
                                       - Parse claims
                                       - Interpret claim scope
                                       - Assess infringement risk
                                            |
                                            v
                                    8. Risk Synthesis (LLM)      -------> Results Display
                                       - Aggregate claim analyses           - Patent list
                                       - Generate FTO opinion               - Risk dashboard
                                       - Assign confidence scores           - Claim details
                                            |
                                            v
                                    9. Report Generation         -------> File Output
                                       - Generate PDF summary              - PDF report
                                       - Generate Excel details            - Excel breakdown
```

### Data Flow Direction Summary

| From | To | Data | Method |
|------|-----|------|--------|
| GUI | Orchestrator | SearchQuery | async method call |
| Orchestrator | SearchService | SearchParams | async method call |
| SearchService | Patent APIs | HTTP request | aiohttp |
| Patent APIs | SearchService | JSON/XML | HTTP response |
| SearchService | Orchestrator | List[Patent] | async return |
| Orchestrator | AnalysisService | Patent, ProductDesc | async method call |
| AnalysisService | Claude API | Prompt | HTTP (anthropic SDK) |
| Claude API | AnalysisService | Analysis | HTTP response |
| Orchestrator | GUI | SearchResults | Qt Signal |
| Orchestrator | ReportService | FTOReport | async method call |
| ReportService | FileSystem | PDF, Excel | file write |

---

## Suggested Build Order

Based on component dependencies, build in this order:

### Phase 1: Foundation

```
1.1 Data Models (no dependencies)
    - Patent, Claim, ChemicalStructure, RiskAssessment, Report
    - Validation logic
    - Serialization

1.2 Infrastructure Adapters (depends on 1.1)
    - USPTO adapter (start with one source)
    - File system utilities

1.3 Chemical Structure Service (depends on 1.1)
    - SMILES parser
    - Structure renderer
```

**Rationale:** Models define the contract for all other components. USPTO is the most accessible API. Chemistry service is independent and well-defined.

### Phase 2: Core Search

```
2.1 Search Service (depends on 1.1, 1.2)
    - Query builder
    - Patent parser
    - Search coordinator

2.2 Basic GUI Shell (depends on 1.1)
    - Main window
    - Question panel (input form)
    - Basic results list

2.3 Orchestrator v1 (depends on 2.1, 2.2)
    - Basic search workflow
    - No analysis yet (just retrieval)
```

**Rationale:** Get end-to-end search working before adding AI. Validates the data flow.

### Phase 3: AI Analysis

```
3.1 LLM Client (depends on 1.1)
    - Anthropic API wrapper
    - Prompt management
    - Response parsing

3.2 Analysis Service (depends on 3.1, 1.1)
    - Claim analyzer
    - Risk assessor

3.3 Orchestrator v2 (depends on 3.2)
    - Add analysis step to workflow
    - Integrate with GUI
```

**Rationale:** AI analysis is the core differentiator but needs stable data models first.

### Phase 4: Report Generation

```
4.1 Report Service (depends on 1.1, 3.2)
    - PDF generator
    - Excel generator
    - Templates

4.2 Full GUI (depends on all above)
    - Risk dashboard
    - Report preview
    - Export controls
```

**Rationale:** Reports are output-only; safe to build last. GUI polish comes after core functionality works.

### Phase 5: Enhancement

```
5.1 Additional Patent Sources
    - Espacenet adapter
    - Google Patents adapter

5.2 Caching & Persistence
    - Search result cache
    - Analysis cache

5.3 Polish
    - Error handling
    - Progress indicators
    - Help documentation
```

---

## Where AI/LLM Fits

### LLM Responsibilities

| Task | Model | Why LLM |
|------|-------|---------|
| Claim interpretation | Claude Sonnet | Natural language understanding of legal text |
| Risk assessment | Claude Opus | Complex reasoning about claim scope vs. product |
| FTO opinion synthesis | Claude Opus | Generating coherent narrative from structured data |
| Keyword extraction | Claude Haiku | Quick, simple NLP task |

### LLM Boundaries (What NOT to Use LLM For)

| Task | Why Not LLM | Alternative |
|------|-------------|-------------|
| SMILES parsing | Deterministic, faster | RDKit |
| Patent search | APIs exist | USPTO/Espacenet APIs |
| PDF generation | Template-based | WeasyPrint |
| Data validation | Rule-based | Custom validators |

### Prompt Engineering Considerations

1. **Structured Output:** Use Claude's JSON mode for consistent parsing
2. **Chain of Thought:** For risk assessment, request reasoning before conclusion
3. **Confidence Scores:** Always request confidence level with assessment
4. **Grounding:** Include relevant patent text in context, don't rely on model knowledge
5. **Disclaimers:** System prompts should include "not legal advice" instruction

### Cost Management

- **Sonnet for volume:** Most claim analyses use Sonnet (cost-effective)
- **Opus for synthesis:** Only final risk synthesis uses Opus (highest quality when it matters)
- **Caching:** Cache analysis by (patent_id, product_hash) to avoid re-analysis
- **Batching:** Group claims for batch analysis where possible

---

## Patterns to Follow

### Pattern 1: Service Abstraction for External APIs

**What:** Wrap each external API (USPTO, Espacenet, Claude) behind an abstract interface.

**When:** Always, for all external dependencies.

**Example:**

```python
# Abstract interface
class PatentSearchAdapter(ABC):
    @abstractmethod
    async def search(self, query: SearchQuery) -> List[Patent]:
        pass

    @abstractmethod
    async def get_patent(self, patent_id: str) -> Patent:
        pass

# Concrete implementation
class USPTOAdapter(PatentSearchAdapter):
    async def search(self, query: SearchQuery) -> List[Patent]:
        # USPTO-specific implementation
        ...

# Usage in orchestrator
class SearchOrchestrator:
    def __init__(self, adapters: List[PatentSearchAdapter]):
        self.adapters = adapters

    async def search_all(self, query: SearchQuery) -> List[Patent]:
        tasks = [adapter.search(query) for adapter in self.adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._aggregate(results)
```

**Why:** Enables testing with mocks, easy addition of new sources, isolated failure handling.

### Pattern 2: Async Throughout

**What:** Use async/await from GUI to infrastructure.

**When:** All I/O operations (API calls, file writes).

**Example:**

```python
# GUI triggers async operation
class SearchViewModel:
    search_started = Signal()
    search_completed = Signal(SearchResults)

    async def start_search(self, query: SearchQuery):
        self.search_started.emit()
        try:
            results = await self.orchestrator.execute_search(query)
            self.search_completed.emit(results)
        except Exception as e:
            self.search_failed.emit(str(e))

# Orchestrator coordinates async services
class SearchOrchestrator:
    async def execute_search(self, query: SearchQuery) -> SearchResults:
        # Parallel patent search
        patents = await self.search_service.search(query)

        # Sequential analysis (could be parallelized with rate limiting)
        analyses = []
        for patent in patents:
            analysis = await self.analysis_service.analyze(patent, query.product)
            analyses.append(analysis)

        return SearchResults(patents=patents, analyses=analyses)
```

**Why:** Patent searches and LLM calls are slow; async keeps GUI responsive.

### Pattern 3: State Machine for Workflow

**What:** Model search workflow as explicit state machine.

**When:** Complex multi-step operations with error recovery needs.

**Example:**

```python
class WorkflowState(Enum):
    IDLE = "idle"
    VALIDATING = "validating"
    SEARCHING = "searching"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"

class SearchWorkflow:
    def __init__(self):
        self.state = WorkflowState.IDLE
        self.state_changed = Signal(WorkflowState)

    def transition(self, new_state: WorkflowState):
        valid_transitions = {
            WorkflowState.IDLE: [WorkflowState.VALIDATING],
            WorkflowState.VALIDATING: [WorkflowState.SEARCHING, WorkflowState.ERROR],
            # ... etc
        }
        if new_state in valid_transitions.get(self.state, []):
            self.state = new_state
            self.state_changed.emit(new_state)
        else:
            raise InvalidTransition(f"Cannot go from {self.state} to {new_state}")
```

**Why:** Clear error recovery paths, easy progress tracking, testable workflow logic.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: LLM as Controller

**What:** Using LLM to decide application flow or make architectural decisions at runtime.

**Why Bad:**
- Non-deterministic behavior
- Slow (API latency)
- Expensive (token costs)
- Hard to debug and test

**Instead:** Use LLM only for analysis tasks where human judgment is needed. Application logic should be deterministic code.

### Anti-Pattern 2: Synchronous API Calls in GUI Thread

**What:** Blocking the GUI thread with patent API or LLM calls.

**Why Bad:**
- GUI freezes during search (bad UX)
- Can't cancel operations
- No progress feedback

**Instead:** Use async/await with QtAsyncio or worker threads.

### Anti-Pattern 3: Monolithic Service

**What:** Single service handling search, analysis, and reporting.

**Why Bad:**
- Hard to test individual components
- Can't parallelize development
- Tight coupling

**Instead:** Separate services with clear interfaces.

### Anti-Pattern 4: Hardcoded Prompts

**What:** Embedding LLM prompts directly in analysis code.

**Why Bad:**
- Hard to iterate on prompts
- Can't A/B test
- No version control for prompts

**Instead:** Prompt templates in separate files, loaded at runtime.

---

## Scalability Considerations

| Concern | Single User | Multi-User (Future) | Notes |
|---------|-------------|---------------------|-------|
| API Rate Limits | Not an issue | Need queuing | USPTO generous, Espacenet stricter |
| LLM Costs | ~$1-5/search | Consider caching | Opus is expensive |
| Search Speed | Acceptable | Need async pooling | Parallel queries help |
| Result Storage | Local files | Need database | SQLite sufficient for single user |

For this desktop application, single-user scalability is sufficient. The architecture supports future migration to multi-user if needed.

---

## Technology Summary

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| GUI Framework | PySide6 | Latest | LGPL license, official Qt bindings, QtAsyncio support |
| Async | asyncio + QtAsyncio | Python 3.11+ | Native async, Qt integration |
| Chemistry | RDKit | 2025.09+ | Industry standard, comprehensive |
| LLM | Anthropic Claude API | Latest | Best reasoning for legal text |
| PDF | WeasyPrint | Latest | HTML/CSS approach, easier templating |
| Excel | XlsxWriter + Pandas | Latest | Good formatting, Pandas integration |
| HTTP | aiohttp | Latest | Async HTTP client |
| Config | python-dotenv | Latest | Environment variable management |

---

## Sources

### HIGH Confidence
- [RDKit Documentation](https://www.rdkit.org/docs/GettingStartedInPython.html) - SMILES parsing, chemical structure handling
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) - Claude API integration
- [XlsxWriter + Pandas](https://xlsxwriter.readthedocs.io/working_with_pandas.html) - Excel generation
- [USPTO Open Data Portal](https://developer.uspto.gov/api-catalog) - Patent search API
- [EPO Open Patent Services](https://patentscope.wipo.int/) - Global patent data

### MEDIUM Confidence
- [PySide6 QtAsyncio](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html) - Async GUI patterns
- [Clean Architecture for PyQt (MVVM)](https://medium.com/@mark_huber/a-clean-architecture-for-a-pyqt-gui-using-the-mvvm-pattern-b8e5d9ae833d) - GUI architecture pattern
- [WeasyPrint](https://weasyprint.org/) - PDF generation
- [FTO Analysis Guide](https://www.cypris.ai/insights/how-to-conduct-a-freedom-to-operate-fto-analysis-complete-guide-for-r-d-teams) - FTO methodology

### LOW Confidence (Needs Validation)
- Specific API rate limits (check official docs before implementation)
- LLM cost estimates (depends on actual usage patterns)
- Espacenet registration requirements (verify current process)
