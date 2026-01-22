"""QApplication creation and configuration."""

import sys

from PySide6.QtWidgets import QApplication

# Stylesheet for validation visual feedback on input widgets.
# Uses Qt property selectors to style widgets based on validation state.
VALIDATION_STYLESHEET = """
/* Validation states for QLineEdit (SMILES input) */
QLineEdit[validationState="error"] {
    border: 2px solid #dc3545;
    background-color: #fff5f5;
}

QLineEdit[validationState="valid"] {
    border: 2px solid #28a745;
}

/* Default state - no validation applied */
QLineEdit {
    border: 1px solid #ccc;
    padding: 4px 8px;
}

/* Group box styling for country selection */
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


def create_app() -> QApplication:
    """Create and configure the QApplication instance.

    Returns:
        QApplication: The configured application instance.
    """
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("FTO Search Agent")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("FTO Agent")
    app.setOrganizationDomain("fto-agent.local")

    # Apply validation stylesheet for visual input feedback
    app.setStyleSheet(VALIDATION_STYLESHEET)

    return app
