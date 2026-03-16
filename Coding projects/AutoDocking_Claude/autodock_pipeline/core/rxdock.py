"""
RxDock orthogonal docking: de novo docking independent of Vina poses.

Uses RxDock (rbdock) to dock candidates from scratch, providing an
orthogonal score for consensus ranking. The cavity is derived from
the Vina docking box coordinates.
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rdkit import Chem
from rdkit.Chem import AllChem, rdmolfiles

from ..utils.io_utils import ensure_dir, safe_filename
from .gnina import _build_cmd, _wsl_path

logger = logging.getLogger(__name__)


@dataclass
class RxDockResult:
    """Stores RxDock docking output for a single ligand."""
    inter_score: float     # Intermolecular energy score
    total_score: float     # Total score (inter + intra)


def smiles_to_sdf(smiles: str, name: str, output_dir: Path) -> Path:
    """Convert SMILES to 3D SDF file for RxDock input.

    Returns path to the SDF file.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("RDKit cannot parse SMILES: {}".format(smiles))

    mol = Chem.AddHs(mol)
    mol.SetProp("_Name", name)

    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=1, params=params)
    if len(conf_ids) == 0:
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=1, randomSeed=42)
        if len(conf_ids) == 0:
            raise RuntimeError("Could not generate 3D coordinates for: {}".format(smiles))

    try:
        AllChem.MMFFOptimizeMolecule(mol, confId=0, maxIters=500)
    except Exception:
        try:
            AllChem.UFFOptimizeMolecule(mol, confId=0, maxIters=500)
        except Exception:
            pass

    fname = safe_filename(name)
    sdf_path = output_dir / "{}.sdf".format(fname)
    writer = rdmolfiles.SDWriter(str(sdf_path))
    writer.write(mol, confId=0)
    writer.close()

    return sdf_path


def prepare_rxdock_cavity(
    receptor_pdb: Path,
    center: tuple,
    size: tuple,
    output_dir: Path,
    rxdock_executable: str = "rbdock",
) -> Optional[Path]:
    """Generate RxDock cavity definition from Vina box coordinates.

    Creates the .prm parameter file and runs rbcavity to generate
    the active site grid file (.as).

    Args:
        receptor_pdb: Path to clean receptor PDB.
        center: (x, y, z) center of the docking box.
        size: (sx, sy, sz) size of the docking box in Angstroms.
        output_dir: Directory for output files.
        rxdock_executable: Path to rbdock (used to derive rbcavity path).

    Returns:
        Path to the .prm file, or None on failure.
    """
    ensure_dir(output_dir)

    # Derive rbcavity path from rbdock path
    # Handle WSL prefix: if rbdock is "wsl rbdock", rbcavity is "wsl rbcavity"
    # Also handle wrapper variants: "wsl rbdock-wrapper" -> "wsl rbcavity-wrapper"
    if rxdock_executable.lower().startswith("wsl "):
        wsl_cmd = rxdock_executable[4:].strip()
        rbcavity = "wsl " + wsl_cmd.replace("rbdock", "rbcavity")
    else:
        rxdock_dir = Path(rxdock_executable).parent
        rbcavity = str(rxdock_dir / "rbcavity")
        if not Path(rbcavity).exists() and not Path(rbcavity + ".exe").exists():
            # Try just "rbcavity" on PATH
            rbcavity = "rbcavity"

    prm_path = output_dir / "rxdock_cavity.prm"
    mol2_path = output_dir / "receptor.mol2"

    # RxDock uses a two-sphere site mapping approach
    # The cavity is defined by a reference point and radius
    radius = max(size[0], size[1], size[2]) / 2.0

    # Write the parameter file
    prm_content = """RBT_PARAMETER_FILE_V1.00
TITLE receptor cavity

RECEPTOR_FILE {receptor}
RECEPTOR_FLEX 3.0

##################################################################
### CAVITY DEFINITION: derived from Vina docking box
##################################################################
SECTION MAPPER
    SITE_MAPPER RbtSphereSiteMapper
    CENTER ({cx:.3f}, {cy:.3f}, {cz:.3f})
    RADIUS {radius:.1f}
    SMALL_SPHERE 1.0
    MIN_VOLUME 100
    MAX_CAVITIES 1
    VOL_INCR 0.0
    GRIDSTEP 0.5
END_SECTION

SECTION CAVITY
    SCORING_FUNCTION RbtCavityGridSF
    WEIGHT 1.0
END_SECTION
""".format(
        receptor=str(receptor_pdb),
        cx=center[0], cy=center[1], cz=center[2],
        radius=radius,
    )

    prm_path.write_text(prm_content)
    logger.info("RxDock parameter file written: %s", prm_path)

    # Run rbcavity to generate the grid (use absolute path for cross-dir calls)
    cmd = _build_cmd(rbcavity, ["-was", "-d", "-r", str(prm_path.resolve())])
    logger.info("Running rbcavity: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(output_dir),
        )

        if result.returncode != 0:
            logger.error("rbcavity failed (exit %d):\n%s",
                         result.returncode, result.stderr[:500])
            return None

        logger.info("RxDock cavity prepared successfully")
        return prm_path

    except FileNotFoundError:
        logger.error("rbcavity executable not found. Tried: %s", rbcavity)
        return None
    except subprocess.TimeoutExpired:
        logger.error("rbcavity timed out")
        return None
    except Exception as e:
        logger.error("rbcavity error: %s", e)
        return None


