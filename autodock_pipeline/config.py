"""
Default configuration and parameter dataclasses for the docking pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class DockingParams:
    """Parameters passed to AutoDock Vina."""
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: float = 20.0
    size_y: float = 20.0
    size_z: float = 20.0
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: int = 3


@dataclass
class OptimizationParams:
    """Parameters controlling the optimization stages."""
    # General
    max_candidates_per_round: int = 20
    top_n_select: int = 5
    delta_affinity_threshold: float = 0.5  # kcal/mol improvement required
    max_rounds: int = 3

    # Side-chain stage
    sc_mutations_per_round: int = 3
    sc_allowed_residues: List[str] = field(default_factory=lambda: [
        "ALA", "VAL", "LEU", "ILE", "PRO", "PHE", "TRP", "MET",
        "GLY", "SER", "THR", "CYS", "TYR", "ASN", "GLN",
        "ASP", "GLU", "LYS", "ARG", "HIS",
    ])

    # Backbone stage
    bb_max_positions: int = 2
    bb_min_interaction_threshold: int = 1  # positions with <= this many bb interactions are candidates

    # Minimization stage
    min_max_deletions: int = 2
    min_score_tolerance: float = 0.3  # kcal/mol worse than best is still acceptable

    # Validation
    max_residues: int = 5            # reject peptides longer than this
    poor_binding_threshold: float = -4.0  # kcal/mol; scores above this trigger alert


@dataclass
class PipelineConfig:
    """Top-level configuration for a pipeline run."""
    # Inputs
    receptor_pdb: Path = Path("receptor.pdb")
    ligand_smiles: str = ""
    ligand_name: str = "ligand"

    # Optional user-specified candidate SMILES
    user_smiles: List[str] = field(default_factory=list)

    # Pocket identification: residue specs for auto-calculating docking box center
    pocket_residues: List[str] = field(default_factory=list)

    # Docking
    docking: DockingParams = field(default_factory=DockingParams)

    # Optimization
    optimization: OptimizationParams = field(default_factory=OptimizationParams)

    # Paths
    output_dir: Path = Path("output")
    vina_executable: str = "vina"  # assumes on PATH; can be full path

    # Receptor preparation
    remove_waters: bool = True
    remove_heteroatoms: bool = True

    # Run mode
    run_mode: str = "full"  # "single_dock", "sidechain", "backbone", "minimize", "full"

    # Stages to run (for granular control)
    stages: List[str] = field(default_factory=lambda: [
        "sidechain", "backbone", "minimize"
    ])
