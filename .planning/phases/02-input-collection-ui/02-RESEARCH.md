# Phase 2: Input Collection UI - Research

**Researched:** 2026-01-22
**Domain:** PySide6 form widgets, input validation, SMILES chemical notation validation with RDKit
**Confidence:** HIGH

## Summary

This research establishes the patterns for building a complete input collection panel in PySide6 for the FTO Search Agent. The panel collects five types of user input: problem description, solution/active description, constraints, optional SMILES notation, and target country selection.

PySide6 provides excellent form-building primitives: **QPlainTextEdit** for multi-line text (problem, solution, constraints), **QLineEdit** for single-line input (SMILES), **QCheckBox** within **QGroupBox** for country multi-select, and **QFormLayout** for clean label-field organization. For SMILES validation, **RDKit** (installable via pip) provides `Chem.MolFromSmiles()` which returns `None` for invalid structures - no exceptions, just a null check.

The key architectural decisions are:
1. Use QPlainTextEdit (not QTextEdit) for multi-line plain text - better performance, simpler API
2. Use QFormLayout for label-field alignment with consistent spacing
3. Use QScrollArea wrapper if content exceeds window height
4. Implement SMILES validation using RDKit's MolFromSmiles with visual feedback via dynamic properties
5. Use QGroupBox with checkbox grid for country selection

**Primary recommendation:** Build a reusable InputPanel widget containing all five input sections, with a validate() method that returns validation state and a getData() method that returns a structured dictionary.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.6+ | Qt bindings | LGPL license, official Qt support, decided in Phase 1 |
| rdkit | 2025.9.3+ | SMILES validation | Standard cheminformatics library, pip-installable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PySide6.QtWidgets.QPlainTextEdit | Built-in | Multi-line plain text | Problem, solution, constraints fields |
| PySide6.QtWidgets.QLineEdit | Built-in | Single-line text | SMILES input |
| PySide6.QtWidgets.QFormLayout | Built-in | Form organization | Label-field alignment |
| PySide6.QtWidgets.QGroupBox | Built-in | Grouped controls | Country selection section |
| PySide6.QtWidgets.QCheckBox | Built-in | Toggle options | Individual country checkboxes |
| PySide6.QtWidgets.QScrollArea | Built-in | Scrollable container | If form exceeds window height |
| PySide6.QtWidgets.QLabel | Built-in | Validation feedback | Show valid/invalid SMILES status |
| rdkit.Chem | Built-in | Molecule operations | MolFromSmiles for validation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| QPlainTextEdit | QTextEdit | QTextEdit supports rich text; QPlainTextEdit is simpler and faster for plain text |
| QCheckBox (multiple) | QListWidget with checkable items | List widget adds complexity; simple checkboxes are clearer for 4-6 countries |
| RDKit | PartialSMILES, PySMILES | RDKit is the industry standard; others are more permissive but less accurate |
| QFormLayout | QGridLayout | QFormLayout handles label-field pairs automatically with proper alignment |

**Installation:**
```bash
pip install PySide6>=6.6 rdkit>=2025.9.3
```

## Architecture Patterns

### Recommended Project Structure
```
src/
    fto_agent/
        widgets/
            __init__.py
            progress.py       # From Phase 1
            input_panel.py    # NEW: Input collection widget
        validators/
            __init__.py
            smiles.py         # NEW: SMILES validation helper
        main_window.py        # Updated to include InputPanel
```

### Pattern 1: InputPanel Widget Structure
**What:** A QWidget subclass containing all input fields organized in a QFormLayout
**When to use:** Central widget of the main window, contains all FTO query inputs

