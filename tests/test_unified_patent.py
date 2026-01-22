"""Unit tests for UnifiedPatent model and PatentSource enum.

Tests verify the unified patent model including:
- PatentSource enum values
- UnifiedPatent.from_uspto conversion
- UnifiedPatent.from_epo conversion
- URL generation for each source
"""

import pytest

from fto_agent.services.epo import EPOPatent
from fto_agent.services.legal_status import PatentStatus
from fto_agent.services.models import PatentSource, UnifiedPatent
from fto_agent.services.uspto import Patent


class TestPatentSource:
    """Tests for PatentSource enum."""

    def test_patent_source_has_uspto(self):
        """PatentSource has USPTO value."""
        assert PatentSource.USPTO.value == "USPTO"

    def test_patent_source_has_epo(self):
        """PatentSource has EPO value."""
        assert PatentSource.EPO.value == "EPO"

    def test_patent_source_all_values(self):
        """PatentSource has exactly 2 values."""
        assert len(PatentSource) == 2


class TestUnifiedPatent:
    """Tests for UnifiedPatent model."""

    def test_unified_patent_required_fields(self):
        """UnifiedPatent requires id, title, source, and url."""
        patent = UnifiedPatent(
            id="US10123456",
            title="Test Patent",
            source=PatentSource.USPTO,
            url="https://example.com",
        )

        assert patent.id == "US10123456"
        assert patent.title == "Test Patent"
        assert patent.source == PatentSource.USPTO
        assert patent.url == "https://example.com"

    def test_unified_patent_optional_fields(self):
        """UnifiedPatent optional fields default correctly."""
        patent = UnifiedPatent(
            id="EP1000000A1",
            title="Test",
            source=PatentSource.EPO,
            url="https://example.com",
        )

        assert patent.abstract is None
        assert patent.date is None
        assert patent.status is None
        assert patent.cpc_codes == []

    def test_unified_patent_all_fields(self):
        """UnifiedPatent with all fields populated."""
        patent = UnifiedPatent(
            id="EP1234567B1",
            title="Cosmetic Composition",
            abstract="A composition for skin care...",
            date="2023-01-15",
            source=PatentSource.EPO,
            url="https://espacenet.com/patent/...",
            status=PatentStatus.ACTIVE,
            cpc_codes=["A61K8/00", "A61Q19/00"],
        )

        assert patent.id == "EP1234567B1"
        assert patent.abstract == "A composition for skin care..."
        assert patent.date == "2023-01-15"
        assert patent.status == PatentStatus.ACTIVE
        assert len(patent.cpc_codes) == 2


class TestUnifiedPatentFromUSPTO:
    """Tests for UnifiedPatent.from_uspto conversion."""

    def test_from_uspto_basic(self):
        """UnifiedPatent.from_uspto converts basic USPTO patent."""
        uspto_patent = Patent(
            patent_id="10123456",
            patent_title="Test USPTO Patent",
        )

        unified = UnifiedPatent.from_uspto(uspto_patent)

        assert unified.id == "US10123456"
        assert unified.title == "Test USPTO Patent"
        assert unified.source == PatentSource.USPTO

    def test_from_uspto_generates_google_patents_url(self):
        """UnifiedPatent.from_uspto generates Google Patents URL."""
        uspto_patent = Patent(
            patent_id="10123456",
            patent_title="Test",
        )

        unified = UnifiedPatent.from_uspto(uspto_patent)

        assert "patents.google.com/patent/US10123456" in unified.url

    def test_from_uspto_with_all_fields(self):
        """UnifiedPatent.from_uspto preserves all available fields."""
        from datetime import date

        uspto_patent = Patent(
            patent_id="10123456",
            patent_title="Full Patent",
            patent_abstract="This patent describes...",
            patent_date=date(2023, 5, 1),
        )

        unified = UnifiedPatent.from_uspto(uspto_patent)

        assert unified.abstract == "This patent describes..."
        assert unified.date == "2023-05-01"

    def test_from_uspto_raises_for_wrong_type(self):
        """UnifiedPatent.from_uspto raises TypeError for wrong input."""
        with pytest.raises(TypeError) as exc_info:
            UnifiedPatent.from_uspto("not a patent")

        assert "Patent" in str(exc_info.value)


class TestUnifiedPatentFromEPO:
    """Tests for UnifiedPatent.from_epo conversion."""

    def test_from_epo_basic(self):
        """UnifiedPatent.from_epo converts basic EPO patent."""
        epo_patent = EPOPatent(
            publication_number="EP1000000A1",
            title="Test EPO Patent",
        )

        unified = UnifiedPatent.from_epo(epo_patent)

        assert unified.id == "EP1000000A1"
        assert unified.title == "Test EPO Patent"
        assert unified.source == PatentSource.EPO

    def test_from_epo_generates_espacenet_url(self):
        """UnifiedPatent.from_epo generates Espacenet URL."""
        epo_patent = EPOPatent(
            publication_number="EP1234567B1",
            title="Test",
        )

        unified = UnifiedPatent.from_epo(epo_patent)

        assert "espacenet.com" in unified.url
        assert "EP1234567B1" in unified.url

    def test_from_epo_with_status(self):
        """UnifiedPatent.from_epo accepts status parameter."""
        epo_patent = EPOPatent(
            publication_number="EP1000000A1",
            title="Test",
        )

        unified = UnifiedPatent.from_epo(epo_patent, status=PatentStatus.ACTIVE)

        assert unified.status == PatentStatus.ACTIVE

    def test_from_epo_with_cpc_codes(self):
        """UnifiedPatent.from_epo preserves CPC codes."""
        epo_patent = EPOPatent(
            publication_number="EP1000000A1",
            title="Test",
            cpc_classifications=["A61K8/00", "A61Q19/00"],
        )

        unified = UnifiedPatent.from_epo(epo_patent)

        assert unified.cpc_codes == ["A61K8/00", "A61Q19/00"]

    def test_from_epo_handles_none_title(self):
        """UnifiedPatent.from_epo handles None title with default."""
        epo_patent = EPOPatent(
            publication_number="EP1000000A1",
            title=None,
        )

        unified = UnifiedPatent.from_epo(epo_patent)

        assert unified.title == "Untitled"

    def test_from_epo_with_all_fields(self):
        """UnifiedPatent.from_epo preserves all available fields."""
        epo_patent = EPOPatent(
            publication_number="EP1234567B1",
            title="Full EPO Patent",
            abstract="Detailed abstract...",
            publication_date="20230515",
            applicants=["Company A"],
            cpc_classifications=["A61K8/00"],
        )

        unified = UnifiedPatent.from_epo(epo_patent)

        assert unified.abstract == "Detailed abstract..."
        assert unified.date == "20230515"
        assert unified.cpc_codes == ["A61K8/00"]

    def test_from_epo_raises_for_wrong_type(self):
        """UnifiedPatent.from_epo raises TypeError for wrong input."""
        with pytest.raises(TypeError) as exc_info:
            UnifiedPatent.from_epo("not a patent")

        assert "EPOPatent" in str(exc_info.value)
