"""Entry point for running FTO Agent as a module: python -m fto_agent"""

import sys

from fto_agent.app import create_app
from PySide6.QtWidgets import QMainWindow


def main():
    """Launch the FTO Search Agent application."""
    app = create_app()

    # Create and show main window
    window = QMainWindow()
    window.setWindowTitle("FTO Search Agent")
    window.setMinimumSize(800, 600)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
