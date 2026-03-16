"""
Ligand preparation: SMILES -> 3D conformer -> PDB -> PDBQT.

Uses RDKit (BSD) for 3D generation and Meeko (Apache-2.0) for PDBQT.
"""

import logging
from pathlib import Path
from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem, rdmolfiles

from ..utils.io_utils import ensure_dir, safe_filename

logger = logging.getLogger(__name__)


# pKa values for ionizable groups in peptides
_IONIZABLE_GROUPS = [
    # (SMARTS for neutral form, SMARTS for charged form, pKa, "acid" or "base")
    # Below pKa = protonated, above pKa = deprotonated

    # Carboxylic acid (ASP/GLU/C-term): neutral = -COOH, charged = -COO-
    ("CC(=O)[OH]", "CC(=O)[O-]", 4.0, "acid"),

    # Primary amine (LYS/N-term): neutral = -NH2, charged = -NH3+
    ("CCCCN", "CCCC[NH3+]", 10.5, "base"),  # LYS sidechain

    # Guanidinium (ARG): stays protonated at all relevant pH
    ("NC(=N)N", "NC(=[NH2+])N", 12.5, "base"),
]


def adjust_protonation(smiles: str, pH: float = 7.3) -> str:
    """Adjust protonation state of ionizable groups based on pH.

    Uses RDKit RWMol to modify protonation at ionizable sites.
    At pH 7.3 (physiological): ASP/GLU deprotonated, LYS/ARG protonated,
    HIS neutral. Returns canonical SMILES with adjusted protonation.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("Cannot parse SMILES for protonation: %s", smiles)
        return smiles

    rw = Chem.RWMol(mol)

    # 1. Carboxylic acids: ASP/GLU sidechains and C-terminus
    #    pKa ~ 3.1-4.1 -> deprotonated at pH > 4.5
    if pH > 4.5:
        # Find C(=O)OH patterns (carboxylic acid)
        acid_pat = Chem.MolFromSmarts('[CX3](=O)[OX2H1]')
        if acid_pat:
            # Deprotonate: remove H from OH, set charge to -1
            for match in rw.GetSubstructMatches(acid_pat):
                o_idx = match[2]  # the OH oxygen
                o_atom = rw.GetAtomWithIdx(o_idx)
                if o_atom.GetFormalCharge() == 0 and o_atom.GetTotalNumHs() > 0:
                    o_atom.SetFormalCharge(-1)
                    o_atom.SetNoImplicit(True)
                    o_atom.SetNumExplicitHs(0)

    # 2. Histidine imidazole: pKa ~ 6.0
    #    At pH < 6: protonated (imidazolium +1)
    #    At pH > 6: neutral
    if pH < 6.0:
        his_pat = Chem.MolFromSmarts('c1c[nH]cn1')
        if his_pat:
            for match in rw.GetSubstructMatches(his_pat):
                # Protonate the non-protonated ring nitrogen
                for idx in match:
                    atom = rw.GetAtomWithIdx(idx)
                    if atom.GetSymbol() == 'N' and atom.GetTotalNumHs() == 0:
                        atom.SetFormalCharge(1)
                        atom.SetNumExplicitHs(1)
                        break

    # 3. Lysine primary amine: pKa ~ 10.5
    #    Protonated (NH3+) at pH < 10.5
    if pH < 10.5:
        # Very specific pattern: 4-carbon chain ending in NH2
        # Use SMARTS that won't match amide N or ring N
        lys_pat = Chem.MolFromSmarts('[CH2][CH2][CH2][CH2][NH2]')
        if lys_pat:
            for match in rw.GetSubstructMatches(lys_pat):
                n_idx = match[4]
                n_atom = rw.GetAtomWithIdx(n_idx)
                if n_atom.GetFormalCharge() == 0:
                    n_atom.SetFormalCharge(1)
                    n_atom.SetNumExplicitHs(3)

    # 4. Arginine guanidinium: pKa ~ 12.5
    #    Almost always protonated
    if pH < 12.5:
        arg_pat = Chem.MolFromSmarts('[NH]C(=[NH])N')
        if arg_pat:
            for match in rw.GetSubstructMatches(arg_pat):
                # Protonate the =NH nitrogen
                eq_n_idx = match[2]  # the =NH
                eq_n = rw.GetAtomWithIdx(eq_n_idx)
                if eq_n.GetFormalCharge() == 0 and eq_n.GetSymbol() == 'N':
                    eq_n.SetFormalCharge(1)
                    eq_n.SetNumExplicitHs(2)

    # Sanitize and return
    try:
        Chem.SanitizeMol(rw)
        result = Chem.MolToSmiles(rw)
        # Verify the result is a single molecule (no fragmentation)
        if '.' in result and '.' not in smiles:
            logger.warning("Protonation adjustment fragmented molecule, reverting")
            return smiles
        logger.info("Protonation adjusted for pH %.1f", pH)
        return result
    except Exception as e:
        logger.warning("Protonation sanitization failed: %s, using original", e)
        return smiles


def _find_cterm_oxygen(mol):
    """Find the C-terminal single-bonded oxygen index in a peptide.

    Identifies the C-terminal by finding C(=O)O where the carbonyl carbon
    is bonded to a backbone alpha carbon (which has a nitrogen neighbor).
    This distinguishes C-terminal from ASP/GLU sidechain carboxylic acids,
    where the C(=O)O is bonded to CH2 rather than directly to the alpha-C.

    Returns (carbonyl_c_idx, single_o_idx) or (None, None) if not found.
    """
    for atom in mol.GetAtoms():
        if atom.GetSymbol() != 'C' or atom.GetIsAromatic():
            continue

        dbl_o_idx = None
        single_o_idx = None
        has_alpha_c = False

        for bond in atom.GetBonds():
            other = bond.GetOtherAtom(atom)
            if other.GetSymbol() == 'O':
                if bond.GetBondTypeAsDouble() == 2.0:
                    dbl_o_idx = other.GetIdx()
                elif bond.GetBondTypeAsDouble() == 1.0:
                    single_o_idx = other.GetIdx()
            elif other.GetSymbol() == 'C':
                # Check if this neighbor is an alpha carbon (directly bonded to N)
                for nb in other.GetNeighbors():
                    if nb.GetSymbol() == 'N' and nb.GetIdx() != atom.GetIdx():
                        has_alpha_c = True
                        break

        if dbl_o_idx is not None and single_o_idx is not None and has_alpha_c:
            return atom.GetIdx(), single_o_idx

    return None, None


def make_cterm_amide(smiles: str) -> Optional[str]:
    """Convert C-terminal carboxylic acid/carboxylate to primary amide (CONH2).

    At pH 7.3, the amide form is neutral (CONH2).
    Returns the modified SMILES, or None if conversion fails.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    _, single_o_idx = _find_cterm_oxygen(mol)
    if single_o_idx is None:
        return None

    try:
        rw = Chem.RWMol(mol)
        o_atom = rw.GetAtomWithIdx(single_o_idx)
        o_atom.SetAtomicNum(7)       # O -> N
        o_atom.SetFormalCharge(0)
        o_atom.SetNumExplicitHs(2)   # NH2
        Chem.SanitizeMol(rw)
        new_smi = Chem.MolToSmiles(rw)
        if new_smi and Chem.MolFromSmiles(new_smi) is not None:
            return new_smi
    except Exception as e:
        logger.debug("C-term amide conversion failed: %s", e)

    return None


