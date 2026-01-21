# Phase 1: Foundation and Async Infrastructure - Research

**Researched:** 2026-01-21
**Domain:** PySide6 GUI framework, async patterns, progress indicators, responsive UI
**Confidence:** HIGH

## Summary

This research establishes the foundation patterns for building a responsive PySide6 desktop application with progress indicators and cancellable long-running operations. The primary challenge is keeping the GUI responsive while performing background operations (patent searches, API calls, AI analysis) that may take seconds to minutes.

PySide6 provides two main approaches for async operations: **QThread/QThreadPool with signals/slots** (mature, well-documented) and **QtAsyncio** (technical preview, simpler syntax). Given the need for reliability in a production application and the requirement to cancel operations, the **QThreadPool + Worker pattern** is recommended as the primary approach.

The key architectural decisions are:
1. Use QThreadPool with QRunnable workers for background operations
2. Use Signal/Slot mechanism for thread-safe GUI updates
3. Use QProgressBar in status bar for modeless progress (with optional QProgressDialog for modal operations)
4. Implement cancellation via flag variables checked in worker loops
5. Show progress indicators after 500ms delay per requirement APP-02

**Primary recommendation:** Implement a reusable Worker/WorkerSignals pattern that all future background operations can use, with built-in progress reporting and cancellation support.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.6+ | Qt bindings for Python | LGPL license, official Qt support, QtAsyncio integration |
| Python | 3.11+ | Runtime | Match user's environment (3.11.9), stable async support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PySide6.QtCore.QThread | Built-in | Thread management | Worker object pattern for event loop tasks |
| PySide6.QtCore.QThreadPool | Built-in | Thread pool management | Recommended for fire-and-forget workers |
| PySide6.QtCore.QRunnable | Built-in | Worker container | Encapsulates work to run in QThreadPool |
| PySide6.QtCore.Signal/Slot | Built-in | Thread-safe communication | All GUI updates from background threads |
| PySide6.QtWidgets.QProgressBar | Built-in | Progress display | Status bar integration |
| PySide6.QtWidgets.QProgressDialog | Built-in | Modal progress dialog | Optional for blocking operations |
| PySide6.QtAsyncio | Built-in (preview) | asyncio integration | Future consideration for simpler async code |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| QThreadPool | QThread subclass | QThread better when event loop needed; QThreadPool simpler for most cases |
| QThreadPool | QtAsyncio | QtAsyncio is in technical preview; lacks Level 2 API (transports/protocols) |
| QThreadPool | Python threading | Python threads require manual Qt signal integration; GIL limits parallelism |
| QProgressBar | QProgressDialog | Dialog is modal/blocking; status bar progress is non-intrusive |

**Installation:**
```bash
pip install PySide6>=6.6
```

## Architecture Patterns

### Recommended Project Structure
```
src/
    fto_agent/
        __init__.py
        __main__.py           # Entry point: python -m fto_agent
        app.py                # QApplication setup
        main_window.py        # QMainWindow subclass
        workers/
            __init__.py
            base.py           # Worker, WorkerSignals base classes
        widgets/
            __init__.py
            progress.py       # Progress bar management
        utils/
            __init__.py
tests/
    __init__.py
    test_workers.py
pyproject.toml
```

### Pattern 1: Worker Signals (Thread-Safe Communication)

**What:** A QObject subclass that defines signals for worker-to-GUI communication
**When to use:** Every background operation that needs to report progress, results, or errors

```python
# Source: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/
from PySide6.QtCore import QObject, Signal

class WorkerSignals(QObject):
    """Signals for worker thread communication.

    Signals:
        started: Emitted when worker begins execution
        progress: Emitted with (current, total, message) during execution
        finished: Emitted when worker completes (success or failure)
        result: Emitted with the operation result on success
        error: Emitted with (exception_type, value, traceback_str) on failure
    """
    started = Signal()
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal()
    result = Signal(object)
    error = Signal(tuple)  # (exctype, value, traceback_str)
```

### Pattern 2: Cancellable Worker (QRunnable)

**What:** A QRunnable subclass with cancellation support via flag variable
**When to use:** All background operations that should be cancellable

```python
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html
# Source: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/
import sys
import traceback
from PySide6.QtCore import QRunnable, Slot

class Worker(QRunnable):
    """Executes a function in a thread pool with cancellation support."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation. Worker must check is_cancelled periodically."""
        self._is_cancelled = True

    @property
    def is_cancelled(self):
        return self._is_cancelled

    @Slot()
    def run(self):
        """Execute the worker function with error handling."""
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
```

