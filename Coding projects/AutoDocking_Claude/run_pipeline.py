#!/usr/bin/env python3
"""
Entry point for the AutoDock iterative optimization pipeline.

Usage examples:
  # Single docking
  python run_pipeline.py --receptor protein.pdb --smiles "CC(=O)NC" --mode single_dock

  # Full optimization pipeline
  python run_pipeline.py --receptor protein.pdb --smiles "CC(=O)NC" --mode full

  # Side-chain only
  python run_pipeline.py --receptor protein.pdb --smiles "CC(=O)NC" --mode sidechain

  # With docking box parameters
  python run_pipeline.py --receptor protein.pdb --smiles "CC(=O)NC" \
      --center 10.0 20.0 30.0 --box_size 25 25 25 --exhaustiveness 16

  # With user-specified extra candidates
  python run_pipeline.py --receptor protein.pdb --smiles "CC(=O)NC" \
      --user_smiles "CC(=O)N" "CC(=O)NCC"
"""

import argparse
import logging
import sys
from pathlib import Path

from autodock_pipeline.config import DockingParams, OptimizationParams, PipelineConfig
from autodock_pipeline.pipeline import DockingPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AutoDock Vina iterative peptide optimization pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required inputs
    p.add_argument("--receptor", required=True, type=Path,
                   help="Path to target protein PDB file")
    p.add_argument("--smiles", required=True,
                   help="SMILES string for the initial ligand")
    p.add_argument("--ligand_name", default="ligand",
                   help="Name / ID for the ligand (default: ligand)")

    # Run mode
    p.add_argument("--mode", default="full",
                   choices=["single_dock", "sidechain", "backbone",
                            "minimize", "full"],
                   help="Pipeline run mode (default: full)")

    # Docking box
    p.add_argument("--center", nargs=3, type=float, default=[0, 0, 0],
                   metavar=("X", "Y", "Z"),
                   help="Docking box center coordinates")
    p.add_argument("--box_size", nargs=3, type=float, default=[20, 20, 20],
                   metavar=("SX", "SY", "SZ"),
                   help="Docking box dimensions in Angstroms")
    p.add_argument("--exhaustiveness", type=int, default=8)
    p.add_argument("--num_modes", type=int, default=9)
    p.add_argument("--energy_range", type=int, default=3)

    # Pocket identification
    p.add_argument("--pocket_residues", nargs="*", default=[],
                   help="Residue specs to define docking pocket (e.g., A:TYR:45 120 GLU55)")

    # Optimization
    p.add_argument("--max_rounds", type=int, default=3,
                   help="Max optimization rounds per stage")
    p.add_argument("--top_n", type=int, default=5,
                   help="Keep top N candidates per round")
    p.add_argument("--delta_threshold", type=float, default=0.5,
                   help="Min improvement (kcal/mol) over original to keep a candidate")

    # Validation
    p.add_argument("--max_residues", type=int, default=5,
                   help="Max peptide length in residues (reject above this, default: 5)")
    p.add_argument("--poor_binding", type=float, default=-4.0,
                   help="Binding score threshold (kcal/mol) above which an alert is raised (default: -4.0)")

    # User-specified candidates
    p.add_argument("--user_smiles", nargs="*", default=[],
                   help="Additional SMILES strings to dock explicitly")

    # Paths
    p.add_argument("--output_dir", type=Path, default=Path("output"),
                   help="Output directory (default: ./output)")
    p.add_argument("--vina", default="vina",
                   help="Path to Vina executable (default: 'vina' on PATH)")

    # Receptor options
    p.add_argument("--keep_waters", action="store_true",
                   help="Do not remove water molecules from receptor")
    p.add_argument("--keep_hetatm", action="store_true",
                   help="Do not remove heteroatoms from receptor")

    # Verbosity
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Enable verbose (DEBUG) logging")

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    docking_params = DockingParams(
        center_x=args.center[0],
        center_y=args.center[1],
        center_z=args.center[2],
        size_x=args.box_size[0],
        size_y=args.box_size[1],
        size_z=args.box_size[2],
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        energy_range=args.energy_range,
    )

    opt_params = OptimizationParams(
        max_rounds=args.max_rounds,
        top_n_select=args.top_n,
        delta_affinity_threshold=args.delta_threshold,
        max_residues=args.max_residues,
        poor_binding_threshold=args.poor_binding,
    )

    # Map run mode to stages list
    mode_to_stages = {
        "single_dock": [],
        "sidechain": ["sidechain"],
        "backbone": ["backbone"],
        "minimize": ["minimize"],
        "full": ["sidechain", "backbone", "minimize"],
    }

    config = PipelineConfig(
        receptor_pdb=args.receptor,
        pocket_residues=args.pocket_residues,
        ligand_smiles=args.smiles,
        ligand_name=args.ligand_name,
        user_smiles=args.user_smiles,
        docking=docking_params,
        optimization=opt_params,
        output_dir=args.output_dir,
        vina_executable=args.vina,
        remove_waters=not args.keep_waters,
        remove_heteroatoms=not args.keep_hetatm,
        run_mode=args.mode,
        stages=mode_to_stages[args.mode],
    )

    # Run
    pipeline = DockingPipeline(config)
    pipeline.run()


if __name__ == "__main__":
    main()
