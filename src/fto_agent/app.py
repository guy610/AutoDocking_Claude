"""QApplication creation and configuration."""

import sys

from PySide6.QtWidgets import QApplication


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

    return app
