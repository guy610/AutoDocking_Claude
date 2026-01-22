# Phase 3: USPTO Patent Search - Research

**Researched:** 2026-01-22
**Domain:** USPTO PatentsView PatentSearch API, HTTP client patterns, keyword extraction
**Confidence:** HIGH

## Summary

This research establishes the patterns for implementing USPTO patent search via the PatentsView PatentSearch API for the FTO Search Agent. The PatentSearch API is the current (non-legacy) API as of 2026, with the legacy API having been discontinued on May 1, 2025.

The PatentSearch API requires an API key (free, obtained via request), has a rate limit of 45 requests/minute, and supports both GET and POST requests. The API uses a JSON-based query syntax with operators like `_text_any`, `_text_all`, and `_and` for building search queries. For keyword-based patent search (SRCH-03), we will convert the user's problem and solution descriptions into search terms using simple NLP techniques.

Key architectural decisions:
1. Use `httpx` library (not raw `requests`) for HTTP calls - it integrates well with both sync and async patterns
2. Create a dedicated PatentSearchService class that encapsulates all USPTO API interactions
3. Use the established Worker pattern from Phase 1 for background execution
4. Implement Pydantic models for response parsing and validation
5. Search patent_title and patent_abstract fields using `_text_any` operator for keyword matching

**Primary recommendation:** Implement a `USPTOSearchWorker` that uses `httpx.Client` (sync) within the existing Worker pattern, with Pydantic models for response parsing and a simple keyword extraction function for query formulation.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.27+ | HTTP client | Modern, supports both sync/async, connection pooling, type hints |
| pydantic | 2.0+ | Response parsing | Automatic validation, JSON parsing, clear error messages |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PySide6 (existing) | 6.6+ | GUI integration | Worker pattern, signals |
| dataclasses (stdlib) | Built-in | Internal DTOs | After validation, for internal processing |
| re (stdlib) | Built-in | Keyword extraction | Simple text tokenization |
| typing (stdlib) | Built-in | Type hints | All modules |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx | requests | requests lacks native async; httpx better for future async needs |
| httpx | aiohttp | aiohttp is async-only; httpx supports both sync and async |
| pydantic | dataclasses | dataclasses lack validation; API responses need validation |
| Simple keyword extraction | KeyBERT/YAKE | Heavy dependencies (transformers/spacy); overkill for v1 |

**Installation:**
```bash
pip install httpx>=0.27 pydantic>=2.0
```

## Architecture Patterns

### Recommended Project Structure
```
src/
    fto_agent/
        services/
            __init__.py
            uspto.py              # NEW: PatentsView API client
            keyword_extractor.py  # NEW: Simple keyword extraction
        models/
            __init__.py
            patent.py             # NEW: Patent data models (Pydantic + dataclass)
        workers/
            base.py               # Existing Worker pattern
            uspto_worker.py       # NEW: USPTO search worker
        widgets/
            results_panel.py      # NEW: Display search results (Phase 3 or later)
```

### Pattern 1: USPTO API Client Service
**What:** A service class that encapsulates all PatentsView API interactions
**When to use:** Any code that needs to query USPTO patents

```python
# Source: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
# Source: https://www.python-httpx.org/advanced/clients/
import httpx
from typing import Optional
from pydantic import BaseModel

class USPTOClient:
    """Client for USPTO PatentsView PatentSearch API.

    Attributes:
        BASE_URL: API endpoint base URL
        RATE_LIMIT: Maximum requests per minute (45)
    """
    BASE_URL = "https://search.patentsview.org/api/v1"
    RATE_LIMIT = 45  # requests per minute

    def __init__(self, api_key: str):
        """Initialize client with API key.

        Args:
            api_key: PatentsView API key from environment or config
        """
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"X-Api-Key": api_key},
            timeout=30.0,  # 30 second timeout
        )

    def search_patents(
        self,
        query: dict,
        fields: list[str] | None = None,
        size: int = 100,
        sort: dict | None = None,
    ) -> dict:
        """Search patents using PatentsView query syntax.

        Args:
            query: Query dict using PatentsView operators
            fields: Fields to return (default: core fields)
            size: Results per page (max 1000)
            sort: Sort specification

        Returns:
            API response dict with patents array

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses
        """
        if fields is None:
            fields = [
                "patent_id",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
            ]

        params = {
            "q": query,
            "f": fields,
            "o": {"size": size},
        }
        if sort:
            params["s"] = sort

        response = self._client.post("/patent/", json=params)
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

### Pattern 2: PatentsView Query Building
**What:** Functions to build PatentsView query syntax from keywords
**When to use:** Converting user input to API queries

```python
# Source: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
def build_keyword_query(keywords: list[str]) -> dict:
    """Build a PatentsView query from keywords.

    Uses _text_any operator to search title and abstract fields.

    Args:
        keywords: List of keywords to search for

    Returns:
        PatentsView query dict

    Example:
        >>> build_keyword_query(["peptide", "collagen", "skin"])
        {"_or": [
            {"_text_any": {"patent_title": "peptide collagen skin"}},
            {"_text_any": {"patent_abstract": "peptide collagen skin"}}
        ]}
    """
    keyword_string = " ".join(keywords)

    return {
        "_or": [
            {"_text_any": {"patent_title": keyword_string}},
            {"_text_any": {"patent_abstract": keyword_string}},
        ]
    }


