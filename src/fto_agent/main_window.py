"""Main application window with async operation support.

This module provides the MainWindow class that serves as the primary user interface
for the FTO Search Agent. It integrates the Worker pattern and ProgressManager
for responsive background operations.
"""

import os

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QWidget,
)

from fto_agent.services import PatentSearchResponse, USPTOSearchError
from fto_agent.widgets import InputPanel, ProgressManager, ResultsPanel
from fto_agent.workers import Worker, create_uspto_search_worker


class MainWindow(QMainWindow):
    """Main application window with async operation support.

    Features:
    - Input panel for FTO query collection (left side)
    - Results panel for patent display (right side)
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
        """Create the central widget with InputPanel and ResultsPanel in a splitter."""
        # Create horizontal splitter for left/right layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left side: Input panel for FTO query collection
        self._input_panel = InputPanel()
        self._input_panel.submitRequested.connect(self._start_fto_search)
        splitter.addWidget(self._input_panel)

        # Right side: Results panel for patent display
        self._results_panel = ResultsPanel()
        splitter.addWidget(self._results_panel)

        # Set initial splitter sizes (50/50 split)
        splitter.setSizes([400, 400])

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
        Validates inputs, creates a USPTO search worker, and starts execution.
        """
        # Get form data
        data = self._input_panel.get_data()

        # Check if US is selected (USPTO search requires US)
        if "US" not in data["countries"]:
            self.statusBar().showMessage(
                "USPTO search requires US country selection"
            )
            return

        # Get API key from environment
        api_key = os.environ.get("PATENTSVIEW_API_KEY")
        if not api_key:
            self.statusBar().showMessage(
                "PATENTSVIEW_API_KEY environment variable not set"
            )
            return

        # Disable input panel during search
        self._input_panel.setEnabled(False)

        # Set results panel to loading state
        self._results_panel.set_loading(True)

        # Create worker for USPTO search
        self._current_worker = create_uspto_search_worker(data, api_key)

        # Connect signals
        self._current_worker.signals.progress.connect(self._on_progress)
        self._current_worker.signals.result.connect(self._on_search_result)
        self._current_worker.signals.error.connect(self._on_search_error)
        self._current_worker.signals.finished.connect(self._on_finished)

        # Start progress manager and worker
        self._progress_manager.start(self._current_worker)
        self._thread_pool.start(self._current_worker)

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
    def _on_search_result(self, result: PatentSearchResponse):
        """Handle successful completion of USPTO search.

        Args:
            result: PatentSearchResponse with search results.
        """
        self._results_panel.set_results(result)
        self.statusBar().showMessage(f"Found {result.total_hits} patents")

    @Slot(tuple)
    def _on_search_error(self, error_info: tuple):
        """Handle error from USPTO search worker.

        Args:
            error_info: Tuple of (exception_type, value, traceback_str).
        """
        exctype, value, tb = error_info

        # Extract error message
        if isinstance(value, USPTOSearchError):
            message = value.message
        else:
            message = str(value)

        # Display error in results panel and status bar
        self._results_panel.set_error(message)
        self.statusBar().showMessage(f"Search failed: {message}")

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
        # Stop loading state in results panel
        self._results_panel.set_loading(False)
        # Re-enable input panel
        self._input_panel.setEnabled(True)
        # Stop progress tracking and hide widgets
        self._progress_manager.stop()
        # Clear worker reference
        self._current_worker = None
