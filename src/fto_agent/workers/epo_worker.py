"""EPO patent search worker for background execution.

This module provides the worker function and factory for executing EPO OPS
patent searches in a background thread using the Worker pattern from Phase 1.

The worker receives data from InputPanel.get_data() and uses the EPOClient
and keyword extractor services to search for relevant patents. It also
supports filtering results to only active patents using INPADOC legal status.

Example:
    >>> from fto_agent.workers import create_epo_search_worker
    >>> data = {"problem": "skin health", "solution": "GHK peptide", ...}
    >>> worker = create_epo_search_worker(data, "key", "secret")
    >>> worker.signals.result.connect(on_search_complete)
    >>> QThreadPool.globalInstance().start(worker)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fto_agent.services.epo import (
    EPOClient,
    EPOPatent,
    EPOSearchError,
    EPOSearchResponse,
)
from fto_agent.services.keyword_extractor import extract_search_terms
from fto_agent.services.legal_status import (
    PatentStatus,
    get_patent_status,
    is_patent_active,
)
from fto_agent.workers.base import Worker

logger = logging.getLogger(__name__)


def perform_epo_search(
    problem: str,
    solution: str,
    constraints: Optional[str],
    consumer_key: str,
    consumer_secret: str,
    filter_active_only: bool = True,
    is_cancelled: Callable[[], bool] = lambda: False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> EPOSearchResponse:
    """Perform EPO patent search in a background thread.

    This function is designed to be executed by a Worker. It extracts keywords
    from the user input, builds a CQL query with cosmetic CPC codes, and
    executes the search via EPO OPS API. Optionally filters results to only
    active patents using INPADOC legal status data.

    Args:
        problem: Problem description from InputPanel.
        solution: Solution/active description from InputPanel.
        constraints: Optional constraints from InputPanel.
        consumer_key: EPO OPS consumer key.
        consumer_secret: EPO OPS consumer secret.
        filter_active_only: If True, filter results to active patents only.
                           This requires additional API calls per patent.
        is_cancelled: Callback to check if operation was cancelled.
        progress_callback: Callback for progress updates (current, total, message).

    Returns:
        EPOSearchResponse with search results (filtered if filter_active_only=True).

    Raises:
        EPOSearchError: On API errors, network errors, or invalid input.

    Note:
        Legal status filtering requires one API call per patent. For large result
        sets (>50 patents), this can be slow. A warning is logged in this case.
    """
    # Default no-op callbacks
    if progress_callback is None:
        progress_callback = lambda c, t, m: None  # noqa: E731

    total_steps = 5 if filter_active_only else 4

    try:
        # Step 1: Extract keywords from user input
        progress_callback(1, total_steps, "Extracting keywords...")
        if is_cancelled():
            return EPOSearchResponse(patents=[], count=0, total_hits=0)

        keywords = extract_search_terms(problem, solution, constraints)
        if not keywords:
            raise EPOSearchError("Could not extract keywords from input")

        # Step 2: Build query
        progress_callback(2, total_steps, f"Building EPO query with {len(keywords)} keywords...")
        if is_cancelled():
            return EPOSearchResponse(patents=[], count=0, total_hits=0)

        # Query is built internally by EPOClient.search_patents

        # Step 3: Execute search
        progress_callback(3, total_steps, "Searching EPO patents...")
        if is_cancelled():
            return EPOSearchResponse(patents=[], count=0, total_hits=0)

        with EPOClient(consumer_key=consumer_key, consumer_secret=consumer_secret) as client:
            response = client.search_patents(
                keywords=keywords,
                include_cosmetic_cpc=True,  # Always include cosmetic CPC filter
                range_begin=1,
                range_end=100,  # Return up to 100 patents
            )

            if is_cancelled():
                return EPOSearchResponse(patents=[], count=0, total_hits=0)

            # Step 4: Filter active patents (if enabled)
            if filter_active_only and response.patents:
                progress_callback(4, total_steps, "Filtering active patents...")

                # Warn if many patents to filter
                if len(response.patents) > 50:
                    logger.warning(
                        f"Filtering legal status for {len(response.patents)} patents - "
                        "this may take a while"
                    )

                active_patents: list[EPOPatent] = []
                statuses: dict[str, PatentStatus] = {}

                for i, patent in enumerate(response.patents):
                    if is_cancelled():
                        return EPOSearchResponse(patents=[], count=0, total_hits=0)

                    # Update progress within filtering step
                    filter_progress = f"Checking legal status ({i + 1}/{len(response.patents)})..."
                    progress_callback(4, total_steps, filter_progress)

                    try:
                        # Get legal status from INPADOC
                        legal_xml = client.get_legal_status(patent.publication_number)
                        status = get_patent_status(legal_xml)
                        statuses[patent.publication_number] = status

                        if is_patent_active(status):
                            active_patents.append(patent)
                    except EPOSearchError as e:
                        # On error, include patent (err on side of caution)
                        logger.warning(
                            f"Failed to get legal status for {patent.publication_number}: {e}"
                        )
                        statuses[patent.publication_number] = PatentStatus.UNKNOWN
                        active_patents.append(patent)

                # Update response with filtered patents
                response = EPOSearchResponse(
                    patents=active_patents,
                    count=len(active_patents),
                    total_hits=response.total_hits,  # Original total
                )

                logger.info(
                    f"Filtered to {len(active_patents)} active patents "
                    f"from {response.total_hits} total"
                )

        # Final step: Complete
        progress_callback(total_steps, total_steps, f"Found {response.count} patents")

        return response

    except EPOSearchError:
        # Re-raise EPOSearchError as-is
        raise
    except Exception as e:
        # Wrap unexpected exceptions in EPOSearchError
        raise EPOSearchError(f"EPO search failed: {str(e)}") from e


def create_epo_search_worker(
    data: dict[str, Any],
    consumer_key: str,
    consumer_secret: str,
    filter_active_only: bool = True,
) -> Worker:
    """Create a Worker for EPO patent search.

    Factory function that creates a configured Worker ready to execute
    an EPO patent search using data from InputPanel.get_data().

    Args:
        data: Dictionary from InputPanel.get_data() with keys:
              - problem (str): Problem description
              - solution (str): Solution/active description
              - constraints (str): Optional constraints
              - smiles (str): SMILES structure (not used in search)
              - countries (list[str]): Target countries (not used in EPO search)
        consumer_key: EPO OPS consumer key.
        consumer_secret: EPO OPS consumer secret.
        filter_active_only: If True, filter results to active patents only.

    Returns:
        Configured Worker ready to start via QThreadPool.

    Example:
        >>> data = panel.get_data()
        >>> worker = create_epo_search_worker(data, key, secret)
        >>> worker.signals.result.connect(self._on_search_complete)
        >>> worker.signals.error.connect(self._on_search_error)
        >>> QThreadPool.globalInstance().start(worker)
    """
    return Worker(
        perform_epo_search,
        problem=data["problem"],
        solution=data["solution"],
        constraints=data.get("constraints"),
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        filter_active_only=filter_active_only,
    )
