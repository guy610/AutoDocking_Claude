"""
Stage 2 - Backbone optimization.

Modify backbone geometry at positions with few backbone-mediated
interactions and that are relatively solvent-exposed.

Modifications include:
  - N-methylation: replace backbone NH with N(CH3) to improve stability
  - D-amino acid substitution: invert stereochemistry at CA
  - Beta-2 amino acid: insert CH2 between CA and C(=O)
  - Beta-3 amino acid: insert CH2 between N and CA
These changes can improve metabolic stability while preserving binding.
"""

import logging
import time
from pathlib import Path
from typing import List, Tuple

from rdkit import Chem

from ..config import PipelineConfig
from ..core.docking import DockingResult, run_vina
from ..core.interactions import InteractionMetrics, compute_interactions
from ..core.ligand import (
    smiles_to_pdbqt, make_cterm_amide, make_cterm_acid_deprot,
    make_nterm_dimethyl, make_nterm_acyl, make_nterm_custom,
)
from ..core.validators import validate_ligand, print_validation_alerts
from ..utils.io_utils import ensure_dir, safe_filename

logger = logging.getLogger(__name__)


def identify_backbone_candidates(metrics: InteractionMetrics,
                                 config: PipelineConfig) -> List[int]:
    """Identify residue positions eligible for backbone modifications.

    A position is eligible if it has few backbone-mediated interactions
    (below the threshold), suggesting the backbone at that position
    is not critical for binding.

    If no positions pass the threshold, the position with the fewest
    backbone interactions is forced as a candidate to guarantee at least
    one backbone modification is always attempted (for QC purposes).
    """
    threshold = config.optimization.bb_min_interaction_threshold
    candidates = []

    for pos_idx, info in metrics.per_residue_position.items():
        n_bb = info.get("n_bb_interactions", 0)
        if n_bb <= threshold:
            candidates.append(pos_idx)
            logger.debug("Position %d eligible for backbone modification "
                         "(backbone interactions: %d <= %d)",
                         pos_idx, n_bb, threshold)

    # Force at least one position: pick the one with fewest backbone interactions
    if not candidates and metrics.per_residue_position:
        all_positions = sorted(
            metrics.per_residue_position.keys(),
            key=lambda p: metrics.per_residue_position[p].get("n_bb_interactions", 0)
        )
        forced = all_positions[0]
        n_bb = metrics.per_residue_position[forced].get("n_bb_interactions", 0)
        candidates.append(forced)
        logger.info("No positions below threshold (%d); forcing position %d "
                     "(fewest backbone interactions: %d) for QC coverage",
                     threshold, forced, n_bb)

    # Limit to max positions
    max_pos = config.optimization.bb_max_positions
    if len(candidates) > max_pos:
        # Prioritize positions with fewest interactions
        candidates.sort(key=lambda p: metrics.per_residue_position[p].get("n_bb_interactions", 0))
        candidates = candidates[:max_pos]

    logger.info("Identified %d backbone modification candidates", len(candidates))
    return candidates


