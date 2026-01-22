"""Main application window with async operation support.

This module provides the MainWindow class that serves as the primary user interface
for the FTO Search Agent. It integrates the Worker pattern and ProgressManager
for responsive background operations.
"""

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fto_agent.widgets import InputPanel, ProgressManager
from fto_agent.workers import Worker


class MainWindow(QMainWindow):
    """Main application window with async operation support.

    Features:
    - Input panel for FTO query collection
    - Status bar with progress indicator (hidden by default)
    - Cancel button for running operations
    - Integration with ProgressManager for 500ms delay

    The window remains responsive during background operations by using
    QThreadPool for execution and signals for communication.
    """

    def __init__(self):
        """Initialize the main window and all UI components."""
        super().__init__()

        # Window configuration
        self.setWindowTitle("FTO Search Agent")
        self.setMinimumSize(800, 600)

        # Thread pool for background operations
        self._thread_pool = QThreadPool()
        self._current_worker = None

        # Set up UI components
        self._setup_central_widget()
        self._setup_status_bar()

        # Create progress manager after status bar is set up
        self._progress_manager = ProgressManager(
            self._progress_bar,
            self._cancel_button,
            self.statusBar(),
        )

    def _setup_central_widget(self):
        """Create the central widget with InputPanel."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Input panel for FTO query collection
        self._input_panel = InputPanel()
        self._input_panel.submitRequested.connect(self._start_fto_search)
        layout.addWidget(self._input_panel)

    def _setup_status_bar(self):
        """Create status bar with progress indicator and cancel button."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Progress bar (hidden by default, shown after 500ms delay)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setVisible(False)
        status_bar.addPermanentWidget(self._progress_bar)

        # Cancel button (hidden by default, shown with progress bar)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._cancel_operation)
        status_bar.addPermanentWidget(self._cancel_button)

    @Slot()
    def _start_fto_search(self):
        """Start the FTO search operation.

        Called when the user clicks the Submit button in InputPanel.
        Currently shows a placeholder message; actual search will be
        implemented in Phase 3.
        """
        # Get form data (for future use in Phase 3)
        data = self._input_panel.get_data()

        # Show status message (search not yet implemented)
        self.statusBar().showMessage(
            f"FTO search not yet implemented. "
            f"Query: {len(data['countries'])} countries selected."
        )

    def _cancel_operation(self):
        """Request cancellation of the current operation."""
        if self._current_worker is not None:
            self._current_worker.cancel()
            self.statusBar().showMessage("Cancelling...")

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str):
        """Handle progress updates from worker.

        Args:
            current: Current progress value.
            total: Total items to process.
            message: Status message.
        """
        self.statusBar().showMessage(message)

    @Slot(object)
    def _on_result(self, result):
        """Handle successful completion of worker.

        Args:
            result: The result returned by the worker function.
        """
        self.statusBar().showMessage(str(result))

    @Slot(tuple)
    def _on_error(self, error_info: tuple):
        """Handle error from worker.

        Args:
            error_info: Tuple of (exception_type, value, traceback_str).
        """
        exctype, value, tb = error_info
        self.statusBar().showMessage(f"Error: {value}")

    @Slot()
    def _on_finished(self):
        """Handle worker completion (success, error, or cancelled)."""
        # Re-enable input panel
        self._input_panel.setEnabled(True)
        # Stop progress tracking and hide widgets
        self._progress_manager.stop()
        # Clear worker reference
        self._current_worker = None
