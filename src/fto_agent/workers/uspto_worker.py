"""USPTO patent search worker for background execution.

This module provides the worker function and factory for executing USPTO
patent searches in a background thread using the Worker pattern from Phase 1.

The worker receives data from InputPanel.get_data() and uses the USPTOClient
and keyword extractor services to search for relevant patents.

Example:
    >>> from fto_agent.workers import create_uspto_search_worker
    >>> data = {"problem": "skin health", "solution": "GHK peptide", ...}
    >>> worker = create_uspto_search_worker(data)
    >>> worker.signals.result.connect(on_search_complete)
    >>> QThreadPool.globalInstance().start(worker)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from fto_agent.services.keyword_extractor import extract_search_terms
from fto_agent.services.uspto import (
    PatentSearchResponse,
    USPTOClient,
    USPTOSearchError,
    build_keyword_query,
)
from fto_agent.workers.base import Worker


def perform_uspto_search(
    problem: str,
    solution: str,
    constraints: Optional[str],
    api_key: Optional[str],
    is_cancelled: Callable[[], bool],
    progress_callback: Callable[[int, int, str], None],
) -> PatentSearchResponse:
    """Perform USPTO patent search in a background thread.

    This function is designed to be executed by a Worker. It extracts keywords
    from the user input, builds a PatentsView query, and executes the search.

    Args:
        problem: Problem description from InputPanel.
        solution: Solution/active description from InputPanel.
        constraints: Optional constraints from InputPanel.
        api_key: PatentsView API key, or None to use environment variable.
        is_cancelled: Callback to check if operation was cancelled.
        progress_callback: Callback for progress updates (current, total, message).

    Returns:
        PatentSearchResponse with search results.

    Raises:
        USPTOSearchError: On API errors, network errors, or invalid input.
    """
    total_steps = 4

    try:
        # Step 1: Extract keywords from user input
        progress_callback(1, total_steps, "Extracting search terms...")
        if is_cancelled():
            return PatentSearchResponse(patents=[], count=0, total_hits=0)

        keywords = extract_search_terms(problem, solution, constraints)
        if not keywords:
            raise USPTOSearchError("Could not extract keywords from input")

        # Step 2: Build query
        progress_callback(2, total_steps, f"Building query with {len(keywords)} keywords...")
        if is_cancelled():
            return PatentSearchResponse(patents=[], count=0, total_hits=0)

        query = build_keyword_query(keywords)

        # Step 3: Execute search
        progress_callback(3, total_steps, "Searching USPTO patent database...")
        if is_cancelled():
            return PatentSearchResponse(patents=[], count=0, total_hits=0)

        with USPTOClient(api_key=api_key) as client:
            response = client.search_patents(
                query=query,
                size=100,  # Return up to 100 patents
                sort=[{"patent_date": "desc"}],  # Most recent first
            )

        # Step 4: Complete
        progress_callback(4, total_steps, f"Found {response.total_hits} matching patents")

        return response

    except USPTOSearchError:
        # Re-raise USPTOSearchError as-is
        raise
    except Exception as e:
        # Wrap unexpected exceptions in USPTOSearchError
        raise USPTOSearchError(f"Search failed: {str(e)}") from e


def create_uspto_search_worker(
    data: dict[str, Any],
    api_key: Optional[str] = None,
) -> Worker:
    """Create a Worker for USPTO patent search.

    Factory function that creates a configured Worker ready to execute
    a USPTO patent search using data from InputPanel.get_data().

    Args:
        data: Dictionary from InputPanel.get_data() with keys:
              - problem (str): Problem description
              - solution (str): Solution/active description
              - constraints (str): Optional constraints
              - smiles (str): SMILES structure (not used in search)
              - countries (list[str]): Target countries (not used in USPTO search)
        api_key: Optional API key, or None to use PATENTSVIEW_API_KEY env var.

    Returns:
        Configured Worker ready to start via QThreadPool.

    Example:
        >>> data = panel.get_data()
        >>> worker = create_uspto_search_worker(data)
        >>> worker.signals.result.connect(self._on_search_complete)
        >>> worker.signals.error.connect(self._on_search_error)
        >>> QThreadPool.globalInstance().start(worker)
    """
    return Worker(
        perform_uspto_search,
        problem=data["problem"],
        solution=data["solution"],
        constraints=data.get("constraints"),
        api_key=api_key,
    )
