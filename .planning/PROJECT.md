# Cosmetic FTO Search Agent

## What This Is

A standalone desktop application for chemists developing cosmetic products that automates freedom-to-operate (FTO) patent searches. The user answers a few targeted questions about their proposed cosmetic solution, and the agent searches public patent databases to determine if the solution is clear to use in specified countries.

## Core Value

Quickly and reliably determine if a proposed cosmetic active/solution has freedom to operate in target markets, with clear risk assessment.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Desktop app with clickable launcher that opens a GUI panel
- [ ] Question panel collecting: cosmetic problem, proposed solution/active, chemical structure (SMILES, optional), constraints, target countries
- [ ] Search across public patent databases (Google Patents, Espacenet, USPTO, WIPO)
- [ ] Filter results to active/enforced patents only (exclude expired)
- [ ] Interpret patent claims against user's specific cosmetic use case
- [ ] Risk rating based on similarity to intended application
- [ ] PDF summary output with clear/blocked verdict per country and key findings
- [ ] Excel breakdown output with patent numbers, titles, relevant claims, risk ratings

### Out of Scope

- Expired patent searches (separate IP search agent planned)
- Patent application filing assistance
- Legal advice (this is a research tool, not legal counsel)
- Subscription-based patent database access (using public databases only)

## Context

**User:** Chemist at a cosmetics company developing state-of-the-art cosmetic products.

**Use case example:** Hair damage during dyeing/bleaching strips the lipid layer from the cuticle. Proposed solution: reactive lipids with a functional group to repair the lipid layer. Constraints: cosmetic grade, non-toxic, non-irritating, preferably leave-on compatible. Need to verify FTO before proceeding with development.

**Workflow:** Problem identification → solution ideation → FTO check (this tool) → proceed or pivot.

**Patent databases to search:**
- Google Patents
- Espacenet (EPO)
- USPTO
- WIPO

**Output requirements:**
- PDF summary: high-level verdict (clear/blocked per country), key blocking patents if any
- Excel detailed breakdown: all relevant patents with numbers, titles, relevant claim excerpts, risk ratings (high/medium/low based on similarity to intended use)

## Constraints

- **Tech stack**: Desktop app with GUI (clickable file to launch)
- **Data sources**: Public patent databases only (no paid API subscriptions)
- **Output formats**: PDF for summary, Excel for detailed breakdown
- **User expertise**: Chemist (not patent attorney) — output should be understandable without legal training

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Public databases only | Avoid subscription costs, accessible to all users | — Pending |
| Risk rating by similarity | User needs quick triage, not full legal analysis | — Pending |
| Dual output (PDF + Excel) | Summary for quick review, breakdown for deep dive | — Pending |

---
*Last updated: 2026-01-20 after initialization*
