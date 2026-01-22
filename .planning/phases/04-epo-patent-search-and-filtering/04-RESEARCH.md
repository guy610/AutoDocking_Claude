# Phase 4: EPO Patent Search and Filtering - Research

**Researched:** 2026-01-22
**Domain:** EPO Open Patent Services (OPS) API, CPC Classification, INPADOC Legal Status
**Confidence:** HIGH

## Summary

The EPO Open Patent Services (OPS) v3.2 is a RESTful API providing access to European and worldwide patent data. The recommended approach is to use the `python-epo-ops-client` library (Apache 2.0 licensed) which handles OAuth authentication, token renewal, and throttling automatically. The API uses CQL (Contextual Query Language) for searches and returns XML data that requires parsing.

For legal status filtering (SRCH-05), the INPADOC database provides worldwide legal status data accessible via the `legal()` method. Patent status determination requires analyzing legal event codes to identify expired, lapsed, or withdrawn patents. For cosmetic-relevant CPC classification search (SRCH-04), the codes A61K 8/00 (cosmetics/toiletry preparations) and A61Q (specific uses) should be included in CQL queries.

**Primary recommendation:** Use `python-epo-ops-client` library with CQL queries including CPC classifications, retrieve legal status separately via the `legal()` endpoint, and implement client-side status filtering based on INPADOC event codes.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-epo-ops-client | 4.x | EPO OPS API client | Official community library, handles OAuth/throttling |
| httpx | (existing) | HTTP fallback/custom requests | Already used in project for USPTO |
| pydantic | (existing) | Response model validation | Existing pattern in project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lxml | 5.x | XML parsing | Parse EPO OPS XML responses |
| defusedxml | 0.7.x | Safe XML parsing | Security: prevent XML attacks |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-epo-ops-client | patent-client | patent-client is higher-level but EPO Register is "not working in v.3" per docs |
| python-epo-ops-client | Raw httpx + OAuth | More control but must implement throttling/token refresh manually |

**Installation:**
```bash
pip install python-epo-ops-client lxml defusedxml
```

## Architecture Patterns

### Recommended Project Structure
```
src/fto_agent/
├── services/
│   ├── epo.py              # EPOClient class (mirrors USPTOClient pattern)
│   ├── legal_status.py     # Legal status parsing and filtering logic
│   └── models.py           # Unified Patent model for both sources
├── workers/
│   └── epo_worker.py       # EPO search worker (mirrors uspto_worker.py)
└── widgets/
    └── results_panel.py    # Update to handle unified results
```

### Pattern 1: EPOClient Following USPTOClient Pattern
**What:** Create EPOClient class mirroring the existing USPTOClient design
**When to use:** All EPO OPS API interactions
**Example:**
```python
# Source: Existing USPTOClient pattern + python-epo-ops-client docs
import epo_ops
from typing import Optional, Any
from pydantic import BaseModel, Field

class EPOPatent(BaseModel):
    """Patent from EPO OPS API."""
    publication_number: str = Field(description="Publication number (e.g., 'EP1000000A1')")
    title: Optional[str] = Field(default=None)
    abstract: Optional[str] = Field(default=None)
    publication_date: Optional[str] = Field(default=None)
    applicants: list[str] = Field(default_factory=list)
    cpc_classifications: list[str] = Field(default_factory=list)

    class Config:
        extra = "ignore"

class EPOSearchResponse(BaseModel):
    """Response from EPO OPS search."""
    patents: list[EPOPatent] = Field(default_factory=list)
    count: int = Field(default=0)
    total_hits: int = Field(default=0)

class EPOSearchError(Exception):
    """Error during EPO patent search."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class EPOClient:
    """Client for EPO Open Patent Services API."""

    COSMETIC_CPC_CODES = ["A61K8", "A61Q"]  # A61K 8/00 and A61Q subclasses

    def __init__(self, consumer_key: Optional[str] = None, consumer_secret: Optional[str] = None):
        """Initialize client with OAuth credentials."""
        import os
        key = consumer_key or os.environ.get("EPO_OPS_CONSUMER_KEY")
        secret = consumer_secret or os.environ.get("EPO_OPS_CONSUMER_SECRET")

        if not key or not secret:
            raise EPOSearchError(
                "EPO OPS credentials required. Set EPO_OPS_CONSUMER_KEY and "
                "EPO_OPS_CONSUMER_SECRET environment variables."
            )

        # Create client with throttling middleware (default)
        self._client = epo_ops.Client(key=key, secret=secret)

    def search_patents(
        self,
        keywords: list[str],
        include_cosmetic_cpc: bool = True,
        range_begin: int = 1,
        range_end: int = 100,
    ) -> EPOSearchResponse:
        """Search patents using CQL query."""
        # Build CQL query
        cql = self._build_cql_query(keywords, include_cosmetic_cpc)

        response = self._client.published_data_search(
            cql=cql,
            range_begin=range_begin,
            range_end=range_end,
        )

        # Parse XML response
        return self._parse_search_response(response)
```

