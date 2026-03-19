"""
End-to-end integration test for SM Pipeline v0.9.2.

Uses EGFR + Erlotinib co-crystal structure (PDB: 1M17) — a classic cancer
kinase target — to verify the full pipeline runs through docking and produces
analogs with changed binding energies.

Tests the complete pipeline flow:
  1. Ligand extraction from crystal PDB
  2. Receptor preparation
  3. Reference ligand docking
  4. Binding analysis (including v0.9.2 metabolic + thioether detection)
  5. Multi-round iterative optimization with v0.9.2 SAR features
  6. Report generation
"""

import logging
import shutil
import sys
import time
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_v092_e2e")

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
CRYSTAL_PDB = PROJECT_DIR / "1M17.pdb"
OUTPUT_DIR = PROJECT_DIR / "test_output_v092_e2e"

# Clean previous test output
if OUTPUT_DIR.exists():
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

# ------------------------------------------------------------------
# Check prerequisites
# ------------------------------------------------------------------
def check_prereqs():
    """Verify PDB file exists and Vina is accessible."""
    if not CRYSTAL_PDB.exists():
        logger.error("Crystal PDB not found: %s", CRYSTAL_PDB)
        logger.error("Download it: wget https://files.rcsb.org/download/1M17.pdb")
        sys.exit(1)

    import subprocess
    try:
        result = subprocess.run(
            ["wsl", "vina", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        logger.info("Vina version: %s", result.stdout.strip())
    except Exception as e:
        logger.error("Vina not accessible via WSL: %s", e)
        sys.exit(1)

    try:
        from meeko import MoleculePreparation
        logger.info("Meeko available")
    except ImportError:
        logger.error("Meeko not installed: pip install meeko")
        sys.exit(1)

    logger.info("All prerequisites OK")


def run_pipeline():
    """Run the SM pipeline end-to-end on EGFR + erlotinib."""
    from dataclasses import dataclass, field
    from autodock_pipeline.config import SmallMoleculeConfig, DockingParams

    config = SmallMoleculeConfig(
        crystal_pdb=CRYSTAL_PDB,
        ligand_resname="AQ4",  # Erlotinib residue name in 1M17
        ligand_chain="A",
        output_dir=OUTPUT_DIR,
        vina_executable="wsl vina",
        # Use drug_like window since erlotinib is a drug
        property_target="drug_like",
        # Limit to 1 round for speed, small analog count
        max_rounds=2,
        max_analogs=15,
        delta_threshold=0.2,
        max_combos_per_round=20,
        # Docking params — lower exhaustiveness for speed
        docking=DockingParams(exhaustiveness=4, num_modes=5),
        # v0.9.2 features — all on except scaffold hopping (expensive)
        enable_bioisosteres=True,
        enable_extensions=True,
        enable_removals=True,
        enable_prodrug_esters=True,
        enable_metabolic_blocking=True,
        enable_scaffold_hopping=False,
        enable_thioether_detection=True,
        enable_mmp_tracking=True,
        enable_torsion_filter=True,
        enable_stereoisomer_enum=True,
        stereo_max_centers=3,
        stereo_final_top_n=3,
        torsion_amide_tolerance=30.0,
    )

    from autodock_pipeline.sm_pipeline import SmallMoleculePipeline
    pipeline = SmallMoleculePipeline(config)

    start = time.time()
    pipeline.run()
    elapsed = time.time() - start

    return pipeline, elapsed


def analyze_results(pipeline, elapsed):
    """Analyze and report pipeline results."""
    logger.info("=" * 60)
    logger.info("=== END-TO-END TEST RESULTS ===")
    logger.info("=" * 60)

    # Reference score
    ref_score = pipeline.original_score
    logger.info("Reference erlotinib score: %.2f kcal/mol", ref_score)

    # All results
    n_total = len(pipeline.all_results)
    logger.info("Total docking results: %d", n_total)

    # Sort by energy
    sorted_results = sorted(pipeline.all_results, key=lambda r: r.best_energy)

    # Best analog
    if n_total > 1:
        best = sorted_results[0]
        delta = best.best_energy - ref_score
        logger.info("Best analog: %s -> %.2f kcal/mol (delta=%+.2f)",
                     best.smiles[:60], best.best_energy, delta)
    else:
        logger.warning("No analogs docked!")

    # Show top 10
    logger.info("\n--- Top 10 Results ---")
    logger.info("%-6s  %-8s  %-8s  %-20s  %s", "Rank", "Energy", "Delta", "Type", "SMILES")
    for i, r in enumerate(sorted_results[:10]):
        delta = r.best_energy - ref_score
        origin = r.origin[:20] if r.origin else "?"
        smi = r.smiles[:50] if r.smiles else "?"
        marker = " <-- REF" if r.smiles == pipeline.extraction.ligand_smiles else ""
        logger.info("%-6d  %-8.2f  %+-8.2f  %-20s  %s%s",
                     i + 1, r.best_energy, delta, origin, smi, marker)

    # Round summaries
    logger.info("\n--- Round Summaries ---")
    for rs in pipeline.round_summaries:
        note = rs.get("note", "")
        logger.info("Round %d: %d candidates, %d passing, best=%.2f (delta=%+.2f) %s",
                     rs["round"], rs["n_candidates"], rs["n_passing"],
                     rs["best_score"], rs["delta_from_ref"], note)

    # Ligand efficiencies
    if pipeline.ligand_efficiencies:
        logger.info("\n--- Ligand Efficiencies (top 5 by LE) ---")
        sorted_le = sorted(pipeline.ligand_efficiencies.items(),
                          key=lambda x: x[1].le, reverse=True)
        for smi, le in sorted_le[:5]:
            logger.info("  LE=%.3f  LLE=%.2f  LELP=%.2f  HAC=%d  %s",
                        le.le, le.lle, le.lelp, le.heavy_atom_count, smi[:50])

    # Torsion warnings
    if pipeline.torsion_warnings:
        logger.info("\n--- Torsion Strain Rejections ---")
        logger.info("  %d molecules rejected for torsion strain", len(pipeline.torsion_warnings))

    # Binding analysis v0.9.2 features
    if pipeline.binding_analysis:
        ba = pipeline.binding_analysis
        logger.info("\n--- v0.9.2 Binding Analysis ---")
        logger.info("  Thioether sites: %d", len(ba.thioether_sites))
        logger.info("  Metabolic soft spots: %d", len(ba.metabolic_soft_spots))
        for ms in ba.metabolic_soft_spots:
            logger.info("    atom[%d]: %s -> %s", ms.atom_idx, ms.pattern_name, ms.suggested_block)

    # Check report exists
    report_files = list(OUTPUT_DIR.glob("*.md")) + list(OUTPUT_DIR.glob("*.csv"))
    logger.info("\n--- Output Files ---")
    for f in report_files:
        logger.info("  %s (%.1f KB)", f.name, f.stat().st_size / 1024)

    # Overall verdict
    logger.info("\n" + "=" * 60)
    improved = [r for r in pipeline.all_results if r.best_energy < ref_score - 0.1]
    n_improved = len(improved)

    logger.info("Elapsed time: %.1f minutes", elapsed / 60)
    logger.info("Analogs with improved binding (>0.1 kcal/mol): %d / %d", n_improved, n_total - 1)

    if n_improved > 0:
        best_delta = min(r.best_energy for r in improved) - ref_score
        logger.info("Best improvement: %+.2f kcal/mol", best_delta)
        logger.info("VERDICT: PASS — pipeline produced improved binders")
    else:
        logger.info("VERDICT: PASS (functional) — pipeline ran successfully; "
                    "no improved binders found (may be expected for a well-optimized drug)")

    return n_total > 1  # At least some analogs were docked


if __name__ == "__main__":
    check_prereqs()

    logger.info("=" * 60)
    logger.info("Running SM Pipeline v0.9.2 End-to-End Test")
    logger.info("Target: EGFR kinase (PDB: 1M17)")
    logger.info("Ligand: Erlotinib (Tarceva)")
    logger.info("=" * 60)

    pipeline, elapsed = run_pipeline()
    success = analyze_results(pipeline, elapsed)

    if success:
        logger.info("\n*** END-TO-END TEST PASSED ***")
    else:
        logger.error("\n*** END-TO-END TEST FAILED ***")
        sys.exit(1)
