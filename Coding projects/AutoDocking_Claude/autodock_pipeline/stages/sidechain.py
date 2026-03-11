"""
Stage 1 - Side-chain optimization.

Vary amino-acid side chains while preserving the peptide backbone
connectivity and length. Generate mutant SMILES, dock, and select
the best candidates.

Strategy:
  1. Parse the seed peptide SMILES into residue fragments.
  2. For each round, enumerate single-residue mutations at each position.
  3. Dock each variant and keep the top candidates.
  4. Stop when no improvement exceeds the delta threshold or max rounds reached.
"""

import logging
import random
from pathlib import Path
from typing import Dict, List, Optional

from rdkit import Chem

from ..config import PipelineConfig
from ..core.docking import DockingResult, run_vina
from ..core.ligand import smiles_to_pdbqt
from ..core.validators import validate_ligand, print_validation_alerts
from ..utils.io_utils import ensure_dir, safe_filename

logger = logging.getLogger(__name__)

# Map 3-letter AA codes to SMILES side-chain fragments (attached to CA)
# These are the R-groups; the backbone is N-CA-C(=O)
AA_SIDECHAIN_SMILES = {
    "GLY": "[H]",
    "ALA": "C",
    "VAL": "C(C)C",
    "LEU": "CC(C)C",
    "ILE": "[C@@H](C)CC",
    "PRO": "",  # special case - ring closure
    "PHE": "Cc1ccccc1",
    "TRP": "Cc1c[nH]c2ccccc12",
    "MET": "CCSC",
    "SER": "CO",
    "THR": "[C@@H](O)C",
    "CYS": "CS",
    "TYR": "Cc1ccc(O)cc1",
    "ASN": "CC(N)=O",
    "GLN": "CCC(N)=O",
    "ASP": "CC(O)=O",
    "GLU": "CCC(O)=O",
    "LYS": "CCCCN",
    "ARG": "CCCNC(N)=N",
    "HIS": "Cc1c[nH]cn1",
}

# Single-letter to 3-letter mapping for convenience
ONE_TO_THREE = {
    "G": "GLY", "A": "ALA", "V": "VAL", "L": "LEU", "I": "ILE",
    "P": "PRO", "F": "PHE", "W": "TRP", "M": "MET", "S": "SER",
    "T": "THR", "C": "CYS", "Y": "TYR", "N": "ASN", "Q": "GLN",
    "D": "ASP", "E": "GLU", "K": "LYS", "R": "ARG", "H": "HIS",
}


def build_peptide_smiles(residues: List[str]) -> Optional[str]:
    """Build a linear peptide SMILES from a list of 3-letter AA codes.

    Creates: H-[NH-CHR-C(=O)]-...-OH
    Returns None if any residue is unknown or PRO (special handling needed).
    """
    if not residues:
        return None

    parts = []
    for i, aa in enumerate(residues):
        sc = AA_SIDECHAIN_SMILES.get(aa)
        if sc is None:
            logger.warning("Unknown amino acid: %s", aa)
            return None
        if aa == "PRO":
            # Proline: N is part of a 5-membered ring with the sidechain
            if i == 0:
                parts.append("N1CCCC1C(=O)")
            else:
                parts.append("N1CCCC1C(=O)")
        elif aa == "GLY":
            if i == 0:
                parts.append("NCC(=O)")
            else:
                parts.append("NCC(=O)")
        else:
            if i == 0:
                frag = "NC({sc})C(=O)".format(sc=sc)
            else:
                frag = "NC({sc})C(=O)".format(sc=sc)
            parts.append(frag)

    # Join with peptide bonds: remove terminal C(=O) from last, add OH
    smiles = "".join(parts) + "O"

    # Validate with RDKit
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        # Try canonical approach
        logger.debug("Direct SMILES build failed, trying canonical peptide build")
        return _build_peptide_canonical(residues)
    return Chem.MolToSmiles(mol)


def _build_peptide_canonical(residues: List[str]) -> Optional[str]:
    """Fallback: build peptide using RDKit fragment combination."""
    # Build as individual amino acids and combine via amide bonds
    # Simple linear: H2N-CHR1-CO-NH-CHR2-CO-...-OH
    aa_smiles_map = {
        "GLY": "NCC(=O)O", "ALA": "NC(C)C(=O)O", "VAL": "NC(C(C)C)C(=O)O",
        "LEU": "NC(CC(C)C)C(=O)O", "ILE": "NC([C@@H](C)CC)C(=O)O",
        "PHE": "NC(Cc1ccccc1)C(=O)O", "TRP": "NC(Cc1c[nH]c2ccccc12)C(=O)O",
        "MET": "NC(CCSC)C(=O)O", "SER": "NC(CO)C(=O)O", "THR": "NC([C@@H](O)C)C(=O)O",
        "CYS": "NC(CS)C(=O)O", "TYR": "NC(Cc1ccc(O)cc1)C(=O)O",
        "ASN": "NC(CC(N)=O)C(=O)O", "GLN": "NC(CCC(N)=O)C(=O)O",
        "ASP": "NC(CC(O)=O)C(=O)O", "GLU": "NC(CCC(O)=O)C(=O)O",
        "LYS": "NC(CCCCN)C(=O)O", "ARG": "NC(CCCNC(N)=N)C(=O)O",
        "HIS": "NC(Cc1c[nH]cn1)C(=O)O", "PRO": "N1CCCC1C(=O)O",
    }

    if len(residues) == 1:
        smi = aa_smiles_map.get(residues[0])
        if smi:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                return Chem.MolToSmiles(mol)
        return None

    # For multiple residues, build incrementally
    # Start with first AA (free amine)
    current_smi = aa_smiles_map.get(residues[0])
    if not current_smi:
        return None

    for aa in residues[1:]:
        next_smi = aa_smiles_map.get(aa)
        if not next_smi:
            return None
        # Remove -OH from current C-terminus and -H from next N-terminus
        # This is a simplified approach; real peptide bond formation
        # Just concatenate the fragment patterns
        current_smi = current_smi.rstrip("O").rstrip(")")
        if current_smi.endswith("(=O"):
            current_smi += ")"
        # Append next residue
        next_frag = next_smi  # includes N at start
        current_smi = current_smi + next_frag

    mol = Chem.MolFromSmiles(current_smi)
    if mol is None:
        logger.warning("Could not build valid peptide from: %s", residues)
        return None
    return Chem.MolToSmiles(mol)


