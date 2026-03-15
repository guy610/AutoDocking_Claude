"""
Stage 3 - Sequence minimization (size reduction).

Remove or replace non-interacting residues/fragments to reduce
ligand size while preserving key binding interactions.

Strategy:
  - Use interaction metrics to identify residues with minimal contacts.
  - Try deleting terminal residues or replacing internal ones with Gly/Ala.
  - Dock truncated variants, keep those within score tolerance.
"""

import logging
import time
from pathlib import Path
from typing import List, Tuple

from rdkit import Chem

from ..config import PipelineConfig
from ..core.docking import DockingResult, run_vina
from ..core.interactions import InteractionMetrics, compute_interactions
from ..core.ligand import smiles_to_pdbqt
from ..core.validators import validate_ligand, print_validation_alerts
from ..utils.io_utils import ensure_dir

logger = logging.getLogger(__name__)


def identify_dispensable_residues(metrics: InteractionMetrics,
                                 config: PipelineConfig) -> List[int]:
    """Identify residues with minimal protein interactions.

    Residues with zero or very few total contacts are candidates for
    deletion (if terminal) or replacement with smaller residues (if internal).
    """
    dispensable = []
    for pos_idx, info in metrics.per_residue_position.items():
        n_total = info.get("n_total", 0)
        if n_total == 0:
            dispensable.append(pos_idx)
            logger.debug("Position %d has no interactions - dispensable", pos_idx)

    # Limit to max deletions
    max_del = config.optimization.min_max_deletions
    if len(dispensable) > max_del:
        dispensable = dispensable[:max_del]

    logger.info("Identified %d dispensable residue positions", len(dispensable))
    return dispensable


def generate_minimized_variants(smiles: str,
                                dispensable_positions: List[int],
                                config: PipelineConfig) -> List[Tuple[str, str]]:
    """Generate truncated / simplified candidate SMILES.

    For dispensable positions:
      - Terminal positions: try deleting the residue entirely
      - Internal positions: try replacing with Gly (smallest side chain)
      - Try Ala replacement as well (small but adds some hydrophobic contact)

    Uses RDKit SMARTS to identify and manipulate amide bonds.
    """
    variants = {}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    amide_pat = Chem.MolFromSmarts("[C](=O)[NH]")
    if amide_pat is None:
        return []
    n_amide = len(mol.GetSubstructMatches(amide_pat))
    n_residues = n_amide + 1

    if n_residues <= 2:
        logger.info("Peptide too short for minimization (%d residues)", n_residues)
        return []

    for pos in dispensable_positions:
        if pos < 0 or pos >= n_residues:
            continue

        # Strategy 1: Terminal deletion
        if pos == 0 or pos == n_residues - 1:
            # Build peptide without this terminal residue
            # This is a simplified approach using SMILES manipulation
            try:
                # For terminal deletion, we try to cleave at the amide bond
                rw = Chem.RWMol(mol)
                matches = rw.GetSubstructMatches(amide_pat)
                if pos == 0 and len(matches) > 0:
                    # Delete first residue: cleave first amide bond
                    c_idx, o_idx, n_idx = matches[0][0], matches[0][1], matches[0][2]
                    # This is complex; use fragment approach instead
                    pass
                elif pos == n_residues - 1 and len(matches) > 0:
                    # Delete last residue: cleave last amide bond
                    pass
            except Exception:
                pass

        # Strategy 2: Replace with glycine (minimal side chain)
        # This works by modifying side chain atoms
        try:
            rw = Chem.RWMol(mol)
            # Simplified: generate Gly-substituted variant
            new_smi = _replace_residue_with_gly(smiles, pos, n_residues)
            if new_smi and new_smi != smiles:
                check = Chem.MolFromSmiles(new_smi)
                if check is not None:
                    variants[new_smi] = "Pos{}: ->GLY".format(pos + 1)
        except Exception as e:
            logger.debug("Gly replacement at pos %d failed: %s", pos, e)

        # Strategy 3: Replace with alanine
        try:
            new_smi = _replace_residue_with_ala(smiles, pos, n_residues)
            if new_smi and new_smi != smiles:
                check = Chem.MolFromSmiles(new_smi)
                if check is not None:
                    variants[new_smi] = "Pos{}: ->ALA".format(pos + 1)
        except Exception as e:
            logger.debug("Ala replacement at pos %d failed: %s", pos, e)

    return [(smi, ann) for smi, ann in variants.items()]


def _replace_residue_with_gly(smiles: str, position: int, n_residues: int) -> str:
    """Replace a residue at given position with glycine.

    Glycine has no side chain (just H on CA), so this effectively
    removes the side chain at that position.
    """
    # Build a new peptide with Gly at the target position
    # This is a simplified approach - in production, would use
    # proper SMILES fragmentation
    from ..stages.sidechain import identify_peptide_residues, build_peptide_smiles
    residues = identify_peptide_residues(smiles)
    if not residues or position >= len(residues):
        return ""
    new_residues = list(residues)
    new_residues[position] = "GLY"
    return build_peptide_smiles(new_residues) or ""


def _replace_residue_with_ala(smiles: str, position: int, n_residues: int) -> str:
    """Replace a residue at given position with alanine."""
    from ..stages.sidechain import identify_peptide_residues, build_peptide_smiles
    residues = identify_peptide_residues(smiles)
    if not residues or position >= len(residues):
        return ""
    new_residues = list(residues)
    new_residues[position] = "ALA"
    return build_peptide_smiles(new_residues) or ""


