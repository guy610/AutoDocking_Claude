---
phase: 02-input-collection-ui
plan: 02
subsystem: ui-integration
tags: [pyside6, mainwindow, input-panel, unit-tests, pytest-qt]

dependency-graph:
  requires:
    - 02-01 (InputPanel widget and SMILES validator)
    - 01-01 (Worker pattern for async operations)
    - 01-02 (ProgressManager for progress display)
  provides:
    - Complete FTO query input interface
    - MainWindow with InputPanel integration
    - Unit test suite for SMILES validation
    - Unit test suite for InputPanel widget
  affects:
    - 03-XX (Patent search receives InputPanel data via get_data())

tech-stack:
  added:
    - pytest-qt>=4.5.0
  patterns:
    - Qt property-based validation styling (validationState property)
    - Signal/slot for form submission

key-files:
  created:
    - tests/test_smiles_validator.py
    - tests/test_input_panel.py
  modified:
    - src/fto_agent/main_window.py
    - src/fto_agent/app.py

decisions:
  - key: validation-stylesheet-in-app
    choice: "Define VALIDATION_STYLESHEET in app.py and apply at app level"
    rationale: "Centralizes styling, ensures consistent validation feedback across all widgets"
  - key: placeholder-fto-search
    choice: "Show 'FTO search not yet implemented' status message on submit"
    rationale: "Allows UI testing without backend; Phase 3 will implement actual search"

metrics:
  duration: ~15 minutes
  completed: 2026-01-22
---

# Phase 2 Plan 02: MainWindow Integration and Unit Tests Summary

**One-liner:** MainWindow integrated with InputPanel for FTO query collection, plus 33 unit tests covering SMILES validation and input panel functionality.

## What Was Built

### Task 1: MainWindow Integration

Updated `src/fto_agent/main_window.py`:

- Imported InputPanel from fto_agent.widgets
- Replaced demo content with InputPanel as central widget
- Connected InputPanel.submitRequested to _start_fto_search method
- Removed demo work function and demo operation code
- Added _start_fto_search that retrieves form data via get_data()
- Status bar shows placeholder message until Phase 3 implements search
- Preserved progress bar, cancel button, and worker infrastructure for future use

Updated `src/fto_agent/app.py`:

- Added VALIDATION_STYLESHEET constant with validation states
- QLineEdit[validationState="error"]: red border, light red background
- QLineEdit[validationState="valid"]: green border
- QGroupBox styling for countries section
- Applied stylesheet to QApplication for global effect

### Task 2: Unit Tests

Created `tests/test_smiles_validator.py` (12 tests):

- Valid SMILES detection (CCO, benzene)
- Invalid SMILES detection (not_a_smiles, XYZ)
- Empty and whitespace handling (optional field)
- GHK peptide SMILES from requirements
- Palmitoyl-GHK SMILES from requirements
- RDKit availability check
- SmilesValidationResult dataclass fields

Created `tests/test_input_panel.py` (21 tests):

- Widget creation and required widget presence
- Initial validity (empty form is invalid)
- Form validity with required fields filled
- Form invalidity without countries
- Form invalidity without problem/solution
- Form validity with valid/invalid SMILES
- get_data() returns expected keys and values
- Optional fields can be empty
- Whitespace trimming in get_data()
- SMILES validation visual feedback (valid/invalid/empty)
- clear() resets all fields
- submitRequested signal emission
- validityChanged signal emission

### Task 3: Human Verification

User verified the complete input UI:

- Application launches and shows input form
- All five input sections visible (problem, solution, constraints, SMILES, countries)
- Submit button disabled until required fields filled
- SMILES validation shows green/red feedback in real-time
- GHK peptide SMILES validated correctly
- Country selection affects form validity
- Application remains responsive

## Commits

| Commit | Description |
|--------|-------------|
| 3c451e7 | feat(02-02): integrate InputPanel into MainWindow |
| 374aa59 | test(02-02): add unit tests for SMILES validator and InputPanel |

## Verification Results

All verification criteria met:

1. **Full test suite passes**: 33 tests pass in 2.19s
2. **INP-01**: Problem description field exists and accepts input
3. **INP-02**: Solution field exists and accepts input
4. **INP-03**: Constraints field exists and accepts input
5. **INP-04**: SMILES field with validation feedback (RDKit-powered)
6. **INP-05**: Country multi-select with US, EU, CN, JP (default checked)
7. **Human verification**: All UI interactions work as expected

## Deviations from Plan

None - plan executed exactly as written.

## Phase 2 Completion

With plan 02-02 complete, Phase 2 (Input Collection UI) is finished:

- Plan 02-01: SMILES validator and InputPanel widget
- Plan 02-02: MainWindow integration and unit tests

All five input requirements (INP-01 through INP-05) are satisfied:
- Users can enter problem description, solution/active, and constraints
- Users can paste SMILES notation with real-time validation feedback
- Users can select target countries for FTO search
- Submit button enables only when form is valid

## Next Phase Readiness

Ready for Phase 3 (Patent Search Backend):

- InputPanel.get_data() provides structured query dict:
  - problem: str
  - solution: str
  - constraints: str
  - smiles: str
  - countries: List[str]
- MainWindow._start_fto_search() receives submitRequested signal
- Worker pattern ready for async search operations
- ProgressManager ready to show search progress