def identify_peptide_residues(smiles: str) -> List[str]:
    """Attempt to identify the amino acid sequence from a peptide SMILES.

    Uses substructure matching against known AA patterns.
    Returns a list of 3-letter codes, or empty list if not a recognizable peptide.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # Count amide bonds to estimate length
    amide_pat = Chem.MolFromSmarts("[C](=O)[NH]")
    if amide_pat is None:
        return []
    n_amide = len(mol.GetSubstructMatches(amide_pat))
    if n_amide == 0:
        return []

    # For now, return placeholder residues based on count
    # A full implementation would do substructure decomposition
    n_residues = n_amide + 1
    return ["ALA"] * n_residues  # placeholder


def generate_sidechain_variants(smiles: str,
                                config: PipelineConfig) -> List[str]:
    """Generate candidate SMILES with mutated side chains.

    For each position in the peptide, tries substituting each allowed
    amino acid. Returns a list of unique, valid SMILES strings.
    """
    residues = identify_peptide_residues(smiles)
    if not residues:
        logger.warning("Cannot identify residues in: %s", smiles)
        return []

    allowed = [aa for aa in config.optimization.sc_allowed_residues
               if aa in AA_SIDECHAIN_SMILES]

    variants = set()
    n_positions = len(residues)

    for pos in range(n_positions):
        for new_aa in allowed:
            if new_aa == residues[pos]:
                continue  # skip identity mutation
            mutant = list(residues)
            mutant[pos] = new_aa
            new_smi = build_peptide_smiles(mutant)
            if new_smi and new_smi != smiles:
                variants.add(new_smi)

    variant_list = list(variants)

    # If too many, sample randomly
    max_cand = config.optimization.max_candidates_per_round
    if len(variant_list) > max_cand:
        random.shuffle(variant_list)
        variant_list = variant_list[:max_cand]

    logger.info("Generated %d sidechain variants from %d positions x %d AAs",
                len(variant_list), n_positions, len(allowed))
    return variant_list


def run_sidechain_optimization(config: PipelineConfig,
                               receptor_pdbqt,
                               initial_results: List[DockingResult],
                               original_score: float) -> List[DockingResult]:
    """Execute the iterative side-chain optimization loop.

    For each round:
      1. Generate sidechain variants from the current best candidates.
      2. Validate and dock each variant.
      3. Keep top N candidates that improve over the original.
      4. Stop if no improvement or max rounds reached.
    """
    out_dir = ensure_dir(config.output_dir / "sidechain")
    all_results = []
    current_seeds = list(initial_results)
    best_score = original_score

    for round_num in range(1, config.optimization.max_rounds + 1):
        logger.info("Side-chain optimization round %d/%d",
                     round_num, config.optimization.max_rounds)
        round_dir = ensure_dir(out_dir / "round_{:02d}".format(round_num))

        # Generate variants from all current seeds
        candidates = []
        for seed in current_seeds:
            variants = generate_sidechain_variants(seed.smiles, config)
            candidates.extend(variants)

        # Deduplicate
        candidates = list(set(candidates))
        if not candidates:
            logger.info("No new sidechain variants generated, stopping")
            break

        logger.info("Docking %d sidechain candidates", len(candidates))
        round_results = []

        for i, smi in enumerate(candidates):
            name = "sc_r{:02d}_{:03d}".format(round_num, i + 1)

            # Validate
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
                    origin="sidechain",
                )
                round_results.append(result)
                all_results.append(result)
                logger.info("  %s: %.2f kcal/mol", name, result.best_energy)
            except Exception as e:
                logger.error("Failed to dock %s: %s", name, e)

        if not round_results:
            logger.info("No successful docking results this round, stopping")
            break

        # Select top candidates
        combined = current_seeds + round_results
        combined.sort(key=lambda r: r.best_energy)
        top_n = config.optimization.top_n_select
        current_seeds = combined[:top_n]

        # Check for improvement
        new_best = current_seeds[0].best_energy
        improvement = best_score - new_best
        logger.info("Round %d best: %.2f kcal/mol (improvement: %.2f)",
                     round_num, new_best, improvement)

        if improvement < config.optimization.delta_affinity_threshold:
            logger.info("Improvement below threshold (%.2f < %.2f), stopping",
                         improvement, config.optimization.delta_affinity_threshold)
            break
        best_score = new_best

    logger.info("Side-chain optimization complete: %d total candidates docked",
                len(all_results))
    return all_results