```python
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFormLayout.html
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QPlainTextEdit,
    QLineEdit, QGroupBox, QCheckBox, QGridLayout, QLabel
)
from PySide6.QtCore import Signal

class InputPanel(QWidget):
    """Panel for collecting FTO query inputs."""

    # Signal emitted when input validity changes
    validityChanged = Signal(bool)  # True if all required fields valid

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Form layout for text inputs
        form = QFormLayout()

        # Problem description (required)
        self.problem_edit = QPlainTextEdit()
        self.problem_edit.setPlaceholderText(
            "Describe the cosmetic problem you want to solve...\n"
            "Example: Improve skin health (TWEL, flexibility) via collagen synthesis"
        )
        self.problem_edit.setMinimumHeight(80)
        form.addRow("Problem:", self.problem_edit)

        # Solution/Active description (required)
        self.solution_edit = QPlainTextEdit()
        self.solution_edit.setPlaceholderText(
            "Describe your proposed solution or active ingredient...\n"
            "Example: GHK peptide (Gly-His-Lys)"
        )
        self.solution_edit.setMinimumHeight(80)
        form.addRow("Solution/Active:", self.solution_edit)

        # Constraints (optional)
        self.constraints_edit = QPlainTextEdit()
        self.constraints_edit.setPlaceholderText(
            "Any constraints (optional)...\n"
            "Example: cosmetic grade, leave-on product, water-soluble"
        )
        self.constraints_edit.setMinimumHeight(60)
        form.addRow("Constraints:", self.constraints_edit)

        # SMILES (optional with validation)
        smiles_container = QWidget()
        smiles_layout = QVBoxLayout(smiles_container)
        smiles_layout.setContentsMargins(0, 0, 0, 0)

        self.smiles_edit = QLineEdit()
        self.smiles_edit.setPlaceholderText("Paste SMILES notation (optional)...")
        smiles_layout.addWidget(self.smiles_edit)

        self.smiles_status = QLabel("")
        self.smiles_status.setStyleSheet("font-size: 11px;")
        smiles_layout.addWidget(self.smiles_status)

        form.addRow("SMILES:", smiles_container)

        layout.addLayout(form)

        # Country selection
        self.country_group = QGroupBox("Target Countries")
        country_layout = QGridLayout(self.country_group)

        self.country_checks = {}
        countries = [
            ("US", "United States"),
            ("EU", "European Union"),
            ("CN", "China"),
            ("JP", "Japan"),
        ]
        for i, (code, name) in enumerate(countries):
            cb = QCheckBox(f"{name} ({code})")
            cb.setChecked(True)  # Default all selected
            self.country_checks[code] = cb
            country_layout.addWidget(cb, i // 2, i % 2)

        layout.addWidget(self.country_group)
        layout.addStretch()
```

### Pattern 2: SMILES Validation with Visual Feedback
**What:** Real-time SMILES validation using RDKit with visual feedback
**When to use:** When user enters/modifies SMILES notation

```python
# Source: https://www.rdkit.org/docs/GettingStartedInPython.html
# Source: https://github.com/rdkit/rdkit/discussions/7677
from rdkit import Chem

def validate_smiles(smiles: str) -> tuple[bool, str]:
    """Validate a SMILES string using RDKit.

    Args:
        smiles: SMILES notation string

    Returns:
        Tuple of (is_valid, message)
    """
    if not smiles or not smiles.strip():
        return True, ""  # Empty is valid (field is optional)

    smiles = smiles.strip()

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False, "Invalid SMILES notation"
        return True, f"Valid ({mol.GetNumAtoms()} atoms)"
    except Exception as e:
        return False, f"Error: {str(e)}"


# In InputPanel class:
def _connect_signals(self):
    """Connect input signals for validation."""
    self.smiles_edit.textChanged.connect(self._validate_smiles)
    self.problem_edit.textChanged.connect(self._check_validity)
    self.solution_edit.textChanged.connect(self._check_validity)

def _validate_smiles(self):
    """Validate SMILES and update visual feedback."""
    smiles = self.smiles_edit.text()
    is_valid, message = validate_smiles(smiles)

    if not smiles:
        self.smiles_status.setText("")
        self.smiles_edit.setProperty("validationState", "")
    elif is_valid:
        self.smiles_status.setText(f"Valid: {message}")
        self.smiles_status.setStyleSheet("font-size: 11px; color: green;")
        self.smiles_edit.setProperty("validationState", "valid")
    else:
        self.smiles_status.setText(f"Invalid: {message}")
        self.smiles_status.setStyleSheet("font-size: 11px; color: red;")
        self.smiles_edit.setProperty("validationState", "error")

    # Force style update
    self.smiles_edit.style().unpolish(self.smiles_edit)
    self.smiles_edit.style().polish(self.smiles_edit)
    self._check_validity()
```