def build_cosmetics_cpc_filter() -> dict:
    """Build a CPC filter for cosmetics patents.

    Uses A61K 8 and A61Q classifications.

    Returns:
        PatentsView query dict for CPC filtering
    """
    # A61K 8/00 - Cosmetics or similar toiletry preparations
    # A61Q - Specific use of cosmetics
    return {
        "_or": [
            {"_begins": {"cpc_group_id": "A61K8"}},
            {"_begins": {"cpc_group_id": "A61Q"}},
        ]
    }


def combine_queries(keyword_query: dict, cpc_filter: dict | None = None) -> dict:
    """Combine keyword query with optional CPC filter.

    Args:
        keyword_query: Keyword-based query
        cpc_filter: Optional CPC classification filter

    Returns:
        Combined query using _and operator
    """
    if cpc_filter is None:
        return keyword_query

    return {
        "_and": [keyword_query, cpc_filter]
    }
```

### Pattern 3: Pydantic Response Models
**What:** Pydantic models for parsing and validating API responses
**When to use:** Parsing all API responses to ensure type safety

```python
# Source: https://docs.pydantic.dev/latest/concepts/dataclasses/
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class Patent(BaseModel):
    """A single patent from the PatentsView API."""

    patent_id: str = Field(description="Patent number")
    patent_title: str = Field(description="Title of the patent")
    patent_abstract: Optional[str] = Field(default=None, description="Abstract text")
    patent_date: Optional[date] = Field(default=None, description="Grant date")
    patent_type: Optional[str] = Field(default=None, description="Patent type")

    class Config:
        # Allow extra fields to be ignored
        extra = "ignore"


class PatentSearchResponse(BaseModel):
    """Response from PatentsView patent search endpoint."""

    patents: list[Patent] = Field(default_factory=list)
    count: int = Field(description="Number of results returned")
    total_hits: int = Field(description="Total matching patents")

    class Config:
        extra = "ignore"
```

### Pattern 4: Simple Keyword Extraction
**What:** Extract keywords from problem and solution text without heavy NLP dependencies
**When to use:** Converting user input to search terms

```python
import re
from typing import List

# Common stop words to filter out
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "this", "that", "these",
    "those", "i", "we", "you", "he", "she", "it", "they", "what", "which",
    "who", "when", "where", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "also", "into",
}


def extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """Extract keywords from text using simple tokenization.

    Args:
        text: Input text (problem/solution description)
        max_keywords: Maximum keywords to return

    Returns:
        List of extracted keywords, lowercased

    Example:
        >>> extract_keywords("Improve skin health via collagen synthesis")
        ['improve', 'skin', 'health', 'collagen', 'synthesis']
    """
    # Tokenize: split on non-alphanumeric characters
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())

    # Filter stop words and short words
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # Return unique keywords preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords[:max_keywords]


def extract_search_terms(problem: str, solution: str) -> list[str]:
    """Extract search terms from problem and solution descriptions.

    Combines keywords from both fields, prioritizing solution terms.

    Args:
        problem: Problem description text
        solution: Solution/active description text

    Returns:
        Combined list of keywords for patent search
    """
    solution_keywords = extract_keywords(solution, max_keywords=8)
    problem_keywords = extract_keywords(problem, max_keywords=5)

    # Combine, solution keywords first
    combined = solution_keywords.copy()
    for kw in problem_keywords:
        if kw not in combined:
            combined.append(kw)

    return combined[:12]  # Max 12 keywords total