### Pattern 3: Progress Bar in Status Bar

**What:** A QProgressBar added to QMainWindow's status bar with show/hide control
**When to use:** Main window setup, modeless progress indication

```python
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QStatusBar.html
from PySide6.QtWidgets import QMainWindow, QProgressBar, QPushButton
from PySide6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Status bar progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setVisible(False)  # Hidden by default
        self.progress_bar.setMaximumWidth(200)

        # Cancel button (hidden by default)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)

        # Add to status bar (permanent = won't be hidden by messages)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.cancel_button)

        # Timer for delayed progress display (500ms per APP-02)
        self._progress_timer = QTimer()
        self._progress_timer.setSingleShot(True)
        self._progress_timer.timeout.connect(self._show_progress)

    def start_progress(self, show_cancel=True):
        """Start progress with 500ms delay before showing."""
        self._pending_cancel_visible = show_cancel
        self._progress_timer.start(500)  # Show after 500ms

    def _show_progress(self):
        """Actually show progress (called by timer)."""
        self.progress_bar.setVisible(True)
        self.cancel_button.setVisible(self._pending_cancel_visible)

    def update_progress(self, current, total, message=""):
        """Update progress bar value."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            # Indeterminate progress
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)
        if message:
            self.statusBar().showMessage(message)

    def stop_progress(self):
        """Hide progress indicator."""
        self._progress_timer.stop()
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.statusBar().clearMessage()
```

### Pattern 4: Operation Manager (Coordinating Workers)

**What:** A class that manages running workers, handles cancellation, and coordinates with the GUI
**When to use:** Complex operations with multiple steps or concurrent workers

```python
from PySide6.QtCore import QObject, QThreadPool

class OperationManager(QObject):
    """Manages background operations and their lifecycle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.threadpool = QThreadPool()
        self._current_worker = None

    def run_operation(self, fn, *args,
                      on_progress=None,
                      on_result=None,
                      on_error=None,
                      on_finished=None,
                      **kwargs):
        """Run an operation in background."""
        # Cancel any existing operation
        self.cancel_current()

        worker = Worker(fn, *args, **kwargs)
        self._current_worker = worker

        # Connect signals
        if on_progress:
            worker.signals.progress.connect(on_progress)
        if on_result:
            worker.signals.result.connect(on_result)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_finished:
            worker.signals.finished.connect(on_finished)

        self.threadpool.start(worker)
        return worker

    def cancel_current(self):
        """Cancel the currently running operation."""
        if self._current_worker:
            self._current_worker.cancel()
            self._current_worker = None

    def wait_for_done(self):
        """Wait for all operations to complete."""
        self.threadpool.waitForDone()
```

### Anti-Patterns to Avoid

- **Updating GUI from worker thread:** Never call widget methods directly from a worker. Always emit signals and let the main thread handle GUI updates via connected slots.

- **Using terminate() on QThread:** This is dangerous and can corrupt data. Always use cancellation flags and cooperative cancellation.

- **Blocking the main thread:** Never call `time.sleep()` or long-running functions in the main thread. Always offload to workers.

- **Forgetting app.exec():** The application event loop must be started with `app.exec()` or the GUI won't respond.

- **Signal emission from callbacks in workers:** Don't emit signals from nested callbacks in workers. Use `QMetaObject.invokeMethod` if needed, or restructure to emit from the worker's run() method.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread pool management | Custom thread management | QThreadPool | Handles thread reuse, queuing, optimal thread count |
| Thread-safe GUI updates | Shared state + locks | Signal/Slot | Qt handles queued connections automatically |
| Progress estimation | Custom timing logic | QProgressDialog.minimumDuration | Built-in estimation and delayed display |
| Async operations | Python threading + queues | QRunnable + WorkerSignals | Integrated with Qt event loop |
| Cancellation | Thread.terminate() | Flag variable + periodic check | Safe, cooperative cancellation |

**Key insight:** Qt's threading infrastructure is deeply integrated with its event loop. Using Python's raw threading or asyncio without proper Qt integration leads to race conditions and frozen GUIs.

## Common Pitfalls

### Pitfall 1: GUI Updates from Worker Threads

**What goes wrong:** Calling widget methods (setText, setValue, etc.) directly from a worker thread causes crashes or undefined behavior.

**Why it happens:** Qt widgets are not thread-safe. They must only be modified from the main thread.

**How to avoid:**
1. Always emit signals from workers
2. Connect signals to slots in the main thread
3. Use `@Slot()` decorator on receiving methods

**Warning signs:** Random crashes, visual glitches, "QObject: Cannot create children for a parent that is in a different thread" errors.

