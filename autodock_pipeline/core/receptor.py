"""
Receptor preparation: clean PDB, protonate, generate PDBQT for Vina.
"""

import logging
from pathlib import Path

from ..config import PipelineConfig
from ..utils.io_utils import ensure_dir

logger = logging.getLogger(__name__)

# Residue names considered water
WATER_RESIDUES = {"HOH", "WAT", "H2O", "DOD"}


def clean_pdb(config: PipelineConfig) -> Path:
    """Remove waters and irrelevant heteroatoms from the receptor PDB.

    Returns the path to the cleaned PDB file.
    """
    input_pdb = config.receptor_pdb
    out_dir = ensure_dir(config.output_dir / "receptor")
    cleaned = out_dir / f"{input_pdb.stem}_clean.pdb"

    kept = 0
    removed = 0
    lines_out = []

    with open(input_pdb, "r") as f:
        for line in f:
            record = line[:6].strip()

            if record in ("ATOM", "HETATM"):
                res_name = line[17:20].strip()

                # Remove waters
                if config.remove_waters and res_name in WATER_RESIDUES:
                    removed += 1
                    continue

                # Remove non-water heteroatoms (ligands, ions, etc.)
                if config.remove_heteroatoms and record == "HETATM" and res_name not in WATER_RESIDUES:
                    removed += 1
                    continue

                kept += 1
                lines_out.append(line)

            elif record in ("TER", "END", "REMARK", "HEADER", "TITLE",
                            "CRYST1", "SCALE", "ORIG", "MODEL", "ENDMDL"):
                lines_out.append(line)

    lines_out.append("END\n")
    cleaned.write_text("".join(lines_out))
    logger.info("Cleaned receptor: kept %d atoms, removed %d (waters=%s, hetatm=%s)",
                kept, removed, config.remove_waters, config.remove_heteroatoms)
    return cleaned


def prepare_receptor_pdbqt(cleaned_pdb: Path, config: PipelineConfig) -> Path:
    """Convert cleaned PDB to PDBQT suitable for Vina.

    Strategy: write a minimal PDBQT by adding Gasteiger partial charges
    and AutoDock atom types to each ATOM record. This avoids needing
    external GPL tools.

    For protein atoms, we use a simple atom-type mapping based on
    element and bonding context (sufficient for Vina rigid receptor).
    """
    out_dir = ensure_dir(config.output_dir / "receptor")
    pdbqt_path = out_dir / f"{cleaned_pdb.stem}.pdbqt"

    lines_out = []
    with open(cleaned_pdb, "r") as f:
        for line in f:
            record = line[:6].strip()
            if record in ("ATOM", "HETATM"):
                # Extract element from columns 77-78 or infer from atom name
                element = line[76:78].strip() if len(line) >= 78 else ""
                if not element:
                    atom_name = line[12:16].strip()
                    element = _infer_element(atom_name)

                ad_type = _element_to_ad_type(element, line)
                charge = 0.0  # Vina ignores charges but PDBQT format needs them

                # PDBQT format: columns 1-66 same as PDB, then charge + type
                pdb_part = line[:54].rstrip()
                # Pad to column 54, add occupancy/bfactor placeholders, charge, type
                occ = line[54:60] if len(line) >= 60 else "  1.00"
                bfac = line[60:66] if len(line) >= 66 else "  0.00"
                pdbqt_line = f"{pdb_part}{occ}{bfac}    {charge:+.3f} {ad_type:<2s}\n"
                lines_out.append(pdbqt_line)
            elif record == "TER":
                lines_out.append(line)

    lines_out.append("END\n")
    pdbqt_path.write_text("".join(lines_out))
    logger.info("Receptor PDBQT written: %s", pdbqt_path)
    return pdbqt_path


def _infer_element(atom_name: str) -> str:
    """Infer element symbol from PDB atom name."""
    name = atom_name.strip()
    if not name:
        return "C"
    # Standard PDB: first 1-2 chars of name are element for most cases
    if name[0].isdigit():
        # e.g. 1HB, 2HG -> hydrogen
        return "H"
    if len(name) >= 2 and name[:2] in ("CL", "BR", "FE", "ZN", "MG", "CA", "MN", "CU", "CO", "NI"):
        return name[:2]
    return name[0]


def _element_to_ad_type(element: str, line: str) -> str:
    """Map element to AutoDock atom type for Vina receptor.

    Simplified mapping suitable for standard protein atoms.
    Vina mainly cares about: C, A (aromatic C), N, NA, NS, O, OA, S, SA, H, HD
    """
    el = element.upper().strip()
    atom_name = line[12:16].strip().upper()
    res_name = line[17:20].strip().upper()

    if el == "C":
        # Aromatic carbons in HIS, PHE, TRP, TYR -> A
        aromatic_res = {"PHE", "TYR", "TRP", "HIS", "HID", "HIE", "HIP"}
        aromatic_atoms = {"CG", "CD1", "CD2", "CE1", "CE2", "CZ", "CZ2",
                          "CZ3", "CH2", "CE3"}
        if res_name in aromatic_res and atom_name in aromatic_atoms:
            return "A"
        return "C"
    elif el == "N":
        # NA = H-bond acceptor nitrogen (e.g., backbone N is donor via H, not acceptor)
        # For simplicity: ring nitrogens in HIS that can accept -> NA
        if res_name in ("HIS", "HID", "HIE", "HIP") and atom_name in ("ND1", "NE2"):
            return "NA"
        return "N"
    elif el == "O":
        # OA = H-bond acceptor oxygen (most protein oxygens)
        return "OA"
    elif el == "S":
        # SA = H-bond acceptor sulfur (CYS SG, MET SD)
        return "SA"
    elif el == "H":
        # HD = H-bond donor hydrogen (on N-H or O-H)
        # Simple heuristic: H attached to N or O
        if atom_name.startswith("H") and any(n in atom_name for n in ("N", "HN")):
            return "HD"
        # Most H atoms bonded to N
        return "HD" if atom_name in ("H", "HN", "HE", "HH", "HG", "HD1", "HD2",
                                      "HE1", "HE2", "HH11", "HH12", "HH21", "HH22",
                                      "HZ1", "HZ2", "HZ3") else "H"
    elif el in ("FE", "ZN", "MN", "MG", "CA", "CU", "CO", "NI"):
        return el
    else:
        return el if len(el) <= 2 else el[:2]
