"""Unit tests for SMILES validation.

Tests verify the SMILES validation module including:
- Valid SMILES detection
- Invalid SMILES detection
- Empty/whitespace handling
- Real-world peptide SMILES (GHK, Pal-GHK)
- RDKit availability check
"""

import pytest

from fto_agent.validators.smiles import (
    SmilesValidationResult,
    is_rdkit_available,
    validate_smiles,
)


class TestValidateSmiles:
    """Tests for validate_smiles function."""

    def test_validate_smiles_valid_simple(self):
        """Valid simple SMILES (ethanol) returns is_valid=True."""
        result = validate_smiles("CCO")

        assert result.is_valid is True
        assert "Valid" in result.message
        assert result.atom_count == 3

    def test_validate_smiles_valid_aromatic(self):
        """Valid aromatic SMILES (benzene) returns is_valid=True."""
        result = validate_smiles("c1ccccc1")

        assert result.is_valid is True
        assert "Valid" in result.message
        assert result.atom_count == 6

    def test_validate_smiles_invalid_not_a_smiles(self):
        """Invalid SMILES string returns is_valid=False."""
        result = validate_smiles("not_a_smiles")

        assert result.is_valid is False
        assert "Invalid" in result.message
        assert result.atom_count is None

    def test_validate_smiles_invalid_xyz(self):
        """Invalid SMILES (XYZ) returns is_valid=False."""
        result = validate_smiles("XYZ")

        assert result.is_valid is False
        assert "Invalid" in result.message

    def test_validate_smiles_empty(self):
        """Empty string returns is_valid=True (optional field)."""
        result = validate_smiles("")

        assert result.is_valid is True
        assert result.message == ""
        assert result.atom_count is None

    def test_validate_smiles_whitespace(self):
        """Whitespace-only string returns is_valid=True."""
        result = validate_smiles("   \t\n  ")

        assert result.is_valid is True
        assert result.message == ""
        assert result.atom_count is None

    def test_validate_smiles_ghk_peptide(self):
        """GHK peptide SMILES from requirements is valid.

        GHK is Gly-His-Lys, a tripeptide with important biological activity.
        SMILES: NCC(=O)NC(Cc1cnc[nH]1)C(=O)NC(CCCCN)C(=O)O
        """
        ghk_smiles = "NCC(=O)NC(Cc1cnc[nH]1)C(=O)NC(CCCCN)C(=O)O"
        result = validate_smiles(ghk_smiles)

        assert result.is_valid is True
        assert "Valid" in result.message
        # GHK has ~20 heavy atoms
        assert result.atom_count is not None
        assert result.atom_count > 15

    def test_validate_smiles_palmitoyl_ghk(self):
        """Palmitoyl-GHK (Pal-GHK) SMILES from requirements is valid.

        Pal-GHK is GHK with a palmitic acid chain attached.
        """
        # Palmitoyl-GHK: palmitic acid + GHK
        palghk_smiles = "CCCCCCCCCCCCCCCC(=O)NCC(=O)NC(Cc1cnc[nH]1)C(=O)NC(CCCCN)C(=O)O"
        result = validate_smiles(palghk_smiles)

        assert result.is_valid is True
        assert "Valid" in result.message
        # Pal-GHK has 16 extra carbons from palmitate
        assert result.atom_count is not None
        assert result.atom_count > 30

    def test_validate_smiles_with_leading_whitespace(self):
        """SMILES with leading whitespace is stripped and validated."""
        result = validate_smiles("  CCO  ")

        assert result.is_valid is True
        assert result.atom_count == 3


class TestRdkitAvailability:
    """Tests for is_rdkit_available function."""

    def test_is_rdkit_available(self):
        """Verify is_rdkit_available returns True when RDKit is installed."""
        # This test should pass in our environment where RDKit is installed
        assert is_rdkit_available() is True


class TestSmilesValidationResult:
    """Tests for SmilesValidationResult dataclass."""

    def test_dataclass_fields(self):
        """SmilesValidationResult has expected fields."""
        result = SmilesValidationResult(
            is_valid=True,
            message="Valid molecule with 5 atoms",
            atom_count=5,
        )

        assert result.is_valid is True
        assert result.message == "Valid molecule with 5 atoms"
        assert result.atom_count == 5

    def test_dataclass_default_atom_count(self):
        """SmilesValidationResult atom_count defaults to None."""
        result = SmilesValidationResult(is_valid=False, message="Invalid")

        assert result.atom_count is None
