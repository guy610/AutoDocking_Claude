"""Patent legal status parsing and determination from INPADOC data.

This module provides utilities for parsing INPADOC legal status XML data
and determining whether a patent is active, expired, lapsed, or withdrawn.

INPADOC (International Patent Documentation) contains legal status data
from 50+ patent offices worldwide.

Example:
    >>> from fto_agent.services.legal_status import get_patent_status, is_patent_active
    >>> status = get_patent_status(legal_xml_bytes)
    >>> if is_patent_active(status):
    ...     print("Patent is still in force")
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from lxml import etree

# XML namespaces for INPADOC legal status responses
NAMESPACES = {
    "ops": "http://ops.epo.org",
    "exchange": "http://www.epo.org/exchange",
    "reg": "http://www.epo.org/register",
}


class PatentStatus(Enum):
    """Legal status of a patent.

    Values:
        ACTIVE: Patent is in force and being maintained.
        EXPIRED: Patent term has ended (typically 20 years from filing).
        LAPSED: Patent abandoned due to non-payment of fees.
        WITHDRAWN: Application withdrawn by applicant.
        PENDING: Application not yet granted.
        UNKNOWN: Insufficient data to determine status.
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    LAPSED = "lapsed"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"
    UNKNOWN = "unknown"


# Keywords in INPADOC event descriptions indicating inactive status
# These are searched case-insensitively in legal event text
INACTIVE_KEYWORDS = [
    "lapse",
    "lapsed",
    "expired",
    "expiry",
    "withdrawn",
    "withdrawal",
    "refusal",
    "refused",
    "revoked",
    "revocation",
    "abandoned",
    "abandonment",
    "non-payment",
    "not paid",
    "fee not paid",
    "deemed to be withdrawn",
    "patent ceased",
    "patent expired",
    "no longer in force",
    "rights ceased",
    "termination",
    "terminated",
]

# Keywords indicating patent is still pending (not yet granted)
PENDING_KEYWORDS = [
    "application",
    "pending",
    "examination",
    "published",
    "search report",
    "filing",
]

# Keywords indicating patent was granted and is likely active
ACTIVE_KEYWORDS = [
    "grant",
    "granted",
    "patent granted",
    "fee paid",
    "renewal",
    "maintenance",
    "in force",
]


def get_patent_status(legal_xml: bytes) -> PatentStatus:
    """Determine patent status from INPADOC legal status XML.

    Parses the INPADOC legal events and analyzes the most recent events
    to determine the current legal status of the patent.

    Args:
        legal_xml: Raw XML bytes from EPO OPS legal endpoint.

    Returns:
        PatentStatus indicating the current status of the patent.

    Note:
        INPADOC data may have delays. For critical decisions, verify
        status directly with the relevant patent office.

    Example:
        >>> xml_data = client.get_legal_status("EP1000000")
        >>> status = get_patent_status(xml_data)
        >>> print(f"Patent status: {status.value}")
    """
    if not legal_xml:
        return PatentStatus.UNKNOWN

    try:
        root = etree.fromstring(legal_xml)
    except Exception:
        return PatentStatus.UNKNOWN

    # Collect all legal events with their text descriptions
    events = _extract_legal_events(root)

    if not events:
        return PatentStatus.UNKNOWN

    # Analyze events from most recent to oldest
    return _analyze_legal_events(events)


