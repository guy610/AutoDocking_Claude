"""Keyword extraction from user input for patent search queries.

This module provides functions to extract search keywords from
problem, solution, and constraints text fields in FTO queries.

The extraction uses simple tokenization and stop word filtering,
which is sufficient for v1. More sophisticated NLP (KeyBERT, YAKE)
may be added in future versions if needed.

Example:
    >>> from fto_agent.services.keyword_extractor import extract_search_terms
    >>> keywords = extract_search_terms(
    ...     problem="Improve skin health and reduce wrinkles",
    ...     solution="GHK peptide for collagen synthesis"
    ... )
    >>> print(keywords)
    ['ghk', 'peptide', 'collagen', 'synthesis', 'improve', 'skin', 'health', 'reduce', 'wrinkles']
"""

from __future__ import annotations

import re
from typing import Set

# Common English stop words to filter out
STOP_WORDS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "been",
    "be",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "this",
    "that",
    "these",
    "those",
    "i",
    "we",
    "you",
    "he",
    "she",
    "it",
    "they",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "also",
    "into",
    "about",
    "after",
    "before",
    "during",
    "through",
    "between",
    "under",
    "over",
    "above",
    "below",
    "up",
    "down",
    "out",
    "off",
    "then",
    "here",
    "there",
    "now",
    "being",
    "any",
    "make",
    "made",
    "use",
    "used",
    "using",
}


def extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """Extract keywords from text using simple tokenization.

    Tokenizes the input text, filters out stop words and short words,
    and returns unique keywords preserving their order of appearance.

    Args:
        text: Input text to extract keywords from. Can be None or empty.
        max_keywords: Maximum number of keywords to return (default 10).

    Returns:
        List of unique keywords, lowercased, ordered by first appearance.
        Returns empty list if text is None or empty.

    Example:
        >>> extract_keywords("Improve skin health via collagen synthesis")
        ['improve', 'skin', 'health', 'via', 'collagen', 'synthesis']

        >>> extract_keywords("The quick brown fox")
        ['quick', 'brown', 'fox']

        >>> extract_keywords("")
        []
    """
    if not text:
        return []

    # Tokenize: extract words (letters only, 3+ chars)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

    # Filter stop words
    filtered = [w for w in words if w not in STOP_WORDS]

    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique: list[str] = []
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
) -> list[str]:
    """Extract search terms from FTO query inputs.

    Combines keywords from problem, solution, and constraints fields.
    Solution keywords are prioritized as they describe the active ingredient.

    Priority order:
    1. Solution (8 keywords max) - describes the active/invention
    2. Problem (6 keywords max) - describes the use case
    3. Constraints (4 keywords max) - describes limitations/context

    Args:
        problem: Problem description text.
        solution: Solution/active description text.
        constraints: Optional constraints text. Can be None or empty.
        max_total: Maximum total keywords to return (default 15).

    Returns:
        Combined list of unique keywords for patent search,
        ordered by priority (solution first, then problem, then constraints).

    Example:
        >>> extract_search_terms(
        ...     problem="improve skin health collagen",
        ...     solution="GHK peptide"
        ... )
        ['ghk', 'peptide', 'improve', 'skin', 'health', 'collagen']

        >>> extract_search_terms(
        ...     problem="reduce wrinkles",
        ...     solution="retinol vitamin",
        ...     constraints="no irritation sensitive skin"
        ... )
        ['retinol', 'vitamin', 'reduce', 'wrinkles', 'irritation', 'sensitive', 'skin']
    """
    # Extract from each field, solution first (highest priority)
    solution_kw = extract_keywords(solution, max_keywords=8)
    problem_kw = extract_keywords(problem, max_keywords=6)
    constraint_kw = extract_keywords(constraints or "", max_keywords=4)

    # Combine, maintaining priority order and deduplicating
    combined: list[str] = solution_kw.copy()

    for kw in problem_kw:
        if kw not in combined:
            combined.append(kw)

    for kw in constraint_kw:
        if kw not in combined:
            combined.append(kw)

    return combined[:max_total]