def generate_backbone_variants(smiles: str,
                               candidate_positions: List[int],
                               config: PipelineConfig) -> List[Tuple[str, str]]:
    """Generate backbone-modified candidate SMILES.

    For each candidate position, generate:
      1. N-methylated variant (replace NH with N(C))
      2. D-amino acid variant (invert CA stereochemistry)
      3. Beta-2 amino acid variant (insert CH2 between CA and C(=O))
      4. Beta-3 amino acid variant (insert CH2 between N and CA)
    """
    variants = {}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # N-methylation: find amide NH patterns and methylate at candidate positions
    amide_pat = Chem.MolFromSmarts("[NH][C]C(=O)")
    if amide_pat is not None:
        matches = mol.GetSubstructMatches(amide_pat)
        for pos in candidate_positions:
            if pos < len(matches):
                # Create N-methylated version
                try:
                    rw_mol = Chem.RWMol(mol)
                    n_idx = matches[pos][0]
                    # Add methyl group to the nitrogen
                    c_idx = rw_mol.AddAtom(Chem.Atom(6))  # Carbon
                    rw_mol.AddBond(n_idx, c_idx, Chem.BondType.SINGLE)
                    new_smi = Chem.MolToSmiles(rw_mol)
                    if new_smi:
                        # Validate
                        check = Chem.MolFromSmiles(new_smi)
                        if check is not None:
                            variants[new_smi] = "Pos{}: N-methylation".format(pos + 1)
                            logger.debug("N-methylation at position %d: %s", pos, new_smi)
                except Exception as e:
                    logger.debug("N-methylation failed at position %d: %s", pos, e)

    # D-amino acid: invert stereochemistry at CA positions
    # Find chiral centers and try inverting at candidate positions
    chiral_info = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    for pos in candidate_positions:
        if pos < len(chiral_info):
            try:
                rw_mol = Chem.RWMol(mol)
                atom_idx = chiral_info[pos][0]
                atom = rw_mol.GetAtomWithIdx(atom_idx)
                current = atom.GetChiralTag()
                if current == Chem.ChiralType.CHI_TETRAHEDRAL_CW:
                    atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
                elif current == Chem.ChiralType.CHI_TETRAHEDRAL_CCW:
                    atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
                else:
                    # Try assigning R then S
                    atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
                new_smi = Chem.MolToSmiles(rw_mol)
                if new_smi and new_smi != smiles:
                    check = Chem.MolFromSmiles(new_smi)
                    if check is not None:
                        variants[new_smi] = "Pos{}: D-amino acid".format(pos + 1)
                        logger.debug("D-AA at position %d: %s", pos, new_smi)
            except Exception as e:
                logger.debug("D-AA substitution failed at position %d: %s", pos, e)

    # Beta-2 amino acid: insert CH2 between CA and C(=O)
    # Pattern: find [NH][CX4H1]C(=O) and convert to [NH][CX4H1]CC(=O)
    backbone_pat = Chem.MolFromSmarts("[NH][CX4H1]C(=O)")
    if backbone_pat is not None:
        matches = mol.GetSubstructMatches(backbone_pat)
        for pos in candidate_positions:
            if pos < len(matches):
                try:
                    rw_mol = Chem.RWMol(mol)
                    ca_idx = matches[pos][1]
                    co_idx = matches[pos][2]
                    # Remove bond between CA and C(=O)
                    rw_mol.RemoveBond(ca_idx, co_idx)
                    # Add new CH2 carbon
                    ch2_idx = rw_mol.AddAtom(Chem.Atom(6))  # Carbon
                    # Connect CA-CH2 and CH2-C(=O)
                    rw_mol.AddBond(ca_idx, ch2_idx, Chem.BondType.SINGLE)
                    rw_mol.AddBond(ch2_idx, co_idx, Chem.BondType.SINGLE)
                    new_smi = Chem.MolToSmiles(rw_mol)
                    if new_smi:
                        check = Chem.MolFromSmiles(new_smi)
                        if check is not None:
                            variants[new_smi] = "Pos{}: beta-2 AA".format(pos + 1)
                            logger.debug("Beta-2 AA at position %d: %s", pos, new_smi)
                except Exception as e:
                    logger.debug("Beta-2 insertion failed at position %d: %s", pos, e)

    # Beta-3 amino acid: insert CH2 between N and CA
    # Pattern: find [NH][CX4H1]C(=O) and convert to [NH]C[CX4H1]C(=O)
    if backbone_pat is not None:
        matches = mol.GetSubstructMatches(backbone_pat)
        for pos in candidate_positions:
            if pos < len(matches):
                try:
                    rw_mol = Chem.RWMol(mol)
                    n_idx = matches[pos][0]
                    ca_idx = matches[pos][1]
                    # Remove bond between N and CA
                    rw_mol.RemoveBond(n_idx, ca_idx)
                    # Add new CH2 carbon
                    ch2_idx = rw_mol.AddAtom(Chem.Atom(6))  # Carbon
                    # Connect N-CH2 and CH2-CA
                    rw_mol.AddBond(n_idx, ch2_idx, Chem.BondType.SINGLE)
                    rw_mol.AddBond(ch2_idx, ca_idx, Chem.BondType.SINGLE)
                    new_smi = Chem.MolToSmiles(rw_mol)
                    if new_smi:
                        check = Chem.MolFromSmiles(new_smi)
                        if check is not None:
                            variants[new_smi] = "Pos{}: beta-3 AA".format(pos + 1)
                            logger.debug("Beta-3 AA at position %d: %s", pos, new_smi)
                except Exception as e:
                    logger.debug("Beta-3 insertion failed at position %d: %s", pos, e)

    return [(smi, ann) for smi, ann in variants.items()]