### Pattern 2: CQL Query Building for Cosmetics
**What:** Build CQL queries with keyword search AND cosmetic CPC classifications
**When to use:** All patent searches for cosmetic FTO
**Example:**
```python
# Source: EPO OPS CQL documentation, Espacenet help
def _build_cql_query(
    self,
    keywords: list[str],
    include_cosmetic_cpc: bool = True,
) -> str:
    """Build CQL query for EPO OPS search.

    CQL Fields:
    - ti = title
    - ab = abstract
    - ta = title and abstract combined
    - cpc = CPC classification
    - pa = applicant
    - in = inventor
    """
    parts = []

    # Keyword search in title and abstract
    if keywords:
        keyword_str = " ".join(keywords)
        parts.append(f'ta="{keyword_str}"')

    # Add cosmetic CPC classification filter
    if include_cosmetic_cpc:
        # A61K8 = Cosmetics or similar toiletry preparations
        # A61Q = Specific use of cosmetics or similar toiletry preparations
        cpc_query = "(cpc=A61K8 OR cpc=A61Q)"
        parts.append(cpc_query)

    # Combine with AND
    return " AND ".join(parts) if parts else ""
```

### Pattern 3: Legal Status Filtering for Active Patents
**What:** Retrieve and filter patents by legal status to exclude expired/lapsed
**When to use:** After search results, before displaying to user (SRCH-05)
**Example:**
```python
# Source: INPADOC documentation, Lens patent status calculations
from enum import Enum
from typing import Optional

class PatentStatus(Enum):
    ACTIVE = "active"          # In force, being renewed
    EXPIRED = "expired"        # Term date passed
    LAPSED = "lapsed"          # Non-payment of fees
    WITHDRAWN = "withdrawn"    # Application withdrawn
    PENDING = "pending"        # Not yet granted
    UNKNOWN = "unknown"        # Insufficient data

# INPADOC event categories indicating lapsed/expired status
LAPSED_EVENT_CATEGORIES = [
    "L",   # Lapse
    "W",   # Withdrawal
    "H",   # Non-payment events
]

# Keywords in event descriptions indicating inactive status
INACTIVE_KEYWORDS = [
    "lapse", "lapsed", "expired", "withdrawn",
    "refusal", "refused", "revoked", "revocation",
    "abandoned", "non-payment", "not paid",
]

def get_legal_status(self, publication_number: str) -> PatentStatus:
    """Get legal status for a patent from INPADOC."""
    try:
        response = self._client.legal(
            reference_type="publication",
            input=epo_ops.models.Epodoc(publication_number),
        )
        return self._parse_legal_status(response)
    except Exception:
        return PatentStatus.UNKNOWN

def _parse_legal_status(self, response) -> PatentStatus:
    """Parse INPADOC legal status response."""
    # Parse XML, look at latest legal events
    # Check for lapse/withdrawal/expiry events
    # Return appropriate status
    pass

def filter_active_patents(
    self,
    patents: list[EPOPatent],
) -> list[EPOPatent]:
    """Filter to only active/enforced patents."""
    active = []
    for patent in patents:
        status = self.get_legal_status(patent.publication_number)
        if status in (PatentStatus.ACTIVE, PatentStatus.PENDING, PatentStatus.UNKNOWN):
            # Include pending (could still be granted) and unknown (err on side of caution)
            active.append(patent)
    return active
```

### Pattern 4: Unified Patent Model
**What:** Common model for patents from both USPTO and EPO
**When to use:** ResultsPanel display, unified results view
**Example:**
```python
# Source: Design pattern for multi-source aggregation
from enum import Enum
from pydantic import BaseModel, Field

class PatentSource(Enum):
    USPTO = "USPTO"
    EPO = "EPO"

class UnifiedPatent(BaseModel):
    """Unified patent model for display from multiple sources."""
    id: str = Field(description="Patent ID (publication number)")
    title: str
    abstract: Optional[str] = None
    date: Optional[str] = None  # Grant or publication date
    source: PatentSource
    url: str = Field(description="Link to patent on official site")

    # Optional fields that may not be available from all sources
    status: Optional[PatentStatus] = None
    cpc_codes: list[str] = Field(default_factory=list)

    @classmethod
    def from_uspto(cls, patent: Patent) -> "UnifiedPatent":
        """Convert USPTO Patent to UnifiedPatent."""
        return cls(
            id=f"US{patent.patent_id}",
            title=patent.patent_title,
            abstract=patent.patent_abstract,
            date=str(patent.patent_date) if patent.patent_date else None,
            source=PatentSource.USPTO,
            url=f"https://patents.google.com/patent/US{patent.patent_id}",
        )

    @classmethod
    def from_epo(cls, patent: EPOPatent, status: PatentStatus = None) -> "UnifiedPatent":
        """Convert EPO Patent to UnifiedPatent."""
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
```

