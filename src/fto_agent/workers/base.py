"""Base worker classes for thread-safe background operations.

This module provides the Worker and WorkerSignals classes that form the foundation
for all background operations in the FTO Search Agent. The pattern follows Qt best
practices for thread-safe GUI updates using Signal/Slot mechanism.

Pattern source: Phase 1 Research - Pattern 2 (Cancellable Worker)
"""

import sys
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals for worker thread communication.

    All signals are emitted from the worker thread and received in the main thread
    via Qt's queued connection mechanism, ensuring thread-safe GUI updates.

    Signals:
        started: Emitted when worker begins execution.
        progress: Emitted with (current, total, message) during execution.
            - current (int): Current progress value (0 to total).
            - total (int): Total items to process (0 for indeterminate).
            - message (str): Status message describing current operation.
        finished: Emitted when worker completes (success, failure, or cancelled).
        result: Emitted with the operation result on success (not emitted if cancelled).
        error: Emitted with (exception_type, value, traceback_str) on failure.
            - exception_type: The exception class (e.g., ValueError).
            - value: The exception instance with message.
            - traceback_str: Full traceback as a string for debugging.
    """

    started = Signal()
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal()
    result = Signal(object)
    error = Signal(tuple)  # (exctype, value, traceback_str)


class Worker(QRunnable):
    """Executes a function in a thread pool with cancellation support.

    The Worker class wraps any callable and runs it in Qt's thread pool,
    providing progress reporting and cooperative cancellation.

    Usage:
        def my_operation(is_cancelled, progress_callback, arg1, arg2):
            for i in range(100):
                if is_cancelled():
                    return None  # Cancelled
                progress_callback(i + 1, 100, f"Processing {i + 1}...")
                # Do work here
            return "Result"

        worker = Worker(my_operation, arg1_value, arg2_value)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(worker)

    The target function MUST accept these keyword arguments:
        - is_cancelled: A callable that returns True if cancellation was requested.
        - progress_callback: A callable(current, total, message) for progress updates.

    Note:
        Do NOT use QThread.terminate() - always use cancel() for cooperative cancellation.
        The worker function must check is_cancelled() periodically and return early.
    """

    def __init__(self, fn, *args, **kwargs):
        """Initialize the worker with a function and its arguments.

        Args:
            fn: The function to execute in the background thread.
                Must accept is_cancelled and progress_callback keyword arguments.
            *args: Positional arguments to pass to fn.
            **kwargs: Keyword arguments to pass to fn.
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker.

        Sets the cancellation flag that the worker function should check
        periodically via the is_cancelled callback. This is cooperative
        cancellation - the worker function must explicitly check and
        honor the cancellation request.
        """
        self._is_cancelled = True

    @property
    def is_cancelled(self):
        """Check if cancellation has been requested.

        Returns:
            bool: True if cancel() has been called.
        """
        return self._is_cancelled

    @Slot()
    def run(self):
        """Execute the worker function with error handling.

        This method is called by QThreadPool when a thread becomes available.
        It emits signals at each stage of execution:
        - started: When execution begins
        - result: On successful completion (not cancelled)
        - error: On exception
        - finished: Always, at the end
        """
        self.signals.started.emit()
        try:
            # Pass cancel check and progress callback to the function
            result = self.fn(
                *self.args,
                is_cancelled=lambda: self._is_cancelled,
                progress_callback=self.signals.progress.emit,
                **self.kwargs
            )
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            if not self._is_cancelled:
                self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
