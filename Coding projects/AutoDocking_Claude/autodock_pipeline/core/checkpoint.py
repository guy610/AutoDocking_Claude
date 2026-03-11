"""
Human-in-the-loop interactive checkpoint between optimization stages.

Displays current top candidates, allows user to:
  - Inject SMILES for immediate docking
  - Continue to next stage
  - Rerun current stage
  - Branch from a specific SMILES
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from .docking import DockingResult, run_vina
from ..config import PipelineConfig
from .validators import validate_ligand, check_binding_quality, print_validation_alerts, print_binding_alerts

logger = logging.getLogger(__name__)


def display_candidates(results: List[DockingResult], stage_name: str,
                       output_dir: Path) -> None:
    """Print a formatted table of the current top candidates."""
    print(f"\n{'='*72}")
    print(f"  CHECKPOINT — End of {stage_name}")
    print(f"{'='*72}")
    print(f"  Top {len(results)} candidates:")
    print(f"  {'#':<4} {'Name':<20} {'Score':>10} {'Origin':<16} SMILES")
    print(f"  {'-'*70}")
    for i, r in enumerate(results, 1):
        smi_display = r.smiles if len(r.smiles) <= 40 else r.smiles[:37] + "..."
        print(f"  {i:<4} {r.ligand_name:<20} {r.best_energy:>10.2f} {r.origin:<16} {smi_display}")

    print(f"\n  Output files are in: {output_dir}")
    print(f"  Each candidate has: *_docked.pdbqt, *_best_pose.pdb, *_vina.log")
    print(f"{'='*72}")


def interactive_checkpoint(results: List[DockingResult],
                           stage_name: str,
                           config: PipelineConfig,
                           receptor_pdbqt: Path,
                           output_dir: Path) -> Tuple[str, List[DockingResult], Optional[str]]:
    """Run an interactive checkpoint.

    Returns:
        (action, updated_results, branch_smiles)
        action: "continue" | "rerun"
        updated_results: results including any user-injected candidates
        branch_smiles: if user typed "branch <SMILES>", the SMILES to fork from
    """
    display_candidates(results, stage_name, output_dir)

    branches = []

    while True:
        print("\nOptions:")
        print("  - Paste SMILES (comma-separated) to inject and dock")
        print("  - 'continue' to proceed to next stage")
        print("  - 'rerun' to repeat this stage with new parameters")
        print("  - 'branch <SMILES>' to fork a new optimization lineage")
        print()

        user_input = input(">>> ").strip()

        if not user_input:
            continue

        if user_input.lower() == "continue":
            return "continue", results, None

        if user_input.lower() == "rerun":
            return "rerun", results, None

        if user_input.lower().startswith("branch "):
            branch_smi = user_input[7:].strip()
            if branch_smi:
                print(f"  -> Branch queued from: {branch_smi}")
                branches.append(branch_smi)
                # Dock the branch SMILES immediately
                results = _dock_and_merge(
                    [branch_smi], results, config, receptor_pdbqt,
                    output_dir, origin="branch"
                )
                display_candidates(
                    sorted(results, key=lambda r: r.best_energy)[:config.optimization.top_n_select],
                    stage_name, output_dir
                )
                continue
            else:
                print("  [!] Please provide a SMILES after 'branch'")
                continue

        # Assume it's SMILES input (comma-separated)
        smiles_list = [s.strip() for s in user_input.split(",") if s.strip()]
        if smiles_list:
            results = _dock_and_merge(
                smiles_list, results, config, receptor_pdbqt,
                output_dir, origin="user-rational"
            )
            # Re-display after injection
            sorted_results = sorted(results, key=lambda r: r.best_energy)
            display_candidates(
                sorted_results[:config.optimization.top_n_select],
                stage_name, output_dir
            )
            results = sorted_results  # keep full list for selection


def _dock_and_merge(smiles_list: List[str],
                    existing_results: List[DockingResult],
                    config: PipelineConfig,
                    receptor_pdbqt: Path,
                    output_dir: Path,
                    origin: str = "user-rational") -> List[DockingResult]:
    """Dock user-provided SMILES and merge into existing results."""
    from .ligand import smiles_to_pdbqt

    all_results = list(existing_results)

    for i, smi in enumerate(smiles_list):
        name = f"{origin}_{len(all_results)+1}"
        try:
            # Validate before docking
            val = validate_ligand(smi, name=name, max_residues=config.optimization.max_residues)
            print_validation_alerts(val)
            if not val.is_valid:
                print(f"  [!] Skipping invalid SMILES: {'; '.join(val.errors)}")
                continue

            print(f"  Docking {origin} candidate: {smi}")
            lig_pdbqt = smiles_to_pdbqt(smi, name=name, output_dir=output_dir)
            result = run_vina(
                receptor_pdbqt=receptor_pdbqt,
                ligand_pdbqt=lig_pdbqt,
                ligand_name=name,
                smiles=smi,
                docking_params=config.docking,
                output_dir=output_dir,
                vina_executable=config.vina_executable,
                origin=origin,
            )
            all_results.append(result)
            print(f"  -> Score: {result.best_energy:.2f} kcal/mol")
            # Check binding quality
            bw = check_binding_quality(result.best_energy, name=name,
                                       poor_binding_threshold=config.optimization.poor_binding_threshold)
            print_binding_alerts(bw)
        except Exception as e:
            print(f"  [!] Failed to dock {smi}: {e}")
            logger.error("Failed to dock user SMILES %s: %s", smi, e)

    return all_results
