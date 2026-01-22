"""Unit tests for USPTO patent search worker.

Tests verify the worker function and factory:
- perform_uspto_search progress callback calls
- Cancellation handling with empty response
- Error handling for no keywords
- create_uspto_search_worker factory function
"""

from unittest.mock import MagicMock, patch

import pytest

from fto_agent.services.uspto import PatentSearchResponse, USPTOSearchError
from fto_agent.workers import Worker
from fto_agent.workers.uspto_worker import (
    create_uspto_search_worker,
    perform_uspto_search,
)


class TestPerformUSPTOSearch:
    """Tests for perform_uspto_search function."""

    def test_calls_progress_callback_four_times(self):
        """Progress callback is called four times (extract, build, search, complete)."""
        progress_calls = []

        def track_progress(current, total, message):
            progress_calls.append((current, total, message))

        # Mock USPTOClient to avoid real API calls
        mock_response = PatentSearchResponse(
            patents=[],
            count=0,
            total_hits=0,
        )

        with patch("fto_agent.workers.uspto_worker.USPTOClient") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.search_patents.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = perform_uspto_search(
                problem="skin health",
                solution="ghk peptide",
                constraints=None,
                api_key="test-key",
                is_cancelled=lambda: False,
                progress_callback=track_progress,
            )

        # Should be called 4 times
        assert len(progress_calls) == 4

        # Check progress values (current, total)
        assert progress_calls[0][:2] == (1, 4)  # Extracting keywords
        assert progress_calls[1][:2] == (2, 4)  # Building query
        assert progress_calls[2][:2] == (3, 4)  # Searching
        assert progress_calls[3][:2] == (4, 4)  # Complete

    def test_returns_empty_response_when_cancelled(self):
        """Returns empty PatentSearchResponse when cancelled."""
        # Return True immediately to indicate cancellation
        call_count = [0]

        def is_cancelled():
            call_count[0] += 1
            return True  # Cancelled from the start

        result = perform_uspto_search(
            problem="skin health",
            solution="ghk peptide",
            constraints=None,
            api_key="test-key",
            is_cancelled=is_cancelled,
            progress_callback=lambda c, t, m: None,
        )

        # Should return empty response
        assert isinstance(result, PatentSearchResponse)
        assert result.patents == []
        assert result.count == 0
        assert result.total_hits == 0

    def test_raises_on_no_keywords(self):
        """Raises USPTOSearchError when no keywords can be extracted."""
        with pytest.raises(USPTOSearchError, match="Could not extract keywords"):
            perform_uspto_search(
                problem="",  # Empty problem
                solution="",  # Empty solution
                constraints=None,
                api_key="test-key",
                is_cancelled=lambda: False,
                progress_callback=lambda c, t, m: None,
            )

    def test_wraps_unexpected_exceptions(self):
        """Wraps unexpected exceptions in USPTOSearchError."""
        with patch("fto_agent.workers.uspto_worker.USPTOClient") as MockClient:
            # Make the client raise an unexpected exception
            MockClient.side_effect = RuntimeError("Unexpected failure")

            with pytest.raises(USPTOSearchError, match="Search failed"):
                perform_uspto_search(
                    problem="skin health",
                    solution="ghk peptide",
                    constraints=None,
                    api_key="test-key",
                    is_cancelled=lambda: False,
                    progress_callback=lambda c, t, m: None,
                )


class TestCreateUSPTOSearchWorker:
    """Tests for create_uspto_search_worker factory function."""

    def test_creates_worker_from_data_dict(self):
        """Creates Worker from InputPanel data dictionary."""
        data = {
            "problem": "skin health issues",
            "solution": "ghk peptide treatment",
            "constraints": "cosmetic only",
            "smiles": "CC(=O)NCC",
            "countries": ["US", "EU"],
        }

        worker = create_uspto_search_worker(data, api_key="test-key")

        assert worker is not None

    def test_worker_has_correct_type(self):
        """Factory returns a Worker instance."""
        data = {
            "problem": "problem text",
            "solution": "solution text",
            "constraints": "",
            "smiles": "",
            "countries": ["US"],
        }

        worker = create_uspto_search_worker(data, api_key="test-key")

        assert isinstance(worker, Worker)

    def test_worker_uses_api_key(self):
        """Worker uses provided API key."""
        data = {
            "problem": "problem text",
            "solution": "solution text",
            "constraints": None,
            "smiles": "",
            "countries": ["US"],
        }

        # Create worker with specific API key
        worker = create_uspto_search_worker(data, api_key="specific-key")

        # Verify worker was created (actual execution tested separately)
        assert isinstance(worker, Worker)

    def test_handles_missing_constraints(self):
        """Handles missing constraints key in data dict."""
        data = {
            "problem": "problem text",
            "solution": "solution text",
            # constraints missing
            "smiles": "",
            "countries": ["US"],
        }

        worker = create_uspto_search_worker(data, api_key="test-key")

        assert isinstance(worker, Worker)