```

### Pattern 5: USPTO Search Worker
**What:** Worker implementation for background USPTO search
**When to use:** Executing patent search without blocking the GUI

```python
# Uses existing Worker pattern from Phase 1
from fto_agent.workers import Worker
from fto_agent.services.uspto import USPTOClient, build_keyword_query
from fto_agent.services.keyword_extractor import extract_search_terms
from fto_agent.models.patent import PatentSearchResponse

def perform_uspto_search(
    problem: str,
    solution: str,
    api_key: str,
    is_cancelled,
    progress_callback,
) -> PatentSearchResponse:
    """Perform USPTO patent search (runs in worker thread).

    Args:
        problem: Problem description
        solution: Solution description
        api_key: PatentsView API key
        is_cancelled: Callback to check for cancellation
        progress_callback: Callback for progress updates

    Returns:
        PatentSearchResponse with search results
    """
    # Step 1: Extract keywords
    progress_callback(1, 4, "Extracting keywords...")
    if is_cancelled():
        return None

    keywords = extract_search_terms(problem, solution)

    # Step 2: Build query
    progress_callback(2, 4, "Building search query...")
    if is_cancelled():
        return None

    query = build_keyword_query(keywords)

    # Step 3: Execute search
    progress_callback(3, 4, "Searching USPTO patents...")
    if is_cancelled():
        return None

    with USPTOClient(api_key) as client:
        response_data = client.search_patents(query, size=100)

    # Step 4: Parse response
    progress_callback(4, 4, "Processing results...")
    response = PatentSearchResponse.model_validate(response_data)

    return response


