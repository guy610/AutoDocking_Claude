"""
Default configuration and parameter dataclasses for the docking pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


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

    # Custom (unnatural) amino acid sidechains
    # Key: a short name (e.g. "NLE", "AIB", "UAA1")
    # Value: SMILES of the sidechain R-group with [*] marking the bond to CA
    #   e.g. "[*]CCCC" for norleucine (n-butyl sidechain)
    #   e.g. "[*](C)C" for alpha-aminoisobutyric acid (two methyl groups)
    # The [*] atom will be replaced by the alpha carbon during peptide building.
    sc_custom_sidechains: Dict[str, str] = field(default_factory=dict)

    # Backbone stage
    bb_max_positions: int = 2
    bb_min_interaction_threshold: int = 1  # positions with <= this many bb interactions are candidates

    # Minimization stage
    min_max_deletions: int = 2
    min_score_tolerance: float = 0.3  # kcal/mol worse than best is still acceptable

    # C-terminal cap scanning
    scan_cterm_caps: bool = False  # dock best candidate per round in both acid (COO-) and amide (CONH2) forms

    # N-terminal modifications (applied to best candidate per round)
    nterm_dimethyl: bool = False       # replace N-H with N-CH3 (2x for primary amines, 1x for proline)
    nterm_acyl: bool = False           # acylate N-terminus with variable chain
    nterm_acyl_carbons: int = 2        # 2=acetyl, 16=palmitoyl
    nterm_custom_smiles: str = ""      # SMILES with [*] for bond to N-terminal nitrogen

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
    ligand_sequence: str = ""  # original peptide sequence (1-letter codes) if known

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

    # Hierarchical screening (Phase 2-4 executables)
    gnina_executable: str = ""       # path to gnina binary; empty = skip phases 2-4
    rxdock_executable: str = ""      # path to rbdock binary; empty = skip phase 3
    hierarchical_top_n: int = 20     # candidates to carry into phases 2-4

    # Pocket Triage (auto_consensus box mode)
    p2rank_executable: str = ""      # path to P2Rank prank binary; e.g. "wsl /opt/p2rank/prank"
    fpocket_executable: str = ""     # path to fpocket binary; e.g. "wsl fpocket"
    min_pocket_volume: float = 300.0  # minimum Fpocket cavity volume (Angstroms^3) to pass triage

    # Receptor preparation
    remove_waters: bool = True
    remove_heteroatoms: bool = True

    # Run mode
    run_mode: str = "full"  # "single_dock", "sidechain", "backbone", "minimize", "full", "hierarchical"

    # Docking box mode: "pocket", "manual", "default", "auto_consensus"
    box_mode: str = "default"

    # Stages to run (for granular control)
    stages: List[str] = field(default_factory=lambda: [
        "sidechain", "backbone", "minimize"
    ])


@dataclass
class SmallMoleculeConfig:
    """Configuration for the small molecule optimization pipeline."""
    # Input: crystal structure containing receptor + co-crystallized ligand
    crystal_pdb: Path = Path("crystal.pdb")
    ligand_resname: str = ""          # 3-letter residue name (auto-detect if empty)
    ligand_chain: str = ""            # chain ID (auto-detect if empty)
    ligand_smiles_override: str = ""  # manual SMILES (bypasses PDB extraction, which can miss aromaticity)

    # Docking box
    autobox_padding: float = 4.0      # Angstroms padding around ligand

    # Binding analysis parameters
    hbond_cutoff: float = 3.5
    hydrophobic_cutoff: float = 4.5
    clash_vdw_scale: float = 0.75
    charge_repulsion_cutoff: float = 4.0

    # Analog generation
    max_analogs: int = 50
    enable_bioisosteres: bool = True
    enable_extensions: bool = True
    enable_removals: bool = True

    # Docking
    docking: DockingParams = field(default_factory=DockingParams)

    # Hierarchical screening (optional)
    run_mode: str = "full"            # "analysis_only", "full", "hierarchical"
    gnina_executable: str = ""
    rxdock_executable: str = ""
    hierarchical_top_n: int = 20

    # Multi-round optimization
    max_rounds: int = 3
    delta_threshold: float = 0.3      # kcal/mol improvement to advance
    max_combos_per_round: int = 100   # cap combinatorial explosion

    # Property target window
    property_target: str = "cosmetic"  # "cosmetic", "drug_like", "custom"
    target_logp_min: float = 1.0
    target_logp_max: float = 3.0
    target_mw_max: float = 350.0
    target_psa_max: float = 70.0
    target_hbd_max: int = 2
    target_hba_max: int = 5

    # Pro-drug esters
    enable_prodrug_esters: bool = True

    # Cyclization detection
    enable_cyclization_detection: bool = True

    # v0.9.2 SAR enhancements
    enable_stereoisomer_enum: bool = True
    stereo_max_centers: int = 4           # cap at 2^4=16 isomers
    stereo_final_top_n: int = 5           # top N binders for full enumeration in final round

    enable_thioether_detection: bool = True

    enable_metabolic_blocking: bool = True

    enable_scaffold_hopping: bool = False  # off by default — expensive
    max_scaffold_hops: int = 10

    enable_mmp_tracking: bool = True

    enable_torsion_filter: bool = True
    torsion_amide_tolerance: float = 30.0  # degrees from 0/180

    target_rotatable_max: int = -1         # -1 = use preset default

    # Paths
    output_dir: Path = Path("output_sm")
    vina_executable: str = "vina"

    # Receptor preparation
    remove_waters: bool = True
