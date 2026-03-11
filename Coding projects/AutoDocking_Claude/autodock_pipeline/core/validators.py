"""
Ligand validation: peptide-specific checks and alerts.

Checks:
  1. Reject peptides longer than 5 residues (hard reject).
  2. Alert if cysteines present (disulfide risk).
  3. Alert if peptide is extremely hydrophobic.
  4. Alert if docking score predicts poor binding.
"""

import logging
from dataclasses import dataclass, field
from typing import List

from rdkit import Chem
from rdkit.Chem import Descriptors

logger = logging.getLogger(__name__)

# SMARTS for peptide (amide) bonds: C(=O)-N
_AMIDE_BOND_SMARTS = Chem.MolFromSmarts("[C](=O)[NH]")


@dataclass
class ValidationResult:
    """Result of ligand validation checks."""
    is_valid: bool = True
    is_peptide: bool = False
    residue_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_ligand(smiles: str,
                    name: str = "ligand",
                    max_residues: int = 5,
                    hydrophobicity_threshold: float = 2.5) -> ValidationResult:
    """Run all validation checks on a ligand SMILES.

    Args:
        smiles: Input SMILES string.
        name: Ligand identifier for log messages.
        max_residues: Maximum allowed peptide length (reject above this).
        hydrophobicity_threshold: Mean LogP/residue above which flagged.

    Returns:
        ValidationResult with errors (hard reject) and warnings (alerts).
    """
    result = ValidationResult()
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        result.is_valid = False
        result.errors.append(f"Cannot parse SMILES: {smiles}")
        return result

    # --- Detect if this is a peptide ---
    n_amide_bonds = _count_amide_bonds(mol)
    if n_amide_bonds > 0:
        result.is_peptide = True
        result.residue_count = n_amide_bonds + 1

        # Check 1: Reject peptides above max_residues
        if result.residue_count > max_residues:
            result.is_valid = False
            result.errors.append(
                f"REJECTED: Peptide \'{name}\' has {result.residue_count} residues "
                f"(maximum allowed: {max_residues}). "
                f"Reduce peptide length or increase --max_residues."
            )

        # Check 2: Cysteine / disulfide alert
        result.warnings.extend(_check_cysteine_disulfide(mol, name))

        # Check 3: Hydrophobicity alert
        result.warnings.extend(_check_hydrophobicity(mol, name, n_amide_bonds))

    else:
        # Non-peptide small molecule
        result.is_peptide = False
        logp = Descriptors.MolLogP(mol)
        if logp > 5.0:
            result.warnings.append(
                f"HYDROPHOBICITY ALERT: \'{name}\' has LogP={logp:.1f} (>5.0). "
                f"May have poor aqueous solubility."
            )

    return result


def check_binding_quality(score: float,
                          name: str = "ligand",
                          poor_binding_threshold: float = -4.0) -> List[str]:
    """Check docking score and return warnings if binding looks poor.

    Args:
        score: Vina best binding energy (kcal/mol, more negative = better).
        poor_binding_threshold: Scores above (less negative than) this value are flagged.

    Returns:
        List of warning strings (empty if binding looks acceptable).
    """
    warnings = []
    if score > poor_binding_threshold:
        warnings.append(
            f"POOR BINDING ALERT: \'{name}\' docking score = {score:.2f} kcal/mol "
            f"(threshold: {poor_binding_threshold:.1f}). "
            f"Binding is predicted to be weak. Consider modifying the ligand "
            f"or verifying the docking box placement."
        )
    if score > -2.0:
        warnings.append(
            f"VERY WEAK BINDING: \'{name}\' score = {score:.2f} kcal/mol. "
            f"This is near the noise floor of Vina scoring. "
            f"The ligand likely does not bind this target meaningfully."
        )
    return warnings


def _count_amide_bonds(mol: Chem.Mol) -> int:
    """Count peptide-like amide bonds in the molecule."""
    if _AMIDE_BOND_SMARTS is None:
        return 0
    return len(mol.GetSubstructMatches(_AMIDE_BOND_SMARTS))


def _check_cysteine_disulfide(mol: Chem.Mol, name: str) -> List[str]:
    """Check for thiol groups that could form disulfide bonds."""
    warnings = []

    thiol_pat = Chem.MolFromSmarts("[SH]")
    n_thiols = len(mol.GetSubstructMatches(thiol_pat)) if thiol_pat else 0

    disulfide_pat = Chem.MolFromSmarts("[S]-[S]")
    n_disulfides = len(mol.GetSubstructMatches(disulfide_pat)) if disulfide_pat else 0

    if n_thiols >= 2:
        warnings.append(
            f"DISULFIDE ALERT: \'{name}\' contains {n_thiols} free thiol (Cys-like) groups. "
            f"Intramolecular disulfide bond formation is possible and would change "
            f"the 3D conformation significantly. The docked pose assumes reduced (free SH) state. "
            f"Consider: (1) testing the oxidized (disulfide) form separately, "
            f"(2) adding explicit disulfide constraints, or (3) replacing Cys with Ser/Abu."
        )
    elif n_thiols == 1:
        warnings.append(
            f"CYSTEINE ALERT: \'{name}\' contains 1 free thiol (Cys-like) group. "
            f"Intermolecular disulfide formation with target Cys residues is possible. "
            f"If the target has solvent-accessible cysteines, this could form a covalent "
            f"interaction not captured by Vina scoring."
        )

    if n_disulfides > 0:
        warnings.append(
            f"DISULFIDE NOTE: \'{name}\' contains {n_disulfides} existing disulfide bond(s). "
            f"Ensure the 3D conformer correctly represents the cyclic constraint."
        )

    return warnings


def _check_hydrophobicity(mol: Chem.Mol, name: str, n_amide_bonds: int) -> List[str]:
    """Check if a peptide is extremely hydrophobic using LogP per residue."""
    warnings = []
    logp = Descriptors.MolLogP(mol)
    n_residues = n_amide_bonds + 1 if n_amide_bonds > 0 else 1
    logp_per_residue = logp / n_residues

    if logp_per_residue > 1.5:
        warnings.append(
            f"HYDROPHOBICITY ALERT: \'{name}\' has LogP={logp:.1f} "
            f"({logp_per_residue:.1f}/residue for ~{n_residues} residues). "
            f"This peptide is extremely hydrophobic. Expect: poor aqueous solubility, "
            f"potential aggregation artifacts in docking, and difficult experimental handling. "
            f"Consider replacing hydrophobic residues (Ile/Leu/Val/Phe) with polar ones."
        )
    elif logp_per_residue > 0.8:
        warnings.append(
            f"HYDROPHOBICITY NOTE: \'{name}\' has LogP={logp:.1f} "
            f"({logp_per_residue:.1f}/residue). Moderately hydrophobic -- "
            f"solubility may be limited in aqueous buffers."
        )

    return warnings


def print_validation_alerts(result: ValidationResult) -> None:
    """Print validation errors and warnings to the console."""
    for err in result.errors:
        print(f"\n  [ERROR] {err}")
    for warn in result.warnings:
        print(f"\n  [WARNING] {warn}")


def print_binding_alerts(warnings: List[str]) -> None:
    """Print binding quality warnings to the console."""
    for warn in warnings:
        print(f"\n  [WARNING] {warn}")