### Pitfall 2: Blocking the Event Loop

**What goes wrong:** The application freezes and becomes unresponsive during long operations.

**Why it happens:** Long-running code in the main thread prevents the event loop from processing events.

**How to avoid:**
1. Offload ALL operations > 100ms to background threads
2. Use QTimer for periodic tasks instead of while loops
3. Never call time.sleep() in the main thread

**Warning signs:** Application stops responding to clicks, window becomes greyed out, "Not Responding" in taskbar.

### Pitfall 3: Forgetting to Keep Worker References

**What goes wrong:** Workers get garbage collected before they finish, causing silent failures.

**Why it happens:** Python's garbage collector deletes objects with no references.

**How to avoid:**
1. Store worker references in instance variables
2. Use QThreadPool (manages worker lifecycle)
3. Connect finished signal to cleanup

**Warning signs:** Operations never complete, callbacks never fire, no errors shown.

### Pitfall 4: Improper Cancellation

**What goes wrong:** Cancelled operations continue running, or the app hangs waiting for cancellation.

**Why it happens:** Using terminate() corrupts state; not checking flags means operation continues.

**How to avoid:**
1. Use a flag variable (`_is_cancelled`)
2. Check the flag periodically in loops (every iteration or every N items)
3. Ensure worker functions accept and use the `is_cancelled` callback

**Warning signs:** Cancel button does nothing, duplicate operations run simultaneously.

### Pitfall 5: Race Conditions with Progress Updates

**What goes wrong:** Progress bar shows incorrect values or jumps around.

**Why it happens:** Multiple progress signals queued and processed out of order.

**How to avoid:**
1. Use queued connections (default for cross-thread signals)
2. Include sequence numbers if needed
3. Use `Qt.QueuedConnection` explicitly if unsure

**Warning signs:** Progress goes backwards, shows values > maximum, shows 100% then back to 50%.

## Code Examples

Verified patterns from official sources:

### Complete Application Skeleton

```python
# Source: https://doc.qt.io/qtforpython-6/
# Source: https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/

import sys
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QProgressBar, QLabel
)
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""
    started = Signal()
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal()
    result = Signal(object)
    error = Signal(tuple)


class Worker(QRunnable):
    """Worker thread for running background tasks."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker."""
        self._is_cancelled = True

    @Slot()
    def run(self):
        """Execute the worker function."""
        self.signals.started.emit()
        try:
            result = self.fn(
                *self.args,
                is_cancelled=lambda: self._is_cancelled,
                progress_callback=self.signals.progress.emit,
                **self.kwargs
            )
        except Exception:
            import traceback
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            if not self._is_cancelled:
                self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


def example_long_operation(is_cancelled, progress_callback):
    """Example operation that reports progress and can be cancelled."""
    total = 100
    for i in range(total):
        if is_cancelled():
            return None  # Cancelled
        progress_callback(i + 1, total, f"Processing item {i + 1}...")
        time.sleep(0.05)  # Simulate work
    return "Operation completed successfully"


class MainWindow(QMainWindow):
    """Main application window with async operation support."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FTO Search Agent")
        self.setMinimumSize(800, 600)

        # Thread pool
        self.threadpool = QThreadPool()
        self._current_worker = None

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Status label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Start button
        self.start_button = QPushButton("Start Operation")
        self.start_button.clicked.connect(self.start_operation)
        layout.addWidget(self.start_button)

        # Status bar with progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_operation)

        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.cancel_button)

    def start_operation(self):
        """Start a background operation."""
        self.start_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.cancel_button.setVisible(True)

        worker = Worker(example_long_operation)
        worker.signals.progress.connect(self.on_progress)
        worker.signals.result.connect(self.on_result)
        worker.signals.error.connect(self.on_error)
        worker.signals.finished.connect(self.on_finished)

        self._current_worker = worker
        self.threadpool.start(worker)

    def cancel_operation(self):
        """Cancel the current operation."""
        if self._current_worker:
            self._current_worker.cancel()
            self.statusBar().showMessage("Cancelling...")

    @Slot(int, int, str)
    def on_progress(self, current, total, message):
        """Handle progress updates from worker."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    @Slot(object)
    def on_result(self, result):
        """Handle successful result from worker."""
        self.status_label.setText(str(result))

    @Slot(tuple)
    def on_error(self, error_info):
        """Handle error from worker."""
        exctype, value, tb = error_info
        self.status_label.setText(f"Error: {value}")

    @Slot()
    def on_finished(self):
        """Handle worker completion."""
        self.start_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self._current_worker = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

### 500ms Delayed Progress Display

```python
# Source: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QProgressDialog.html
from PySide6.QtCore import QTimer

