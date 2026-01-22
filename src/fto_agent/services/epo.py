"""EPO Open Patent Services (OPS) API client for patent search.

This module provides a client for the EPO OPS API, including Pydantic models
for response validation and CQL query building utilities.

API Reference: https://developers.epo.org/ops-v3-2/apis
Rate Limit: Throttler middleware handles EPO's rolling window limits

Example:
    >>> from fto_agent.services.epo import EPOClient
    >>> with EPOClient() as client:
    ...     response = client.search_patents(["peptide", "collagen"])
    ...     print(f"Found {response.total_hits} patents")
"""

from __future__ import annotations

import os
from typing import Optional

import epo_ops
from epo_ops.models import Epodoc
from lxml import etree
from pydantic import BaseModel, ConfigDict, Field


# XML namespaces for EPO OPS responses
NAMESPACES = {
    "ops": "http://ops.epo.org",
    "exchange": "http://www.epo.org/exchange",
    "reg": "http://www.epo.org/register",
}


class EPOPatent(BaseModel):
    """A single patent from EPO OPS API.

    Attributes:
        publication_number: Publication number (e.g., 'EP1000000A1').
        title: Title of the patent.
        abstract: Abstract text, may be None.
        publication_date: Publication date string.
        applicants: List of applicant names.
        cpc_classifications: List of CPC classification codes.
    """

    publication_number: str = Field(description="Publication number (e.g., 'EP1000000A1')")
    title: Optional[str] = Field(default=None, description="Title of the patent")
    abstract: Optional[str] = Field(default=None, description="Abstract text")
    publication_date: Optional[str] = Field(default=None, description="Publication date")
    applicants: list[str] = Field(default_factory=list, description="Applicant names")
    cpc_classifications: list[str] = Field(
        default_factory=list, description="CPC classification codes"
    )

    model_config = ConfigDict(extra="ignore")


class EPOSearchResponse(BaseModel):
    """Response from EPO OPS search.

    Attributes:
        patents: List of matching patents.
        count: Number of results in this response.
        total_hits: Total matching patents across all pages.
    """

    patents: list[EPOPatent] = Field(default_factory=list)
    count: int = Field(default=0, description="Number of results in this response")
    total_hits: int = Field(default=0, description="Total matching patents")

    model_config = ConfigDict(extra="ignore")


