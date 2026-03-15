"""
Docking engine: call AutoDock Vina and parse results.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..config import DockingParams
from ..utils.io_utils import ensure_dir, read_pdbqt_energies, write_vina_config, extract_best_pose_pdb, safe_filename

logger = logging.getLogger(__name__)


@dataclass
class DockingResult:
    """Stores the result of a single Vina docking run."""
    ligand_name: str
    smiles: str
    best_energy: float          # kcal/mol (most negative = best)
    output_pdbqt: Path          # best-pose PDBQT
    all_energies: List[float] = field(default_factory=list)
    log_path: Optional[Path] = None
    best_pose_pdb: Optional[Path] = None
    origin: str = "initial"     # initial / sidechain / backbone / minimize / user / user-rational / branch


def run_vina(receptor_pdbqt: Path,
             ligand_pdbqt: Path,
             ligand_name: str,
             smiles: str,
             docking_params: DockingParams,
             output_dir: Path,
             vina_executable: str = "vina",
             origin: str = "initial") -> DockingResult:
    """Run AutoDock Vina via subprocess and return parsed results."""
    ensure_dir(output_dir)
    fname = safe_filename(ligand_name)

    out_pdbqt = output_dir / f"{fname}_docked.pdbqt"
    log_path = output_dir / f"{fname}_vina.log"
    config_path = output_dir / f"{fname}_vina.conf"

    # Write Vina config
    write_vina_config(
        config_path=config_path,
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=ligand_pdbqt,
        out_pdbqt=out_pdbqt,
        center=(docking_params.center_x, docking_params.center_y, docking_params.center_z),
        size=(docking_params.size_x, docking_params.size_y, docking_params.size_z),
        exhaustiveness=docking_params.exhaustiveness,
        num_modes=docking_params.num_modes,
        energy_range=docking_params.energy_range,
    )

    # Run Vina
    cmd = [vina_executable, "--config", str(config_path)]
    logger.info("Running Vina: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
        )
        log_path.write_text(result.stdout + "\n" + result.stderr)

        if result.returncode != 0:
            logger.error("Vina failed (exit %d) for %s:\n%s",
                         result.returncode, ligand_name, result.stderr)
            raise RuntimeError(f"Vina failed for {ligand_name}: {result.stderr[:500]}")

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Vina timed out for {ligand_name}")

    # Parse results
    energies = read_pdbqt_energies(out_pdbqt)
    if not energies:
        # Try parsing from stdout
        energies = _parse_energies_from_log(log_path)

    if not energies:
        raise RuntimeError(f"No docking results found for {ligand_name}")

    best_energy = min(energies)

    # Extract best pose as PDB
    best_pose_pdb = output_dir / f"{fname}_best_pose.pdb"
    extract_best_pose_pdb(out_pdbqt, best_pose_pdb)

    logger.info("Docking complete: %s -> %.2f kcal/mol (%d modes)",
                ligand_name, best_energy, len(energies))

    return DockingResult(
        ligand_name=ligand_name,
        smiles=smiles,
        best_energy=best_energy,
        output_pdbqt=out_pdbqt,
        all_energies=energies,
        log_path=log_path,
        best_pose_pdb=best_pose_pdb,
        origin=origin,
    )


def _parse_energies_from_log(log_path: Path) -> List[float]:
    """Parse energies from Vina stdout log as fallback.

    Vina prints a table like:
       mode |   affinity | dist from best mode
            | (kcal/mol) | rmsd l.b.| rmsd u.b.
       -----+------------+----------+----------
          1       -7.3          0.0        0.0
          2       -6.9          1.2        2.1
    """
    energies = []
    in_table = False
    raw = log_path.read_bytes().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        if "-----+------" in line:
            in_table = True
            continue
        if in_table:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    energies.append(float(parts[1]))
                except (ValueError, IndexError):
                    break
            else:
                break
    return energies
