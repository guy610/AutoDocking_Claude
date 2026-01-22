"""Unit tests for EPO search worker.

Tests verify the EPO worker functionality including:
- perform_epo_search function
- Keyword extraction and progress reporting
- Cancellation handling
- create_epo_search_worker factory function
"""

from unittest.mock import MagicMock, patch

import pytest

from fto_agent.services.epo import EPOPatent, EPOSearchError, EPOSearchResponse
from fto_agent.workers import Worker
from fto_agent.workers.epo_worker import create_epo_search_worker, perform_epo_search


class TestPerformEpoSearch:
    """Tests for perform_epo_search function."""

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_extracts_keywords(
        self, mock_extract, mock_client_class
    ):
        """perform_epo_search calls extract_search_terms with inputs."""
        mock_extract.return_value = ["peptide", "skin"]

        # Mock client to return empty response
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.search_patents.return_value = EPOSearchResponse()

        perform_epo_search(
            problem="Improve skin health",
            solution="GHK peptide",
            constraints=None,
            consumer_key="test_key",
            consumer_secret="test_secret",
            filter_active_only=False,
        )

        # Verify extract_search_terms was called
        mock_extract.assert_called_once_with(
            "Improve skin health",
            "GHK peptide",
            None,
        )

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_handles_cancellation_early(
        self, mock_extract, mock_client_class
    ):
        """perform_epo_search returns empty response on early cancellation."""
        is_cancelled = MagicMock(return_value=True)  # Already cancelled

        result = perform_epo_search(
            problem="Test",
            solution="Test",
            constraints=None,
            consumer_key="key",
            consumer_secret="secret",
            is_cancelled=is_cancelled,
            filter_active_only=False,
        )

        assert result.patents == []
        assert result.count == 0

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_handles_cancellation_mid_search(
        self, mock_extract, mock_client_class
    ):
        """perform_epo_search returns empty on mid-search cancellation."""
        mock_extract.return_value = ["keyword"]

        # Cancel during search step
        call_count = [0]

        def is_cancelled():
            call_count[0] += 1
            return call_count[0] >= 3  # Cancel on 3rd check (search step)

        result = perform_epo_search(
            problem="Test",
            solution="Test",
            constraints=None,
            consumer_key="key",
            consumer_secret="secret",
            is_cancelled=is_cancelled,
            filter_active_only=False,
        )

        assert result.patents == []
        assert result.count == 0

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_calls_progress_callback(
        self, mock_extract, mock_client_class
    ):
        """perform_epo_search calls progress_callback at each step."""
        mock_extract.return_value = ["keyword"]

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.search_patents.return_value = EPOSearchResponse()

        progress_calls = []

        def progress_callback(current, total, message):
            progress_calls.append((current, total, message))

        perform_epo_search(
            problem="Test",
            solution="Test",
            constraints=None,
            consumer_key="key",
            consumer_secret="secret",
            filter_active_only=False,
            progress_callback=progress_callback,
        )

        # Should have at least 4 progress calls (no filtering)
        assert len(progress_calls) >= 4
        # First call should be step 1
        assert progress_calls[0][0] == 1
        # Last call should be final step
        assert progress_calls[-1][0] == progress_calls[-1][1]

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_returns_empty_on_cancel(
        self, mock_extract, mock_client_class
    ):
        """perform_epo_search returns empty EPOSearchResponse on cancel."""
        result = perform_epo_search(
            problem="Test",
            solution="Test",
            constraints=None,
            consumer_key="key",
            consumer_secret="secret",
            is_cancelled=lambda: True,
        )

        assert isinstance(result, EPOSearchResponse)
        assert result.patents == []
        assert result.count == 0
        assert result.total_hits == 0

    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    def test_perform_epo_search_raises_on_no_keywords(self, mock_extract):
        """perform_epo_search raises EPOSearchError if no keywords extracted."""
        mock_extract.return_value = []  # No keywords

        with pytest.raises(EPOSearchError) as exc_info:
            perform_epo_search(
                problem="",
                solution="",
                constraints=None,
                consumer_key="key",
                consumer_secret="secret",
            )

        assert "keyword" in exc_info.value.message.lower()