def make_cterm_acid_deprot(smiles: str) -> Optional[str]:
    """Ensure C-terminal carboxylic acid is deprotonated (COO-) for pH 7.3.

    At pH 7.3, C-terminal carboxyl (pKa ~2-3) is fully deprotonated.
    If already deprotonated, returns canonicalized SMILES unchanged.
    Returns the modified SMILES, or None if conversion fails.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    _, single_o_idx = _find_cterm_oxygen(mol)
    if single_o_idx is None:
        return None

    try:
        rw = Chem.RWMol(mol)
        o_atom = rw.GetAtomWithIdx(single_o_idx)
        if o_atom.GetFormalCharge() == 0:
            # Deprotonate: OH -> O-
            o_atom.SetFormalCharge(-1)
            o_atom.SetNoImplicit(True)
            o_atom.SetNumExplicitHs(0)
        Chem.SanitizeMol(rw)
        new_smi = Chem.MolToSmiles(rw)
        if new_smi and Chem.MolFromSmiles(new_smi) is not None:
            return new_smi
    except Exception as e:
        logger.debug("C-term acid deprotonation failed: %s", e)

    return None


def find_nterm_nitrogen(mol) -> Optional[int]:
    """Find the N-terminal nitrogen atom index in a peptide.

    The N-terminal N is identified by:
    1. Being bonded to an alpha carbon (a C that has a C(=O) neighbor)
    2. NOT being itself bonded to any carbonyl C (which would make it a mid-chain amide N)
    3. NOT being part of a guanidinium group (arginine)

    This naturally excludes lysine sidechain NH2 (bonded to CH2 with no C=O)
    and UAA sidechain amines.

    Returns the atom index, or None if not found.
    """
    if mol is None:
        return None

    # Pre-compute guanidinium nitrogens to exclude (arginine)
    guanidinium_ns = set()
    guan_pat = Chem.MolFromSmarts('[NH]C(=[NH])N')
    if guan_pat:
        for match in mol.GetSubstructMatches(guan_pat):
            for idx in match:
                if mol.GetAtomWithIdx(idx).GetSymbol() == 'N':
                    guanidinium_ns.add(idx)
    # Also catch protonated forms
    guan_pat2 = Chem.MolFromSmarts('[NH]C(=[NH2+])N')
    if guan_pat2:
        for match in mol.GetSubstructMatches(guan_pat2):
            for idx in match:
                if mol.GetAtomWithIdx(idx).GetSymbol() == 'N':
                    guanidinium_ns.add(idx)

    for atom in mol.GetAtoms():
        if atom.GetSymbol() != 'N':
            continue
        if atom.GetIdx() in guanidinium_ns:
            continue

        # Check: is this N bonded to any C that has a C=O? (amide N check)
        is_amide_n = False
        has_alpha_c_neighbor = False

        for bond in atom.GetBonds():
            neighbor = bond.GetOtherAtom(atom)
            if neighbor.GetSymbol() != 'C':
                continue

            # Check if this neighbor C has a double bond to O (making this an amide N)
            neighbor_has_carbonyl = False
            for nb_bond in neighbor.GetBonds():
                nb_other = nb_bond.GetOtherAtom(neighbor)
                if (nb_other.GetSymbol() == 'O' and
                        nb_bond.GetBondTypeAsDouble() == 2.0):
                    neighbor_has_carbonyl = True
                    break

            if neighbor_has_carbonyl:
                # This N is bonded to a C=O carbon -> it's an amide N
                is_amide_n = True
                break

            # Check if this neighbor C is an alpha carbon
            # (alpha-C has a C(=O) neighbor, i.e., the peptide bond carbonyl)
            for nb_bond2 in neighbor.GetBonds():
                nb_other2 = nb_bond2.GetOtherAtom(neighbor)
                if nb_other2.GetIdx() == atom.GetIdx():
                    continue
                if nb_other2.GetSymbol() == 'C':
                    for nb_bond3 in nb_other2.GetBonds():
                        nb_other3 = nb_bond3.GetOtherAtom(nb_other2)
                        if (nb_other3.GetSymbol() == 'O' and
                                nb_bond3.GetBondTypeAsDouble() == 2.0):
                            has_alpha_c_neighbor = True
                            break
                    if has_alpha_c_neighbor:
                        break

        if not is_amide_n and has_alpha_c_neighbor:
            return atom.GetIdx()

    return None


def make_nterm_dimethyl(smiles: str) -> Optional[str]:
    """Replace all N-H bonds on N-terminal nitrogen with N-CH3.

    For primary amines (most AAs): NH2 -> N(CH3)2 (2 methyls added)
    For secondary amines (proline): NH -> N(CH3) (1 methyl added)

    Returns modified SMILES, or None if conversion fails.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    n_idx = find_nterm_nitrogen(mol)
    if n_idx is None:
        logger.debug("Cannot find N-terminal nitrogen for dimethylation")
        return None

    try:
        rw = Chem.RWMol(mol)
        n_atom = rw.GetAtomWithIdx(n_idx)
        n_hs = n_atom.GetTotalNumHs()

        if n_hs == 0:
            logger.debug("N-terminal N has no H's to replace with CH3")
            return None

        # Add methyl groups for each H
        n_atom.SetNoImplicit(True)
        n_atom.SetNumExplicitHs(0)
        # Clear any formal charge (e.g. NH3+ -> N(CH3)2 at neutral state)
        n_atom.SetFormalCharge(0)

        for _ in range(n_hs):
            c_idx = rw.AddAtom(Chem.Atom(6))  # carbon
            rw.AddBond(n_idx, c_idx, Chem.BondType.SINGLE)

        Chem.SanitizeMol(rw)
        new_smi = Chem.MolToSmiles(rw)
        if new_smi and Chem.MolFromSmiles(new_smi) is not None:
            return new_smi
    except Exception as e:
        logger.debug("N-term dimethylation failed: %s", e)

    return None