class ProgressManager:
    """Manages progress display with 500ms delay per APP-02 requirement."""

    def __init__(self, progress_bar, cancel_button):
        self.progress_bar = progress_bar
        self.cancel_button = cancel_button
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show)
        self._is_running = False

    def start(self):
        """Start operation - show progress after 500ms."""
        self._is_running = True
        self._timer.start(500)

    def _show(self):
        """Actually show the progress bar (called by timer)."""
        if self._is_running:
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)

    def update(self, current, total):
        """Update progress value."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def stop(self):
        """Stop and hide progress."""
        self._is_running = False
        self._timer.stop()
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
```

### Indeterminate Progress (for API calls)

```python
# For operations where duration is unknown (e.g., single API call)
def set_indeterminate_progress(progress_bar):
    """Set progress bar to indeterminate mode (spinning/pulsing)."""
    progress_bar.setMinimum(0)
    progress_bar.setMaximum(0)  # This makes it indeterminate

def set_determinate_progress(progress_bar, total):
    """Set progress bar back to determinate mode."""
    progress_bar.setMinimum(0)
    progress_bar.setMaximum(total)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| QThread subclass with run() | Worker object + moveToThread | Qt 5+ | Cleaner separation, reusable workers |
| QThread subclass | QThreadPool + QRunnable | Qt 5+ | Automatic thread management, pooling |
| Manual threading + queues | Signal/Slot connections | Always | Thread-safe by default |
| Python asyncio (raw) | QtAsyncio (preview) | PySide6 6.6.2 | Native Qt integration |
| *.pyproject files | pyproject.toml | PySide6 6.9.0 | Standard Python packaging |

**Deprecated/outdated:**
- `QThread.terminate()`: Dangerous, causes data corruption. Use cooperative cancellation.
- `*.pyproject` files: Deprecated in favor of `pyproject.toml` (PySide6 6.9.0+).
- Direct widget manipulation from threads: Never supported, always wrong.

## Open Questions

Things that couldn't be fully resolved:

1. **QtAsyncio Production Readiness**
   - What we know: QtAsyncio is in "technical preview" as of PySide6 6.6.2. It covers Level 1 API (event loop, tasks) but not Level 2 (transports, protocols).
   - What's unclear: Whether it's stable enough for production use in 2026.
   - Recommendation: Use QThreadPool pattern for Phase 1. Can revisit QtAsyncio for simpler async operations in later phases if needed.

2. **Thread Count Optimization**
   - What we know: QThreadPool.globalInstance() manages optimal thread count automatically.
   - What's unclear: Whether to use global pool or dedicated pool for this application.
   - Recommendation: Use global pool initially; can optimize later if needed.

3. **Progress Granularity for API Calls**
   - What we know: Patent API calls are single requests with indeterminate duration.
   - What's unclear: Best UX pattern for indeterminate progress vs. determinate.
   - Recommendation: Use indeterminate progress (min=max=0) for single API calls; determinate for batch operations.

## Sources

### Primary (HIGH confidence)
- [Qt for Python QThread Documentation](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html) - Official Qt docs on threading
- [Qt for Python QProgressDialog Documentation](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QProgressDialog.html) - Official progress dialog docs
- [Qt for Python QtAsyncio Documentation](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html) - Official QtAsyncio docs
- [Qt for Python Signals and Slots Tutorial](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html) - Official signal/slot tutorial
- [Qt for Python Thread Signals Example](https://doc.qt.io/qtforpython-6/examples/example_widgets_thread_signals.html) - Official threading example

### Secondary (MEDIUM confidence)
- [PythonGUIs Multithreading Tutorial](https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/) - Comprehensive QThreadPool tutorial with working examples
- [PythonGUIs Packaging Tutorial](https://www.pythonguis.com/tutorials/packaging-pyside6-applications-windows-pyinstaller-installforge/) - PyInstaller packaging guide
- [Qt Forum Thread on Signal Emission](https://forum.qt.io/topic/137276/pyside-6-gui-freezing-even-when-using-qthreadpool-class) - QMetaObject.invokeMethod pattern

### Tertiary (LOW confidence)
- Various WebSearch results on project structure - Patterns verified against official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Based on official Qt documentation and user's prior decisions
- Architecture patterns: HIGH - Based on official Qt examples and verified tutorials
- Pitfalls: HIGH - Based on official Qt warnings and documented issues

**Research date:** 2026-01-21
**Valid until:** 2026-03-21 (60 days - PySide6 is stable, patterns well-established)
