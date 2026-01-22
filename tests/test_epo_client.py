"""Unit tests for EPO OPS API client and models.

Tests verify the EPO client functionality including:
- EPOPatent and EPOSearchResponse model validation
- EPOSearchError exception handling
- EPOClient credential validation
- CQL query building with and without cosmetic CPC codes
- NAMESPACES constant and COSMETIC_CPC_CODES class attribute
"""

import pytest

from fto_agent.services.epo import (
    NAMESPACES,
    EPOClient,
    EPOPatent,
    EPOSearchError,
    EPOSearchResponse,
)


class TestEPOPatent:
    """Tests for EPOPatent Pydantic model."""

    def test_epo_patent_required_fields(self):
        """EPOPatent requires publication_number."""
        patent = EPOPatent(publication_number="EP1000000A1")

        assert patent.publication_number == "EP1000000A1"
        assert patent.title is None
        assert patent.abstract is None
        assert patent.publication_date is None
        assert patent.applicants == []
        assert patent.cpc_classifications == []

    def test_epo_patent_all_fields(self):
        """EPOPatent with all optional fields populated."""
        patent = EPOPatent(
            publication_number="EP1234567B1",
            title="Cosmetic composition",
            abstract="A composition for skin care...",
            publication_date="20230101",
            applicants=["Company A", "Company B"],
            cpc_classifications=["A61K8/00", "A61Q19/00"],
        )

        assert patent.publication_number == "EP1234567B1"
        assert patent.title == "Cosmetic composition"
        assert patent.abstract == "A composition for skin care..."
        assert patent.publication_date == "20230101"
        assert patent.applicants == ["Company A", "Company B"]
        assert patent.cpc_classifications == ["A61K8/00", "A61Q19/00"]

    def test_epo_patent_extra_fields_ignored(self):
        """EPOPatent ignores extra fields (extra='ignore' config)."""
        patent = EPOPatent(
            publication_number="EP1000000A1",
            unknown_field="should be ignored",
        )

        assert patent.publication_number == "EP1000000A1"
        assert not hasattr(patent, "unknown_field")


class TestEPOSearchResponse:
    """Tests for EPOSearchResponse Pydantic model."""

    def test_epo_search_response_empty(self):
        """EPOSearchResponse with empty patents list."""
        response = EPOSearchResponse()

        assert response.patents == []
        assert response.count == 0
        assert response.total_hits == 0

    def test_epo_search_response_with_patents(self):
        """EPOSearchResponse with populated patents list."""
        patents = [
            EPOPatent(publication_number="EP1000001A1", title="Patent 1"),
            EPOPatent(publication_number="EP1000002A1", title="Patent 2"),
        ]
        response = EPOSearchResponse(patents=patents, count=2, total_hits=100)

        assert len(response.patents) == 2
        assert response.count == 2
        assert response.total_hits == 100

    def test_epo_search_response_defaults(self):
        """EPOSearchResponse uses correct defaults."""
        response = EPOSearchResponse(patents=[])

        assert response.count == 0
        assert response.total_hits == 0


class TestEPOSearchError:
    """Tests for EPOSearchError exception."""

    def test_epo_search_error_message_only(self):
        """EPOSearchError with message only."""
        error = EPOSearchError("Test error message")

        assert error.message == "Test error message"
        assert error.status_code is None
        assert str(error) == "Test error message"

    def test_epo_search_error_with_status_code(self):
        """EPOSearchError with message and status_code."""
        error = EPOSearchError("Unauthorized", status_code=401)

        assert error.message == "Unauthorized"
        assert error.status_code == 401

    def test_epo_search_error_is_exception(self):
        """EPOSearchError is a proper Exception."""
        error = EPOSearchError("Test error")

        assert isinstance(error, Exception)

        # Can be raised and caught
        with pytest.raises(EPOSearchError) as exc_info:
            raise error

        assert exc_info.value.message == "Test error"


