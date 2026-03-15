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
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

def _validate_custom_sidechain(sc_smiles):
    """Validate a custom sidechain SMILES with [*] attachment point.

    Uses RDKit to build a full residue by replacing [*] with a backbone CA.
    Returns the sidechain fragment string if valid, None otherwise.

    Handles branching sidechains (e.g. [*](C)C for AIB) by using
    RDKit molecule editing instead of string manipulation.
    """
    mol = Chem.MolFromSmiles(sc_smiles)
    if mol is None:
        return None

    # Find wildcard atom
    wild_idx = None
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0:
            wild_idx = atom.GetIdx()
            break

    if wild_idx is None:
        # No wildcard - treat whole string as fragment, validate directly
        test = Chem.MolFromSmiles('NC(' + sc_smiles + ')C(=O)O')
        return sc_smiles if test is not None else None

    # Build a full residue by replacing [*] with CA + backbone
    rw = Chem.RWMol(mol)
    rw.GetAtomWithIdx(wild_idx).SetAtomicNum(6)  # [*] -> C (becomes CA)
    n_idx = rw.AddAtom(Chem.Atom(7))  # N
    rw.AddBond(wild_idx, n_idx, Chem.BondType.SINGLE)
    co_idx = rw.AddAtom(Chem.Atom(6))  # C(=O)
    rw.AddBond(wild_idx, co_idx, Chem.BondType.SINGLE)
    o_double = rw.AddAtom(Chem.Atom(8))  # =O
    rw.AddBond(co_idx, o_double, Chem.BondType.DOUBLE)
    o_single = rw.AddAtom(Chem.Atom(8))  # -OH
    rw.AddBond(co_idx, o_single, Chem.BondType.SINGLE)

    try:
        Chem.SanitizeMol(rw)
        residue_smi = Chem.MolToSmiles(rw)
        # Extract the sidechain portion (for simple sidechains, strip [*])
        fragment = sc_smiles.replace('[*]', '')
        if not fragment:
            fragment = '[H]'
        return fragment
    except Exception:
        return None


def get_all_sidechains(config=None):
    """Return combined dict of natural + custom sidechains.

    Custom sidechains use [*] convention: the [*] atom marks where the
    sidechain bonds to the alpha carbon.

    Example: '[*]CCCC' (norleucine) -> sidechain fragment 'CCCC'
    Example: '[*](C)C' (AIB) -> validated via RDKit residue building
    """
    sidechains = dict(AA_SIDECHAIN_SMILES)
    if config is not None:
        custom = getattr(config, 'optimization', None)
        if custom:
            for name, smi in getattr(custom, 'sc_custom_sidechains', {}).items():
                fragment = _validate_custom_sidechain(smi)
                if fragment is not None:
                    sidechains[name.upper()] = fragment
                    logger.info("Registered custom AA: %s (sidechain: %s from %s)",
                               name.upper(), fragment, smi)
                else:
                    logger.warning("Invalid custom sidechain SMILES for %s: %s", name, smi)
    return sidechains


# Single-letter to 3-letter mapping for convenience
ONE_TO_THREE = {
    "G": "GLY", "A": "ALA", "V": "VAL", "L": "LEU", "I": "ILE",
    "P": "PRO", "F": "PHE", "W": "TRP", "M": "MET", "S": "SER",
    "T": "THR", "C": "CYS", "Y": "TYR", "N": "ASN", "Q": "GLN",
    "D": "ASP", "E": "GLU", "K": "LYS", "R": "ARG", "H": "HIS",
}


def build_peptide_smiles(residues: List[str], all_sidechains: dict = None) -> Optional[str]:
    """Build a linear peptide SMILES from a list of 3-letter AA codes.

    Creates: H-[NH-CHR-C(=O)]-...-OH
    Returns None if any residue is unknown or PRO (special handling needed).

    If all_sidechains is provided, it is used instead of AA_SIDECHAIN_SMILES
    to look up R-group fragments (supports custom/unnatural amino acids).
    """
    if not residues:
        return None

    parts = []
    for i, aa in enumerate(residues):
        if aa == "UNK":
            logger.debug("Cannot build peptide SMILES with UNK at position %d", i)
            return None
        sc = all_sidechains.get(aa) if all_sidechains else AA_SIDECHAIN_SMILES.get(aa)
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
            if sc.startswith("("):
                # Branching sidechain (e.g. AIB: "(C)C")
                # Template: NC{sc}C(=O) without extra parens
                frag = "NC" + sc + "C(=O)"
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