def make_nterm_acyl(smiles: str, n_carbons: int = 2) -> Optional[str]:
    """Acylate the N-terminal nitrogen with a variable-length acyl chain.

    Forms an amide bond: R-C(=O)-NH-peptide
    n_carbons=2 -> acetyl (CH3-CO-), n_carbons=16 -> palmitoyl (C15H31-CO-)

    For primary amines: NH2 -> NH-C(=O)-R (one H replaced)
    For secondary amines (proline): NH -> N-C(=O)-R (the one H replaced)

    Returns modified SMILES, or None if conversion fails.
    """
    if n_carbons < 2:
        logger.debug("n_carbons must be >= 2 for acylation")
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    n_idx = find_nterm_nitrogen(mol)
    if n_idx is None:
        logger.debug("Cannot find N-terminal nitrogen for acylation")
        return None

    try:
        rw = Chem.RWMol(mol)
        n_atom = rw.GetAtomWithIdx(n_idx)
        n_hs = n_atom.GetTotalNumHs()

        if n_hs == 0:
            logger.debug("N-terminal N has no H's for acylation")
            return None

        # Remove one H from N
        n_atom.SetNoImplicit(True)
        n_atom.SetNumExplicitHs(max(0, n_hs - 1))
        n_atom.SetFormalCharge(0)

        # Build acyl chain: carbonyl C first, then CH2 chain, then terminal CH3
        # N -- C(=O) -- (CH2)_{n-2} -- CH3
        # Actually: N -- C(=O) -- CH2 -- CH2 -- ... -- CH3
        # The carbonyl C is the first C, then (n-2) more carbons in the chain
        # Total carbons = n_carbons

        # Add carbonyl carbon
        co_c_idx = rw.AddAtom(Chem.Atom(6))  # carbonyl C
        rw.AddBond(n_idx, co_c_idx, Chem.BondType.SINGLE)

        # Add carbonyl oxygen (=O)
        o_idx = rw.AddAtom(Chem.Atom(8))
        rw.AddBond(co_c_idx, o_idx, Chem.BondType.DOUBLE)

        # Add remaining carbons in chain (n_carbons - 1 more carbons)
        prev_idx = co_c_idx
        for _ in range(n_carbons - 1):
            c_idx = rw.AddAtom(Chem.Atom(6))
            rw.AddBond(prev_idx, c_idx, Chem.BondType.SINGLE)
            prev_idx = c_idx

        Chem.SanitizeMol(rw)
        new_smi = Chem.MolToSmiles(rw)
        if new_smi and Chem.MolFromSmiles(new_smi) is not None:
            return new_smi
    except Exception as e:
        logger.debug("N-term acylation failed: %s", e)

    return None