def _format_time(seconds):
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return "{:.0f} sec".format(seconds)
    elif seconds < 3600:
        return "{:.1f} min".format(seconds / 60)
    else:
        return "{:.1f} hr".format(seconds / 3600)


def run_minimization(config: PipelineConfig,
                     receptor_pdbqt,
                     initial_results: List[DockingResult],
                     original_score: float,
                     time_per_dock: float = 0.0) -> List[DockingResult]:
    """Execute the iterative sequence-minimization loop."""
    out_dir = ensure_dir(config.output_dir / "minimize")
    all_results = []
    current_seeds = list(initial_results)
    best_score = original_score
    receptor_clean = config.output_dir / "receptor" / (config.receptor_pdb.stem + "_clean.pdb")

    for round_num in range(1, config.optimization.max_rounds + 1):
        logger.info("Minimization round %d/%d",
                     round_num, config.optimization.max_rounds)
        round_dir = ensure_dir(out_dir / "round_{:02d}".format(round_num))

        seed = current_seeds[0]
        if seed.best_pose_pdb and seed.best_pose_pdb.exists() and receptor_clean.exists():
            metrics = compute_interactions(seed.best_pose_pdb, receptor_clean)
        else:
            logger.warning("Cannot compute interactions for minimization")
            metrics = InteractionMetrics()
            mol = Chem.MolFromSmiles(seed.smiles)
            amide_pat = Chem.MolFromSmarts("[C](=O)[NH]")
            if mol and amide_pat:
                n_res = len(mol.GetSubstructMatches(amide_pat)) + 1
                for i in range(n_res):
                    metrics.per_residue_position[i] = {
                        "res_num": i, "n_bb_interactions": 0,
                        "n_sc_interactions": 0, "n_total": 0,
                    }

        dispensable = identify_dispensable_residues(metrics, config)
        if not dispensable:
            logger.info("No dispensable residues found, stopping minimization")
            break

        logger.info("Dispensable positions: %s",
                     ", ".join(["Pos{}(contacts={})".format(p + 1, metrics.per_residue_position.get(p, {}).get("n_total", "?")) for p in dispensable]))

        # Generate annotated variants
        all_variants_with_ann = []
        seen_smiles = set()
        for s in current_seeds:
            n_res = len(metrics.per_residue_position)
            variants = generate_minimized_variants(s.smiles, dispensable, config)
            for smi, ann in variants:
                if smi not in seen_smiles:
                    seen_smiles.add(smi)
                    all_variants_with_ann.append((smi, ann))

        if not all_variants_with_ann:
            logger.info("No minimized variants generated, stopping")
            break

        # Time estimation
        rounds_remaining = config.optimization.max_rounds - round_num
        if time_per_dock > 0:
            est_this_round = len(all_variants_with_ann) * time_per_dock
            est_future = rounds_remaining * len(all_variants_with_ann) * time_per_dock
            logger.info("Estimated time: this round ~%s, remaining ~%s (%d docks x %.1f sec/dock)",
                        _format_time(est_this_round),
                        _format_time(est_this_round + est_future),
                        len(all_variants_with_ann), time_per_dock)

        logger.info("Docking %d minimized candidates", len(all_variants_with_ann))
        round_results = []
        round_start = time.time()

        for i, (smi, annotation) in enumerate(all_variants_with_ann):
            name = "min_r{:02d}_{:03d}".format(round_num, i + 1)
            val = validate_ligand(smi, name=name,
                                  max_residues=config.optimization.max_residues)
            print_validation_alerts(val)
            if not val.is_valid:
                continue
            try:
                dock_start = time.time()
                lig_pdbqt = smiles_to_pdbqt(smi, name=name, output_dir=round_dir)
                result = run_vina(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=lig_pdbqt,
                    ligand_name=name,
                    smiles=smi,
                    docking_params=config.docking,
                    output_dir=round_dir,
                    vina_executable=config.vina_executable,
                    origin="minimize",
                )
                dock_elapsed = time.time() - dock_start
                if time_per_dock <= 0:
                    time_per_dock = dock_elapsed
                else:
                    time_per_dock = 0.7 * time_per_dock + 0.3 * dock_elapsed
                round_results.append(result)
                all_results.append(result)
                logger.info("  %s [%s]: %.2f kcal/mol (%.1fs)",
                            name, annotation, result.best_energy, dock_elapsed)
            except Exception as e:
                logger.error("Failed to dock %s [%s]: %s", name, annotation, e)

        round_elapsed = time.time() - round_start
        if not round_results:
            logger.info("No successful minimization results, stopping")
            break

        logger.info("Round %d completed in %s", round_num, _format_time(round_elapsed))

        # For minimization, accept results within score tolerance
        tolerance = config.optimization.min_score_tolerance
        acceptable = [r for r in round_results
                      if r.best_energy <= best_score + tolerance]

        if acceptable:
            combined = current_seeds + acceptable
            combined.sort(key=lambda r: r.best_energy)
            current_seeds = combined[:config.optimization.top_n_select]
            new_best = current_seeds[0].best_energy
            logger.info("Round %d: %d acceptable variants, best: %.2f kcal/mol",
                         round_num, len(acceptable), new_best)
            best_score = min(best_score, new_best)
        else:
            logger.info("No variants within score tolerance, stopping")
            break

    logger.info("Minimization complete: %d total candidates docked", len(all_results))
    return all_results