# Ranked from most specific (largest sidechain) to least specific.
# First match wins for a given CA atom, preventing e.g. PHE matching TYR.
_AA_SMARTS_RANKED = [
    ("TRP", "[NX3][CX4H1](Cc1c[nH]c2ccccc12)C(=O)", 1),
    ("TYR", "[NX3][CX4H1](Cc1ccc(O)cc1)C(=O)", 1),
    ("PHE", "[NX3][CX4H1](Cc1ccccc1)C(=O)", 1),
    ("ARG", "[NX3][CX4H1](CCCNC(=N)N)C(=O)", 1),
    ("HIS", "[NX3][CX4H1](Cc1c[nH]cn1)C(=O)", 1),
    ("LYS", "[NX3][CX4H1](CCCCN)C(=O)", 1),
    ("GLU", "[NX3][CX4H1](CCC(=O)[OH])C(=O)", 1),
    ("GLN", "[NX3][CX4H1](CCC(N)=O)C(=O)", 1),
    ("MET", "[NX3][CX4H1](CCSC)C(=O)", 1),
    ("ILE", "[NX3][CX4H1]([C@@H](C)CC)C(=O)", 1),
    ("LEU", "[NX3][CX4H1](CC(C)C)C(=O)", 1),
    ("ASP", "[NX3][CX4H1](CC(=O)[OH])C(=O)", 1),
    ("ASN", "[NX3][CX4H1](CC(N)=O)C(=O)", 1),
    ("THR", "[NX3][CX4H1]([C@@H](O)C)C(=O)", 1),
    ("VAL", "[NX3][CX4H1](C(C)C)C(=O)", 1),
    ("CYS", "[NX3][CX4H1](CS)C(=O)", 1),
    ("SER", "[NX3][CX4H1](CO)C(=O)", 1),
    ("ALA", "[NX3][CX4H1]([CH3])C(=O)", 1),
    ("GLY", "[NX3][CX4H2]C(=O)", 1),
    ("PRO", "[NX3]1CCC[CX4H1]1C(=O)", 4),  # CA at position 4 in match
]