def make_nterm_custom(smiles: str, mod_smiles: str) -> Optional[str]:
    """Apply a custom modification to the N-terminal nitrogen.

    The mod_smiles must contain [*] (dummy atom) marking the bond point
    to the N-terminal nitrogen. The [*] is replaced by a direct bond.

    Example: mod_smiles = "[*]C(=O)CCCCC" for hexanoyl
             mod_smiles = "[*]C" for simple methylation

    For primary amines: one H is replaced by the modification
    For secondary amines (proline): the single H is replaced

    Returns modified SMILES, or None if conversion fails.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    mod_mol = Chem.MolFromSmiles(mod_smiles)
    if mod_mol is None:
        logger.debug("Cannot parse modification SMILES: %s", mod_smiles)
        return None

    n_idx = find_nterm_nitrogen(mol)
    if n_idx is None:
        logger.debug("Cannot find N-terminal nitrogen for custom modification")
        return None

    # Find the dummy atom [*] in the modification
    dummy_idx = None
    dummy_neighbor_idx = None
    for atom in mod_mol.GetAtoms():
        if atom.GetAtomicNum() == 0:  # dummy atom
            dummy_idx = atom.GetIdx()
            # Find the neighbor of the dummy (the actual attachment point)
            neighbors = atom.GetNeighbors()
            if len(neighbors) != 1:
                logger.debug("Dummy atom [*] must have exactly 1 neighbor, got %d",
                             len(neighbors))
                return None
            dummy_neighbor_idx = neighbors[0].GetIdx()
            break

    if dummy_idx is None:
        logger.debug("No [*] dummy atom found in modification SMILES: %s", mod_smiles)
        return None

    try:
        # Combine both molecules
        combo = Chem.RWMol(Chem.CombineMols(mol, mod_mol))

        # Adjust indices: mod atoms are shifted by mol.GetNumAtoms()
        offset = mol.GetNumAtoms()
        new_dummy_idx = dummy_idx + offset
        new_neighbor_idx = dummy_neighbor_idx + offset

        # Remove one H from N-terminal
        n_atom = combo.GetAtomWithIdx(n_idx)
        n_hs = n_atom.GetTotalNumHs()
        if n_hs == 0:
            logger.debug("N-terminal N has no H's for custom modification")
            return None

        n_atom.SetNoImplicit(True)
        n_atom.SetNumExplicitHs(max(0, n_hs - 1))
        n_atom.SetFormalCharge(0)

        # Add bond from N to the dummy's neighbor
        combo.AddBond(n_idx, new_neighbor_idx, Chem.BondType.SINGLE)

        # Remove the dummy atom
        combo.RemoveAtom(new_dummy_idx)

        Chem.SanitizeMol(combo)
        new_smi = Chem.MolToSmiles(combo)
        if new_smi and Chem.MolFromSmiles(new_smi) is not None:
            return new_smi
    except Exception as e:
        logger.debug("N-term custom modification failed: %s", e)

    return None


def smiles_to_3d(smiles: str, name: str = "ligand",
                 output_dir: Optional[Path] = None,
                 num_conformers: int = 1,
                 random_seed: int = 42) -> Path:
    """Generate a 3D conformer from SMILES using RDKit, write PDB.

    Returns the path to the ligand PDB file.
    """
    if output_dir is None:
        output_dir = Path(".")
    ensure_dir(output_dir)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit cannot parse SMILES: {smiles}")

    # Add hydrogens for proper 3D geometry
    mol = Chem.AddHs(mol)

    # Set molecule name
    mol.SetProp("_Name", name)

    # Generate 3D conformer(s)
    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    params.numThreads = 0  # use all available cores

    n_confs = max(1, num_conformers)
    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=n_confs, params=params)

    if len(conf_ids) == 0:
        # Fallback: try without distance geometry constraints
        logger.warning("ETKDG failed for %s, trying unconstrained embedding", name)
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=n_confs,
                                               randomSeed=random_seed)
        if len(conf_ids) == 0:
            raise RuntimeError(f"Could not generate 3D coordinates for: {smiles}")

    # Minimize with MMFF94 (or UFF fallback)
    best_conf_id = 0
    best_energy = float("inf")
    for cid in conf_ids:
        try:
            res = AllChem.MMFFOptimizeMolecule(mol, confId=cid, maxIters=500)
            ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol), confId=cid)
            if ff is not None:
                energy = ff.CalcEnergy()
                if energy < best_energy:
                    best_energy = energy
                    best_conf_id = cid
        except Exception:
            # UFF fallback
            try:
                AllChem.UFFOptimizeMolecule(mol, confId=cid, maxIters=500)
            except Exception:
                pass

    # Write PDB
    fname = safe_filename(name)
    pdb_path = output_dir / f"{fname}.pdb"
    rdmolfiles.MolToPDBFile(mol, str(pdb_path), confId=best_conf_id)
    logger.info("Ligand 3D structure written: %s (energy=%.1f)", pdb_path, best_energy)

    return pdb_path


def smiles_to_pdbqt(smiles: str, name: str = "ligand",
                    output_dir: Optional[Path] = None,
                    random_seed: int = 42) -> Path:
    """Generate PDBQT directly from SMILES using RDKit + Meeko.

    Returns the path to the ligand .pdbqt file.
    """
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    if output_dir is None:
        output_dir = Path(".")
    ensure_dir(output_dir)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit cannot parse SMILES: {smiles}")

    mol = Chem.AddHs(mol)
    mol.SetProp("_Name", name)

    # Generate 3D
    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=1, params=params)
    if len(conf_ids) == 0:
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=1, randomSeed=random_seed)
        if len(conf_ids) == 0:
            raise RuntimeError(f"Could not generate 3D coordinates for: {smiles}")

    # Minimize
    try:
        AllChem.MMFFOptimizeMolecule(mol, confId=0, maxIters=500)
    except Exception:
        try:
            AllChem.UFFOptimizeMolecule(mol, confId=0, maxIters=500)
        except Exception:
            logger.warning("Could not minimize %s, using unminimized conformer", name)

    # Use Meeko to prepare PDBQT
    preparator = MoleculePreparation()
    mol_setup_list = preparator.prepare(mol)

    fname = safe_filename(name)
    pdbqt_path = output_dir / f"{fname}.pdbqt"

    # Write PDBQT using Meeko's writer
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setup_list[0])
    if not is_ok:
        raise RuntimeError(f"Meeko PDBQT conversion failed for {name}: {error_msg}")

    pdbqt_path.write_text(pdbqt_string)
    logger.info("Ligand PDBQT written: %s", pdbqt_path)

    return pdbqt_path


def smiles_to_mol(smiles: str, name: str = "ligand") -> Chem.Mol:
    """Parse SMILES and return a 3D RDKit Mol with hydrogens."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Cannot parse SMILES: {smiles}")
    mol = Chem.AddHs(mol)
    mol.SetProp("_Name", name)

    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    cids = AllChem.EmbedMultipleConfs(mol, numConfs=1, params=params)
    if not cids:
        cids = AllChem.EmbedMultipleConfs(mol, numConfs=1, randomSeed=42)
    if cids:
        try:
            AllChem.MMFFOptimizeMolecule(mol, confId=0, maxIters=500)
        except Exception:
            pass
    return mol