### Pattern 3: Validation State Styling
**What:** CSS-like stylesheet for validation visual feedback
**When to use:** Apply to application to show validation states on inputs

```python
# Source: https://doc.qt.io/qt-6/stylesheet-examples.html
VALIDATION_STYLESHEET = """
QLineEdit[validationState="error"] {
    border: 2px solid #dc3545;
    background-color: #fff5f5;
}

QLineEdit[validationState="valid"] {
    border: 2px solid #28a745;
}

QLineEdit[validationState=""] {
    border: 1px solid #ccc;
}

QPlainTextEdit[validationState="error"] {
    border: 2px solid #dc3545;
    background-color: #fff5f5;
}
"""
```

### Pattern 4: Data Collection Method
**What:** Method to collect all input data as a structured dictionary
**When to use:** When user submits the form to start FTO search

```python
def get_data(self) -> dict:
    """Collect all input data as a dictionary.

    Returns:
        Dictionary with keys: problem, solution, constraints, smiles, countries
    """
    return {
        "problem": self.problem_edit.toPlainText().strip(),
        "solution": self.solution_edit.toPlainText().strip(),
        "constraints": self.constraints_edit.toPlainText().strip(),
        "smiles": self.smiles_edit.text().strip() or None,
        "countries": [
            code for code, cb in self.country_checks.items()
            if cb.isChecked()
        ],
    }

def is_valid(self) -> bool:
    """Check if all required fields are valid.

    Returns:
        True if form is valid and can be submitted
    """
    data = self.get_data()

    # Required: problem and solution
    if not data["problem"]:
        return False
    if not data["solution"]:
        return False

    # Required: at least one country
    if not data["countries"]:
        return False

    # If SMILES provided, must be valid
    if data["smiles"]:
        is_valid_smiles, _ = validate_smiles(data["smiles"])
        if not is_valid_smiles:
            return False

    return True
```

### Pattern 5: Scrollable Form Container
**What:** Wrap InputPanel in QScrollArea for tall forms
**When to use:** If the input panel may exceed window height

```python
# Source: https://www.pythonguis.com/tutorials/pyside-qscrollarea/
from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import Qt

def create_scrollable_input_panel(parent=None) -> QScrollArea:
    """Create a scrollable container for the input panel.

    Returns:
        QScrollArea containing the InputPanel
    """
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    input_panel = InputPanel()
    scroll.setWidget(input_panel)

    return scroll
```

### Anti-Patterns to Avoid

- **Using QTextEdit for plain text:** QTextEdit is for rich text (HTML/Markdown). Use QPlainTextEdit for plain text - it's faster and has a simpler API.

- **Validating on every keystroke for expensive operations:** SMILES validation with RDKit is fast, but for expensive validations, use a QTimer with 300-500ms delay to debounce.

- **Storing validation state in the view:** Keep validation logic in a separate validator or in the data model, not scattered in UI code.

- **Hard-coding country list:** The country list should be easily extensible. Use a data-driven approach with a list of (code, name) tuples.

