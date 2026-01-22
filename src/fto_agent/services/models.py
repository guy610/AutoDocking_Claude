"""Unified models for multi-source patent display.

This module provides data models that can represent patents from multiple
sources (USPTO, EPO) in a unified format for display in the results panel.

Example:
    >>> from fto_agent.services import UnifiedPatent, PatentSource
    >>> unified = UnifiedPatent(
    ...     id="US10123456",
    ...     title="Test Patent",
    ...     source=PatentSource.USPTO,
    ...     url="https://patents.google.com/patent/US10123456",
    ... )
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field

# Import PatentStatus at runtime for Pydantic validation
from fto_agent.services.legal_status import PatentStatus

if TYPE_CHECKING:
    from fto_agent.services.epo import EPOPatent
    from fto_agent.services.uspto import Patent


class PatentSource(Enum):
    """Source database for a patent.

    Values:
        USPTO: United States Patent and Trademark Office.
        EPO: European Patent Office (via OPS API).
    """

    USPTO = "USPTO"
    EPO = "EPO"


class UnifiedPatent(BaseModel):
    """Unified patent model for display from multiple sources.

    This model normalizes patents from different databases into a common
    format for display in the results panel. It provides conversion methods
    for each supported source.

    Attributes:
        id: Patent ID (publication number with country prefix).
        title: Title of the patent.
        abstract: Abstract text, may be None.
        date: Grant or publication date string.
        source: Source database (USPTO or EPO).
        url: Link to patent on official or Google Patents site.
        status: Legal status from INPADOC (EPO only).
        cpc_codes: CPC classification codes.
    """

    id: str = Field(description="Patent ID (publication number)")
    title: str
    abstract: Optional[str] = None
    date: Optional[str] = None  # Grant or publication date
    source: PatentSource
    url: str = Field(description="Link to patent on official site")

    # Optional fields that may not be available from all sources
    status: Optional[PatentStatus] = None
    cpc_codes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_uspto(cls, patent: "Patent") -> "UnifiedPatent":
        """Convert USPTO Patent to UnifiedPatent.

        Args:
            patent: USPTO Patent model from PatentsView API.

        Returns:
            UnifiedPatent with Google Patents URL.

        Example:
            >>> from fto_agent.services import Patent
            >>> p = Patent(patent_id="10123456", patent_title="Test")
            >>> unified = UnifiedPatent.from_uspto(p)
            >>> print(unified.id)  # "US10123456"
        """
        # Import here to avoid circular imports
        from fto_agent.services.uspto import Patent as PatentModel

        if not isinstance(patent, PatentModel):
            raise TypeError(f"Expected Patent, got {type(patent).__name__}")

        return cls(
            id=f"US{patent.patent_id}",
            title=patent.patent_title,
            abstract=patent.patent_abstract,
            date=str(patent.patent_date) if patent.patent_date else None,
            source=PatentSource.USPTO,
            url=f"https://patents.google.com/patent/US{patent.patent_id}",
        )

    @classmethod
    def from_epo(
        cls,
        patent: "EPOPatent",
        status: Optional[PatentStatus] = None,
    ) -> "UnifiedPatent":
        """Convert EPO Patent to UnifiedPatent.

        Args:
            patent: EPO Patent model from OPS API.
            status: Optional legal status from INPADOC query.

        Returns:
            UnifiedPatent with Espacenet URL.

        Example:
            >>> from fto_agent.services import EPOPatent
            >>> p = EPOPatent(publication_number="EP1000000A1", title="Test")
            >>> unified = UnifiedPatent.from_epo(p)
            >>> print(unified.url)  # Espacenet URL
        """
        # Import here to avoid circular imports
        from fto_agent.services.epo import EPOPatent as EPOPatentModel

        if not isinstance(patent, EPOPatentModel):
            raise TypeError(f"Expected EPOPatent, got {type(patent).__name__}")

        return cls(
            id=patent.publication_number,
            title=patent.title or "Untitled",
            abstract=patent.abstract,
            date=patent.publication_date,
            source=PatentSource.EPO,
            url=f"https://worldwide.espacenet.com/patent/search?q=pn%3D{patent.publication_number}",
            status=status,
            cpc_codes=patent.cpc_classifications,
        )