# Usage in MainWindow:
# worker = Worker(perform_uspto_search, problem, solution, api_key)
# worker.signals.result.connect(self._on_search_results)
# self._thread_pool.start(worker)
```

### Anti-Patterns to Avoid

- **Creating httpx.Client per request:** Always use a single client instance with connection pooling. Creating clients in loops is inefficient.

- **Ignoring rate limits:** The API allows 45 requests/minute. Don't hammer the API; implement backoff on 429 responses.

- **Hardcoding API key:** Store API key in environment variable or config file, never in source code.

- **Blocking GUI with synchronous calls:** Always use the Worker pattern for HTTP requests, even if they seem fast.

- **Overly complex NLP for v1:** KeyBERT/YAKE add significant dependencies. Simple tokenization is sufficient for keyword-based search.

- **Not validating API responses:** Always use Pydantic models to validate responses. The API may return unexpected data or errors.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP requests | urllib, manual sockets | httpx | Connection pooling, timeouts, retry handling |
| JSON parsing + validation | manual dict access | Pydantic | Type safety, validation errors, optional fields |
| Rate limiting | Custom counters | API 429 handling | API returns Retry-After header |
| Query building | String concatenation | Dict structure | PatentsView expects specific JSON format |
| Background execution | threading.Thread | Worker (Phase 1) | Qt integration, signals, cancellation |

**Key insight:** The PatentsView API has a well-defined query format. Don't try to abstract it away - learn the operators (`_text_any`, `_and`, `_or`, `_begins`) and use them directly.

## Common Pitfalls

### Pitfall 1: Legacy API vs PatentSearch API
**What goes wrong:** Code makes requests to api.patentsview.org and gets 410 Gone errors.
**Why it happens:** The legacy API was discontinued May 1, 2025. Documentation still references it.
**How to avoid:**
1. Use `https://search.patentsview.org/api/v1/` as base URL
2. Use POST with JSON body (not GET with query params)
3. Include `X-Api-Key` header (legacy API didn't require auth)
**Warning signs:** 410 Gone responses, "API not found" errors, authentication failures.

### Pitfall 2: Rate Limit Exceeded (HTTP 429)
**What goes wrong:** Searches fail intermittently with 429 status codes.
**Why it happens:** API allows only 45 requests/minute per API key.
**How to avoid:**
1. Implement exponential backoff on 429 responses
2. Check `Retry-After` header for wait time
3. Don't parallelize requests excessively
4. Consider caching results
**Warning signs:** Intermittent failures, "Too Many Requests" errors.

### Pitfall 3: Missing API Key
**What goes wrong:** Application crashes or fails silently when API key not configured.
**Why it happens:** API key stored in environment variable that may not be set.
**How to avoid:**
1. Check for API key at startup
2. Show clear error message if missing
3. Provide instructions for obtaining key
4. Consider graceful degradation (search disabled)
**Warning signs:** Empty responses, 401/403 errors, KeyError on config access.

### Pitfall 4: Timeout on Large Queries
**What goes wrong:** Searches hang or timeout for broad keyword queries.
**Why it happens:** Default timeout too short; broad queries return lots of data.
**How to avoid:**
1. Set explicit 30-second timeout on httpx client
2. Limit result size (100-200 patents per request)
3. Show progress/loading state in UI
4. Allow cancellation
**Warning signs:** Long wait times, httpx.TimeoutException, frozen progress bar.

### Pitfall 5: Unescaped Special Characters in Keywords
**What goes wrong:** Queries fail or return unexpected results when keywords contain special characters.
**Why it happens:** User may input parentheses, quotes, or operators that conflict with query syntax.
**How to avoid:**
1. Strip special characters during keyword extraction
2. Use only alphanumeric characters in `_text_any` values
3. Test with edge cases (chemical formulas, hyphenated terms)
**Warning signs:** API errors mentioning invalid query syntax, empty results for valid terms.

### Pitfall 6: Empty Search Results Handling
**What goes wrong:** Application crashes or shows broken UI when no patents match.
**Why it happens:** Code assumes results array is non-empty.
**How to avoid:**
1. Pydantic model has `default_factory=list` for patents
2. UI shows "No results found" message
3. Test with obscure keywords that return zero results
**Warning signs:** IndexError, AttributeError on results, blank result panels.

## Code Examples

Verified patterns from official sources:

### Complete USPTO Client Module

```python
# src/fto_agent/services/uspto.py
# Source: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
# Source: https://www.python-httpx.org/advanced/clients/

import httpx
import os
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import date


class Patent(BaseModel):
    """A single patent from PatentsView API."""

    patent_id: str = Field(description="Patent number (e.g., '10123456')")
    patent_title: str = Field(description="Title of the patent")
    patent_abstract: Optional[str] = Field(
        default=None,
        description="Abstract text, may be None for older patents"
    )
    patent_date: Optional[date] = Field(
        default=None,
        description="Grant date"
    )
    patent_type: Optional[str] = Field(
        default=None,
        description="utility, design, plant, or reissue"
    )

    class Config:
        extra = "ignore"


class PatentSearchResponse(BaseModel):
    """Response from PatentsView patent search endpoint."""

    patents: list[Patent] = Field(default_factory=list)
    count: int = Field(default=0, description="Number of results in this response")
    total_hits: int = Field(default=0, description="Total matching patents")

    class Config:
        extra = "ignore"


class USPTOSearchError(Exception):
    """Error during USPTO patent search."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class USPTOClient:
    """Client for USPTO PatentsView PatentSearch API.

    Requires an API key obtained from:
    https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18

    Rate limit: 45 requests/minute per API key.
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
        """
        if fields is None:
            fields = self.DEFAULT_FIELDS.copy()

        # Clamp size to API limits
        size = max(1, min(size, 1000))

        request_body = {
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
                    status_code=429
                )

            response.raise_for_status()

            # Parse response
            data = response.json()
            return PatentSearchResponse.model_validate(data)

        except httpx.TimeoutException:
            raise USPTOSearchError("Request timed out. Try a more specific query.")
        except httpx.HTTPStatusError as e:
            raise USPTOSearchError(
                f"API error: {e.response.status_code}",
                status_code=e.response.status_code
            )
        except Exception as e:
            raise USPTOSearchError(f"Search failed: {str(e)}")

    def close(self):
        """Close the HTTP client and release resources."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def build_keyword_query(keywords: list[str]) -> dict[str, Any]:
    """Build a PatentsView keyword query.

    Searches patent_title and patent_abstract using _text_any operator.

    Args:
        keywords: List of keywords to search for.

    Returns:
        Query dict for PatentsView API.
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
```

### Complete Keyword Extractor Module

```python
# src/fto_agent/services/keyword_extractor.py

import re
from typing import List, Set

# Common English stop words
STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "this", "that", "these",
    "those", "i", "we", "you", "he", "she", "it", "they", "what", "which",
    "who", "when", "where", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "also", "into",
    "about", "after", "before", "during", "through", "between", "under",
    "over", "above", "below", "up", "down", "out", "off", "then", "here",
    "there", "now", "being", "any", "make", "made", "use", "used", "using",
}

# Cosmetics domain terms to boost
COSMETICS_TERMS: Set[str] = {
    "skin", "hair", "cosmetic", "peptide", "collagen", "wrinkle", "aging",
    "moisturizer", "sunscreen", "active", "formulation", "topical", "dermal",
    "anti-aging", "antioxidant", "vitamin", "hyaluronic", "retinol",
}


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract keywords from text using simple tokenization.

    Args:
        text: Input text to extract keywords from.
        max_keywords: Maximum number of keywords to return.

    Returns:
        List of unique keywords, lowercased, ordered by appearance.
    """
    if not text:
        return []

    # Tokenize: extract words (letters only, 3+ chars)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

    # Filter stop words
    filtered = [w for w in words if w not in STOP_WORDS]

    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique: List[str] = []
    for word in filtered:
        if word not in seen:
            seen.add(word)
            unique.append(word)

    return unique[:max_keywords]


def extract_search_terms(
    problem: str,
    solution: str,
    constraints: str | None = None,
    max_total: int = 15,
) -> List[str]:
    """Extract search terms from FTO query inputs.

    Combines keywords from problem, solution, and constraints.
    Solution keywords are prioritized as they describe the active.

    Args:
        problem: Problem description text.
        solution: Solution/active description text.
        constraints: Optional constraints text.
        max_total: Maximum total keywords to return.

    Returns:
        Combined list of keywords for patent search.
    """
    # Extract from each field, solution first
    solution_kw = extract_keywords(solution, max_keywords=8)
    problem_kw = extract_keywords(problem, max_keywords=6)
    constraint_kw = extract_keywords(constraints or "", max_keywords=4)

    # Combine, maintaining priority order
    combined: List[str] = solution_kw.copy()

    for kw in problem_kw:
        if kw not in combined:
            combined.append(kw)

    for kw in constraint_kw:
        if kw not in combined:
            combined.append(kw)

    return combined[:max_total]
```

### Complete USPTO Search Worker Module

```python
# src/fto_agent/workers/uspto_worker.py

from typing import Callable, Optional, Any
from fto_agent.workers import Worker
from fto_agent.services.uspto import (
    USPTOClient,
    USPTOSearchError,
    PatentSearchResponse,
    build_keyword_query,
)
from fto_agent.services.keyword_extractor import extract_search_terms


def perform_uspto_search(
    problem: str,
    solution: str,
    constraints: Optional[str],
    api_key: Optional[str],
    is_cancelled: Callable[[], bool],
    progress_callback: Callable[[int, int, str], None],
) -> PatentSearchResponse:
    """Perform USPTO patent search.

    This function is designed to run in a Worker thread.

    Args:
        problem: Problem description from InputPanel.
        solution: Solution/active description from InputPanel.
        constraints: Optional constraints from InputPanel.
        api_key: PatentsView API key, or None to use environment variable.
        is_cancelled: Callback to check if operation was cancelled.
        progress_callback: Callback for progress updates (current, total, message).

    Returns:
        PatentSearchResponse with search results.

    Raises:
        USPTOSearchError: On API or network errors.
    """
    total_steps = 4

    # Step 1: Extract keywords from user input
    progress_callback(1, total_steps, "Extracting search terms...")
    if is_cancelled():
        return PatentSearchResponse(patents=[], count=0, total_hits=0)

    keywords = extract_search_terms(problem, solution, constraints)
    if not keywords:
        raise USPTOSearchError("Could not extract keywords from input")

    # Step 2: Build query
    progress_callback(2, total_steps, f"Building query with {len(keywords)} keywords...")
    if is_cancelled():
        return PatentSearchResponse(patents=[], count=0, total_hits=0)

    query = build_keyword_query(keywords)

    # Step 3: Execute search
    progress_callback(3, total_steps, "Searching USPTO patent database...")
    if is_cancelled():
        return PatentSearchResponse(patents=[], count=0, total_hits=0)

    with USPTOClient(api_key=api_key) as client:
        response = client.search_patents(
            query=query,
            size=100,  # Return up to 100 patents
            sort=[{"patent_date": "desc"}],  # Most recent first
        )

    # Step 4: Complete
    progress_callback(4, total_steps, f"Found {response.total_hits} matching patents")

    return response


def create_uspto_search_worker(
    data: dict[str, Any],
    api_key: Optional[str] = None,
) -> Worker:
    """Create a Worker for USPTO patent search.

    Args:
        data: Dictionary from InputPanel.get_data() with keys:
              problem, solution, constraints, smiles, countries
        api_key: Optional API key, or None to use environment.

    Returns:
        Configured Worker ready to start.
    """
    return Worker(
        perform_uspto_search,
        problem=data["problem"],
        solution=data["solution"],
        constraints=data.get("constraints"),
        api_key=api_key,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| api.patentsview.org (Legacy API) | search.patentsview.org (PatentSearch API) | May 1, 2025 | All new code must use PatentSearch API |
| No authentication | X-Api-Key header required | May 1, 2025 | Must obtain and configure API key |
| GET with query params | POST with JSON body | May 1, 2025 | Request structure completely different |
| MySQL-style query syntax | Elasticsearch-style operators | May 1, 2025 | New operators: _text_any, _text_all, _text_phrase |
| requests library | httpx library | 2024 | Better async support, type hints, connection pooling |
| dict manual parsing | Pydantic models | 2023 | Automatic validation, clearer error messages |

**Deprecated/outdated:**
- `api.patentsview.org` - Returns 410 Gone, use `search.patentsview.org`
- Legacy query operators (`_eq`, `_contains` for text) - Use `_text_*` operators for full-text search
- PatentsView-APIWrapper library - Archived, was for legacy API only

## Open Questions

Things that couldn't be fully resolved:

1. **API Key Management for Distribution**
   - What we know: API key required, one key per user, 45 req/min limit
   - What's unclear: Should users provide their own key, or should we request a project key?
   - Recommendation: For v1, require user to set PATENTSVIEW_API_KEY environment variable. Document how to obtain key.

2. **CPC Classification Search**
   - What we know: A61K 8 and A61Q are cosmetics CPC codes; Phase 4 requirement
   - What's unclear: Whether to add CPC filtering in Phase 3 or defer to Phase 4
   - Recommendation: Defer CPC filtering to Phase 4 per requirements. Phase 3 focuses on keyword search only.

3. **Keyword Extraction Quality**
   - What we know: Simple tokenization works for basic cases; KeyBERT gives better results but adds dependencies
   - What's unclear: Whether simple extraction is good enough for real cosmetics queries
   - Recommendation: Start with simple extraction; gather feedback from test cases; upgrade to KeyBERT in v2 if needed.

4. **Result Pagination**
   - What we know: API returns up to 1000 per request, uses cursor-based pagination
   - What's unclear: Whether to implement full pagination or limit to first 100 results
   - Recommendation: Return first 100 results for v1. Pagination can be added in v2.

## Sources

### Primary (HIGH confidence)
- [PatentSearch API Reference](https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/) - Official API documentation
- [PatentsView Endpoint Dictionary](https://search.patentsview.org/docs/docs/Search%20API/EndpointDictionary/) - Field definitions
- [HTTPX Documentation](https://www.python-httpx.org/) - HTTP client patterns
- [Pydantic Documentation](https://docs.pydantic.dev/latest/) - Response validation patterns

### Secondary (MEDIUM confidence)
- [PatentsView Code Examples GitHub](https://github.com/PatentsView/PatentsView-Code-Examples) - Official Python examples
- [USPTO CPC A61K Definition](https://www.uspto.gov/web/patents/classification/cpc/html/defA61K.html) - Cosmetics classification
- [USPTO CPC A61Q Definition](https://www.uspto.gov/web/patents/classification/cpc/html/defA61Q.html) - Cosmetics use classification

### Tertiary (LOW confidence)
- WebSearch results on keyword extraction methods - Patterns verified conceptually
- WebSearch results on patent search best practices - General guidance

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Based on official API docs, established httpx/pydantic patterns
- Architecture patterns: HIGH - Follows Phase 1 Worker pattern, official API examples
- Pitfalls: HIGH - Based on official API docs (legacy discontinuation, rate limits)
- Keyword extraction: MEDIUM - Simple approach verified, but not tested on real cosmetics queries

**Research date:** 2026-01-22
**Valid until:** 2026-03-22 (60 days - API stable, but check for updates)