### Anti-Patterns to Avoid
- **Bulk legal status queries:** Querying legal status for 100+ patents sequentially will be slow and hit rate limits. Batch or cache results.
- **Ignoring throttling:** EPO OPS has strict throttling (green/yellow/red/black). The middleware handles this, but custom implementations must respect it.
- **Hardcoding CPC without context:** A61K 8/00 and A61Q are cosmetics-specific; don't apply to other domains.
- **Trusting legal status 100%:** INPADOC has delays; for critical decisions, verify with patent office directly.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth token management | Custom token refresh | python-epo-ops-client | Handles expiration, 400 errors, auto-renewal |
| API throttling | Custom rate limiter | epo_ops.middlewares.Throttler | Built-in, respects EPO's rolling window |
| XML parsing | Manual string parsing | lxml with defusedxml | Security, namespace handling, XPath |
| CQL query building | String concatenation | Structured builder | Escaping, validation, boolean logic |
| Patent status calculation | Simple date check | INPADOC event analysis | Status depends on events not just dates |

**Key insight:** EPO OPS has quirks (XML responses, OAuth, throttling) that the community library handles. The legal status determination requires understanding INPADOC event codes which are country-specific.

## Common Pitfalls

### Pitfall 1: Registration Delay
**What goes wrong:** EPO developer portal registration can take 24-48 hours for approval
**Why it happens:** Manual approval process at EPO
**How to avoid:** Start registration at the beginning of Phase 4, not when implementing
**Warning signs:** "Account pending" status on developer portal

### Pitfall 2: XML Response Handling
**What goes wrong:** EPO OPS returns XML, not JSON. Naive parsing fails with namespaces.
**Why it happens:** Legacy API design
**How to avoid:** Use lxml with proper namespace handling:
```python
# Source: lxml documentation
from lxml import etree

NAMESPACES = {
    'ops': 'http://ops.epo.org',
    'exchange': 'http://www.epo.org/exchange',
    'reg': 'http://www.epo.org/register',
}

def parse_response(xml_content: bytes):
    root = etree.fromstring(xml_content)
    # Use namespaced XPath
    titles = root.xpath('//exchange:invention-title', namespaces=NAMESPACES)
```
**Warning signs:** Empty results when patents exist, XPath returning nothing

### Pitfall 3: Legal Status Complexity
**What goes wrong:** Assuming "expired" is a simple date calculation
**Why it happens:** Patent term varies by country, extensions exist, fees can reinstate
**How to avoid:** Use INPADOC legal events, not just dates. Look for specific event codes.
**Warning signs:** Filtering out active patents or including truly expired ones

### Pitfall 4: CPC Hierarchy Truncation
**What goes wrong:** Searching "cpc=A61K" returns everything, not cosmetics
**Why it happens:** A61K covers ALL medical/dental/toiletry preparations
**How to avoid:** Use A61K8 (group 8/00 specifically for cosmetics) not A61K broadly
**Warning signs:** Search returns pharmaceutical patents not relevant to cosmetics

### Pitfall 5: Rate Limit Colors
**What goes wrong:** Getting blocked (black status) after heavy querying
**Why it happens:** Not respecting yellow/red warnings, querying too fast
**How to avoid:** Use Throttler middleware, implement exponential backoff
**Warning signs:** X-Throttling-Control header showing "yellow" or "red"

## Code Examples

Verified patterns from official sources:

### Basic EPO OPS Client Usage
```python
# Source: python-epo-ops-client GitHub README
import epo_ops

# Initialize with OAuth credentials
client = epo_ops.Client(key="consumer_key", secret="consumer_secret")

# Search using CQL
response = client.published_data_search(
    cql='ta="peptide collagen" AND cpc=A61K8',
    range_begin=1,
    range_end=25,
)

# Get legal status
from epo_ops.models import Epodoc
legal_response = client.legal(
    reference_type="publication",
    input=Epodoc("EP1000000"),
)

# Get patent family
family_response = client.family(
    reference_type="publication",
    input=Epodoc("EP1000000"),
    constituents=["biblio", "legal"],
)
```

