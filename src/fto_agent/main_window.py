"""Main application window with async operation support.

This module provides the MainWindow class that serves as the primary user interface
for the FTO Search Agent. It integrates the Worker pattern and ProgressManager
for responsive background operations.
"""

import time

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fto_agent.widgets import ProgressManager
from fto_agent.workers import Worker


def _demo_work(is_cancelled, progress_callback):
    """Demo operation that takes ~5 seconds and can be cancelled.

    This function demonstrates the Worker pattern with:
    - Cooperative cancellation checking
    - Progress reporting
    - Return value on completion

    Args:
        is_cancelled: Callable that returns True if cancellation requested.
        progress_callback: Callable(current, total, message) for progress updates.

    Returns:
        str: Result message (completion or cancellation status).
    """
    total = 100
    for i in range(total):
        if is_cancelled():
            return "Operation cancelled"
        progress_callback(i + 1, total, f"Processing item {i + 1} of {total}...")
        time.sleep(0.05)  # 50ms * 100 = 5 seconds total
    return "Demo operation completed successfully!"


class MainWindow(QMainWindow):
    """Main application window with async operation support.

    Features:
    - Status bar with progress indicator (hidden by default)
    - Cancel button for running operations
    - Integration with ProgressManager for 500ms delay
    - Demo button to test async infrastructure

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
        """Create the central widget with main content."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Status label for displaying operation results
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(self._status_label)

        # Demo button to test async infrastructure
        self._demo_button = QPushButton("Run Demo Operation")
        self._demo_button.setFixedWidth(200)
        self._demo_button.clicked.connect(self._start_demo_operation)
        layout.addWidget(self._demo_button)

        # Push everything to the top
        layout.addStretch()

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

    def _start_demo_operation(self):
        """Start the demo background operation."""
        # Disable button to prevent multiple concurrent operations
        self._demo_button.setEnabled(False)
        self._status_label.setText("Starting operation...")

        # Start progress tracking (will show after 500ms)
        self._progress_manager.start()

        # Create and configure worker
        worker = Worker(_demo_work)

        # Connect signals for progress and completion
        worker.signals.progress.connect(self._progress_manager.update)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)

        # Store reference for cancellation
        self._current_worker = worker

        # Start worker in thread pool
        self._thread_pool.start(worker)

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
        self._status_label.setText(message)

    @Slot(object)
    def _on_result(self, result):
        """Handle successful completion of worker.

        Args:
            result: The result returned by the worker function.
        """
        self._status_label.setText(str(result))

    @Slot(tuple)
    def _on_error(self, error_info: tuple):
        """Handle error from worker.

        Args:
            error_info: Tuple of (exception_type, value, traceback_str).
        """
        exctype, value, tb = error_info
        self._status_label.setText(f"Error: {value}")

    @Slot()
    def _on_finished(self):
        """Handle worker completion (success, error, or cancelled)."""
        # Re-enable the demo button
        self._demo_button.setEnabled(True)
        # Stop progress tracking and hide widgets
        self._progress_manager.stop()
        # Clear worker reference
        self._current_worker = None