class EPOSearchError(Exception):
    """Error during EPO patent search.

    Attributes:
        message: Error description.
        status_code: HTTP status code if applicable.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        """Initialize the error.

        Args:
            message: Error description.
            status_code: HTTP status code if applicable.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class EPOClient:
    """Client for EPO Open Patent Services API.

    Requires OAuth credentials obtained from:
    https://developers.epo.org/user/register

    The client uses the python-epo-ops-client library which handles
    OAuth token management and API throttling automatically.

    Example:
        >>> with EPOClient() as client:
        ...     response = client.search_patents(["peptide", "skin"])
        ...     for patent in response.patents:
        ...         print(patent.title)
    """

    # Cosmetic-relevant CPC classifications
    # A61K8 = Cosmetics or similar toiletry preparations
    # A61Q = Specific use of cosmetics or similar toiletry preparations
    COSMETIC_CPC_CODES = ["A61K8", "A61Q"]

    def __init__(
        self,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None,
    ):
        """Initialize client with OAuth credentials.

        Args:
            consumer_key: EPO OPS consumer key. If None, reads from
                         EPO_OPS_CONSUMER_KEY environment variable.
            consumer_secret: EPO OPS consumer secret. If None, reads from
                            EPO_OPS_CONSUMER_SECRET environment variable.

        Raises:
            EPOSearchError: If credentials not provided and not in environment.
        """
        key = consumer_key or os.environ.get("EPO_OPS_CONSUMER_KEY")
        secret = consumer_secret or os.environ.get("EPO_OPS_CONSUMER_SECRET")

        if not key or not secret:
            raise EPOSearchError(
                "EPO OPS credentials required. Set EPO_OPS_CONSUMER_KEY and "
                "EPO_OPS_CONSUMER_SECRET environment variables."
            )

        # Create client with built-in throttling middleware
        self._client = epo_ops.Client(key=key, secret=secret)

    def search_patents(
        self,
        keywords: list[str],
        include_cosmetic_cpc: bool = True,
        range_begin: int = 1,
        range_end: int = 100,
    ) -> EPOSearchResponse:
        """Search patents using CQL query.

        Builds a CQL query from keywords and optionally adds cosmetic
        CPC classification filters (A61K8, A61Q).

        Args:
            keywords: List of keywords to search in title and abstract.
            include_cosmetic_cpc: If True, add CPC filter for cosmetic patents.
            range_begin: First result to return (1-indexed).
            range_end: Last result to return (max 100 per request).

        Returns:
            EPOSearchResponse with parsed results.

        Raises:
            EPOSearchError: On API errors or parsing failures.

        Example:
            >>> response = client.search_patents(["peptide", "collagen"])
            >>> print(f"Found {response.count} of {response.total_hits} patents")
        """
        if not keywords:
            return EPOSearchResponse(patents=[], count=0, total_hits=0)

        # Build CQL query
        cql = self._build_cql_query(keywords, include_cosmetic_cpc)

        try:
            response = self._client.published_data_search(
                cql=cql,
                range_begin=range_begin,
                range_end=range_end,
            )
            return self._parse_search_response(response)

        except Exception as e:
            error_msg = str(e)
            status_code = None

            # Try to extract status code from epo_ops errors
            if hasattr(e, "response") and hasattr(e.response, "status_code"):
                status_code = e.response.status_code

            raise EPOSearchError(f"EPO search failed: {error_msg}", status_code)

    def get_legal_status(self, publication_number: str) -> bytes:
        """Get legal status data for a patent from INPADOC.

        Args:
            publication_number: Patent publication number (e.g., 'EP1000000').

        Returns:
            Raw XML response bytes from INPADOC legal endpoint.

        Raises:
            EPOSearchError: On API errors.
        """
        try:
            response = self._client.legal(
                reference_type="publication",
                input=Epodoc(publication_number),
            )
            return response.content

        except Exception as e:
            error_msg = str(e)
            raise EPOSearchError(f"Legal status query failed: {error_msg}")

    def _build_cql_query(
        self,
        keywords: list[str],
        include_cosmetic_cpc: bool = True,
    ) -> str:
        """Build CQL query for EPO OPS search.

        CQL (Contextual Query Language) fields:
        - ti = title
        - ab = abstract
        - ta = title and abstract combined
        - cpc = CPC classification
        - pa = applicant
        - in = inventor

        Args:
            keywords: Keywords to search.
            include_cosmetic_cpc: If True, add cosmetic CPC filter.

        Returns:
            CQL query string.

        Example:
            >>> query = client._build_cql_query(["peptide", "collagen"], True)
            >>> # Returns: 'ta="peptide collagen" AND (cpc=A61K8 OR cpc=A61Q)'
        """
        parts = []

        # Keyword search in title and abstract
        if keywords:
            keyword_str = " ".join(keywords)
            parts.append(f'ta="{keyword_str}"')

        # Add cosmetic CPC classification filter
        if include_cosmetic_cpc:
            cpc_parts = [f"cpc={code}" for code in self.COSMETIC_CPC_CODES]
            cpc_query = f"({' OR '.join(cpc_parts)})"
            parts.append(cpc_query)

        return " AND ".join(parts) if parts else ""

    def _parse_search_response(self, response) -> EPOSearchResponse:
        """Parse EPO OPS XML search response.

        Args:
            response: Raw response from epo_ops client.

        Returns:
            EPOSearchResponse with parsed patent data.
        """
        try:
            root = etree.fromstring(response.content)
        except Exception as e:
            raise EPOSearchError(f"Failed to parse XML response: {e}")

        patents = []

        # Get total results count from search result
        total_hits = 0
        total_elem = root.xpath(
            "//ops:biblio-search/@total-result-count", namespaces=NAMESPACES
        )
        if total_elem:
            try:
                total_hits = int(total_elem[0])
            except (ValueError, TypeError):
                pass

        # Navigate to exchange documents
        for doc in root.xpath(
            "//exchange:exchange-document", namespaces=NAMESPACES
        ):
            patent = self._parse_exchange_document(doc)
            if patent:
                patents.append(patent)

        return EPOSearchResponse(
            patents=patents,
            count=len(patents),
            total_hits=total_hits,
        )

    def _parse_exchange_document(self, doc) -> Optional[EPOPatent]:
        """Parse a single exchange-document element.

        Args:
            doc: lxml Element for exchange:exchange-document.

        Returns:
            EPOPatent or None if parsing fails.
        """
        try:
            # Build publication number from attributes
            country = doc.get("country", "")
            doc_number = doc.get("doc-number", "")
            kind = doc.get("kind", "")
            publication_number = f"{country}{doc_number}{kind}"

            if not publication_number:
                return None

            # Get title (prefer English)
            title = None
            title_elems = doc.xpath(
                ".//exchange:invention-title[@lang='en']", namespaces=NAMESPACES
            )
            if title_elems:
                title = title_elems[0].text
            else:
                # Fall back to any title
                title_elems = doc.xpath(
                    ".//exchange:invention-title", namespaces=NAMESPACES
                )
                if title_elems:
                    title = title_elems[0].text

            # Get abstract (prefer English)
            abstract = None
            abstract_elems = doc.xpath(
                ".//exchange:abstract[@lang='en']/exchange:p", namespaces=NAMESPACES
            )
            if abstract_elems:
                abstract = abstract_elems[0].text
            else:
                abstract_elems = doc.xpath(
                    ".//exchange:abstract/exchange:p", namespaces=NAMESPACES
                )
                if abstract_elems:
                    abstract = abstract_elems[0].text

            # Get publication date
            pub_date = None
            pub_ref = doc.xpath(
                ".//exchange:publication-reference//exchange:date", namespaces=NAMESPACES
            )
            if pub_ref:
                pub_date = pub_ref[0].text

            # Get applicants
            applicants = []
            for app_elem in doc.xpath(
                ".//exchange:applicants//exchange:applicant-name/exchange:name",
                namespaces=NAMESPACES,
            ):
                if app_elem.text:
                    applicants.append(app_elem.text)

            # Get CPC classifications
            cpc_codes = []
            for cpc_elem in doc.xpath(
                ".//exchange:patent-classifications//exchange:classification-cpc-text",
                namespaces=NAMESPACES,
            ):
                if cpc_elem.text:
                    cpc_codes.append(cpc_elem.text.strip())

            return EPOPatent(
                publication_number=publication_number,
                title=title,
                abstract=abstract,
                publication_date=pub_date,
                applicants=applicants,
                cpc_classifications=cpc_codes,
            )

        except Exception:
            # Skip malformed documents
            return None

    def close(self) -> None:
        """Close the client and release resources."""
        # epo_ops.Client doesn't have explicit close, but we can clear reference
        self._client = None

    def __enter__(self) -> EPOClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args) -> None:
        """Exit context manager and close client."""
        self.close()