def _extract_legal_events(root) -> list[dict]:
    """Extract legal events from INPADOC XML.

    Args:
        root: lxml root Element.

    Returns:
        List of event dicts with 'date', 'code', and 'text' keys,
        sorted by date descending (most recent first).
    """
    events = []

    # Look for legal event elements
    # INPADOC structure: ops:legal/ops:patent-family/ops:family-member/ops:legal
    for legal_elem in root.xpath(
        "//ops:legal", namespaces=NAMESPACES
    ):
        event = {}

        # Get event date
        date_elem = legal_elem.xpath(".//ops:L007EP", namespaces=NAMESPACES)
        if date_elem:
            event["date"] = date_elem[0].text

        # Get event code
        code_elem = legal_elem.xpath(".//ops:L500EP", namespaces=NAMESPACES)
        if code_elem:
            event["code"] = code_elem[0].text

        # Get event text/description
        text_elem = legal_elem.xpath(".//ops:L502EP", namespaces=NAMESPACES)
        if text_elem:
            event["text"] = text_elem[0].text

        # Alternative structure for different response formats
        if not event.get("text"):
            text_elem = legal_elem.xpath(".//exchange:text", namespaces=NAMESPACES)
            if text_elem:
                event["text"] = text_elem[0].text

        if event:
            events.append(event)

    # Try alternative XPath for different INPADOC response structures
    if not events:
        for event_elem in root.xpath(
            "//exchange:legal-event", namespaces=NAMESPACES
        ):
            event = {}

            # Get event text
            desc_elem = event_elem.xpath(
                ".//exchange:event-description/exchange:text", namespaces=NAMESPACES
            )
            if desc_elem:
                event["text"] = desc_elem[0].text

            # Get date
            date_elem = event_elem.xpath(
                ".//exchange:event-date/exchange:date", namespaces=NAMESPACES
            )
            if date_elem:
                event["date"] = date_elem[0].text

            if event:
                events.append(event)

    # Sort by date descending (most recent first)
    events.sort(key=lambda e: e.get("date", ""), reverse=True)

    return events


def _analyze_legal_events(events: list[dict]) -> PatentStatus:
    """Analyze legal events to determine patent status.

    Args:
        events: List of event dicts, sorted by date descending.

    Returns:
        Determined PatentStatus.
    """
    # Check most recent events first
    # Limit to last 10 events to focus on current status
    recent_events = events[:10]

    # Combine all event text for analysis
    all_text = " ".join(
        (e.get("text", "") or "").lower() for e in recent_events
    )

    # Check for inactive indicators first (these are decisive)
    for keyword in INACTIVE_KEYWORDS:
        if keyword in all_text:
            # Determine specific inactive status
            if "lapse" in all_text or "non-payment" in all_text or "not paid" in all_text:
                return PatentStatus.LAPSED
            elif "withdrawn" in all_text or "withdrawal" in all_text:
                return PatentStatus.WITHDRAWN
            elif "expired" in all_text or "expiry" in all_text or "terminated" in all_text:
                return PatentStatus.EXPIRED
            elif "revoke" in all_text:
                return PatentStatus.WITHDRAWN
            else:
                # Generic inactive
                return PatentStatus.LAPSED

    # Check for active indicators
    for keyword in ACTIVE_KEYWORDS:
        if keyword in all_text:
            return PatentStatus.ACTIVE

    # Check for pending indicators
    for keyword in PENDING_KEYWORDS:
        if keyword in all_text:
            # Only pending if no grant indication
            if "grant" not in all_text:
                return PatentStatus.PENDING

    # Default to unknown if can't determine
    return PatentStatus.UNKNOWN


def is_patent_active(status: PatentStatus) -> bool:
    """Check if a patent should be considered for FTO analysis.

    Returns True for patents that could potentially be enforced:
    - ACTIVE: Clearly in force
    - PENDING: Could be granted in the future
    - UNKNOWN: Err on the side of caution

    Args:
        status: The patent's legal status.

    Returns:
        True if the patent should be included in FTO analysis.

    Example:
        >>> if is_patent_active(PatentStatus.ACTIVE):
        ...     print("Include in FTO analysis")
    """
    return status in (
        PatentStatus.ACTIVE,
        PatentStatus.PENDING,
        PatentStatus.UNKNOWN,
    )


def filter_active_patents(
    patents: list,
    get_legal_xml_func,
) -> list:
    """Filter a list of patents to only include active ones.

    This is a utility function for batch filtering. For performance,
    consider caching legal status results.

    Args:
        patents: List of patent objects with publication_number attribute.
        get_legal_xml_func: Function that takes publication_number and
                           returns legal XML bytes.

    Returns:
        List of patents that are considered active.

    Note:
        This performs one API call per patent. For large lists,
        consider implementing caching or batch processing.
    """
    active_patents = []

    for patent in patents:
        try:
            pub_num = getattr(patent, "publication_number", None)
            if not pub_num:
                # Can't check status, include by default (cautious)
                active_patents.append(patent)
                continue

            legal_xml = get_legal_xml_func(pub_num)
            status = get_patent_status(legal_xml)

            if is_patent_active(status):
                active_patents.append(patent)

        except Exception:
            # On error, include patent (err on side of caution)
            active_patents.append(patent)

    return active_patents
