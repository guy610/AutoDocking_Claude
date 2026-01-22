"""Unit tests for patent legal status parsing.

Tests verify the legal status module including:
- PatentStatus enum values
- is_patent_active helper function
- get_patent_status XML parsing
- INACTIVE_KEYWORDS constant
"""

import pytest

from fto_agent.services.legal_status import (
    INACTIVE_KEYWORDS,
    PatentStatus,
    get_patent_status,
    is_patent_active,
)


class TestPatentStatusEnum:
    """Tests for PatentStatus enum."""

    def test_patent_status_has_active(self):
        """PatentStatus has ACTIVE value."""
        assert PatentStatus.ACTIVE.value == "active"

    def test_patent_status_has_expired(self):
        """PatentStatus has EXPIRED value."""
        assert PatentStatus.EXPIRED.value == "expired"

    def test_patent_status_has_lapsed(self):
        """PatentStatus has LAPSED value."""
        assert PatentStatus.LAPSED.value == "lapsed"

    def test_patent_status_has_withdrawn(self):
        """PatentStatus has WITHDRAWN value."""
        assert PatentStatus.WITHDRAWN.value == "withdrawn"

    def test_patent_status_has_pending(self):
        """PatentStatus has PENDING value."""
        assert PatentStatus.PENDING.value == "pending"

    def test_patent_status_has_unknown(self):
        """PatentStatus has UNKNOWN value."""
        assert PatentStatus.UNKNOWN.value == "unknown"

    def test_patent_status_all_values(self):
        """PatentStatus has exactly 6 values."""
        assert len(PatentStatus) == 6


class TestIsPatentActive:
    """Tests for is_patent_active function."""

    def test_is_patent_active_returns_true_for_active(self):
        """is_patent_active returns True for ACTIVE status."""
        assert is_patent_active(PatentStatus.ACTIVE) is True

    def test_is_patent_active_returns_true_for_pending(self):
        """is_patent_active returns True for PENDING status."""
        assert is_patent_active(PatentStatus.PENDING) is True

    def test_is_patent_active_returns_true_for_unknown(self):
        """is_patent_active returns True for UNKNOWN status (conservative)."""
        # Conservative approach: include UNKNOWN as potentially active
        assert is_patent_active(PatentStatus.UNKNOWN) is True

    def test_is_patent_active_returns_false_for_expired(self):
        """is_patent_active returns False for EXPIRED status."""
        assert is_patent_active(PatentStatus.EXPIRED) is False

    def test_is_patent_active_returns_false_for_lapsed(self):
        """is_patent_active returns False for LAPSED status."""
        assert is_patent_active(PatentStatus.LAPSED) is False

    def test_is_patent_active_returns_false_for_withdrawn(self):
        """is_patent_active returns False for WITHDRAWN status."""
        assert is_patent_active(PatentStatus.WITHDRAWN) is False


class TestInactiveKeywords:
    """Tests for INACTIVE_KEYWORDS constant."""

    def test_inactive_keywords_contains_lapse(self):
        """INACTIVE_KEYWORDS contains 'lapse'."""
        assert "lapse" in INACTIVE_KEYWORDS

    def test_inactive_keywords_contains_expired(self):
        """INACTIVE_KEYWORDS contains 'expired'."""
        assert "expired" in INACTIVE_KEYWORDS

    def test_inactive_keywords_contains_withdrawn(self):
        """INACTIVE_KEYWORDS contains 'withdrawn'."""
        assert "withdrawn" in INACTIVE_KEYWORDS

    def test_inactive_keywords_contains_revoked(self):
        """INACTIVE_KEYWORDS contains 'revoked'."""
        assert "revoked" in INACTIVE_KEYWORDS

    def test_inactive_keywords_contains_non_payment(self):
        """INACTIVE_KEYWORDS contains 'non-payment'."""
        assert "non-payment" in INACTIVE_KEYWORDS

    def test_inactive_keywords_is_list(self):
        """INACTIVE_KEYWORDS is a list."""
        assert isinstance(INACTIVE_KEYWORDS, list)


class TestGetPatentStatus:
    """Tests for get_patent_status function."""

    def test_get_patent_status_empty_xml(self):
        """get_patent_status returns UNKNOWN for empty bytes."""
        status = get_patent_status(b"")
        assert status == PatentStatus.UNKNOWN

    def test_get_patent_status_invalid_xml(self):
        """get_patent_status returns UNKNOWN for invalid XML."""
        status = get_patent_status(b"not valid xml at all")
        assert status == PatentStatus.UNKNOWN

    def test_get_patent_status_with_lapse_event(self):
        """get_patent_status returns LAPSED for XML with lapse event."""
        # Simplified XML structure that mimics INPADOC response with lapse
        xml = b"""<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org">
            <ops:legal>
                <ops:L007EP>20230101</ops:L007EP>
                <ops:L502EP>Patent has lapsed due to non-payment of fees</ops:L502EP>
            </ops:legal>
        </ops:world-patent-data>
        """
        status = get_patent_status(xml)
        assert status == PatentStatus.LAPSED

    def test_get_patent_status_with_expiry_event(self):
        """get_patent_status returns EXPIRED for XML with expiry event."""
        xml = b"""<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org">
            <ops:legal>
                <ops:L007EP>20230101</ops:L007EP>
                <ops:L502EP>Patent expired after 20 year term</ops:L502EP>
            </ops:legal>
        </ops:world-patent-data>
        """
        status = get_patent_status(xml)
        assert status == PatentStatus.EXPIRED

    def test_get_patent_status_with_grant_event(self):
        """get_patent_status returns ACTIVE for XML with grant event."""
        xml = b"""<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org">
            <ops:legal>
                <ops:L007EP>20230101</ops:L007EP>
                <ops:L502EP>Patent granted after examination</ops:L502EP>
            </ops:legal>
        </ops:world-patent-data>
        """
        status = get_patent_status(xml)
        assert status == PatentStatus.ACTIVE

    def test_get_patent_status_with_no_events(self):
        """get_patent_status returns UNKNOWN for XML with no legal events."""
        xml = b"""<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org">
            <ops:other-data>No legal events here</ops:other-data>
        </ops:world-patent-data>
        """
        status = get_patent_status(xml)
        assert status == PatentStatus.UNKNOWN

    def test_get_patent_status_with_withdrawn_event(self):
        """get_patent_status returns WITHDRAWN for XML with withdrawal event."""
        xml = b"""<?xml version="1.0"?>
        <ops:world-patent-data xmlns:ops="http://ops.epo.org">
            <ops:legal>
                <ops:L007EP>20230101</ops:L007EP>
                <ops:L502EP>Application deemed to be withdrawn</ops:L502EP>
            </ops:legal>
        </ops:world-patent-data>
        """
        status = get_patent_status(xml)
        assert status == PatentStatus.WITHDRAWN