- **Forgetting placeholder text:** Placeholder text is essential UX for helping users understand what to enter. Always provide meaningful examples.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SMILES validation | Regex pattern matching | RDKit MolFromSmiles | SMILES syntax is complex; RDKit handles valence, kekulization, aromaticity |
| Form layout alignment | Manual positioning | QFormLayout | Handles label-field alignment, accessibility, RTL languages automatically |
| Multi-line text input | QLineEdit with hacks | QPlainTextEdit | Purpose-built for multi-line, handles scrolling and selection properly |
| Visual validation feedback | Manual border changes | Qt property + stylesheet | Qt handles repaint; properties are declarative and maintainable |
| Scrollable forms | Manual scroll handling | QScrollArea + widgetResizable | Qt handles scroll bars, viewport, and resize events |

**Key insight:** Qt's form widgets and RDKit handle the hard parts. Focus on wiring them together, not reimplementing their functionality.

## Common Pitfalls

### Pitfall 1: RDKit Import Failures
**What goes wrong:** RDKit import fails with DLL/library errors on Windows.
**Why it happens:** RDKit has native dependencies that may conflict or be missing.
**How to avoid:**
1. Use a clean virtual environment
2. Install via `pip install rdkit` (not conda) for consistency
3. Test import immediately after installation: `python -c "from rdkit import Chem; print(Chem.MolFromSmiles('C'))"`
**Warning signs:** ImportError mentioning DLLs, "module not found" for rdkit.Chem.

### Pitfall 2: MolFromSmiles Silent Failures
**What goes wrong:** Invalid SMILES returns None but also prints to stderr, cluttering logs.
**Why it happens:** RDKit logs errors to stderr by default.
**How to avoid:**
1. Check for None explicitly before using the mol object
2. If stderr logging is problematic, capture or suppress RDKit output:
   ```python
   from rdkit import RDLogger
   RDLogger.DisableLog('rdApp.*')  # Suppress RDKit logging
   ```
3. For user feedback, just check if mol is None - that's sufficient
**Warning signs:** Console filled with RDKit error messages during validation.

### Pitfall 3: Property-Based Stylesheet Not Updating
**What goes wrong:** Setting a Qt property doesn't change the widget's appearance.
**Why it happens:** Qt caches stylesheet computations; properties alone don't trigger repaint.
**How to avoid:**
1. After setting property, force style update:
   ```python
   widget.setProperty("validationState", "error")
   widget.style().unpolish(widget)
   widget.style().polish(widget)
   ```
2. Alternative: use setStyleSheet directly on the widget (less maintainable but simpler)
**Warning signs:** Property value changes but widget appearance doesn't update.

### Pitfall 4: Empty String vs None for Optional Fields
**What goes wrong:** Code treats empty string and None differently, causing inconsistent behavior.
**Why it happens:** QLineEdit.text() returns "" not None; some code expects None for "not provided".
**How to avoid:**
1. Normalize in getData(): `smiles = self.smiles_edit.text().strip() or None`
2. Validate consistently: `if not smiles` works for both "" and None
3. Document the convention: empty optional fields return None
**Warning signs:** Validation passes for "" but fails for None, or vice versa.

### Pitfall 5: Country Selection State Management
**What goes wrong:** User unchecks all countries, form seems valid but search fails.
**Why it happens:** "At least one country required" validation is often forgotten.
**How to avoid:**
1. Include country count in is_valid() check
2. Consider visual feedback: disable submit button when no countries selected
3. Connect all checkbox stateChanged signals to validation check
**Warning signs:** Search runs with empty country list, returns no results or errors.

## Code Examples

Verified patterns from official sources:

### Complete SMILES Validator Module

