#!/usr/bin/env python3
"""
MMP-9 Hydroxamate Peptidic Inhibitor — Full Hierarchical Pipeline Test

Receptor: MMP-9 catalytic domain (PDB: 1GKC)
Ligand:   Phe-Leu-NHOH (hydroxamic acid warhead targeting catalytic zinc)
Pipeline: Sidechain (1 round, 5 mut pos1 + 5 mut pos2, +2 UAAs, +backbone)
          → Hierarchical (GNINA rescore + RxDock de novo + Consensus)

Uses mock GNINA/RxDock executables since neither has Windows binaries.
"""
import sys
import os
import subprocess
import time
import csv

os.environ["PYTHONUTF8"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from unittest.mock import patch

# ── Mock executable setup ────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
MOCK_DIR = PROJECT_DIR / "mock_tools"
MOCK_GNINA = str(MOCK_DIR / "mock_gnina.py")
MOCK_RBCAVITY = str(MOCK_DIR / "mock_rbcavity.py")
MOCK_RBDOCK = str(MOCK_DIR / "mock_rbdock.py")

GNINA_EXE = "MOCK_GNINA_EXE"
RBDOCK_EXE = "MOCK_RBDOCK_EXE"

_real_subprocess_run = subprocess.run


class AutoContinueCheckpoint:
    """Checkpoint handler that auto-continues (no user input needed)."""
    def interactive_checkpoint(self, results, stage_name, config, receptor_pdbqt, output_dir):
        print("\n  [AUTO-CONTINUE] Checkpoint: {} ({} results)".format(
            stage_name, len(results)))
        return ("continue", results, None)


def _patched_subprocess_run(cmd, **kwargs):
    """Intercept subprocess.run calls for mock GNINA/RxDock."""
    if not isinstance(cmd, list) or len(cmd) == 0:
        return _real_subprocess_run(cmd, **kwargs)
    exe = cmd[0]
    if exe == GNINA_EXE:
        return _real_subprocess_run([sys.executable, MOCK_GNINA] + cmd[1:], **kwargs)
    if exe == RBDOCK_EXE:
        return _real_subprocess_run([sys.executable, MOCK_RBDOCK] + cmd[1:], **kwargs)
    if "rbcavity" in str(exe):
        return _real_subprocess_run([sys.executable, MOCK_RBCAVITY] + cmd[1:], **kwargs)
    return _real_subprocess_run(cmd, **kwargs)


def main():
    from autodock_pipeline.config import PipelineConfig
    from autodock_pipeline.pipeline import DockingPipeline

    output_dir = Path("output_mmp9_test")

    print("=" * 70)
    print("  MMP-9 HYDROXAMATE INHIBITOR — HIERARCHICAL PIPELINE TEST")
    print("=" * 70)

    # ── Config ───────────────────────────────────────────────
    config = PipelineConfig()
    config.receptor_pdb = PROJECT_DIR / "MMP9_1GKC.pdb"
    config.output_dir = output_dir

    # Phe-Leu-NHOH hydroxamic acid inhibitor
    config.ligand_smiles = "N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CC(C)C)C(=O)NO"
    config.ligand_name = "PheLeu_NHOH"

    # Vina executable
    config.vina_executable = str(PROJECT_DIR / "vina_1.2.7_win_x86_64.exe.exe")

    # Hierarchical mode
    config.run_mode = "hierarchical"
    config.gnina_executable = GNINA_EXE
    config.rxdock_executable = RBDOCK_EXE
    config.hierarchical_top_n = 5

    # Docking box centered on active site (midpoint of zinc + co-crystallized NFH ligand)
    config.center_x = 64.6
    config.center_y = 30.3
    config.center_z = 115.1
    config.size_x = 25.0
    config.size_y = 25.0
    config.size_z = 25.0

    # Speed settings (fast for testing)
    config.docking.exhaustiveness = 4
    config.docking.num_modes = 3

    # Sidechain stage: 1 round, 5 mutations per position
    config.optimization.max_rounds = 1
    config.optimization.sc_mutations_per_round = 5
    config.optimization.top_n_select = 5

    # Include 2 unnatural amino acids
    config.optimization.sc_custom_sidechains = {
        "AIB": "[*](C)C",        # alpha-aminoisobutyric acid (helix stabilizer)
        "NLE": "[*]CCCC",        # norleucine (Met isostere, protease-resistant)
    }

    # Allowed natural residues for sidechain scanning
    # (keep list short for faster test — 8 natural + 2 UAA = 10 options)
    config.optimization.sc_allowed_residues = [
        "ALA", "VAL", "LEU", "ILE", "PHE", "TRP", "LYS", "ARG",
    ]

    # Pipeline stages: sidechain + backbone + minimize for hierarchical
    config.stages = ["sidechain", "backbone", "minimize"]

    # Receptor cleanup
    config.remove_waters = True
    config.remove_heteroatoms = True

    print("\n  Receptor:  MMP-9 (PDB: 1GKC)")
    print("  Ligand:    Phe-Leu-NHOH (hydroxamic acid)")
    print("  SMILES:    {}".format(config.ligand_smiles))
    print("  Box:       center=({:.1f}, {:.1f}, {:.1f}), size=({:.0f}, {:.0f}, {:.0f})".format(
        config.center_x, config.center_y, config.center_z,
        config.size_x, config.size_y, config.size_z))
    print("  Mode:      hierarchical (Vina + GNINA + RxDock)")
    print("  Sidechain: 1 round, 5 mutations/position")
    print("  UAAs:      AIB, NLE")
    print("  Backbone:  enabled")
    print("  Minimize:  enabled")
    print()

    # ── Run pipeline ─────────────────────────────────────────
    pipeline = DockingPipeline(config)
    pipeline.checkpoint_handler = AutoContinueCheckpoint()

    start_time = time.time()

    # Monkey-patch subprocess.run for GNINA/RxDock mocks
    with patch("subprocess.run", side_effect=_patched_subprocess_run):
        pipeline.run()

    elapsed = time.time() - start_time

    # ── Results ──────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print("  Total time: {:.0f}s ({:.1f} min)".format(elapsed, elapsed / 60))
    print("  Total candidates docked: {}".format(len(pipeline.all_results)))

    if pipeline.all_results:
        best = min(pipeline.all_results, key=lambda r: r.best_energy)
        print("  Best overall: {} = {:.2f} kcal/mol [{}]".format(
            best.ligand_name, best.best_energy, best.origin))

    # Check CSV outputs
    csv_path = output_dir / "results_summary.csv"
    if csv_path.exists():
        with open(csv_path) as f:
            lines = f.readlines()
        print("\n  results_summary.csv: {} rows".format(len(lines) - 1))
    else:
        print("\n  WARNING: results_summary.csv not found")

    consensus_path = output_dir / "consensus_summary.csv"
    if consensus_path.exists():
        with open(consensus_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print("  consensus_summary.csv: {} rows".format(len(rows)))
        print()
        print("  {:<4} {:<45} {:>7} {:>7} {:>7} {:>8} {:>9} {:>6}  {}".format(
            "Rank", "Candidate", "Vina", "VRank", "GNINA", "GNPose",
            "RxDock", "RxRnk", "Flag"))
        print("  " + "-" * 110)

        gnina_count = 0
        rxdock_count = 0
        uaa_in_consensus = []

        for row in rows:
            gnina = row.get("gnina_cnn_affinity", "")
            gpose = row.get("gnina_pose_confidence", "")
            rxdock = row.get("rxdock_score", "")
            rxrank = row.get("rxdock_rank", "")
            flag = row.get("pose_confidence_flag", "")
            uid = row.get("uid", "")
            ann = row.get("annotation", "")

            if gnina:
                gnina_count += 1
            if rxdock:
                rxdock_count += 1
            if "AIB" in uid.upper() or "NLE" in uid.upper() or "AIB" in ann.upper() or "NLE" in ann.upper():
                uaa_in_consensus.append(uid)

            print("  {:<4} {:<45} {:>7} {:>7} {:>7} {:>8} {:>9} {:>6}  {}".format(
                row["rank"],
                uid[:45],
                row["vina_score"],
                row["vina_rank"],
                gnina or "-",
                gpose or "-",
                rxdock or "-",
                rxrank or "-",
                flag))

        print()
        print("  GNINA scores: {}/{}".format(gnina_count, len(rows)))
        print("  RxDock scores: {}/{}".format(rxdock_count, len(rows)))
        if uaa_in_consensus:
            print("  UAA in consensus: {}".format(", ".join(uaa_in_consensus)))
        else:
            print("  UAA in consensus: none (UAAs may not have appeared in sidechain scan)")
    else:
        print("  WARNING: consensus_summary.csv not found!")

    # Check complex PDB
    complex_path = output_dir / "best_complex.pdb"
    print("\n  best_complex.pdb: {}".format(
        "exists ({} bytes)".format(complex_path.stat().st_size) if complex_path.exists() else "NOT FOUND"))

    print()
    print("=" * 70)
    if consensus_path.exists() and gnina_count > 0 and rxdock_count > 0:
        print("  TEST PASSED: All 4 phases completed successfully")
    elif not consensus_path.exists():
        print("  TEST ISSUE: Consensus CSV not generated")
    else:
        print("  TEST PARTIAL: Some engine scores missing")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
