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
