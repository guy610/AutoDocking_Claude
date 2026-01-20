# Feature Landscape: Cosmetic FTO Search Agent

**Domain:** Patent Freedom-to-Operate Search Tool (Cosmetic Industry Focus)
**Researched:** 2026-01-20
**User Persona:** Chemist (non-patent-attorney) needing clear, actionable output

## Table Stakes

Features users expect. Missing = product feels incomplete or unusable.

### Input Collection

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Natural language problem description | Users describe cosmetic problems in plain language, not patent terminology | Medium | AI/NLP parsing required; translate chemist language to searchable concepts |
| Solution/active ingredient input | Core to FTO - must specify what they want to use | Low | Text field with optional structure |
| SMILES structure input (optional) | Standard chemical notation; enables structure-based searching | Medium | Need SMILES parser/validator; critical for precise compound identification |
| Target country selection | FTO is jurisdiction-specific; patent rights are territorial | Low | Multi-select dropdown; support major cosmetic markets (US, EU, CN, JP, KR, BR) |
| Constraint specification | User may have formulation constraints that narrow scope | Low | Optional text field for context |

### Patent Database Searching

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-jurisdiction patent search | FTO must cover all target markets | High | Requires access to USPTO, EPO, CNIPA, JPO, KIPO, INPI databases or aggregators |
| Chemical structure search (Markush) | Cosmetic patents often claim chemical classes via Markush structures | High | Requires SureChEMBL, PatCID, or CAS integration for structure matching |
| Semantic/conceptual search | Find patents using different terminology for same concept | Medium | AI-powered; "moisturizer" should find "hydrating composition" |
| Classification-based search (CPC/IPC) | Cosmetics use A61K (preparations), A61Q (specific use) | Medium | Auto-suggest relevant classifications based on input |
| Legal status filtering | Only active patents matter for FTO | Medium | Filter out expired, lapsed, abandoned patents |
| Full-text claim search | Claims define infringement scope, not abstracts | Medium | Must search within claim text specifically |

### Results Filtering and Analysis

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Relevance ranking | Too many results = unusable; must surface highest-risk patents | Medium | AI/ML scoring based on claim overlap |
| Legal status display | Show if patent is active, expired, pending | Low | Basic metadata display from databases |
| Jurisdiction grouping | Group results by country for per-market assessment | Low | UI organization feature |
| Patent family aggregation | Avoid analyzing same invention multiple times across filings | Medium | Link family members; analyze representative patent |
| Expiration date display | Know when patent clears | Low | Calculate from filing date + 20 years + adjustments |
| Assignee/owner display | Know who owns the blocking patent | Low | Metadata field |

### Risk Assessment

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-patent risk rating | Clear/Caution/Blocked indication per patent | High | Core value prop; requires claim analysis + product mapping |
| Per-country risk summary | Clear/Blocked status per target market | Medium | Aggregate patent risks by jurisdiction |
| Claim element mapping | Show which claims potentially cover the proposed solution | High | Feature-to-claim mapping; highlight overlapping elements |
| Confidence level indication | User needs to know reliability of assessment | Medium | Distinguish high-confidence vs needs-attorney-review |

### Report Generation

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PDF summary report | Shareable, printable executive summary | Medium | Clear/Blocked per country; key blocking patents identified |
| Excel detailed breakdown | Detailed data for review; standard format per project requirements | Medium | All patents, claims, risk ratings, legal status |
| Patent bibliographic data | Title, number, assignee, dates, status | Low | Standard metadata export |
| Hyperlinks to source patents | User must be able to verify/review original patents | Low | Link to Espacenet, USPTO, etc. |

## Differentiators

Features that would make this tool stand out. Not expected, but highly valued.

### Enhanced Input

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Chemical structure drawing tool | Users can draw molecule without knowing SMILES | High | Integrate JS-based structure editor (e.g., JSME, Ketcher) |
| Formulation composition input | Specify full formulation, not just active | Medium | Multiple ingredients with concentrations |
| Prior art date specification | User may have prior use evidence affecting FTO | Low | Date picker affecting novelty assessment |
| Competitor product input | "Can I make something like Brand X's Product Y?" | Medium | Reverse-engineer competitor formulation to assess FTO |