```python
# src/fto_agent/validators/smiles.py
# Source: https://www.rdkit.org/docs/GettingStartedInPython.html

from dataclasses import dataclass
from typing import Optional

try:
    from rdkit import Chem
    from rdkit import RDLogger
    # Suppress RDKit stderr logging
    RDLogger.DisableLog('rdApp.*')
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@dataclass
class SmilesValidationResult:
    """Result of SMILES validation."""
    is_valid: bool
    message: str
    atom_count: Optional[int] = None


def validate_smiles(smiles: str) -> SmilesValidationResult:
    """Validate a SMILES string.

    Args:
        smiles: SMILES notation string (may be empty)

    Returns:
        SmilesValidationResult with validity status and message
    """
    # Empty is valid (field is optional)
    if not smiles or not smiles.strip():
        return SmilesValidationResult(True, "")

    smiles = smiles.strip()

    if not RDKIT_AVAILABLE:
        return SmilesValidationResult(
            False,
            "RDKit not installed - cannot validate SMILES"
        )

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return SmilesValidationResult(False, "Invalid SMILES notation")

        atom_count = mol.GetNumAtoms()
        return SmilesValidationResult(
            True,
            f"Valid molecule with {atom_count} atoms",
            atom_count
        )
    except Exception as e:
        return SmilesValidationResult(False, f"Validation error: {str(e)}")


def is_rdkit_available() -> bool:
    """Check if RDKit is available for SMILES validation."""
    return RDKIT_AVAILABLE
```

### Complete InputPanel Widget

