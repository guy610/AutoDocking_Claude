"""Progress management with 500ms delayed display.

This module provides the ProgressManager class that implements requirement APP-02:
progress indicators during search/analysis operations with 500ms delay.

The 500ms delay prevents flickering for fast operations - if an operation completes
in under 500ms, the user never sees a progress bar at all.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QProgressBar, QPushButton, QStatusBar


class ProgressManager:
    """Manages progress display with 500ms delay per APP-02 requirement.

    Shows progress bar and cancel button only if operation exceeds 500ms.
    Supports both determinate (known total) and indeterminate (unknown duration) modes.

    Usage:
        progress_manager = ProgressManager(progress_bar, cancel_button, status_bar)

        # Starting an operation
        progress_manager.start()

        # Update progress (from worker signal)
        progress_manager.update(current=50, total=100, message="Processing...")

        # Operation complete
        progress_manager.stop()

    Attributes:
        DELAY_MS: Class constant for the display delay (500ms).
    """

    DELAY_MS = 500

    def __init__(
        self,
        progress_bar: QProgressBar,
        cancel_button: QPushButton,
        status_bar: QStatusBar,
    ):
        """Initialize the progress manager with widget references.

        Args:
            progress_bar: The QProgressBar widget to show/hide and update.
            cancel_button: The QPushButton for cancellation (shown with progress bar).
            status_bar: The QStatusBar for displaying status messages.
        """
        self._progress_bar = progress_bar
        self._cancel_button = cancel_button
        self._status_bar = status_bar
        self._is_running = False

        # Create single-shot timer for delayed display
        self._show_timer = QTimer()
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(self.DELAY_MS)
        self._show_timer.timeout.connect(self._show_widgets)

        # Ensure widgets start hidden
        self._progress_bar.setVisible(False)
        self._cancel_button.setVisible(False)

    def start(self):
        """Start tracking an operation.

        Starts the 500ms timer. If the operation exceeds 500ms, the progress
        bar and cancel button will be shown. If stop() is called before 500ms,
        the user never sees the progress widgets.
        """
        self._is_running = True
        # Reset progress bar to determinate mode with 0%
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        # Start the delay timer (widgets shown after 500ms)
        self._show_timer.start()

    def _show_widgets(self):
        """Show progress widgets after delay expires.

        Only shows widgets if the operation is still running (not cancelled
        or completed before the 500ms delay).
        """
        if self._is_running:
            self._progress_bar.setVisible(True)
            self._cancel_button.setVisible(True)

    def update(self, current: int, total: int, message: str = ""):
        """Update progress display.

        Args:
            current: Current progress value (0 to total).
            total: Total items to process.
                   If > 0: Determinate mode (shows percentage).
                   If == 0: Indeterminate mode (shows animation).
            message: Optional status message to display in status bar.
        """
        if total > 0:
            # Determinate mode - show actual progress
            self._progress_bar.setMinimum(0)
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)
        else:
            # Indeterminate mode - animated "busy" indicator
            self._progress_bar.setMinimum(0)
            self._progress_bar.setMaximum(0)

        if message:
            self._status_bar.showMessage(message)

    def stop(self):
        """Stop tracking and hide progress widgets.

        Call this when the operation completes (successfully, with error,
        or cancelled). Stops the delay timer and hides all progress widgets.
        """
        self._is_running = False
        # Stop timer in case operation finished before 500ms
        self._show_timer.stop()
        # Hide widgets
        self._progress_bar.setVisible(False)
        self._cancel_button.setVisible(False)
        # Clear status message
        self._status_bar.clearMessage()
