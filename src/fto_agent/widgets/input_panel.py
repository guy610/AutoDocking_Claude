"""Input panel widget for collecting FTO query inputs.

This module provides the InputPanel widget containing all five input sections
for FTO queries: problem description, solution/active, constraints, SMILES,
and target countries. Also includes API credentials management with local
persistence.
"""

import json
import os
from pathlib import Path

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


def get_config_path() -> Path:
    """Get the path to the config file for storing credentials.

    Returns:
        Path to config.json in user's app data directory.
    """
    if os.name == "nt":  # Windows
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        config_dir = Path(app_data) / "fto_agent"
    else:  # Unix/Mac
        config_dir = Path.home() / ".fto_agent"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_credentials() -> dict:
    """Load saved credentials from config file.

    Returns:
        Dictionary with credential keys, empty values if not found.
    """
    config_path = get_config_path()
    defaults = {
        "patentsview_api_key": "",
        "epo_consumer_key": "",
        "epo_consumer_secret": "",
    }

    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                saved = json.load(f)
                defaults.update(saved)
        except (json.JSONDecodeError, IOError):
            pass

    return defaults


def save_credentials(credentials: dict) -> None:
    """Save credentials to config file.

    Args:
        credentials: Dictionary with credential keys and values.
    """
    config_path = get_config_path()
    try:
        with open(config_path, "w") as f:
            json.dump(credentials, f, indent=2)
    except IOError:
        pass  # Silently fail if can't write

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

        # === API Credentials section ===
        self.credentials_group = QGroupBox("API Credentials")
        credentials_layout = QFormLayout(self.credentials_group)
        credentials_layout.setSpacing(8)

        # Load saved credentials
        saved_creds = load_credentials()

        # PatentsView API Key (USPTO)
        patentsview_container = QHBoxLayout()
        self.patentsview_key_edit = QLineEdit()
        self.patentsview_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.patentsview_key_edit.setPlaceholderText("PatentsView API key for USPTO search")
        self.patentsview_key_edit.setText(saved_creds.get("patentsview_api_key", ""))
        patentsview_container.addWidget(self.patentsview_key_edit)

        self.patentsview_show_btn = QPushButton("Show")
        self.patentsview_show_btn.setFixedWidth(50)
        self.patentsview_show_btn.setCheckable(True)
        self.patentsview_show_btn.clicked.connect(
            lambda checked: self._toggle_visibility(self.patentsview_key_edit, checked)
        )
        patentsview_container.addWidget(self.patentsview_show_btn)
        credentials_layout.addRow("PatentsView Key:", patentsview_container)

        # EPO Consumer Key
        epo_key_container = QHBoxLayout()
        self.epo_key_edit = QLineEdit()
        self.epo_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.epo_key_edit.setPlaceholderText("EPO OPS consumer key")
        self.epo_key_edit.setText(saved_creds.get("epo_consumer_key", ""))
        epo_key_container.addWidget(self.epo_key_edit)

        self.epo_key_show_btn = QPushButton("Show")
        self.epo_key_show_btn.setFixedWidth(50)
        self.epo_key_show_btn.setCheckable(True)
        self.epo_key_show_btn.clicked.connect(
            lambda checked: self._toggle_visibility(self.epo_key_edit, checked)
        )
        epo_key_container.addWidget(self.epo_key_show_btn)
        credentials_layout.addRow("EPO Key:", epo_key_container)

        # EPO Consumer Secret
        epo_secret_container = QHBoxLayout()
        self.epo_secret_edit = QLineEdit()
        self.epo_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.epo_secret_edit.setPlaceholderText("EPO OPS consumer secret")
        self.epo_secret_edit.setText(saved_creds.get("epo_consumer_secret", ""))
        epo_secret_container.addWidget(self.epo_secret_edit)

        self.epo_secret_show_btn = QPushButton("Show")
        self.epo_secret_show_btn.setFixedWidth(50)
        self.epo_secret_show_btn.setCheckable(True)
        self.epo_secret_show_btn.clicked.connect(
            lambda checked: self._toggle_visibility(self.epo_secret_edit, checked)
        )
        epo_secret_container.addWidget(self.epo_secret_show_btn)
        credentials_layout.addRow("EPO Secret:", epo_secret_container)

        # Save credentials button
        save_creds_layout = QHBoxLayout()
        save_creds_layout.addStretch()
        self.save_credentials_btn = QPushButton("Save Credentials")
        self.save_credentials_btn.clicked.connect(self._save_credentials)
        save_creds_layout.addWidget(self.save_credentials_btn)
        credentials_layout.addRow("", save_creds_layout)

        # Info label about credential storage
        creds_info = QLabel("Credentials are stored locally in your user profile.")
        creds_info.setStyleSheet("font-size: 10px; color: #666;")
        credentials_layout.addRow("", creds_info)

        layout.addWidget(self.credentials_group)

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

    def _toggle_visibility(self, line_edit: QLineEdit, show: bool):
        """Toggle visibility of a password field.

        Args:
            line_edit: The QLineEdit to toggle.
            show: True to show password, False to hide.
        """
        if show:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)

    @Slot()
    def _save_credentials(self):
        """Save API credentials to local config file and set environment variables."""
        credentials = {
            "patentsview_api_key": self.patentsview_key_edit.text().strip(),
            "epo_consumer_key": self.epo_key_edit.text().strip(),
            "epo_consumer_secret": self.epo_secret_edit.text().strip(),
        }

        # Save to file for persistence across sessions
        save_credentials(credentials)

        # Also set environment variables for current session
        if credentials["patentsview_api_key"]:
            os.environ["PATENTSVIEW_API_KEY"] = credentials["patentsview_api_key"]
        if credentials["epo_consumer_key"]:
            os.environ["EPO_OPS_CONSUMER_KEY"] = credentials["epo_consumer_key"]
        if credentials["epo_consumer_secret"]:
            os.environ["EPO_OPS_CONSUMER_SECRET"] = credentials["epo_consumer_secret"]