```python
# src/fto_agent/widgets/input_panel.py
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFormLayout.html
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QPlainTextEdit.html

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPlainTextEdit, QLineEdit, QGroupBox, QCheckBox,
    QGridLayout, QLabel, QPushButton
)
from PySide6.QtCore import Signal, Slot

from fto_agent.validators.smiles import validate_smiles, is_rdkit_available


# Countries available for FTO search
COUNTRIES = [
    ("US", "United States"),
    ("EU", "European Union"),
    ("CN", "China"),
    ("JP", "Japan"),
]


class InputPanel(QWidget):
    """Panel for collecting FTO query inputs.

    Signals:
        validityChanged(bool): Emitted when form validity changes
        submitRequested(): Emitted when user clicks submit
    """

    validityChanged = Signal(bool)
    submitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()
        # Initial validity check
        self._check_validity()

    def _setup_ui(self):
        """Set up the UI layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # === Text inputs section ===
        form = QFormLayout()
        form.setSpacing(12)

        # Problem description (required)
        self.problem_edit = QPlainTextEdit()
        self.problem_edit.setPlaceholderText(
            "Describe the cosmetic problem you want to solve...\n"
            "Example: Improve skin health (TWEL, flexibility) via collagen synthesis"
        )
        self.problem_edit.setMinimumHeight(80)
        self.problem_edit.setMaximumHeight(120)
        form.addRow("Problem *:", self.problem_edit)

        # Solution/Active description (required)
        self.solution_edit = QPlainTextEdit()
        self.solution_edit.setPlaceholderText(
            "Describe your proposed solution or active ingredient...\n"
            "Example: GHK peptide (Gly-His-Lys)"
        )
        self.solution_edit.setMinimumHeight(80)
        self.solution_edit.setMaximumHeight(120)
        form.addRow("Solution/Active *:", self.solution_edit)

        # Constraints (optional)
        self.constraints_edit = QPlainTextEdit()
        self.constraints_edit.setPlaceholderText(
            "Any constraints (optional)...\n"
            "Example: cosmetic grade, leave-on product, water-soluble"
        )
        self.constraints_edit.setMinimumHeight(60)
        self.constraints_edit.setMaximumHeight(100)
        form.addRow("Constraints:", self.constraints_edit)

        # SMILES input with validation feedback
        smiles_container = QWidget()
        smiles_layout = QVBoxLayout(smiles_container)
        smiles_layout.setContentsMargins(0, 0, 0, 0)
        smiles_layout.setSpacing(4)

        self.smiles_edit = QLineEdit()
        self.smiles_edit.setPlaceholderText(
            "Paste SMILES notation (optional)..."
        )
        smiles_layout.addWidget(self.smiles_edit)

        self.smiles_status = QLabel("")
        self.smiles_status.setStyleSheet("font-size: 11px;")
        smiles_layout.addWidget(self.smiles_status)

        # Show RDKit availability status
        if not is_rdkit_available():
            self.smiles_edit.setEnabled(False)
            self.smiles_status.setText("RDKit not installed - SMILES validation unavailable")
            self.smiles_status.setStyleSheet("font-size: 11px; color: orange;")

        form.addRow("SMILES:", smiles_container)

        layout.addLayout(form)

        # === Country selection section ===
        self.country_group = QGroupBox("Target Countries *")
        country_layout = QGridLayout(self.country_group)
        country_layout.setSpacing(8)

        self.country_checks = {}
        for i, (code, name) in enumerate(COUNTRIES):
            cb = QCheckBox(f"{name} ({code})")
            cb.setChecked(True)  # Default: all selected
            self.country_checks[code] = cb
            row, col = divmod(i, 2)
            country_layout.addWidget(cb, row, col)

        layout.addWidget(self.country_group)

        # === Submit button ===
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.submit_button = QPushButton("Start FTO Search")
        self.submit_button.setMinimumWidth(150)
        self.submit_button.setEnabled(False)
        button_layout.addWidget(self.submit_button)

        layout.addLayout(button_layout)
        layout.addStretch()

    def _connect_signals(self):
        """Connect widget signals to handlers."""
        # Text changes trigger validity check
        self.problem_edit.textChanged.connect(self._check_validity)
        self.solution_edit.textChanged.connect(self._check_validity)

        # SMILES validation
        self.smiles_edit.textChanged.connect(self._on_smiles_changed)

        # Country checkbox changes
        for cb in self.country_checks.values():
            cb.stateChanged.connect(self._check_validity)

        # Submit button
        self.submit_button.clicked.connect(self.submitRequested.emit)

    @Slot()
    def _on_smiles_changed(self):
        """Handle SMILES input changes."""
        smiles = self.smiles_edit.text()
        result = validate_smiles(smiles)

        if not smiles:
            self.smiles_status.setText("")
            self._set_validation_style(self.smiles_edit, "")
        elif result.is_valid:
            self.smiles_status.setText(result.message)
            self.smiles_status.setStyleSheet("font-size: 11px; color: #28a745;")
            self._set_validation_style(self.smiles_edit, "valid")
        else:
            self.smiles_status.setText(result.message)
            self.smiles_status.setStyleSheet("font-size: 11px; color: #dc3545;")
            self._set_validation_style(self.smiles_edit, "error")

        self._check_validity()

    def _set_validation_style(self, widget, state: str):
        """Set validation state property and refresh style."""
        widget.setProperty("validationState", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    @Slot()
    def _check_validity(self):
        """Check form validity and update submit button state."""
        valid = self.is_valid()
        self.submit_button.setEnabled(valid)
        self.validityChanged.emit(valid)

    def is_valid(self) -> bool:
        """Check if all required fields are valid."""
        # Required: problem and solution must have content
        if not self.problem_edit.toPlainText().strip():
            return False
        if not self.solution_edit.toPlainText().strip():
            return False

        # Required: at least one country selected
        if not any(cb.isChecked() for cb in self.country_checks.values()):
            return False

        # If SMILES provided, must be valid
        smiles = self.smiles_edit.text().strip()
        if smiles:
            result = validate_smiles(smiles)
            if not result.is_valid:
                return False

        return True

    def get_data(self) -> dict:
        """Collect all input data as a dictionary."""
        return {
            "problem": self.problem_edit.toPlainText().strip(),
            "solution": self.solution_edit.toPlainText().strip(),
            "constraints": self.constraints_edit.toPlainText().strip() or None,
            "smiles": self.smiles_edit.text().strip() or None,
            "countries": [
                code for code, cb in self.country_checks.items()
                if cb.isChecked()
            ],
        }

    def clear(self):
        """Clear all input fields to their default state."""
        self.problem_edit.clear()
        self.solution_edit.clear()
        self.constraints_edit.clear()
        self.smiles_edit.clear()
        for cb in self.country_checks.values():
            cb.setChecked(True)
```

### Validation Stylesheet

