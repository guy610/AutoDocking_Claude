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