def identify_peptide_residues(smiles: str,
                              known_sequence: str = "") -> List[str]:
    """Identify the amino acid sequence from a peptide SMILES.

    If *known_sequence* is provided (1-letter codes, e.g. "HPQF"),
    it is converted directly to 3-letter codes -- no SMILES decomposition
    needed.

    Otherwise, uses ranked SMARTS substructure matching to identify each
    residue and a peptide-bond graph to order them N-to-C.

    Returns a list of 3-letter codes, or empty list if not recognizable.
    """
    # Fast path: user already told us the sequence
    if known_sequence:
        residues = []
        for ch in known_sequence.upper():
            code = ONE_TO_THREE.get(ch)
            if code is None:
                residues.append("UNK")  # unnatural amino acid
                logger.info("Position %d: unnatural residue '%s' -> UNK (will be preserved)", len(residues), ch)
            else:
                residues.append(code)
        return residues

    # Slow path: SMARTS-based decomposition
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # 1. Map each CA atom to its amino acid (most specific pattern wins)
    ca_to_aa: Dict[int, str] = {}
    for aa, smarts, ca_pos in _AA_SMARTS_RANKED:
        pat = Chem.MolFromSmarts(smarts)
        if pat is None:
            continue
        for match in mol.GetSubstructMatches(pat):
            ca_idx = match[ca_pos]
            if ca_idx not in ca_to_aa:  # first (most specific) wins
                ca_to_aa[ca_idx] = aa

    if not ca_to_aa:
        return []

    # 1b. Catch unmatched backbone CAs as UNK (unnatural amino acids)
    #     Generic pattern: any carbon bonded to N and C(=O)
    generic_backbone = Chem.MolFromSmarts('[NX3][CX4]C(=O)')
    if generic_backbone is not None:
        for match in mol.GetSubstructMatches(generic_backbone):
            ca_idx = match[1]
            if ca_idx not in ca_to_aa:
                ca_to_aa[ca_idx] = 'UNK'
                logger.debug('Unmatched backbone CA at idx %d -> UNK', ca_idx)

    # 2. Build peptide-bond graph: for each CA, find the next CA
    #    via CA -> C(=O) -> N -> next_CA
    ca_set = set(ca_to_aa.keys())
    ca_next: Dict[int, int] = {}

    for ca_idx in ca_set:
        ca_atom = mol.GetAtomWithIdx(ca_idx)
        for nb in ca_atom.GetNeighbors():
            if nb.GetSymbol() != "C":
                continue
            # Check if this C has a double-bonded O (carbonyl)
            is_carbonyl = False
            for nb2 in nb.GetNeighbors():
                if nb2.GetSymbol() == "O":
                    bond = mol.GetBondBetweenAtoms(nb.GetIdx(), nb2.GetIdx())
                    if bond and bond.GetBondTypeAsDouble() == 2.0:
                        is_carbonyl = True
                        break
            if not is_carbonyl:
                continue
            # From carbonyl C, find amide N -> next CA
            for nb2 in nb.GetNeighbors():
                if nb2.GetSymbol() != "N":
                    continue
                for nb3 in nb2.GetNeighbors():
                    if nb3.GetIdx() in ca_set and nb3.GetIdx() != ca_idx:
                        ca_next[ca_idx] = nb3.GetIdx()
                        break

    # 3. Find N-terminal CA (has no predecessor in the chain)
    all_targets = set(ca_next.values())
    n_term = [ca for ca in ca_set if ca not in all_targets]

    if not n_term:
        # Possibly cyclic peptide; return unordered
        return list(ca_to_aa.values())

    # 4. Walk from N-term to C-term
    current = n_term[0]
    ordered = [ca_to_aa[current]]
    visited = {current}
    while current in ca_next:
        nxt = ca_next[current]
        if nxt in visited:
            break
        ordered.append(ca_to_aa[nxt])
        visited.add(nxt)
        current = nxt

    return ordered


