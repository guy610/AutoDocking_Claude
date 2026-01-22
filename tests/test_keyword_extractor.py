"""Unit tests for keyword extraction utilities.

Tests verify keyword extraction from user input for patent search queries:
- Basic keyword extraction from text
- Stop word filtering
- Edge cases (empty, None inputs)
- Deduplication and case handling
- Combined extraction from problem/solution/constraints
"""

import pytest

from fto_agent.services.keyword_extractor import extract_keywords, extract_search_terms


class TestExtractKeywords:
    """Tests for extract_keywords function."""

    def test_extracts_keywords_from_simple_text(self):
        """Extracts words from simple text input."""
        result = extract_keywords("skin health collagen synthesis")

        assert "skin" in result
        assert "health" in result
        assert "collagen" in result
        assert "synthesis" in result

    def test_filters_stop_words(self):
        """Filters common English stop words."""
        result = extract_keywords("the skin is for health")

        # Stop words filtered
        assert "the" not in result
        assert "is" not in result
        assert "for" not in result

        # Content words kept
        assert "skin" in result
        assert "health" in result

    def test_handles_empty_string(self):
        """Returns empty list for empty string input."""
        result = extract_keywords("")

        assert result == []

    def test_handles_none_input(self):
        """Returns empty list for None input."""
        result = extract_keywords(None)

        assert result == []

    def test_respects_max_keywords_limit(self):
        """Limits output to specified maximum keywords."""
        text = "one two three four five six seven eight nine ten eleven twelve"

        result = extract_keywords(text, max_keywords=5)

        assert len(result) == 5

    def test_deduplicates_keywords(self):
        """Removes duplicate keywords, keeping first occurrence."""
        result = extract_keywords("skin skin skin health skin")

        assert result.count("skin") == 1
        assert result.count("health") == 1
        # skin appears first in text
        assert result[0] == "skin"

    def test_case_insensitive(self):
        """Converts keywords to lowercase."""
        result = extract_keywords("SKIN Health CoLLaGeN")

        assert "skin" in result
        assert "health" in result
        assert "collagen" in result
        # No uppercase versions
        assert "SKIN" not in result
        assert "Health" not in result

    def test_filters_short_words(self):
        """Filters words with 2 characters or less."""
        result = extract_keywords("to be or not to be skin a")

        # 2 char or less removed
        assert "to" not in result
        assert "be" not in result
        assert "or" not in result
        assert "a" not in result

        # Longer words kept (unless stop words)
        assert "skin" in result

    def test_preserves_order_of_first_appearance(self):
        """Preserves order based on first appearance in text."""
        result = extract_keywords("collagen skin health peptide")

        assert result[0] == "collagen"
        assert result[1] == "skin"
        assert result[2] == "health"
        assert result[3] == "peptide"


class TestExtractSearchTerms:
    """Tests for extract_search_terms function."""

    def test_combines_problem_and_solution(self):
        """Combines keywords from both problem and solution fields."""
        result = extract_search_terms(
            problem="improve skin health",
            solution="ghk peptide collagen"
        )

        # Solution keywords
        assert "ghk" in result
        assert "peptide" in result
        assert "collagen" in result

        # Problem keywords
        assert "improve" in result
        assert "skin" in result
        assert "health" in result

    def test_solution_keywords_first(self):
        """Prioritizes solution keywords before problem keywords."""
        result = extract_search_terms(
            problem="skin health",
            solution="ghk peptide"
        )

        # Solution keywords should come first
        assert result.index("ghk") < result.index("skin")
        assert result.index("peptide") < result.index("health")

    def test_includes_constraints_if_provided(self):
        """Includes keywords from constraints field when provided."""
        result = extract_search_terms(
            problem="skin health",
            solution="ghk peptide",
            constraints="cosmetic formulation stable"
        )

        assert "cosmetic" in result
        assert "formulation" in result
        assert "stable" in result

    def test_handles_empty_constraints(self):
        """Works correctly when constraints is empty string."""
        result = extract_search_terms(
            problem="skin health",
            solution="ghk peptide",
            constraints=""
        )

        assert len(result) > 0
        assert "ghk" in result
        assert "skin" in result

    def test_handles_none_constraints(self):
        """Works correctly when constraints is None."""
        result = extract_search_terms(
            problem="skin health",
            solution="ghk peptide",
            constraints=None
        )

        assert len(result) > 0
        assert "ghk" in result
        assert "skin" in result

    def test_respects_max_total_limit(self):
        """Limits total keywords to specified maximum."""
        result = extract_search_terms(
            problem="alpha beta gamma delta epsilon zeta",
            solution="primary secondary tertiary quaternary",
            constraints="first second third",
            max_total=5
        )

        assert len(result) == 5

    def test_with_ghk_peptide_input(self):
        """Test case based on GHK peptide example from REQUIREMENTS.md."""
        result = extract_search_terms(
            problem="Improve skin health via collagen synthesis",
            solution="GHK peptide copper complex",
            constraints="cosmetic formulation not pharmaceutical"
        )

        # Key terms from solution (priority)
        assert "ghk" in result
        assert "peptide" in result
        assert "copper" in result
        assert "complex" in result

        # Key terms from problem
        assert "collagen" in result or "skin" in result or "health" in result

        # Some constraint terms
        assert "cosmetic" in result or "formulation" in result

    def test_deduplicates_across_fields(self):
        """Removes duplicates that appear in multiple fields."""
        result = extract_search_terms(
            problem="skin health",
            solution="skin peptide",  # "skin" also in problem
            constraints="skin care"   # "skin" also here
        )

        # "skin" should appear only once
        assert result.count("skin") == 1
