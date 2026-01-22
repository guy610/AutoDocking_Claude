"""USPTO PatentsView API client for patent search.

This module provides a client for the USPTO PatentsView PatentSearch API,
including Pydantic models for response validation and query building utilities.

API Reference: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
Rate Limit: 45 requests/minute per API key

Example:
    >>> from fto_agent.services.uspto import USPTOClient, build_keyword_query
    >>> with USPTOClient(api_key="your-key") as client:
    ...     query = build_keyword_query(["peptide", "collagen"])
    ...     response = client.search_patents(query)
    ...     print(f"Found {response.total_hits} patents")
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field


class Patent(BaseModel):
    """A single patent from PatentsView API.

    Attributes:
        patent_id: Patent number (e.g., '10123456').
        patent_title: Title of the patent.
        patent_abstract: Abstract text, may be None for older patents.
        patent_date: Grant date.
        patent_type: Patent type (utility, design, plant, or reissue).
    """

    patent_id: str = Field(description="Patent number (e.g., '10123456')")
    patent_title: str = Field(description="Title of the patent")
    patent_abstract: Optional[str] = Field(
        default=None, description="Abstract text, may be None for older patents"
    )
    patent_date: Optional[date] = Field(default=None, description="Grant date")
    patent_type: Optional[str] = Field(
        default=None, description="utility, design, plant, or reissue"
    )

    class Config:
        """Pydantic model configuration."""

        extra = "ignore"


class PatentSearchResponse(BaseModel):
    """Response from PatentsView patent search endpoint.

    Attributes:
        patents: List of matching patents.
        count: Number of results in this response.
        total_hits: Total matching patents across all pages.
    """

    patents: list[Patent] = Field(default_factory=list)
    count: int = Field(default=0, description="Number of results in this response")
    total_hits: int = Field(default=0, description="Total matching patents")

    class Config:
        """Pydantic model configuration."""

        extra = "ignore"


class USPTOSearchError(Exception):
    """Error during USPTO patent search.

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


class USPTOClient:
    """Client for USPTO PatentsView PatentSearch API.

    Requires an API key obtained from:
    https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18

    Rate limit: 45 requests/minute per API key.

    Example:
        >>> with USPTOClient() as client:
        ...     response = client.search_patents({"_text_any": {"patent_title": "peptide"}})
        ...     for patent in response.patents:
        ...         print(patent.patent_title)
    """

    BASE_URL = "https://search.patentsview.org/api/v1"
    DEFAULT_FIELDS = [
        "patent_id",
        "patent_title",
        "patent_abstract",
        "patent_date",
        "patent_type",
    ]

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        """Initialize client with API key.

        Args:
            api_key: PatentsView API key. If None, reads from
                     PATENTSVIEW_API_KEY environment variable.
            timeout: Request timeout in seconds (default 30).

        Raises:
            USPTOSearchError: If API key not provided and not in environment.
        """
        if api_key is None:
            api_key = os.environ.get("PATENTSVIEW_API_KEY")

        if not api_key:
            raise USPTOSearchError(
                "API key required. Set PATENTSVIEW_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    def search_patents(
        self,
        query: dict[str, Any],
        fields: Optional[list[str]] = None,
        size: int = 100,
        sort: Optional[list[dict[str, str]]] = None,
    ) -> PatentSearchResponse:
        """Search patents using PatentsView query syntax.

        Args:
            query: Query dict using PatentsView operators (_text_any, _and, etc.)
            fields: Fields to return. Defaults to core patent fields.
            size: Results per page (1-1000, default 100).
            sort: Sort specification, e.g., [{"patent_date": "desc"}]

        Returns:
            PatentSearchResponse with parsed results.

        Raises:
            USPTOSearchError: On API errors or validation failures.

        Example:
            >>> query = {"_text_any": {"patent_title": "collagen peptide"}}
            >>> response = client.search_patents(query, size=50)
            >>> print(f"Found {response.count} of {response.total_hits} patents")
        """
        if fields is None:
            fields = self.DEFAULT_FIELDS.copy()

        # Clamp size to API limits
        size = max(1, min(size, 1000))

        request_body: dict[str, Any] = {
            "q": query,
            "f": fields,
            "o": {"size": size},
        }
        if sort:
            request_body["s"] = sort

        try:
            response = self._client.post("/patent/", json=request_body)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise USPTOSearchError(
                    f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    status_code=429,
                )

            response.raise_for_status()

            # Parse response
            data = response.json()
            return PatentSearchResponse.model_validate(data)

        except httpx.TimeoutException:
            raise USPTOSearchError("Request timed out. Try a more specific query.")
        except httpx.HTTPStatusError as e:
            raise USPTOSearchError(
                f"API error: {e.response.status_code}", status_code=e.response.status_code
            )
        except USPTOSearchError:
            raise
        except Exception as e:
            raise USPTOSearchError(f"Search failed: {str(e)}")

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        self._client.close()

    def __enter__(self) -> USPTOClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager and close client."""
        self.close()


def build_keyword_query(keywords: list[str]) -> dict[str, Any]:
    """Build a PatentsView keyword query.

    Searches patent_title and patent_abstract using _text_any operator.
    The query matches patents containing any of the keywords in either field.

    Args:
        keywords: List of keywords to search for.

    Returns:
        Query dict for PatentsView API.

    Raises:
        ValueError: If keywords list is empty.

    Example:
        >>> query = build_keyword_query(["peptide", "collagen", "skin"])
        >>> # Returns:
        >>> # {"_or": [
        >>> #     {"_text_any": {"patent_title": "peptide collagen skin"}},
        >>> #     {"_text_any": {"patent_abstract": "peptide collagen skin"}}
        >>> # ]}
    """
    if not keywords:
        raise ValueError("At least one keyword required")

    keyword_string = " ".join(keywords)

    return {
        "_or": [
            {"_text_any": {"patent_title": keyword_string}},
            {"_text_any": {"patent_abstract": keyword_string}},
        ]
    }
