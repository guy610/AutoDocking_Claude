"""
Pocket identification: calculate docking box center from specified residues.

Given a list of residue identifiers (e.g., "A:TYR:45", "A:GLU:120", or just "45", "120"),
parse the receptor PDB to find those residues and compute the geometric center
of their CA (alpha-carbon) atoms. This center becomes the docking box center.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_residue_spec(spec: str) -> Tuple[Optional[str], Optional[str], int]:
    """Parse a residue specification string.

    Accepted formats:
        "45"          -> (None, None, 45)      # residue number only
        "A:45"        -> ("A", None, 45)        # chain:resnum
        "A:TYR:45"    -> ("A", "TYR", 45)       # chain:resname:resnum
        "TYR45"       -> (None, "TYR", 45)       # resname+resnum (no separator)

    Returns:
        (chain_id, residue_name, residue_number)
    """
    spec = spec.strip()

    # Format: chain:resname:resnum
    if spec.count(":") == 2:
        parts = spec.split(":")
        return (parts[0].strip(), parts[1].strip().upper(), int(parts[2].strip()))

    # Format: chain:resnum
    if spec.count(":") == 1:
        parts = spec.split(":")
        chain = parts[0].strip()
        try:
            resnum = int(parts[1].strip())
            return (chain, None, resnum)
        except ValueError:
            # Maybe it's resname:resnum
            return (None, parts[0].strip().upper(), int(parts[1].strip()))

    # Format: just a number
    try:
        return (None, None, int(spec))
    except ValueError:
        pass

    # Format: TYR45, GLU120 etc.
    import re
    m = re.match(r"([A-Za-z]+)(\d+)$", spec)
    if m:
        return (None, m.group(1).upper(), int(m.group(2)))

    raise ValueError(f"Cannot parse residue specification: '{spec}'")


def find_pocket_center(pdb_path: Path,
                       residue_specs: List[str],
                       padding: float = 4.0) -> Tuple[Tuple[float, float, float],
                                                        Tuple[float, float, float]]:
    """Calculate docking box center and suggested size from specified residues.

    Reads the PDB file, finds CA atoms for each specified residue, computes
    the geometric center as the box center, and estimates box dimensions
    from the spread of the CA atoms plus padding on each side.

    Args:
        pdb_path: Path to the receptor PDB file.
        residue_specs: List of residue specifications (e.g., ["A:45", "A:120"]).
        padding: Extra space (Angstroms) added to each side of the bounding box.

    Returns:
        (center, size) where center = (cx, cy, cz) and size = (sx, sy, sz).
    """
    targets = [parse_residue_spec(s) for s in residue_specs]

    # Collect coordinates of CA atoms matching the target residues
    matched_coords = []
    matched_residues = set()

    with open(pdb_path, "r") as f:
        for line in f:
            record = line[:6].strip()
            if record not in ("ATOM", "HETATM"):
                continue

            atom_name = line[12:16].strip()

            # Use CA atoms for center calculation; fall back to any atom if no CA
            # We collect CA first, then fill in with all-atom if needed
            chain_id = line[21].strip() if len(line) > 21 else ""
            res_name = line[17:20].strip().upper()
            try:
                res_num = int(line[22:26].strip())
            except ValueError:
                continue

            for t_chain, t_resname, t_resnum in targets:
                if t_resnum != res_num:
                    continue
                if t_chain is not None and t_chain != chain_id:
                    continue
                if t_resname is not None and t_resname != res_name:
                    continue

                # Match found
                if atom_name == "CA":
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    matched_coords.append((x, y, z))
                    key = (chain_id, res_name, res_num)
                    matched_residues.add(key)
                break

    if not matched_coords:
        raise ValueError(
            f"No matching residues found in {pdb_path} for specifications: "
            + ", ".join(residue_specs)
        )

    # Report which residues were found
    for chain, rname, rnum in sorted(matched_residues):
        chain_str = f"chain {chain}:" if chain else ""
        logger.info("Pocket residue found: %s%s %d", chain_str, rname, rnum)

    not_found = []
    for spec, (t_chain, t_resname, t_resnum) in zip(residue_specs, targets):
        found = False
        for chain, rname, rnum in matched_residues:
            if rnum == t_resnum:
                if t_chain is None or t_chain == chain:
                    if t_resname is None or t_resname == rname:
                        found = True
                        break
        if not found:
            not_found.append(spec)

    if not_found:
        logger.warning("These residue specs were NOT found in the PDB: %s", ", ".join(not_found))
        msg = ", ".join(not_found)
        print("  [WARNING] Residues not found in PDB: " + msg)

    # Compute geometric center
    n = len(matched_coords)
    cx = sum(c[0] for c in matched_coords) / n
    cy = sum(c[1] for c in matched_coords) / n
    cz = sum(c[2] for c in matched_coords) / n

    # Compute bounding box + padding for suggested size
    min_x = min(c[0] for c in matched_coords)
    max_x = max(c[0] for c in matched_coords)
    min_y = min(c[1] for c in matched_coords)
    max_y = max(c[1] for c in matched_coords)
    min_z = min(c[2] for c in matched_coords)
    max_z = max(c[2] for c in matched_coords)

    # Box size = range + 2*padding, with a minimum of 20 Angstroms
    sx = max(20.0, (max_x - min_x) + 2 * padding)
    sy = max(20.0, (max_y - min_y) + 2 * padding)
    sz = max(20.0, (max_z - min_z) + 2 * padding)

    center = (round(cx, 3), round(cy, 3), round(cz, 3))
    size = (round(sx, 1), round(sy, 1), round(sz, 1))

    logger.info("Pocket center: (%.3f, %.3f, %.3f)", *center)
    logger.info("Suggested box size: (%.1f, %.1f, %.1f) Angstroms", *size)
    logger.info("Based on %d CA atoms from %d residues", n, len(matched_residues))

    return center, size
