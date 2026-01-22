"""Input panel widget for collecting FTO query inputs.

This module provides the InputPanel widget containing all five input sections
for FTO queries: problem description, solution/active, constraints, SMILES,
and target countries.
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fto_agent.validators.smiles import is_rdkit_available, validate_smiles

# Countries available for FTO search
COUNTRIES = [
    ("US", "United States"),
    ("EU", "European Union"),
    ("CN", "China"),
    ("JP", "Japan"),
]


class InputPanel(QWidget):
    """Panel for collecting FTO query inputs.

    This widget provides input fields for:
    - Problem description (required)
    - Solution/active description (required)
    - Constraints (optional)
    - SMILES notation (optional, validated with RDKit)
    - Target countries (at least one required)

    Signals:
        validityChanged(bool): Emitted when form validity changes.
        submitRequested(): Emitted when user clicks the submit button.
    """

    validityChanged = Signal(bool)
    submitRequested = Signal()

    def __init__(self, parent=None):
        """Initialize the input panel.

        Args:
            parent: Optional parent widget.
        """
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
        self.smiles_edit.setPlaceholderText("Paste SMILES notation (optional)...")
        smiles_layout.addWidget(self.smiles_edit)

        self.smiles_status = QLabel("")
        self.smiles_status.setStyleSheet("font-size: 11px;")
        smiles_layout.addWidget(self.smiles_status)

        # Show RDKit availability status
        if not is_rdkit_available():
            self.smiles_edit.setEnabled(False)
            self.smiles_status.setText(
                "RDKit not installed - SMILES validation unavailable"
            )
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
        """Set validation state property and refresh style.

        Args:
            widget: The widget to update.
            state: Validation state ("", "valid", or "error").
        """
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
        """Check if all required fields are valid.

        Returns:
            True if form is valid and can be submitted.
        """
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
        """Collect all input data as a dictionary.

        Returns:
            Dictionary with keys: problem, solution, constraints, smiles, countries.
        """
        return {
            "problem": self.problem_edit.toPlainText().strip(),
            "solution": self.solution_edit.toPlainText().strip(),
            "constraints": self.constraints_edit.toPlainText().strip() or None,
            "smiles": self.smiles_edit.text().strip() or None,
            "countries": [
                code for code, cb in self.country_checks.items() if cb.isChecked()
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