### Advanced Search

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Image-based patent search | Upload cosmetic/packaging image to find related patents | High | AI visual similarity search; IPRally offers this |
| Automatic query expansion | System identifies related actives/synonyms automatically | Medium | NLP expansion based on cosmetic chemistry knowledge |
| Non-patent literature integration | Search scientific literature for prior art | High | Useful for validity assessment; PubMed, journal integration |
| Competitor patent portfolio analysis | Show what competitors have patented in the space | Medium | Assignee-based analysis |

### Enhanced Analysis

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Patent validity indicators | Flag patents that may be invalid (prior art exists) | High | Requires prior art assessment capability |
| Claim scope visualization | Visual representation of claim breadth | High | Help non-attorneys understand claim coverage |
| Patent landscape map | Visual map of patent density in technology space | Medium | Heat map showing crowded vs open areas |
| Design-around suggestions | Suggest modifications to avoid infringement | Very High | AI-generated alternative formulations; legally sensitive |
| Maintenance fee monitoring | Alert when blocking patent lapses for non-payment | Medium | Ongoing monitoring feature |

### Advanced Reporting

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Claim chart generation | Auto-generate feature-to-claim mapping charts | High | Standard format for patent attorneys to review |
| Citation network visualization | Show how patents relate via citations | Medium | Helps identify key foundational patents |
| Patent family tree visualization | Graphical view of related applications | Medium | Chronological view of family members |
| Risk trend over time | Show how FTO risk changes as patents expire | Medium | Timeline view of blocking patents |
| Saved search / monitoring alerts | Alert when new relevant patents publish | Medium | Weekly/monthly monitoring of patent landscape |

### User Experience

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Plain-language explanations | Explain patent concepts to non-attorneys | Medium | Tooltips, glossary, contextual help |
| Search history / saved projects | Resume previous analyses | Low | User account with saved state |
| Collaboration features | Share analysis with team members | Medium | Multi-user access to projects |
| Audit trail | Track what was searched and when (for legal defensibility) | Medium | Important for "good faith" FTO defense |

## Anti-Features

Features to deliberately NOT build. Common mistakes or scope creep risks.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Legal opinions / infringement conclusions | Only licensed attorneys can provide legal opinions; liability risk | Provide "risk indicators" and "flags for attorney review"; always include disclaimer |
| Freedom-to-operate guarantees | FTO is inherently probabilistic; can never guarantee "clear" | Provide confidence levels; recommend attorney review for high-risk cases |
| Automatic licensing negotiations | Out of scope; requires business/legal negotiation | Identify patent owner contact info only |
| Patent filing assistance | Different domain (prosecution vs. clearance) | Stay focused on FTO analysis |
| Real-time patent monitoring (without user trigger) | Cost and complexity; scope creep | Offer on-demand search with option to save/re-run |
| Comprehensive validity analysis | Requires deep prior art search and legal expertise | Flag obvious validity concerns; recommend formal opinion for important patents |
| Multi-tenant competitive intelligence | Exposes competitive research to other users | Keep all searches private per user |
| Design-around legal advice | Crosses into patent attorney territory | Suggest "alternative approaches exist" without specific legal guidance |
| Automated cease-and-desist generation | Legal document generation requires attorney oversight | Out of scope entirely |
| Regulatory compliance advice | Different domain (FDA, EU cosmetics regulation vs. patents) | Note: patents != regulatory approval; suggest separate regulatory review |

## Feature Dependencies

```
Input Collection
    |
    v
Patent Database Searching
    |-- Multi-jurisdiction search (requires database access)
    |-- Chemical structure search (requires SMILES input + structure DB)
    |
    v
Results Filtering
    |-- Legal status filtering (requires legal status data)
    |-- Patent family aggregation (requires family linking data)
    |
    v
Risk Assessment
    |-- Per-patent risk rating (requires claim analysis)
    |-- Claim element mapping (requires NLP/AI claim parsing)
    |-- Per-country summary (requires jurisdiction + legal status data)
    |
    v
Report Generation
    |-- PDF summary (aggregates risk assessment)
    |-- Excel breakdown (includes all filtered results + ratings)
```

### Critical Path Dependencies

1. **Database access** must be established before any search functionality
2. **Search results** must exist before filtering can be applied
3. **Legal status data** required for accurate FTO (expired patents = no risk)
4. **Claim analysis** required for meaningful risk ratings
5. **Risk ratings** required for useful report generation

### Optional Feature Dependencies