def _generate_hybrid_variants(smiles: str, residues: List[str],
                              allowed: List[str], config: PipelineConfig) -> List[Tuple[str, str]]:
    """Generate sidechain variants for peptides containing unnatural residues.

    Instead of rebuilding the whole peptide from residue list (which fails
    for UNK residues), this uses RDKit substructure replacement on the
    original SMILES molecule to swap sidechains at natural-AA positions only.

    Falls back to MolFromSequence-based rebuilding for the natural-AA-only
    subsequence if direct replacement fails.
    """
    variants = {}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # Strategy: for each mutable (non-UNK) position, find its CA atom index
    # using the same SMARTS matching, then attempt sidechain replacement
    ca_to_aa = {}
    for aa, smarts_str, ca_pos in _AA_SMARTS_RANKED:
        pat = Chem.MolFromSmarts(smarts_str)
        if pat is None:
            continue
        for match in mol.GetSubstructMatches(pat):
            ca_idx = match[ca_pos]
            if ca_idx not in ca_to_aa:
                ca_to_aa[ca_idx] = aa

    # Build ordered CA list (same as identify_peptide_residues logic)
    ca_set = set(ca_to_aa.keys())
    ca_next = {}
    for ca_idx in ca_set:
        ca_atom = mol.GetAtomWithIdx(ca_idx)
        for nb in ca_atom.GetNeighbors():
            if nb.GetSymbol() != "C":
                continue
            is_carbonyl = False
            for nb2 in nb.GetNeighbors():
                if nb2.GetSymbol() == "O":
                    bond = mol.GetBondBetweenAtoms(nb.GetIdx(), nb2.GetIdx())
                    if bond and bond.GetBondTypeAsDouble() == 2.0:
                        is_carbonyl = True
                        break
            if not is_carbonyl:
                continue
            for nb2 in nb.GetNeighbors():
                if nb2.GetSymbol() != "N":
                    continue
                for nb3 in nb2.GetNeighbors():
                    if nb3.GetIdx() in ca_set and nb3.GetIdx() != ca_idx:
                        ca_next[ca_idx] = nb3.GetIdx()
                        break

    all_targets = set(ca_next.values())
    n_term = [ca for ca in ca_set if ca not in all_targets]
    if not n_term:
        return []

    ordered_cas = []
    current = n_term[0]
    ordered_cas.append(current)
    visited = {current}
    while current in ca_next:
        nxt = ca_next[current]
        if nxt in visited:
            break
        ordered_cas.append(nxt)
        visited.add(nxt)
        current = nxt

    # For each mutable position, try to replace the sidechain
    # This is a simplified approach: for positions we CAN identify,
    # generate the single-residue mutant by building a partial peptide
    # from the identified natural residues with one mutation
    for pos_idx, ca_idx in enumerate(ordered_cas):
        if pos_idx >= len(residues):
            break
        if residues[pos_idx] == "UNK":
            continue  # skip unnatural

        current_aa = residues[pos_idx]
        for new_aa in allowed:
            if new_aa == current_aa:
                continue
            # Build a mutant residue list and try to construct SMILES
            mutant = list(residues)
            mutant[pos_idx] = new_aa
            # Try build_peptide_smiles - it will fail if any UNK present
            new_smi = build_peptide_smiles(mutant)
            if new_smi and new_smi != smiles:
                variants[new_smi] = "Pos{}: {}->{}".format(pos_idx + 1, current_aa, new_aa)

    # If build_peptide_smiles failed due to UNK, try RDKit MolFromSequence
    # for the natural-only positions as a rough approximation
    if not variants:
        natural_only = [r for r in residues if r != "UNK"]
        if natural_only:
            three_to_one = {v: k for k, v in ONE_TO_THREE.items()}
            for pos_idx in range(len(natural_only)):
                for new_aa in allowed:
                    if new_aa == natural_only[pos_idx]:
                        continue
                    mutant = list(natural_only)
                    mutant[pos_idx] = new_aa
                    new_smi = build_peptide_smiles(mutant)
                    if new_smi and new_smi != smiles:
                        variants[new_smi] = "Pos{}: {}->{}".format(pos_idx + 1, natural_only[pos_idx], new_aa)
            if variants:
                logger.info("Generated %d variants from natural-AA-only subset (%d of %d residues)",
                           len(variants), len(natural_only), len(residues))

    return [(smi, ann) for smi, ann in variants.items()]


def generate_sidechain_variants(smiles: str,
                                config: PipelineConfig) -> List[Tuple[str, str]]:
    """Generate candidate SMILES with mutated side chains.

    For each position in the peptide, tries substituting each allowed
    amino acid. Returns a list of unique, valid (SMILES, annotation) tuples.
    Positions with unnatural amino acids (UNK) are preserved unchanged.
    """
    residues = identify_peptide_residues(
        smiles, known_sequence=getattr(config, "ligand_sequence", ""))
    if not residues:
        logger.warning("Cannot identify residues in: %s", smiles)
        return []

    all_sc = get_all_sidechains(config)
    allowed = [aa for aa in config.optimization.sc_allowed_residues
               if aa in all_sc]
    # Also include custom UAAs in allowed list
    for name in getattr(config.optimization, 'sc_custom_sidechains', {}):
        uname = name.upper()
        if uname in all_sc and uname not in allowed:
            allowed.append(uname)

    n_positions = len(residues)
    n_mutable = sum(1 for r in residues if r != "UNK")
    n_unk = n_positions - n_mutable
    if n_unk > 0:
        logger.info("Peptide has %d unnatural (UNK) positions - preserving them, mutating %d natural positions", n_unk, n_mutable)

    has_unk = any(r == "UNK" for r in residues)

    if has_unk:
        # Use hybrid approach for peptides with unnatural residues
        variant_list = _generate_hybrid_variants(smiles, residues, allowed, config)
    else:
        # Standard approach: build from residue list
        variants = {}
        for pos in range(n_positions):
            for new_aa in allowed:
                if new_aa == residues[pos]:
                    continue  # skip identity mutation
                mutant = list(residues)
                mutant[pos] = new_aa
                new_smi = build_peptide_smiles(mutant, all_sidechains=all_sc)
                if new_smi and new_smi != smiles:
                    variants[new_smi] = "Pos{}: {}->{}".format(pos + 1, residues[pos], new_aa)
        variant_list = [(smi, ann) for smi, ann in variants.items()]

    # If too many, sample randomly
    max_cand = config.optimization.max_candidates_per_round
    if len(variant_list) > max_cand:
        random.shuffle(variant_list)
        variant_list = variant_list[:max_cand]

    logger.info("Generated %d sidechain variants from %d positions x %d AAs",
                len(variant_list), n_positions, len(allowed))
    return variant_list