```python
# Add to app.py or main_window.py
# Source: https://doc.qt.io/qt-6/stylesheet-examples.html

VALIDATION_STYLESHEET = """
/* Validation states for QLineEdit */
QLineEdit[validationState="error"] {
    border: 2px solid #dc3545;
    background-color: #fff5f5;
}

QLineEdit[validationState="valid"] {
    border: 2px solid #28a745;
}

/* Default state - no validation */
QLineEdit {
    border: 1px solid #ccc;
    padding: 4px 8px;
}

/* Required field indicator styling */
QLabel {
    color: #333;
}

/* Group box styling */
QGroupBox {
    font-weight: bold;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
"""

# Apply in create_app() or MainWindow.__init__():
# app.setStyleSheet(VALIDATION_STYLESHEET)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| rdkit-pypi package | rdkit package | 2025 | Update pip install command; rdkit-pypi is deprecated |
| QRegExpValidator | QRegularExpressionValidator | Qt 6 | Use QRegularExpression instead of QRegExp |
| Manual form layout | QFormLayout | Always | Automatic label alignment and accessibility |
| QTextEdit for all text | QPlainTextEdit for plain | Always | Better performance for plain text |

**Deprecated/outdated:**
- `rdkit-pypi`: Use `rdkit` package instead (the project was renamed)
- `QRegExpValidator`: Use `QRegularExpressionValidator` with `QRegularExpression`
- Manual style manipulation: Use property-based stylesheets for cleaner code

## Open Questions

Things that couldn't be fully resolved:

1. **Additional Countries for v1**
   - What we know: Requirements specify US, EU, CN, JP minimum
   - What's unclear: Whether to include KR, AU, CA, BR in initial release
   - Recommendation: Start with the four specified; add more later based on user feedback

2. **SMILES Validation Strictness**
   - What we know: RDKit can be more or less strict (sanitize=True/False)
   - What's unclear: Should we accept unusual chemistry that RDKit rejects?
   - Recommendation: Use default sanitize=True; accept what RDKit accepts

3. **Real-time vs Submit-time Validation**
   - What we know: Current design validates SMILES in real-time, other fields on change
   - What's unclear: Is real-time validation too aggressive for some users?
   - Recommendation: Keep current behavior; it provides immediate feedback without blocking typing

## Sources

### Primary (HIGH confidence)
- [Qt for Python QPlainTextEdit](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QPlainTextEdit.html) - Official documentation
- [Qt for Python QFormLayout](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFormLayout.html) - Official documentation
- [Qt for Python QLineEdit](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QLineEdit.html) - Official documentation
- [Qt for Python QCheckBox](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QCheckBox.html) - Official documentation
- [Qt for Python QGroupBox](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGroupBox.html) - Official documentation
- [Qt Style Sheets Examples](https://doc.qt.io/qt-6/stylesheet-examples.html) - Official styling guide
- [RDKit Getting Started](https://www.rdkit.org/docs/GettingStartedInPython.html) - Official RDKit documentation
- [RDKit PyPI](https://pypi.org/project/rdkit/) - Package installation info

### Secondary (MEDIUM confidence)
- [PythonGUIs QScrollArea Tutorial](https://www.pythonguis.com/tutorials/pyside-qscrollarea/) - Comprehensive scroll area guide
- [PythonGUIs QLineEdit Docs](https://www.pythonguis.com/docs/qlineedit/) - Validation patterns
- [RDKit SMILES Validation Discussion](https://github.com/rdkit/rdkit/discussions/7677) - Community best practices

### Tertiary (LOW confidence)
- WebSearch results for validation patterns - Verified against official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Based on official Qt and RDKit documentation
- Architecture patterns: HIGH - Based on official Qt examples and documented patterns
- Pitfalls: HIGH - Based on official documentation warnings and verified community reports
- RDKit integration: HIGH - Based on official RDKit documentation and maintained examples

**Research date:** 2026-01-22
**Valid until:** 2026-03-22 (60 days - PySide6 and RDKit are stable)
