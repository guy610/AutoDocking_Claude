"""Services for external API integrations.

This module provides clients and utilities for interacting with
patent databases and processing user input for search queries.

Exports:
    USPTOClient: Client for USPTO PatentsView PatentSearch API.
    Patent: Pydantic model for a single patent.
    PatentSearchResponse: Pydantic model for search results.
    USPTOSearchError: Exception for USPTO API errors.
    build_keyword_query: Build PatentsView query from keywords.
    extract_keywords: Extract keywords from text.
    extract_search_terms: Extract search terms from FTO query inputs.
"""

from fto_agent.services.uspto import (
    USPTOClient,
    Patent,
    PatentSearchResponse,
    USPTOSearchError,
    build_keyword_query,
)
from fto_agent.services.keyword_extractor import (
    extract_keywords,
    extract_search_terms,
)

__all__ = [
    "USPTOClient",
    "Patent",
    "PatentSearchResponse",
    "USPTOSearchError",
    "build_keyword_query",
    "extract_keywords",
    "extract_search_terms",
]