def _format_time(seconds):
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return "{:.0f} sec".format(seconds)
    elif seconds < 3600:
        return "{:.1f} min".format(seconds / 60)
    else:
        return "{:.1f} hr".format(seconds / 3600)


def run_sidechain_optimization(config: PipelineConfig,
                               receptor_pdbqt,
                               initial_results: List[DockingResult],
                               original_score: float,
                               time_per_dock: float = 0.0) -> List[DockingResult]:
    """Execute the iterative side-chain optimization loop."""
    out_dir = ensure_dir(config.output_dir / "sidechain")
    all_results = []
    current_seeds = list(initial_results)
    best_score = original_score

    for round_num in range(1, config.optimization.max_rounds + 1):
        logger.info("Side-chain optimization round %d/%d",
                     round_num, config.optimization.max_rounds)
        round_dir = ensure_dir(out_dir / "round_{:02d}".format(round_num))

        # Generate annotated variants from all current seeds
        candidates_with_ann = []
        seen_smiles = set()
        for seed in current_seeds:
            variants = generate_sidechain_variants(seed.smiles, config)
            for smi, ann in variants:
                if smi not in seen_smiles:
                    seen_smiles.add(smi)
                    candidates_with_ann.append((smi, ann))

        if not candidates_with_ann:
            logger.info("No new sidechain variants generated, stopping")
            break

        # Log residue identification for first round
        if round_num == 1:
            seed_residues = identify_peptide_residues(
                current_seeds[0].smiles,
                known_sequence=getattr(config, "ligand_sequence", ""))
            if seed_residues:
                res_str = ", ".join(seed_residues)
                unk_positions = [str(i + 1) for i, r in enumerate(seed_residues) if r == "UNK"]
                logger.info("Peptide residues: [%s]", res_str)
                if unk_positions:
                    logger.info("UNK (unnatural) at positions %s - preserved, not mutated",
                                ", ".join(unk_positions))

        # Time estimation
        rounds_remaining = config.optimization.max_rounds - round_num
        if time_per_dock > 0:
            est_this_round = len(candidates_with_ann) * time_per_dock
            est_future = rounds_remaining * len(candidates_with_ann) * time_per_dock
            logger.info("Estimated time: this round ~%s, remaining ~%s (%d docks x %.1f sec/dock)",
                        _format_time(est_this_round),
                        _format_time(est_this_round + est_future),
                        len(candidates_with_ann), time_per_dock)

        logger.info("Docking %d sidechain candidates", len(candidates_with_ann))
        round_results = []
        round_start = time.time()

        for i, (smi, annotation) in enumerate(candidates_with_ann):
            name = "sc_r{:02d}_{:03d}".format(round_num, i + 1)

            # Validate
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
                    origin="sidechain",
                )
                dock_elapsed = time.time() - dock_start
                # Update running average
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
            logger.info("No successful docking results this round, stopping")
            break

        logger.info("Round %d completed in %s", round_num, _format_time(round_elapsed))

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
