"""
I/O helpers: file reading/writing, directory management, PDBQT utilities.
"""

import re
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def read_pdbqt_energies(pdbqt_path: Path) -> list[float]:
    """Read binding energies from a multi-model Vina output PDBQT.

    Vina writes lines like:
        REMARK VINA RESULT:    -7.3      0.000      0.000
    """
    energies = []
    raw = pdbqt_path.read_bytes().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        if line.startswith("REMARK VINA RESULT"):
            parts = line.split()
            # parts: REMARK VINA RESULT: <energy> <rmsd_lb> <rmsd_ub>
            energies.append(float(parts[3]))
    return energies


def write_vina_config(config_path: Path,
                      receptor_pdbqt: Path,
                      ligand_pdbqt: Path,
                      out_pdbqt: Path,
                      center: tuple[float, float, float],
                      size: tuple[float, float, float],
                      exhaustiveness: int = 8,
                      num_modes: int = 9,
                      energy_range: int = 3) -> Path:
    """Write a Vina configuration file and return its path."""
    NL = chr(10)
    lines = [
        f"receptor = {receptor_pdbqt}",
        f"ligand = {ligand_pdbqt}",
        f"out = {out_pdbqt}",
        "",
        f"center_x = {center[0]:.3f}",
        f"center_y = {center[1]:.3f}",
        f"center_z = {center[2]:.3f}",
        "",
        f"size_x = {size[0]:.1f}",
        f"size_y = {size[1]:.1f}",
        f"size_z = {size[2]:.1f}",
        "",
        f"exhaustiveness = {exhaustiveness}",
        f"num_modes = {num_modes}",
        f"energy_range = {energy_range}",
    ]
    config_path.write_text(NL.join(lines) + NL)
    return config_path


def extract_best_pose_pdb(vina_output_pdbqt: Path, output_pdb: Path) -> Path:
    """Extract the first (best) pose from Vina output PDBQT and write as PDB.

    Strips PDBQT-specific columns (partial charges, AD atom types) and
    writes standard PDB ATOM/HETATM records.
    """
    NL = chr(10)
    lines_out = []
    in_first_model = False
    found_model = False

    raw = vina_output_pdbqt.read_bytes().decode("utf-8", errors="replace")
    for line in raw.splitlines(True):
        if line.startswith("MODEL") and not found_model:
            in_first_model = True
            found_model = True
            continue
        if line.startswith("ENDMDL") and in_first_model:
            break
        if in_first_model or not found_model:
            if line.startswith(("ATOM", "HETATM")):
                # PDBQT has extra columns after col 66; truncate to PDB
                lines_out.append(line[:66].rstrip() + NL)

    # If no MODEL records (single pose), we already captured all ATOM lines
    lines_out.append("END" + NL)
    output_pdb.write_text("".join(lines_out))
    return output_pdb


def generate_complex_pdb(receptor_pdb, ligand_pose_pdb,
                         output_path, ligand_name="best_ligand"):
    """Combine receptor PDB and best ligand pose into a single complex PDB.

    The receptor atoms are written first, then the ligand as a separate chain
    (HETATM records). This file can be opened directly in PyMOL, ChimeraX,
    or any molecular viewer to visualize the docked complex.
    """
    NL = chr(10)
    lines = []
    lines.append("REMARK  Stephen Docking -- Receptor-Ligand Complex" + NL)
    lines.append("REMARK  Ligand: " + str(ligand_name) + NL)

    # Write receptor atoms
    raw_rec = Path(receptor_pdb).read_bytes().decode("utf-8", errors="replace")
    for line in raw_rec.splitlines(True):
        if line.startswith(("ATOM", "HETATM", "TER")):
            lines.append(line)

    lines.append("TER" + NL)

    # Write ligand atoms as HETATM
    raw_lig = Path(ligand_pose_pdb).read_bytes().decode("utf-8", errors="replace")
    for line in raw_lig.splitlines(True):
        if line.startswith("ATOM"):
            lines.append("HETATM" + line[6:])
        elif line.startswith("HETATM"):
            lines.append(line)

    lines.append("END" + NL)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines))
    return output_path