def _format_time(seconds):
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return "{:.0f} sec".format(seconds)
    elif seconds < 3600:
        return "{:.1f} min".format(seconds / 60)
    else:
        return "{:.1f} hr".format(seconds / 3600)


def run_backbone_optimization(config: PipelineConfig,
                              receptor_pdbqt,
                              initial_results: List[DockingResult],
                              original_score: float,
                              time_per_dock: float = 0.0) -> List[DockingResult]:
    """Execute the iterative backbone optimization loop."""
    out_dir = ensure_dir(config.output_dir / "backbone")
    all_results = []
    current_seeds = list(initial_results)
    best_score = original_score
    receptor_clean = config.output_dir / "receptor" / (config.receptor_pdb.stem + "_clean.pdb")

    for round_num in range(1, config.optimization.max_rounds + 1):
        logger.info("Backbone optimization round %d/%d",
                     round_num, config.optimization.max_rounds)
        round_dir = ensure_dir(out_dir / "round_{:02d}".format(round_num))

        # Compute interactions for best seed to identify modification sites
        seed = current_seeds[0]
        if seed.best_pose_pdb and seed.best_pose_pdb.exists() and receptor_clean.exists():
            metrics = compute_interactions(seed.best_pose_pdb, receptor_clean)
        else:
            logger.warning("Cannot compute interactions, using all positions")
            metrics = InteractionMetrics()
            amide_pat = Chem.MolFromSmarts("[C](=O)[NH]")
            mol = Chem.MolFromSmiles(seed.smiles)
            if mol and amide_pat:
                n_res = len(mol.GetSubstructMatches(amide_pat)) + 1
                for i in range(n_res):
                    metrics.per_residue_position[i] = {
                        "res_num": i, "n_bb_interactions": 0,
                        "n_sc_interactions": 0, "n_total": 0,
                    }

        # Identify candidates
        candidates_pos = identify_backbone_candidates(metrics, config)
        if not candidates_pos:
            logger.info("No backbone modification candidates found, stopping")
            break

        logger.info("Backbone candidate positions: %s",
                     ", ".join(["Pos{}(bb_int={})".format(p + 1, metrics.per_residue_position.get(p, {}).get("n_bb_interactions", "?")) for p in candidates_pos]))

        # Generate annotated variants from all seeds
        all_variants_with_ann = []
        seen_smiles = set()
        for s in current_seeds:
            variants = generate_backbone_variants(s.smiles, candidates_pos, config)
            for smi, ann in variants:
                if smi not in seen_smiles:
                    seen_smiles.add(smi)
                    all_variants_with_ann.append((smi, ann))

        if not all_variants_with_ann:
            logger.info("No backbone variants generated, stopping")
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

        logger.info("Docking %d backbone candidates", len(all_variants_with_ann))
        round_results = []
        round_start = time.time()

        for i, (smi, annotation) in enumerate(all_variants_with_ann):
            name = "bb_r{:02d}_{:03d}".format(round_num, i + 1)
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
                    origin="backbone",
                )
                dock_elapsed = time.time() - dock_start
                if time_per_dock <= 0:
                    time_per_dock = dock_elapsed
                else:
                    time_per_dock = 0.7 * time_per_dock + 0.3 * dock_elapsed
                result.annotation = annotation
                round_results.append(result)
                all_results.append(result)
                logger.info("  %s [%s]: %.2f kcal/mol (%.1fs)",
                            name, annotation, result.best_energy, dock_elapsed)
            except Exception as e:
                logger.error("Failed to dock %s [%s]: %s", name, annotation, e)

        round_elapsed = time.time() - round_start
        if not round_results:
            logger.info("No successful backbone docking results, stopping")
            break

        logger.info("Round %d completed in %s", round_num, _format_time(round_elapsed))

        combined = current_seeds + round_results
        combined.sort(key=lambda r: r.best_energy)
        current_seeds = combined[:config.optimization.top_n_select]

        # C-terminal cap scanning: dock acid (COO-) and amide (CONH2) of best candidate
        if getattr(config.optimization, 'scan_cterm_caps', False):
            best_seed = current_seeds[0]
            cterm_variants = []
            acid_smi = make_cterm_acid_deprot(best_seed.smiles)
            if acid_smi and acid_smi != best_seed.smiles:
                cterm_variants.append((acid_smi, "C-term acid of {}".format(best_seed.ligand_name)))
            amide_smi = make_cterm_amide(best_seed.smiles)
            if amide_smi:
                cterm_variants.append((amide_smi, "C-term amide of {}".format(best_seed.ligand_name)))

            for ct_smi, ct_ann in cterm_variants:
                ct_name = "bb_r{:02d}_cterm_{}".format(
                    round_num, "acid" if "acid" in ct_ann else "amide")
                try:
                    ct_pdbqt = smiles_to_pdbqt(ct_smi, name=ct_name, output_dir=round_dir)
                    ct_result = run_vina(
                        receptor_pdbqt=receptor_pdbqt,
                        ligand_pdbqt=ct_pdbqt,
                        ligand_name=ct_name,
                        smiles=ct_smi,
                        docking_params=config.docking,
                        output_dir=round_dir,
                        vina_executable=config.vina_executable,
                        origin="backbone",
                    )
                    ct_result.annotation = ct_ann
                    all_results.append(ct_result)
                    logger.info("  %s [%s]: %.2f kcal/mol", ct_name, ct_ann, ct_result.best_energy)
                except Exception as e:
                    logger.error("Failed to dock %s [%s]: %s", ct_name, ct_ann, e)

        # N-terminal modifications: dock variants of best candidate
        nterm_variants = []
        best_seed = current_seeds[0]
        opt = config.optimization

        if getattr(opt, 'nterm_dimethyl', False):
            dm_smi = make_nterm_dimethyl(best_seed.smiles)
            if dm_smi:
                nterm_variants.append((dm_smi, "dimethyl",
                    "N-term methylation of {}".format(best_seed.ligand_name)))

        if getattr(opt, 'nterm_acyl', False):
            nc = getattr(opt, 'nterm_acyl_carbons', 2)
            ac_smi = make_nterm_acyl(best_seed.smiles, n_carbons=nc)
            if ac_smi:
                chain_name = {2: "acetyl", 3: "propionyl", 16: "palmitoyl"}.get(
                    nc, "C{}-acyl".format(nc))
                nterm_variants.append((ac_smi, "acyl",
                    "N-term {} of {}".format(chain_name, best_seed.ligand_name)))

        custom_smi_str = getattr(opt, 'nterm_custom_smiles', "")
        if custom_smi_str:
            cu_smi = make_nterm_custom(best_seed.smiles, custom_smi_str)
            if cu_smi:
                nterm_variants.append((cu_smi, "custom",
                    "N-term custom mod of {}".format(best_seed.ligand_name)))

        for nt_smi, nt_tag, nt_ann in nterm_variants:
            nt_name = "bb_r{:02d}_nterm_{}".format(round_num, nt_tag)
            try:
                nt_pdbqt = smiles_to_pdbqt(nt_smi, name=nt_name, output_dir=round_dir)
                nt_result = run_vina(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=nt_pdbqt,
                    ligand_name=nt_name,
                    smiles=nt_smi,
                    docking_params=config.docking,
                    output_dir=round_dir,
                    vina_executable=config.vina_executable,
                    origin="backbone",
                )
                nt_result.annotation = nt_ann
                all_results.append(nt_result)
                logger.info("  %s [%s]: %.2f kcal/mol", nt_name, nt_ann, nt_result.best_energy)
            except Exception as e:
                logger.error("Failed to dock %s [%s]: %s", nt_name, nt_ann, e)

        new_best = current_seeds[0].best_energy
        improvement = best_score - new_best
        logger.info("Round %d best: %.2f kcal/mol (improvement: %.2f)",
                     round_num, new_best, improvement)

        if improvement < config.optimization.delta_affinity_threshold:
            logger.info("Improvement below threshold, stopping")
            break
        best_score = new_best

    logger.info("Backbone optimization complete: %d total candidates docked",
                len(all_results))
    return all_results
