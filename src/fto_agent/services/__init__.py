"""Services for external API integrations.

This module provides clients and utilities for interacting with
patent databases and processing user input for search queries.

Exports:
    Unified Models:
        PatentSource: Enum for patent source (USPTO, EPO).
        UnifiedPatent: Unified patent model for multi-source display.

    USPTO:
        USPTOClient: Client for USPTO PatentsView PatentSearch API.
        Patent: Pydantic model for a single USPTO patent.
        PatentSearchResponse: Pydantic model for USPTO search results.
        USPTOSearchError: Exception for USPTO API errors.
        build_keyword_query: Build PatentsView query from keywords.

    EPO:
        EPOClient: Client for EPO Open Patent Services API.
        EPOPatent: Pydantic model for a single EPO patent.
        EPOSearchResponse: Pydantic model for EPO search results.
        EPOSearchError: Exception for EPO API errors.

    Legal Status:
        PatentStatus: Enum for patent legal status.
        get_patent_status: Parse legal status from INPADOC XML.
        is_patent_active: Check if patent should be included in FTO analysis.
        filter_active_patents: Filter list to only active patents.

    Keywords:
        extract_keywords: Extract keywords from text.
        extract_search_terms: Extract search terms from FTO query inputs.
"""

from fto_agent.services.models import (
    PatentSource,
    UnifiedPatent,
)
from fto_agent.services.uspto import (
    USPTOClient,
    Patent,
    PatentSearchResponse,
    USPTOSearchError,
    build_keyword_query,
)
from fto_agent.services.epo import (
    EPOClient,
    EPOPatent,
    EPOSearchResponse,
    EPOSearchError,
)
from fto_agent.services.legal_status import (
    PatentStatus,
    get_patent_status,
    is_patent_active,
    filter_active_patents,
)
from fto_agent.services.keyword_extractor import (
    extract_keywords,
    extract_search_terms,
)

__all__ = [
    # Unified Models
    "PatentSource",
    "UnifiedPatent",
    # USPTO
    "USPTOClient",
    "Patent",
    "PatentSearchResponse",
    "USPTOSearchError",
    "build_keyword_query",
    # EPO
    "EPOClient",
    "EPOPatent",
    "EPOSearchResponse",
    "EPOSearchError",
    # Legal Status
    "PatentStatus",
    "get_patent_status",
    "is_patent_active",
    "filter_active_patents",
    # Keywords
    "extract_keywords",
    "extract_search_terms",
]