- Structure drawing tool -> SMILES conversion -> Structure search
- Competitor portfolio analysis -> Assignee filtering + aggregation
- Patent landscape map -> Search results + visualization library
- Claim chart generation -> Claim parsing + element extraction + mapping logic

## MVP Recommendation

For MVP, prioritize:

### Must Have (Phase 1)
1. **Natural language input** - Problem + solution description
2. **Target country selection** - Multi-select for key markets
3. **Multi-jurisdiction patent search** - At minimum: USPTO, EPO
4. **Basic keyword + classification search** - CPC A61K, A61Q
5. **Legal status filtering** - Active patents only
6. **Per-patent risk indicator** - Simple High/Medium/Low
7. **Per-country summary** - Clear/Caution/Blocked
8. **PDF summary report** - Executive summary format
9. **Excel detailed export** - All patent data

### Should Have (Phase 2)
1. **SMILES input + structure search** - Via SureChEMBL or similar
2. **Semantic search** - AI-powered concept matching
3. **Claim element mapping** - Show overlap with proposed solution
4. **Patent family aggregation** - Reduce duplicate analysis
5. **Confidence levels** - Distinguish reliable vs uncertain assessments

### Nice to Have (Phase 3)
1. **Chemical structure drawing** - Visual structure input
2. **Saved searches / monitoring** - Track landscape over time
3. **Citation network visualization** - Patent relationship graphs
4. **Claim chart export** - For attorney review

### Defer to Post-MVP
- Non-patent literature search (complexity)
- Design-around suggestions (legal sensitivity)
- Full validity analysis (deep expertise required)
- Real-time monitoring/alerts (operational complexity)
- Competitor portfolio deep analysis (scope creep)

## Complexity Summary

| Complexity | Count | Examples |
|------------|-------|----------|
| Low | 12 | Country selection, legal status display, hyperlinks |
| Medium | 18 | NLP input parsing, semantic search, PDF generation |
| High | 9 | Chemical structure search, claim element mapping, risk rating |
| Very High | 1 | Design-around suggestions (also anti-feature) |

## Sources

### FTO and Patent Search Tools
- [IPRally FTO Search](https://www.iprally.com/use-cases/freedom-to-operate)
- [PatSnap FTO Glossary](https://www.patsnap.com/glossary/freedom-to-operate/)
- [Cypris FTO Guide](https://www.cypris.ai/insights/how-to-conduct-a-freedom-to-operate-fto-analysis-complete-guide-for-r-d-teams)
- [Parola Analytics FTO Guide](https://parolaanalytics.com/guide/fto-search-guide/)

### Patent Search Software
- [Cypris AI Research Tools 2026](https://www.cypris.ai/insights/the-best-ai-research-tools-for-patent-and-technical-intelligence-in-2026)
- [GreyB AI Patent Databases 2026](https://greyb.com/blog/ai-based-patent-databases/)
- [PatSnap FTO Tools 2025](https://www.patsnap.com/resources/blog/articles/fto-search-tools-patent-attorneys-2025/)

### Chemical Structure Search
- [SureChEMBL](https://www.surechembl.org/)
- [PatCID Nature Publication](https://www.nature.com/articles/s41467-024-50779-y)
- [PubChem Patents](https://pubchem.ncbi.nlm.nih.gov/docs/patents)

### Risk Assessment
- [PatentPC Risk Assessment](https://patentpc.com/blog/how-to-conduct-a-patent-infringement-risk-assessment)
- [Aaron Hall Risk Quantification](https://aaronhall.com/patent-infringement-risk-quantification-guide/)

### Patent Legal Status
- [The Lens Legal Status](https://support.lens.org/knowledge-base/patent-legal-status-calculations/)
- [PATOffice Status Monitoring](https://www.patoffice.de/en/blog/patent-status-monitoring-what-are-the-possible-statuses)

### Claim Charts
- [IIPRD Claim Charts](https://www.iiprd.com/why-are-claim-charts-required-and-basics-of-how-they-are-prepared/)
- [Lumenci Claim Chart Guide](https://lumenci.com/blogs/create-effective-patent-claim-chart/)

### Cosmetic Industry
- [USPTO CPC A61Q Definition](https://www.uspto.gov/web/patents/classification/cpc/html/defA61Q.html)
- [Global CosIng Database](https://globalcosing.chemradar.com/)
- [MDPI Cosmetic Regulatory Overview](https://www.mdpi.com/2079-9284/9/4/72)