def run_rxdock(
    prm_path: Path,
    ligand_sdf: Path,
    rxdock_executable: str,
    output_dir: Path,
    ligand_name: str = "",
    n_runs: int = 50,
) -> Optional[RxDockResult]:
    """Dock a ligand from scratch using RxDock.

    Args:
        prm_path: Path to the RxDock .prm parameter file (with cavity).
        ligand_sdf: Path to the input ligand SDF file.
        rxdock_executable: Path to rbdock binary.
        output_dir: Directory for output files.
        ligand_name: Name for logging.
        n_runs: Number of docking runs (default 50).

    Returns:
        RxDockResult with intermolecular and total scores, or None on failure.
    """
    if not rxdock_executable:
        return None

    ensure_dir(output_dir)
    fname = safe_filename(ligand_name or ligand_sdf.stem)
    output_prefix = str(output_dir / fname)

    cmd = _build_cmd(rxdock_executable, [
        "-r", str(Path(prm_path).resolve()),
        "-i", str(Path(ligand_sdf).resolve()),
        "-o", str(Path(output_prefix).resolve()),
        "-p", "dock.prm",
        "-n", str(n_runs),
    ])

    logger.info("RxDock docking: %s", ligand_name)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(output_dir),
        )

        if result.returncode != 0:
            logger.error("RxDock failed (exit %d) for %s:\n%s",
                         result.returncode, ligand_name, result.stderr[:500])
            return None

        # Parse output SDF for scores
        # RxDock writes output as {prefix}_out.sd
        out_sd = Path(output_prefix + "_out.sd")
        if not out_sd.exists():
            # Try alternative naming
            out_sd = Path(output_prefix + ".sd")
        if not out_sd.exists():
            logger.error("RxDock output not found for %s", ligand_name)
            return None

        return _parse_rxdock_output(out_sd, ligand_name)

    except FileNotFoundError:
        logger.error("RxDock executable not found: %s", rxdock_executable)
        return None
    except subprocess.TimeoutExpired:
        logger.error("RxDock timed out for %s", ligand_name)
        return None
    except Exception as e:
        logger.error("RxDock error for %s: %s", ligand_name, e)
        return None


def _parse_rxdock_output(sd_path: Path, ligand_name: str) -> Optional[RxDockResult]:
    """Parse RxDock output SDF to extract scores.

    RxDock writes scores as SD data fields:
      > <SCORE.INTER>    intermolecular energy
      > <SCORE>          total score
      > <SCORE.INTRA>    intramolecular energy

    Returns the best (lowest SCORE.INTER) result.
    """
    try:
        raw = sd_path.read_text(errors="replace")
    except Exception as e:
        logger.error("Cannot read RxDock output %s: %s", sd_path, e)
        return None

    best_inter = None
    best_total = None

    # Split into molecules (separated by $$$$)
    molecules = raw.split("$$$$")

    for mol_block in molecules:
        if not mol_block.strip():
            continue

        inter = None
        total = None

        # Parse SD fields
        for match in re.finditer(r'>\s*<([^>]+)>\s*\n\s*([\d.eE+-]+)', mol_block):
            field_name = match.group(1).strip()
            try:
                value = float(match.group(2))
            except ValueError:
                continue

            if field_name == "SCORE.INTER":
                inter = value
            elif field_name == "SCORE":
                total = value

        if inter is not None:
            if best_inter is None or inter < best_inter:
                best_inter = inter
                best_total = total if total is not None else inter

    if best_inter is not None:
        logger.info("RxDock %s: inter=%.2f, total=%.2f",
                    ligand_name, best_inter, best_total)
        return RxDockResult(inter_score=best_inter, total_score=best_total)
    else:
        logger.warning("RxDock: no scores parsed from %s for %s", sd_path, ligand_name)
        return None
