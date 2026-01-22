"""Worker classes for background operations.

This package provides the Worker pattern for executing background operations
without blocking the GUI, with support for progress reporting and cancellation.

Exports:
    Worker: Base worker class for background execution.
    WorkerSignals: Signals for worker thread communication.
    perform_uspto_search: Worker function for USPTO patent search.
    create_uspto_search_worker: Factory to create USPTO search worker.
"""

from fto_agent.workers.base import Worker, WorkerSignals
from fto_agent.workers.uspto_worker import (
    create_uspto_search_worker,
    perform_uspto_search,
)

__all__ = [
    "Worker",
    "WorkerSignals",
    "perform_uspto_search",
    "create_uspto_search_worker",
]
