"""Unit tests for Worker and WorkerSignals classes.

Tests verify the async worker pattern including:
- Signal existence and connectivity
- Function execution and result emission
- Progress callback handling
- Error handling and signal emission
- Cooperative cancellation
- Kwargs pass-through to target functions
"""

import pytest
from PySide6.QtCore import QCoreApplication, Signal

from fto_agent.workers import Worker, WorkerSignals


@pytest.fixture(scope="session")
def qapp():
    """Create a QCoreApplication for the test session.

    Required for Qt signals to work in tests.
    """
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class TestWorkerSignals:
    """Tests for WorkerSignals class."""

    def test_worker_signals_exist(self, qapp):
        """Verify WorkerSignals has all required signals."""
        signals = WorkerSignals()

        # Check each signal exists and is a Signal type
        assert hasattr(signals, "started"), "WorkerSignals missing 'started' signal"
        assert hasattr(signals, "progress"), "WorkerSignals missing 'progress' signal"
        assert hasattr(signals, "finished"), "WorkerSignals missing 'finished' signal"
        assert hasattr(signals, "result"), "WorkerSignals missing 'result' signal"
        assert hasattr(signals, "error"), "WorkerSignals missing 'error' signal"


class TestWorkerExecution:
    """Tests for Worker execution and signal emission."""

    def test_worker_executes_function(self, qapp):
        """Worker executes function and emits result signal on success."""
        def simple_function(is_cancelled, progress_callback):
            return "success"

        worker = Worker(simple_function)

        # Track signal emissions
        results = []
        finished_called = []

        worker.signals.result.connect(lambda r: results.append(r))
        worker.signals.finished.connect(lambda: finished_called.append(True))

        # Run synchronously (not via threadpool)
        worker.run()

        # Verify result signal emitted with "success"
        assert len(results) == 1, "Result signal should be emitted once"
        assert results[0] == "success", f"Expected 'success', got {results[0]}"

        # Verify finished signal emitted
        assert len(finished_called) == 1, "Finished signal should be emitted"

    def test_worker_emits_progress(self, qapp):
        """Worker emits progress signals from target function."""
        def progress_function(is_cancelled, progress_callback):
            progress_callback(50, 100, "halfway")
            return "done"

        worker = Worker(progress_function)

        # Track progress emissions
        progress_calls = []
        worker.signals.progress.connect(
            lambda c, t, m: progress_calls.append((c, t, m))
        )

        worker.run()

        # Verify progress signal emitted
        assert len(progress_calls) == 1, "Progress should be emitted once"
        assert progress_calls[0] == (50, 100, "halfway"), \
            f"Expected (50, 100, 'halfway'), got {progress_calls[0]}"

    def test_worker_handles_exception(self, qapp):
        """Worker emits error signal on exception, not result signal."""
        def failing_function(is_cancelled, progress_callback):
            raise ValueError("test error")

        worker = Worker(failing_function)

        # Track signal emissions
        results = []
        errors = []
        finished_called = []

        worker.signals.result.connect(lambda r: results.append(r))
        worker.signals.error.connect(lambda e: errors.append(e))
        worker.signals.finished.connect(lambda: finished_called.append(True))

        worker.run()

        # Verify error signal emitted
        assert len(errors) == 1, "Error signal should be emitted once"

        # Check error tuple contains ValueError
        exc_type, exc_value, tb_str = errors[0]
        assert exc_type is ValueError, f"Expected ValueError, got {exc_type}"
        assert "test error" in str(exc_value), \
            f"Error message should contain 'test error': {exc_value}"

        # Verify result signal NOT emitted
        assert len(results) == 0, "Result signal should not be emitted on error"

        # Verify finished still emitted
        assert len(finished_called) == 1, "Finished signal should still be emitted"

    def test_worker_cancellation(self, qapp):
        """Worker cancellation stops execution and skips result emission."""
        execution_iterations = []

        def cancellable_function(is_cancelled, progress_callback):
            for i in range(10):
                if is_cancelled():
                    return None  # Early return on cancellation
                execution_iterations.append(i)
            return "completed"

        worker = Worker(cancellable_function)

        # Track result emissions
        results = []
        worker.signals.result.connect(lambda r: results.append(r))

        # Cancel before running
        worker.cancel()

        worker.run()

        # Verify result signal NOT emitted when cancelled
        assert len(results) == 0, \
            "Result signal should not be emitted when cancelled"

        # Since we cancelled before run, the function should check is_cancelled
        # immediately and return None. No iterations should happen.
        assert len(execution_iterations) == 0, \
            "Function should check is_cancelled and return early"

    def test_worker_passes_kwargs(self, qapp):
        """Worker passes custom kwargs to target function."""
        received_kwargs = {}

        def kwargs_function(is_cancelled, progress_callback, **kwargs):
            received_kwargs.update(kwargs)
            return "done"

        worker = Worker(kwargs_function, custom_arg="custom_value", another=42)
        worker.run()

        # Verify custom kwargs received
        assert "custom_arg" in received_kwargs, "custom_arg should be passed"
        assert received_kwargs["custom_arg"] == "custom_value", \
            f"Expected 'custom_value', got {received_kwargs['custom_arg']}"
        assert "another" in received_kwargs, "another should be passed"
        assert received_kwargs["another"] == 42, \
            f"Expected 42, got {received_kwargs['another']}"

    def test_worker_emits_started_signal(self, qapp):
        """Worker emits started signal when execution begins."""
        def simple_function(is_cancelled, progress_callback):
            return "done"

        worker = Worker(simple_function)

        started_called = []
        worker.signals.started.connect(lambda: started_called.append(True))

        worker.run()

        assert len(started_called) == 1, "Started signal should be emitted"
