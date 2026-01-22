"""SMILES validation using RDKit.

This module provides SMILES string validation for chemical structures.
SMILES (Simplified Molecular Input Line Entry System) is a notation
for describing molecular structures as text strings.

Example:
    >>> from fto_agent.validators.smiles import validate_smiles
    >>> result = validate_smiles("CCO")  # Ethanol
    >>> print(result.is_valid, result.message)
    True Valid molecule with 3 atoms
"""

from dataclasses import dataclass
from typing import Optional

try:
    from rdkit import Chem
    from rdkit import RDLogger

    # Suppress RDKit stderr logging for cleaner output
    RDLogger.DisableLog("rdApp.*")
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@dataclass
class SmilesValidationResult:
    """Result of SMILES validation.

    Attributes:
        is_valid: True if the SMILES string is valid or empty.
        message: Human-readable validation message.
        atom_count: Number of atoms in the molecule if valid, None otherwise.
    """

    is_valid: bool
    message: str
    atom_count: Optional[int] = None


def validate_smiles(smiles: str) -> SmilesValidationResult:
    """Validate a SMILES string.

    Args:
        smiles: SMILES notation string (may be empty).

    Returns:
        SmilesValidationResult with validity status and message.

    Note:
        Empty or whitespace-only SMILES returns valid result with empty message,
        as the SMILES field is optional.
    """
    # Empty is valid (field is optional)
    if not smiles or not smiles.strip():
        return SmilesValidationResult(True, "")

    smiles = smiles.strip()

    if not RDKIT_AVAILABLE:
        return SmilesValidationResult(
            False, "RDKit not installed - cannot validate SMILES"
        )

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return SmilesValidationResult(False, "Invalid SMILES notation")

        atom_count = mol.GetNumAtoms()
        return SmilesValidationResult(
            True, f"Valid molecule with {atom_count} atoms", atom_count
        )
    except Exception as e:
        return SmilesValidationResult(False, f"Validation error: {str(e)}")


def is_rdkit_available() -> bool:
    """Check if RDKit is available for SMILES validation.

    Returns:
        True if RDKit is installed and can be imported.
    """
    return RDKIT_AVAILABLE
