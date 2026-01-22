"""Unit tests for USPTO PatentsView API client.

Tests verify the USPTO client models and query building:
- Patent Pydantic model parsing
- PatentSearchResponse model parsing
- build_keyword_query function
- USPTOSearchError exception
- USPTOClient initialization (mocked, no real API calls)
"""

import os
from datetime import date
from unittest.mock import patch

import pytest

from fto_agent.services.uspto import (
    Patent,
    PatentSearchResponse,
    USPTOClient,
    USPTOSearchError,
    build_keyword_query,
)


class TestPatentModel:
    """Tests for Patent Pydantic model."""

    def test_patent_parses_all_fields(self):
        """Parses all patent fields correctly."""
        data = {
            "patent_id": "10123456",
            "patent_title": "Method for skin treatment",
            "patent_abstract": "A novel peptide for skin health",
            "patent_date": "2023-05-15",
            "patent_type": "utility",
        }

        patent = Patent.model_validate(data)

        assert patent.patent_id == "10123456"
        assert patent.patent_title == "Method for skin treatment"
        assert patent.patent_abstract == "A novel peptide for skin health"
        assert patent.patent_date == date(2023, 5, 15)
        assert patent.patent_type == "utility"

    def test_patent_handles_missing_optional_fields(self):
        """Handles missing optional fields with None defaults."""
        data = {
            "patent_id": "10123456",
            "patent_title": "Method for skin treatment",
            # patent_abstract, patent_date, patent_type omitted
        }

        patent = Patent.model_validate(data)

        assert patent.patent_id == "10123456"
        assert patent.patent_title == "Method for skin treatment"
        assert patent.patent_abstract is None
        assert patent.patent_date is None
        assert patent.patent_type is None

    def test_patent_ignores_extra_fields(self):
        """Ignores extra fields not in model (extra='ignore')."""
        data = {
            "patent_id": "10123456",
            "patent_title": "Method for skin treatment",
            "extra_field": "should be ignored",
            "another_unknown": 12345,
        }

        patent = Patent.model_validate(data)

        assert patent.patent_id == "10123456"
        assert patent.patent_title == "Method for skin treatment"
        assert not hasattr(patent, "extra_field")
        assert not hasattr(patent, "another_unknown")


class TestPatentSearchResponse:
    """Tests for PatentSearchResponse Pydantic model."""

    def test_response_parses_patent_list(self):
        """Parses response with list of patents."""
        data = {
            "patents": [
                {"patent_id": "111", "patent_title": "First patent"},
                {"patent_id": "222", "patent_title": "Second patent"},
            ],
            "count": 2,
            "total_hits": 100,
        }

        response = PatentSearchResponse.model_validate(data)

        assert len(response.patents) == 2
        assert response.patents[0].patent_id == "111"
        assert response.patents[1].patent_id == "222"
        assert response.count == 2
        assert response.total_hits == 100

    def test_response_handles_empty_patents(self):
        """Handles empty patents list."""
        data = {
            "patents": [],
            "count": 0,
            "total_hits": 0,
        }

        response = PatentSearchResponse.model_validate(data)

        assert len(response.patents) == 0
        assert response.count == 0
        assert response.total_hits == 0

    def test_response_defaults_to_zero_counts(self):
        """Defaults to zero counts and empty list when fields missing."""
        data = {}  # All fields missing

        response = PatentSearchResponse.model_validate(data)

        assert response.patents == []
        assert response.count == 0
        assert response.total_hits == 0


class TestBuildKeywordQuery:
    """Tests for build_keyword_query function."""

    def test_builds_or_query_for_title_and_abstract(self):
        """Builds query that searches title and abstract."""
        query = build_keyword_query(["peptide", "collagen"])

        # Should have _or at top level
        assert "_or" in query
        assert len(query["_or"]) == 2

        # First element searches title
        assert "_text_any" in query["_or"][0]
        assert "patent_title" in query["_or"][0]["_text_any"]
        assert "peptide collagen" == query["_or"][0]["_text_any"]["patent_title"]

        # Second element searches abstract
        assert "_text_any" in query["_or"][1]
        assert "patent_abstract" in query["_or"][1]["_text_any"]
        assert "peptide collagen" == query["_or"][1]["_text_any"]["patent_abstract"]

    def test_raises_on_empty_keywords(self):
        """Raises ValueError when keywords list is empty."""
        with pytest.raises(ValueError, match="At least one keyword required"):
            build_keyword_query([])

    def test_joins_multiple_keywords_with_space(self):
        """Joins multiple keywords with space separator."""
        query = build_keyword_query(["skin", "health", "peptide"])

        keyword_string = query["_or"][0]["_text_any"]["patent_title"]
        assert keyword_string == "skin health peptide"


class TestUSPTOSearchError:
    """Tests for USPTOSearchError exception."""

    def test_error_has_message(self):
        """Error stores message attribute."""
        error = USPTOSearchError("Something went wrong")

        assert error.message == "Something went wrong"
        assert str(error) == "Something went wrong"

    def test_error_has_optional_status_code(self):
        """Error stores optional status_code attribute."""
        error = USPTOSearchError("Rate limited", status_code=429)

        assert error.message == "Rate limited"
        assert error.status_code == 429

    def test_error_status_code_defaults_to_none(self):
        """Status code defaults to None when not provided."""
        error = USPTOSearchError("Network error")

        assert error.status_code is None


class TestUSPTOClient:
    """Tests for USPTOClient initialization (no real API calls)."""

    def test_raises_without_api_key(self):
        """Raises USPTOSearchError when no API key provided or in env."""
        # Clear environment variable if set
        with patch.dict(os.environ, {}, clear=True):
            # Remove PATENTSVIEW_API_KEY if present
            os.environ.pop("PATENTSVIEW_API_KEY", None)

            with pytest.raises(USPTOSearchError, match="API key required"):
                USPTOClient()

    def test_accepts_api_key_parameter(self):
        """Accepts API key passed as parameter."""
        # Should not raise when api_key provided directly
        client = USPTOClient(api_key="test-api-key")
        client.close()

    def test_reads_api_key_from_env(self):
        """Reads API key from PATENTSVIEW_API_KEY environment variable."""
        with patch.dict(os.environ, {"PATENTSVIEW_API_KEY": "env-api-key"}):
            client = USPTOClient()
            client.close()

    def test_client_is_context_manager(self):
        """Client can be used as context manager."""
        with USPTOClient(api_key="test-key") as client:
            assert client is not None
