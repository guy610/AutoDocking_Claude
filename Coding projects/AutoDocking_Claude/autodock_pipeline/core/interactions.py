"""
Interaction metric computation: H-bonds, polar contacts,
backbone vs side-chain classification.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class InteractionMetrics:
    """Summary of ligand-protein interactions for a docked pose."""
    n_hbonds: int = 0
    n_polar_contacts: int = 0
    n_backbone_interactions: int = 0
    n_sidechain_interactions: int = 0
    n_backbone_mutations: int = 0  # relative to original ligand
    details: List[dict] = field(default_factory=list)


def compute_interactions(ligand_pdb: Path,
                         receptor_pdb: Path,
                         original_smiles: str = "") -> InteractionMetrics:
    """Compute H-bond and polar-contact metrics between ligand and receptor.

    Uses distance/angle criteria (no GPL tools):
      - H-bond: donor-acceptor distance <= 3.5 A, D-H-A angle >= 120 deg
      - Polar contact: distance <= 4.0 A between polar atoms
    Classifies interactions by ligand backbone vs side-chain atoms.
    """
    # TODO: Step 3 – implement
    raise NotImplementedError


def classify_ligand_atom(atom_name: str) -> str:
    """Classify a ligand atom as 'backbone' or 'sidechain'.

    Backbone atoms in a canonical peptide: N, CA, C, O, H (amide).
    Everything else is considered side chain.
    """
    backbone_names = {"N", "CA", "C", "O", "H", "HN", "HA"}
    return "backbone" if atom_name.strip() in backbone_names else "sidechain"
