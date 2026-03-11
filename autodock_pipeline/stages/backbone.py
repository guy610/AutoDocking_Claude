"""
Stage 2 - Backbone optimization.

Modify backbone geometry at positions with few backbone-mediated
interactions and that are relatively solvent-exposed.

Modifications include:
  - N-methylation: replace backbone NH with N(CH3) to improve stability
  - D-amino acid substitution: invert stereochemistry at CA
These changes can improve metabolic stability while preserving binding.
"""

import logging
from pathlib import Path
from typing import List

from rdkit import Chem

from ..config import PipelineConfig
from ..core.docking import DockingResult, run_vina
from ..core.interactions import InteractionMetrics, compute_interactions
from ..core.ligand import smiles_to_pdbqt
from ..core.validators import validate_ligand, print_validation_alerts
from ..utils.io_utils import ensure_dir, safe_filename

logger = logging.getLogger(__name__)


def identify_backbone_candidates(metrics: InteractionMetrics,
                                 config: PipelineConfig) -> List[int]:
    """Identify residue positions eligible for backbone modifications.

    A position is eligible if it has few backbone-mediated interactions
    (below the threshold), suggesting the backbone at that position
    is not critical for binding.
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
                               config: PipelineConfig) -> List[str]:
    """Generate backbone-modified candidate SMILES.

    For each candidate position, generate:
      1. N-methylated variant (replace NH with N(C))
      2. D-amino acid variant (invert CA stereochemistry)
    """
    variants = set()
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
                            variants.add(new_smi)
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
                        variants.add(new_smi)
                        logger.debug("D-AA at position %d: %s", pos, new_smi)
            except Exception as e:
                logger.debug("D-AA substitution failed at position %d: %s", pos, e)

    return list(variants)


def run_backbone_optimization(config: PipelineConfig,
                              receptor_pdbqt,
                              initial_results: List[DockingResult],
                              original_score: float) -> List[DockingResult]:
    """Execute the iterative backbone optimization loop.

    For each round:
      1. Compute interaction metrics for current best poses.
      2. Identify backbone modification candidates.
      3. Generate variants, dock, and select top candidates.
      4. Stop if no improvement or max rounds reached.
    """
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
            # Create dummy per_residue with all positions eligible
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

        # Generate variants from all seeds
        all_variants = []
        for s in current_seeds:
            variants = generate_backbone_variants(s.smiles, candidates_pos, config)
            all_variants.extend(variants)

        all_variants = list(set(all_variants))
        if not all_variants:
            logger.info("No backbone variants generated, stopping")
            break

        logger.info("Docking %d backbone candidates", len(all_variants))
        round_results = []

        for i, smi in enumerate(all_variants):
            name = "bb_r{:02d}_{:03d}".format(round_num, i + 1)
            val = validate_ligand(smi, name=name,
                                  max_residues=config.optimization.max_residues)
            print_validation_alerts(val)
            if not val.is_valid:
                continue
            try:
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
                round_results.append(result)
                all_results.append(result)
                logger.info("  %s: %.2f kcal/mol", name, result.best_energy)
            except Exception as e:
                logger.error("Failed to dock %s: %s", name, e)

        if not round_results:
            logger.info("No successful backbone docking results, stopping")
            break

        combined = current_seeds + round_results
        combined.sort(key=lambda r: r.best_energy)
        current_seeds = combined[:config.optimization.top_n_select]

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
