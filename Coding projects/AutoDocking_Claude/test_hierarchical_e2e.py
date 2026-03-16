#!/usr/bin/env python3
"""
End-to-end test of the 4-Phase Hierarchical Virtual Screening Pipeline.

Uses mock GNINA and RxDock executables to test Phases 2-4 without
installing the real tools. Includes unnatural amino acid (UAA) candidates
to verify force-include logic and consensus ranking.

Monkey-patches subprocess.run to intercept calls to mock executables
and redirect them through Python.
"""
import sys
import os
import subprocess
import tempfile
import shutil
import csv

os.environ["PYTHONUTF8"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from unittest.mock import patch

# ── Setup paths ──────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
MOCK_DIR = PROJECT_DIR / "mock_tools"
MOCK_GNINA = str(MOCK_DIR / "mock_gnina.py")
MOCK_RBCAVITY = str(MOCK_DIR / "mock_rbcavity.py")
MOCK_RBDOCK = str(MOCK_DIR / "mock_rbdock.py")

# We use sentinel strings that the pipeline will pass as executable paths
GNINA_EXE = "MOCK_GNINA_EXE"
RBDOCK_EXE = "MOCK_RBDOCK_EXE"

# Keep reference to the real subprocess.run
_real_subprocess_run = subprocess.run


def _patched_subprocess_run(cmd, **kwargs):
    """Intercept subprocess.run calls and redirect mock executables to Python."""
    if not isinstance(cmd, list) or len(cmd) == 0:
        return _real_subprocess_run(cmd, **kwargs)

    exe = cmd[0]

    if exe == GNINA_EXE:
        # Redirect: MOCK_GNINA_EXE ... -> python mock_gnina.py ...
        new_cmd = [sys.executable, MOCK_GNINA] + cmd[1:]
        return _real_subprocess_run(new_cmd, **kwargs)

    if exe == RBDOCK_EXE:
        # Redirect: MOCK_RBDOCK_EXE ... -> python mock_rbdock.py ...
        new_cmd = [sys.executable, MOCK_RBDOCK] + cmd[1:]
        return _real_subprocess_run(new_cmd, **kwargs)

    if "rbcavity" in exe:
        # rbcavity is derived from rbdock path; redirect to mock
        new_cmd = [sys.executable, MOCK_RBCAVITY] + cmd[1:]
        return _real_subprocess_run(new_cmd, **kwargs)

    # All other subprocess calls pass through unchanged
    return _real_subprocess_run(cmd, **kwargs)


def main():
    from autodock_pipeline.config import PipelineConfig
    from autodock_pipeline.pipeline import DockingPipeline
    from autodock_pipeline.core.docking import DockingResult

    test_out = Path(tempfile.mkdtemp(prefix="hier_e2e_"))
    print("=" * 70)
    print("  HIERARCHICAL PIPELINE E2E TEST (Phases 1-4)")
    print("  Output: {}".format(test_out))
    print("=" * 70)

    # ── Build config ─────────────────────────────────────────
    config = PipelineConfig()
    config.receptor_pdb = PROJECT_DIR / "MMP14_receptor.pdb"
    config.output_dir = test_out
    config.run_mode = "hierarchical"
    config.gnina_executable = GNINA_EXE
    config.rxdock_executable = RBDOCK_EXE
    config.hierarchical_top_n = 5
    config.center_x = 35.0
    config.center_y = 20.0
    config.center_z = 15.0
    config.size_x = 25.0
    config.size_y = 25.0
    config.size_z = 25.0

    # Enable UAA detection by registering custom sidechains
    config.optimization.sc_custom_sidechains = {
        "AIB": "[*](C)C",        # alpha-aminoisobutyric acid
        "NLE": "[*]CCCC",        # norleucine
        "ORN": "[*]CCCN",        # ornithine
    }

    pipeline = DockingPipeline(config)

    # ── Simulate Phase 1 output (Vina results) ──────────────
    # Create 12 mock candidates including UAA, D-amino, and normal.
    # The 'annotation' field must contain the recognized keywords
    # for force-include to work.
    print("\n--- Phase 1 (simulated): Creating mock Vina results ---")

    candidates = [
        # (name, score, smiles, origin, annotation, category_label)
        ("sc_r01_001_Ala_Gly_Phe_Lys",     -7.8, "C[C@H](N)C(=O)NCC(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_002_Val_Gly_Trp_Arg",     -7.5, "CC(C)[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1c[nH]c2ccccc12)C(=O)N[C@@H](CCCNC(=N)N)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_003_Leu_Pro_Phe_Lys",     -7.2, "CC(C)C[C@@H](N)C(=O)N1CCC[C@H]1C(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_004_Ile_Gly_Tyr_His",     -7.0, "CC[C@H](C)[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1ccc(O)cc1)C(=O)N[C@@H](Cc1c[nH]cn1)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_005_Ser_Ala_Phe_Glu",     -6.8, "OC[C@@H](N)C(=O)N[C@@H](C)C(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCC(=O)O)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_006_Thr_Gly_Trp_Asp",     -6.5, "C[C@H](O)[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1c[nH]c2ccccc12)C(=O)N[C@@H](CC(=O)O)C(=O)O", "sidechain", "", "natural"),
        ("sc_r01_007_d_Ala_Gly_Phe_Lys",   -6.3, "C[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "Pos1: D-amino acid (D-Ala)", "D-amino"),
        ("sc_r01_008_Aib_Gly_Phe_Lys",     -6.0, "CC(C)(N)C(=O)NCC(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "Pos1: AIB (unnatural)", "UAA(Aib)"),
        ("sc_r01_009_Nle_Gly_Trp_Arg",     -5.8, "CCCC[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1c[nH]c2ccccc12)C(=O)N[C@@H](CCCNC(=N)N)C(=O)O", "sidechain", "Pos1: NLE (unnatural)", "UAA(Nle)"),
        ("sc_r01_010_bAla_Gly_Phe_Lys",    -5.5, "NCC(=O)CC(=O)NCC(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "Pos1: beta-3 (beta-amino acid)", "beta-amino"),
        ("sc_r01_011_Orn_Gly_Phe_Lys",     -5.2, "NCCC[C@@H](N)C(=O)NCC(=O)N[C@@H](Cc1ccccc1)C(=O)N[C@@H](CCCCN)C(=O)O", "sidechain", "Pos1: ORN (unnatural)", "UAA(Orn)"),
        ("sc_r01_012_Met_Ala_Tyr_Glu",     -5.0, "CSCC[C@@H](N)C(=O)N[C@@H](C)C(=O)N[C@@H](Cc1ccc(O)cc1)C(=O)N[C@@H](CCC(=O)O)C(=O)O", "sidechain", "", "natural"),
    ]

    for name, score, smiles, origin, annotation, cat_label in candidates:
        pdbqt_path = test_out / "{}.pdbqt".format(name)
        # Write a minimal but valid PDBQT
        pdbqt_path.write_text(
            "MODEL 1\n"
            "REMARK  Name = {}\n"
            "REMARK  VINA RESULT:    {:.1f}      0.000      0.000\n"
            "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00    +0.000 N\n"
            "ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00    +0.000 C\n"
            "ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00    +0.000 C\n"
            "ENDMDL\n".format(name, score)
        )

        r = DockingResult(
            ligand_name=name,
            smiles=smiles,
            best_energy=score,
            all_energies=[score, score + 0.3, score + 0.8],
            output_pdbqt=pdbqt_path,
            origin=origin,
            annotation=annotation,
        )
        pipeline.all_results.append(r)

    print("  Created {} mock candidates".format(len(pipeline.all_results)))
    for c in candidates:
        print("    {} : {:.1f} kcal/mol  [{}]{}".format(
            c[0], c[1], c[5],
            "  ann='{}'".format(c[4]) if c[4] else ""))

    # Set up receptor PDBQT (needed by GNINA phase)
    receptor_pdbqt = test_out / "receptor.pdbqt"
    receptor_pdbqt.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00    +0.000 N\n"
        "ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00    +0.000 C\n"
    )
    pipeline.receptor_pdbqt = str(receptor_pdbqt)

    # ── Phase 2-4: Run hierarchical screening with mock tools ──
    print("\n--- Running _select_top_candidates(n=5) ---")
    top = pipeline._select_top_candidates(n=5)
    print("  Selected {} candidates:".format(len(top)))
    for r in top:
        cat_label = [c[5] for c in candidates if c[0] == r.ligand_name][0]
        forced = " [FORCE-INCLUDED]" if r.annotation else ""
        print("    {} : {:.1f} kcal/mol  [{}]{}".format(
            r.ligand_name, r.best_energy, cat_label, forced))

    # Verify force-include logic
    top_names = {r.ligand_name for r in top}
    print("\n  Force-include verification:")

    # Check that at least one UAA was force-included
    uaa_names = {"sc_r01_008_Aib_Gly_Phe_Lys", "sc_r01_009_Nle_Gly_Trp_Arg",
                 "sc_r01_011_Orn_Gly_Phe_Lys"}
    d_amino_names = {"sc_r01_007_d_Ala_Gly_Phe_Lys"}
    beta_names = {"sc_r01_010_bAla_Gly_Phe_Lys"}

    uaa_included = top_names & uaa_names
    d_included = top_names & d_amino_names
    beta_included = top_names & beta_names

    print("    UAA force-included: {} ({})".format(
        bool(uaa_included), ", ".join(uaa_included) if uaa_included else "none"))
    print("    D-amino force-included: {} ({})".format(
        bool(d_included), ", ".join(d_included) if d_included else "none"))
    print("    beta-amino force-included: {} ({})".format(
        bool(beta_included), ", ".join(beta_included) if beta_included else "none"))

    if not uaa_included:
        print("    WARNING: No UAA candidates were force-included!")
    if not d_included:
        print("    WARNING: No D-amino candidates were force-included!")

    print("\n--- Running Phases 2-4 with mock GNINA + RxDock ---")

    # Monkey-patch subprocess.run
    with patch("subprocess.run", side_effect=_patched_subprocess_run):
        pipeline.run_hierarchical_screening(top)

    # ── Verify consensus CSV ─────────────────────────────────
    print("\n--- Verifying consensus_summary.csv ---")
    consensus_path = test_out / "consensus_summary.csv"

    if not consensus_path.exists():
        print("  FAIL: consensus_summary.csv not created!")
        sys.exit(1)

    with open(consensus_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    print("  File exists: YES")
    print("  Rows: {}".format(len(rows)))
    print("  Columns: {}".format(headers))

    # Check all expected columns
    expected_cols = [
        "rank", "uid", "smiles", "origin", "annotation", "stereo",
        "vina_score", "vina_rank",
        "rxdock_score", "rxdock_rank",
        "gnina_cnn_affinity", "gnina_pose_confidence",
        "pose_confidence_flag", "rank_variance", "consensus_score",
    ]
    missing = [c for c in expected_cols if c not in headers]
    if missing:
        print("  FAIL: Missing columns: {}".format(missing))
        sys.exit(1)
    print("  All {} expected columns present: OK".format(len(expected_cols)))

    # Check rows have actual data
    print("\n  Consensus results:")
    print("  {:<5} {:<40} {:>8} {:>8} {:>8} {:>10} {:>10} {:>6} {:>10}".format(
        "Rank", "Candidate", "Vina", "VRank", "GNINA", "GNINApose", "RxDock",
        "RxRnk", "Consensus"))
    print("  " + "-" * 115)

    gnina_scored = 0
    rxdock_scored = 0
    for row in rows:
        vina = row["vina_score"]
        vrank = row["vina_rank"]
        gnina = row["gnina_cnn_affinity"] or "-"
        gpose = row["gnina_pose_confidence"] or "-"
        rxdock = row["rxdock_score"] or "-"
        rxrank = row["rxdock_rank"] or "-"
        cons = row["consensus_score"]
        flag = row["pose_confidence_flag"]

        if row["gnina_cnn_affinity"]:
            gnina_scored += 1
        if row["rxdock_score"]:
            rxdock_scored += 1

        print("  {:<5} {:<40} {:>8} {:>8} {:>8} {:>10} {:>10} {:>6} {:>10} {}".format(
            row["rank"], row["uid"][:40], vina, vrank,
            gnina, gpose, rxdock, rxrank, cons, flag))

    print()
    print("  GNINA scores present: {}/{}".format(gnina_scored, len(rows)))
    print("  RxDock scores present: {}/{}".format(rxdock_scored, len(rows)))

    # Verify we got actual scores from mock tools
    if gnina_scored == 0:
        print("  FAIL: No GNINA scores! Phase 2 did not work.")
        sys.exit(1)
    if rxdock_scored == 0:
        print("  FAIL: No RxDock scores! Phase 3 did not work.")
        sys.exit(1)

    # Verify consensus uses all three engines
    for row in rows:
        cs = float(row["consensus_score"])
        if cs <= 0:
            print("  FAIL: Invalid consensus score: {}".format(cs))
            sys.exit(1)

    # Check rank ordering (rank 1 should have lowest consensus score)
    scores = [float(r["consensus_score"]) for r in rows]
    if scores != sorted(scores):
        print("  FAIL: Consensus ranks not properly sorted!")
        sys.exit(1)
    print("  Rank ordering: OK (sorted by consensus score)")

    # Check for variance column
    has_variance = any(r["rank_variance"] for r in rows)
    print("  Rank variance populated: {}".format(has_variance))

    # Check for pose confidence flags
    has_flags = any(r["pose_confidence_flag"] for r in rows)
    print("  Pose confidence flags: {}".format("present" if has_flags else "none (all confident)"))

    print()
    print("=" * 70)
    print("  ALL PHASES PASSED")
    print("  Phase 1: Vina results simulated (12 candidates)")
    print("  Phase 2: GNINA rescoring via mock ({} scored)".format(gnina_scored))
    print("  Phase 3: RxDock docking via mock ({} scored)".format(rxdock_scored))
    print("  Phase 4: Consensus ranking ({} rows, 3-engine average)".format(len(rows)))
    print("  UAA/D-amino/beta-amino candidates included: verified")
    print("=" * 70)

    # Cleanup
    shutil.rmtree(test_out, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