class TestCreateEpoSearchWorker:
    """Tests for create_epo_search_worker factory function."""

    def test_create_epo_search_worker_returns_worker(self):
        """create_epo_search_worker returns a Worker instance."""
        data = {
            "problem": "Test problem",
            "solution": "Test solution",
            "constraints": "Some constraints",
            "smiles": "",
            "countries": ["EU"],
        }

        worker = create_epo_search_worker(
            data,
            consumer_key="test_key",
            consumer_secret="test_secret",
        )

        assert isinstance(worker, Worker)

    def test_create_epo_search_worker_with_filter_active_true(self):
        """create_epo_search_worker with filter_active_only=True."""
        data = {
            "problem": "Test",
            "solution": "Test",
        }

        worker = create_epo_search_worker(
            data,
            consumer_key="key",
            consumer_secret="secret",
            filter_active_only=True,
        )

        # Worker should be created (actual filtering tested via integration)
        assert isinstance(worker, Worker)

    def test_create_epo_search_worker_with_filter_active_false(self):
        """create_epo_search_worker with filter_active_only=False."""
        data = {
            "problem": "Test",
            "solution": "Test",
        }

        worker = create_epo_search_worker(
            data,
            consumer_key="key",
            consumer_secret="secret",
            filter_active_only=False,
        )

        assert isinstance(worker, Worker)

    def test_create_epo_search_worker_has_signals(self):
        """create_epo_search_worker returns Worker with signals."""
        data = {"problem": "Test", "solution": "Test"}

        worker = create_epo_search_worker(data, "key", "secret")

        assert hasattr(worker, "signals")
        assert hasattr(worker.signals, "result")
        assert hasattr(worker.signals, "error")
        assert hasattr(worker.signals, "progress")
        assert hasattr(worker.signals, "finished")

    def test_create_epo_search_worker_extracts_data_fields(self):
        """create_epo_search_worker extracts correct data fields."""
        data = {
            "problem": "Skin aging",
            "solution": "Peptide treatment",
            "constraints": "Must be safe",
            "smiles": "CCO",  # Not used in EPO search
            "countries": ["EU", "US"],  # Not used directly
        }

        worker = create_epo_search_worker(data, "key", "secret")

        # Worker kwargs should contain problem, solution, constraints
        assert worker.kwargs.get("problem") == "Skin aging"
        assert worker.kwargs.get("solution") == "Peptide treatment"
        assert worker.kwargs.get("constraints") == "Must be safe"


class TestPerformEpoSearchWithFiltering:
    """Tests for perform_epo_search with active patent filtering."""

    @patch("fto_agent.workers.epo_worker.EPOClient")
    @patch("fto_agent.workers.epo_worker.extract_search_terms")
    @patch("fto_agent.workers.epo_worker.get_patent_status")
    @patch("fto_agent.workers.epo_worker.is_patent_active")
    def test_perform_epo_search_filters_active_patents(
        self, mock_is_active, mock_get_status, mock_extract, mock_client_class
    ):
        """perform_epo_search filters to active patents when enabled."""
        from fto_agent.services.legal_status import PatentStatus

        mock_extract.return_value = ["keyword"]
        mock_is_active.return_value = True
        mock_get_status.return_value = PatentStatus.ACTIVE

        # Create mock patents
        patents = [
            EPOPatent(publication_number="EP1000001A1"),
            EPOPatent(publication_number="EP1000002A1"),
        ]

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.search_patents.return_value = EPOSearchResponse(
            patents=patents, count=2, total_hits=2
        )
        mock_client.get_legal_status.return_value = b"<xml>legal data</xml>"

        result = perform_epo_search(
            problem="Test",
            solution="Test",
            constraints=None,
            consumer_key="key",
            consumer_secret="secret",
            filter_active_only=True,
        )

        # Should have called get_legal_status for each patent
        assert mock_client.get_legal_status.call_count == 2
        # All patents should be in result (all active)
        assert result.count == 2