### Parsing Search Results
```python
# Source: EPO OPS response structure + lxml docs
from lxml import etree

NAMESPACES = {
    'ops': 'http://ops.epo.org',
    'exchange': 'http://www.epo.org/exchange',
}

def parse_search_results(xml_bytes: bytes) -> list[dict]:
    """Parse EPO OPS search XML response."""
    root = etree.fromstring(xml_bytes)

    patents = []
    # Navigate to exchange documents
    for doc in root.xpath('//exchange:exchange-document', namespaces=NAMESPACES):
        patent = {
            'country': doc.get('country'),
            'doc_number': doc.get('doc-number'),
            'kind': doc.get('kind'),
        }

        # Get title (may be in multiple languages)
        title_elem = doc.xpath('.//exchange:invention-title[@lang="en"]', namespaces=NAMESPACES)
        if title_elem:
            patent['title'] = title_elem[0].text

        # Get abstract
        abstract_elem = doc.xpath('.//exchange:abstract[@lang="en"]/exchange:p', namespaces=NAMESPACES)
        if abstract_elem:
            patent['abstract'] = abstract_elem[0].text

        patents.append(patent)

    return patents
```

### CQL Query Examples for Cosmetics
```python
# Source: Espacenet CQL help, EPO classification search
# Search cosmetic peptides
cql_peptide_cosmetic = 'ta="peptide" AND (cpc=A61K8 OR cpc=A61Q)'

# Search skin health cosmetics
cql_skin = 'ta="skin health collagen" AND cpc=A61Q19'  # A61Q19 = preparations for care of the skin

# Search hair cosmetics
cql_hair = 'ta="hair" AND (cpc=A61Q5 OR cpc=A61K8)'  # A61Q5 = preparations for care of the hair

# Exclude certain applicants (if needed)
cql_exclude = 'ta="peptide" AND cpc=A61K8 NOT pa="CompanyName"'
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OPS v3.1 | OPS v3.2 | 2020+ | New endpoints, better rate limiting |
| Manual OAuth | Library-handled | Ongoing | No token management code needed |
| Paying users only | Free tier (4GB/week) | Years ago | Free access sufficient for most use cases |
| XML only | Still XML only | N/A | Still requires XML parsing (no JSON option) |

**Deprecated/outdated:**
- Direct OAuth implementation: Use library instead
- Old EPO developer portal URLs: Now at developers.epo.org

## Open Questions

Things that couldn't be fully resolved:

1. **Legal status event code completeness**
   - What we know: INPADOC has 4,400+ legal status codes, country-specific
   - What's unclear: Which specific codes reliably indicate "active" vs "expired" across all jurisdictions
   - Recommendation: Start with EP (European) codes, expand based on testing. Download EPO's weekly legal status code table for reference.

2. **Rate limits for legal status queries**
   - What we know: Throttler handles general rate limits
   - What's unclear: Is there a separate limit for `legal()` endpoint vs `published_data_search()`?
   - Recommendation: Implement caching for legal status, batch requests where possible

3. **Combined USPTO + EPO result deduplication**
   - What we know: Same patent can appear in both databases (e.g., US application with EP family member)
   - What's unclear: Best strategy for deduplication in unified view
   - Recommendation: Display both but group by patent family in future phase

## Sources

### Primary (HIGH confidence)
- [python-epo-ops-client GitHub](https://github.com/ip-tools/python-epo-ops-client) - API methods, usage examples
- [Patent Client Documentation](https://patent-client.readthedocs.io/en/latest/getting_started.html) - EPO setup, CQL basics
- [EPO CQL Go Package](https://pkg.go.dev/github.com/patent-dev/epo-ops/cql) - Field names and query syntax

### Secondary (MEDIUM confidence)
- [Lens Patent Legal Status](https://support.lens.org/knowledge-base/patent-legal-status-calculations/) - Status calculation logic
- [PublicAPI.dev EPO API](https://publicapi.dev/epo-api) - Endpoint summary, rate limits
- [Espacenet Classification Search](https://worldwide.espacenet.com/help?locale=en_EP&method=handleHelpTopic&topic=classificationsearch) - CPC/IPC field usage

### Tertiary (LOW confidence)
- WebSearch results for legal status codes - Country-specific, needs verification with EPO tables
- INPADOC event code documentation - Referenced but not directly fetched

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Library is well-established, actively maintained
- Architecture: HIGH - Follows existing USPTOClient pattern
- CQL/CPC search: MEDIUM - Syntax verified, but nuances may exist
- Legal status filtering: MEDIUM - Logic understood, but event codes need validation
- Pitfalls: HIGH - Well-documented in community resources

**Research date:** 2026-01-22
**Valid until:** 2026-02-22 (30 days - stable API, infrequent changes)

---

## Registration Reminder

**IMPORTANT:** Register for EPO OPS credentials immediately at:
https://developers.epo.org/user/register

Approval may take 24-48 hours. Environment variables to set after registration:
- `EPO_OPS_CONSUMER_KEY`
- `EPO_OPS_CONSUMER_SECRET`
