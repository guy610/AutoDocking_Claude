---
phase: 02-input-collection-ui
plan: 01
subsystem: ui-widgets
tags: [pyside6, rdkit, smiles, form-validation, input-collection]

dependency-graph:
  requires:
    - 01-01 (Worker pattern for async operations)
    - 01-02 (ProgressManager for UI feedback)
  provides:
    - SMILES validator with RDKit integration
    - InputPanel widget with five input sections
    - Form validation for FTO queries
  affects:
    - 02-02 (MainWindow integration)
    - 03-XX (Patent search uses InputPanel data)

tech-stack:
  added:
    - rdkit>=2025.9.3
  patterns:
    - Qt property-based validation styling
    - Signal/slot for form validity changes

key-files:
  created:
    - src/fto_agent/validators/__init__.py
    - src/fto_agent/validators/smiles.py
    - src/fto_agent/widgets/input_panel.py
  modified:
    - src/fto_agent/widgets/__init__.py
    - pyproject.toml

decisions:
  - key: rdkit-for-smiles-validation
    choice: "Use RDKit MolFromSmiles for SMILES validation"
    rationale: "Industry standard cheminformatics library, handles valence and aromaticity correctly"
  - key: empty-smiles-valid
    choice: "Treat empty SMILES as valid"
    rationale: "SMILES field is optional; empty should not block form submission"
  - key: countries-default-selected
    choice: "All countries selected by default"
    rationale: "Most users want comprehensive FTO search; easier to uncheck than check"
  - key: real-time-smiles-validation
    choice: "Validate SMILES on every keystroke"
    rationale: "RDKit is fast enough; immediate feedback improves UX"

metrics:
  duration: ~7 minutes
  completed: 2026-01-22
---

# Phase 2 Plan 01: SMILES Validator and InputPanel Widget Summary

**One-liner:** RDKit-powered SMILES validation with InputPanel form collecting problem, solution, constraints, SMILES, and target countries for FTO queries.

## What Was Built

### Task 1: SMILES Validator Module

Created `src/fto_agent/validators/smiles.py` with:

- `SmilesValidationResult` dataclass for structured validation results
- `validate_smiles(smiles: str)` function using RDKit's MolFromSmiles
- `is_rdkit_available()` function to check RDKit presence
- Graceful handling when RDKit not installed
- RDKit stderr logging suppressed for clean output
- Empty SMILES treated as valid (optional field)

Added `rdkit>=2025.9.3` to pyproject.toml dependencies.

### Task 2: InputPanel Widget

Created `src/fto_agent/widgets/input_panel.py` with:

- **Problem description** - QPlainTextEdit, required, 80px minimum height
- **Solution/active** - QPlainTextEdit, required, 80px minimum height
- **Constraints** - QPlainTextEdit, optional, 60px minimum height
- **SMILES** - QLineEdit with real-time validation and status feedback
- **Target Countries** - QGroupBox with QCheckBox grid (US, EU, CN, JP)
- **Submit button** - Disabled until form is valid

Signals:
- `validityChanged(bool)` - Emitted when form validity changes
- `submitRequested()` - Emitted when user clicks submit

Methods:
- `is_valid()` - Check if required fields filled and SMILES (if provided) is valid
- `get_data()` - Return dict with problem, solution, constraints, smiles, countries
- `clear()` - Reset all fields to defaults

## Commits

| Commit | Description |
|--------|-------------|
| a38d943 | feat(02-01): create SMILES validator module |
| 119dff4 | feat(02-01): create InputPanel widget |

## Verification Results

All success criteria verified:

1. SMILES validator correctly identifies valid/invalid SMILES notation
2. Empty SMILES is treated as valid (optional field)
3. InputPanel contains all five input sections
4. Form validation requires problem, solution, and at least one country
5. get_data() returns structured dictionary with all inputs
6. rdkit added to pyproject.toml dependencies

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

Ready for 02-02 (MainWindow integration):
- InputPanel widget exports from widgets package
- COUNTRIES constant available for reference
- validityChanged signal ready for MainWindow to monitor
- submitRequested signal ready for search initiation

Technical notes for next plan:
- InputPanel requires QApplication context (like all Qt widgets)
- SMILES input auto-disables if RDKit not available
- All countries default to checked on widget creation