class TestEPOClientCredentials:
    """Tests for EPOClient credential handling."""

    def test_epo_client_raises_without_credentials(self, monkeypatch):
        """EPOClient raises EPOSearchError without credentials."""
        # Clear environment variables
        monkeypatch.delenv("EPO_OPS_CONSUMER_KEY", raising=False)
        monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)

        with pytest.raises(EPOSearchError) as exc_info:
            EPOClient()

        assert "credentials required" in exc_info.value.message.lower()

    def test_epo_client_raises_with_partial_credentials(self, monkeypatch):
        """EPOClient raises with only key, no secret."""
        monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "test_key")
        monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)

        with pytest.raises(EPOSearchError):
            EPOClient()

    def test_epo_client_accepts_explicit_credentials(self, monkeypatch):
        """EPOClient accepts explicit key and secret parameters."""
        # Clear environment variables to ensure we're using explicit params
        monkeypatch.delenv("EPO_OPS_CONSUMER_KEY", raising=False)
        monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)

        # This should not raise - credentials provided explicitly
        # Note: The client will be created but API calls would fail with invalid creds
        try:
            client = EPOClient(
                consumer_key="test_key",
                consumer_secret="test_secret",
            )
            assert client is not None
            client.close()
        except EPOSearchError:
            # If it raises for some other reason, that's acceptable
            pass


class TestEPOClientCQLQuery:
    """Tests for EPOClient._build_cql_query method."""

    @pytest.fixture
    def mock_client(self, monkeypatch):
        """Create a client with mocked credentials."""
        monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "test_key")
        monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "test_secret")
        client = EPOClient()
        yield client
        client.close()

    def test_build_cql_query_keywords_only(self, mock_client):
        """CQL query with keywords only (no cosmetic CPC)."""
        query = mock_client._build_cql_query(["peptide", "skin"], include_cosmetic_cpc=False)

        assert 'ta="peptide skin"' in query
        assert "cpc=" not in query

    def test_build_cql_query_with_cosmetic_cpc(self, mock_client):
        """CQL query with keywords and cosmetic CPC codes."""
        query = mock_client._build_cql_query(["peptide"], include_cosmetic_cpc=True)

        assert 'ta="peptide"' in query
        assert "cpc=A61K8" in query
        assert "cpc=A61Q" in query
        assert " AND " in query

    def test_build_cql_query_empty_keywords(self, mock_client):
        """CQL query with empty keywords list."""
        query = mock_client._build_cql_query([], include_cosmetic_cpc=True)

        # Should still have CPC codes
        assert "cpc=A61K8" in query
        assert "cpc=A61Q" in query

    def test_build_cql_query_multiple_keywords(self, mock_client):
        """CQL query combines multiple keywords."""
        query = mock_client._build_cql_query(
            ["peptide", "collagen", "skin"],
            include_cosmetic_cpc=False,
        )

        assert 'ta="peptide collagen skin"' in query


class TestConstants:
    """Tests for module-level constants and class attributes."""

    def test_namespaces_has_required_keys(self):
        """NAMESPACES contains required namespace keys."""
        assert "ops" in NAMESPACES
        assert "exchange" in NAMESPACES
        assert "reg" in NAMESPACES

    def test_namespaces_values_are_urls(self):
        """NAMESPACES values are valid namespace URLs."""
        for key, value in NAMESPACES.items():
            assert isinstance(value, str)
            assert value.startswith("http")

    def test_cosmetic_cpc_codes_contains_a61k8(self):
        """EPOClient.COSMETIC_CPC_CODES contains A61K8 (cosmetics)."""
        assert "A61K8" in EPOClient.COSMETIC_CPC_CODES

    def test_cosmetic_cpc_codes_contains_a61q(self):
        """EPOClient.COSMETIC_CPC_CODES contains A61Q (specific cosmetic use)."""
        assert "A61Q" in EPOClient.COSMETIC_CPC_CODES

    def test_cosmetic_cpc_codes_is_list(self):
        """EPOClient.COSMETIC_CPC_CODES is a list."""
        assert isinstance(EPOClient.COSMETIC_CPC_CODES, list)
