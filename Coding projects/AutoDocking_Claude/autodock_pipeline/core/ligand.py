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

    Uses approximate pKa values for standard amino acid functional groups.
    At pH < pKa, the group is protonated; at pH > pKa, it is deprotonated.

    Parameters
    ----------
    smiles : str
        Input SMILES string
    pH : float
        Target pH value (default 7.3 = physiological)

    Returns
    -------
    str
        SMILES with adjusted protonation state
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("Cannot parse SMILES for protonation adjustment: %s", smiles)
        return smiles

    # Work on a copy
    adjusted_smi = smiles
    adjusted_mol = Chem.MolFromSmiles(adjusted_smi)
    if adjusted_mol is None:
        return smiles

    # 1. Carboxylic acids (ASP, GLU, C-terminus): pKa ~ 3.1-4.1
    #    At pH 5.0: partially protonated for ASP/GLU
    #    At pH 7.3: fully deprotonated
    carboxyl_pka = 4.0
    acid_neutral = Chem.MolFromSmarts("C(=O)[OH]")
    acid_charged = Chem.MolFromSmarts("C(=O)[O-]")

    if pH > carboxyl_pka:
        # Deprotonate: -COOH -> -COO- (remove H from OH, add negative charge)
        if acid_neutral and adjusted_mol.HasSubstructMatch(acid_neutral):
            try:
                repl_from = Chem.MolFromSmiles("C(=O)O")
                repl_to = Chem.MolFromSmiles("C(=O)[O-]")
                if repl_from and repl_to:
                    products = AllChem.ReplaceSubstructs(adjusted_mol, repl_from, repl_to)
                    if products:
                        new_smi = Chem.MolToSmiles(products[0])
                        test = Chem.MolFromSmiles(new_smi)
                        if test is not None:
                            adjusted_smi = new_smi
                            adjusted_mol = test
            except Exception as e:
                logger.debug("Carboxyl deprotonation failed: %s", e)
    else:
        # Protonate: ensure -COOH form
        if acid_charged and adjusted_mol.HasSubstructMatch(acid_charged):
            try:
                repl_from = Chem.MolFromSmiles("C(=O)[O-]")
                repl_to = Chem.MolFromSmiles("C(=O)O")
                if repl_from and repl_to:
                    products = AllChem.ReplaceSubstructs(adjusted_mol, repl_from, repl_to)
                    if products:
                        new_smi = Chem.MolToSmiles(products[0])
                        test = Chem.MolFromSmiles(new_smi)
                        if test is not None:
                            adjusted_smi = new_smi
                            adjusted_mol = test
            except Exception as e:
                logger.debug("Carboxyl protonation failed: %s", e)

    # 2. Histidine imidazole: pKa ~ 6.0
    #    At pH 5.0: protonated (imidazolium, +1 charge)
    #    At pH 7.3: neutral
    his_pka = 6.0
    if pH < his_pka:
        # Protonate HIS: add H to the unprotonated N in imidazole
        his_neutral = Chem.MolFromSmarts("c1c[nH]cn1")
        if his_neutral and adjusted_mol.HasSubstructMatch(his_neutral):
            adjusted_smi = adjusted_smi.replace("[nH]cn", "[nH]c[nH+]")
            test = Chem.MolFromSmiles(adjusted_smi)
            if test is not None:
                adjusted_mol = test
            else:
                # Revert if invalid
                adjusted_smi = Chem.MolToSmiles(adjusted_mol)

    # 3. Lysine amine: pKa ~ 10.5 (protonated at both pH 5 and 7.3)
    lys_pka = 10.5
    if pH < lys_pka:
        # LYS should be protonated at both pH 5 and 7.3: -NH3+
        lys_neutral = Chem.MolFromSmarts("CCCCN")
        if lys_neutral and adjusted_mol.HasSubstructMatch(lys_neutral):
            # Check if already charged
            lys_charged = Chem.MolFromSmarts("CCCC[NH3+]")
            if lys_charged and not adjusted_mol.HasSubstructMatch(lys_charged):
                try:
                    repl_from = Chem.MolFromSmiles("CCCCN")
                    repl_to = Chem.MolFromSmiles("CCCC[NH3+]")
                    if repl_from and repl_to:
                        products = AllChem.ReplaceSubstructs(adjusted_mol, repl_from, repl_to)
                        if products:
                            new_smi = Chem.MolToSmiles(products[0])
                            test = Chem.MolFromSmiles(new_smi)
                            if test is not None:
                                adjusted_smi = new_smi
                                adjusted_mol = test
                except Exception as e:
                    logger.debug("LYS protonation failed: %s", e)

    # 4. Arginine guanidinium: pKa ~ 12.5 (always protonated)
    # Usually already represented correctly in SMILES

    logger.info("Protonation adjusted for pH %.1f: %s", pH, adjusted_smi)
    return adjusted_smi


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
