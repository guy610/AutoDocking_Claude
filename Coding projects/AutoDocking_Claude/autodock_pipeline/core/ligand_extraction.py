"""
Ligand extraction from co-crystal PDB structures.

Parses HETATM records to identify and extract the co-crystallized small-molecule
ligand, produces a cleaned receptor PDB, and computes an auto-box centered on
the ligand position.
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Common crystallographic additives / buffers to ignore
BUFFER_RESIDUES = {
    "HOH", "WAT", "H2O", "DOD",          # waters
    "SO4", "PO4", "NO3", "CL", "NA", "K", "MG", "ZN", "CA", "MN",
    "FE", "CU", "CO", "NI", "CD",        # ions
    "GOL", "EDO", "PEG", "PGE", "DMS",   # cryo-protectants / solvents
    "ACT", "FMT", "ACE", "TRS", "BME",   # buffers
    "MPD", "IPA", "EPE", "MES", "HED",
    "IMD", "CIT", "TAR", "SUC",
}


@dataclass
class ExtractionResult:
    """Result of ligand extraction from a crystal PDB."""
    ligand_pdb: Path              # PDB file containing only the ligand
    receptor_pdb: Path            # PDB file with protein only (no ligand, no waters)
    ligand_resname: str           # 3-letter residue name of the ligand
    ligand_chain: str             # chain ID
    ligand_resnum: int            # residue number
    n_ligand_atoms: int           # number of heavy atoms in ligand
    crystal_waters: List[Tuple[float, float, float]] = field(default_factory=list)
    ligand_smiles: str = ""       # canonical SMILES (if RDKit conversion succeeds)


def extract_ligand_from_pdb(
    pdb_path: Path,
    output_dir: Path,
    ligand_resname: str = "",
    ligand_chain: str = "",
    ligand_resnum: int = 0,
) -> ExtractionResult:
    """Extract the co-crystallized ligand from a PDB file.

    If ligand_resname is provided, use it to identify the ligand.
    Otherwise, auto-detect by finding the largest non-buffer HETATM group.

    Returns an ExtractionResult with paths to separated ligand and receptor PDBs.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = pdb_path.read_bytes().decode("utf-8", errors="replace")
    lines = raw.splitlines(True)

    # --- Parse all records ---
    atom_lines = []       # protein ATOM records
    hetatm_groups: Dict[Tuple[str, str, int], List[str]] = {}  # (chain, resname, resnum) -> lines
    water_lines = []
    other_lines = []      # REMARK, HEADER, CRYST1, etc.

    for line in lines:
        record = line[:6].strip()
        if record == "ATOM":
            atom_lines.append(line)
        elif record == "HETATM":
            res_name = line[17:20].strip()
            chain = line[21].strip() if len(line) > 21 else ""
            try:
                res_num = int(line[22:26].strip())
            except (ValueError, IndexError):
                res_num = 0

            if res_name in {"HOH", "WAT", "H2O", "DOD"}:
                water_lines.append(line)
            else:
                key = (chain, res_name, res_num)
                hetatm_groups.setdefault(key, []).append(line)
        elif record in ("TER", "END", "REMARK", "HEADER", "TITLE",
                        "CRYST1", "SCALE", "ORIG", "MODEL", "ENDMDL"):
            other_lines.append(line)

    # --- Identify the ligand ---
    # Filter out buffer/ion residues
    ligand_candidates = {
        k: v for k, v in hetatm_groups.items()
        if k[1] not in BUFFER_RESIDUES
    }

    if not ligand_candidates:
        raise ValueError(
            f"No ligand HETATM groups found in {pdb_path.name} after filtering "
            f"buffers/ions. Available HETATM residues: "
            f"{sorted(set(k[1] for k in hetatm_groups))}"
        )

    selected_key = None

    if ligand_resname:
        # User specified the residue name
        matches = [k for k in ligand_candidates if k[1] == ligand_resname.upper()]
        if ligand_chain:
            matches = [k for k in matches if k[0] == ligand_chain]
        if ligand_resnum > 0:
            matches = [k for k in matches if k[2] == ligand_resnum]

        if not matches:
            available = sorted(set(k[1] for k in ligand_candidates))
            raise ValueError(
                f"Ligand '{ligand_resname}' not found. "
                f"Available non-buffer HETATM residues: {available}"
            )
        # Pick the one with most atoms
        selected_key = max(matches, key=lambda k: len(ligand_candidates[k]))
    else:
        # Auto-detect: largest HETATM group by atom count
        selected_key = max(ligand_candidates, key=lambda k: len(ligand_candidates[k]))
        logger.info("Auto-detected ligand: %s chain=%s resnum=%d (%d atoms)",
                     selected_key[1], selected_key[0], selected_key[2],
                     len(ligand_candidates[selected_key]))

    lig_chain, lig_resname, lig_resnum = selected_key
    lig_lines = ligand_candidates[selected_key]

    # --- Extract crystal waters bridging ligand and receptor ---
    lig_coords = _parse_coords(lig_lines)
    rec_coords = _parse_coords(atom_lines)
    water_coords = _parse_water_coords(water_lines)

    bridging_waters = []
    for wx, wy, wz in water_coords:
        near_lig = any(
            _dist3(wx, wy, wz, lx, ly, lz) <= 4.0
            for lx, ly, lz in lig_coords
        )
        near_rec = any(
            _dist3(wx, wy, wz, rx, ry, rz) <= 4.0
            for rx, ry, rz in rec_coords
        )
        if near_lig and near_rec:
            bridging_waters.append((wx, wy, wz))

    logger.info("Found %d bridging crystal waters", len(bridging_waters))

    # --- Write ligand PDB ---
    lig_pdb_path = output_dir / f"{pdb_path.stem}_ligand_{lig_resname}.pdb"
    with open(lig_pdb_path, "w", encoding="utf-8") as f:
        for ln in lig_lines:
            f.write(ln if ln.endswith("\n") else ln + "\n")
        f.write("END\n")

    # --- Write receptor PDB (protein atoms only) ---
    rec_pdb_path = output_dir / f"{pdb_path.stem}_receptor.pdb"
    with open(rec_pdb_path, "w", encoding="utf-8") as f:
        for ln in atom_lines:
            f.write(ln if ln.endswith("\n") else ln + "\n")
        f.write("END\n")

    # --- Try to get SMILES ---
    # Priority: 1) PDB Chemical Component Dictionary (CCD) lookup (authoritative)
    #           2) RDKit PDB-to-SMILES conversion (fallback, may miss bond orders)
    smiles = ""
    ccd_smiles = lookup_ccd_smiles(lig_resname)
    if ccd_smiles:
        smiles = ccd_smiles
        logger.info("Ligand SMILES (CCD lookup): %s", smiles)
    else:
        try:
            smiles = ligand_pdb_to_smiles(lig_pdb_path)
            logger.info("Ligand SMILES (RDKit PDB): %s", smiles)
            logger.warning("CCD lookup failed for '%s' — using RDKit PDB extraction. "
                          "Bond orders and aromaticity may be incorrect. "
                          "Consider using ligand_smiles_override.", lig_resname)
        except Exception as e:
            logger.warning("Could not convert ligand to SMILES: %s", e)

    n_heavy = sum(1 for ln in lig_lines
                  if ln[:6].strip() == "HETATM"
                  and _get_element(ln).upper() not in ("H", ""))

    result = ExtractionResult(
        ligand_pdb=lig_pdb_path,
        receptor_pdb=rec_pdb_path,
        ligand_resname=lig_resname,
        ligand_chain=lig_chain,
        ligand_resnum=lig_resnum,
        n_ligand_atoms=n_heavy,
        crystal_waters=bridging_waters,
        ligand_smiles=smiles,
    )

    logger.info("Extraction complete: ligand=%s (%d heavy atoms), receptor=%d atoms, "
                "%d bridging waters",
                lig_resname, n_heavy, len(atom_lines), len(bridging_waters))

    return result


def compute_autobox(
    ligand_pdb: Path,
    padding: float = 4.0,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute a docking box centered on the ligand with padding.

    Returns (center_xyz, size_xyz) tuples.
    """
    coords = _parse_coords_from_pdb(ligand_pdb)
    if not coords:
        raise ValueError(f"No atoms found in ligand PDB: {ligand_pdb}")

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    center = (
        (min_x + max_x) / 2.0,
        (min_y + max_y) / 2.0,
        (min_z + max_z) / 2.0,
    )

    size = (
        max(20.0, (max_x - min_x) + 2 * padding),
        max(20.0, (max_y - min_y) + 2 * padding),
        max(20.0, (max_z - min_z) + 2 * padding),
    )

    logger.info("Auto-box: center=(%.1f, %.1f, %.1f), size=(%.1f, %.1f, %.1f)",
                center[0], center[1], center[2], size[0], size[1], size[2])

    return center, size


def lookup_ccd_smiles(resname: str) -> str:
    """Look up canonical SMILES from the PDB Chemical Component Dictionary.

    Queries the RCSB PDB REST API for the given 3-letter residue code.
    Returns the canonical SMILES string, or empty string on failure.

    This is the authoritative source for ligand SMILES — unlike RDKit's
    PDB-to-SMILES conversion, it preserves correct bond orders, aromaticity,
    and stereochemistry.
    """
    import urllib.request
    import json

    if not resname or len(resname) > 3:
        return ""

    resname = resname.upper().strip()

    # RCSB PDB Chemical Component API
    url = f"https://data.rcsb.org/rest/v1/core/chemcomp/{resname}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Extract SMILES — try canonical first, then isomeric
        descriptors = data.get("rcsb_chem_comp_descriptor", {})
        smiles = ""

        # Look in descriptor list
        desc_list = descriptors.get("comp_descriptor", [])
        if isinstance(desc_list, list):
            for d in desc_list:
                if d.get("type") == "SMILES_CANONICAL":
                    smiles = d.get("descriptor", "")
                    break
            if not smiles:
                for d in desc_list:
                    if "SMILES" in d.get("type", ""):
                        smiles = d.get("descriptor", "")
                        break

        # Fallback: top-level SMILES fields
        if not smiles:
            smiles = (descriptors.get("smiles_canonical", "")
                      or descriptors.get("smiles", ""))

        # Validate with RDKit
        if smiles:
            try:
                from rdkit import Chem
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:
                    canonical = Chem.MolToSmiles(mol)
                    logger.info("CCD lookup for '%s': %s (canonical: %s)",
                                resname, smiles, canonical)
                    return canonical
                else:
                    logger.warning("CCD SMILES for '%s' failed RDKit validation: %s",
                                   resname, smiles)
                    return ""
            except Exception:
                return smiles  # return raw CCD SMILES if RDKit unavailable

        logger.debug("No SMILES found in CCD for '%s'", resname)
        return ""

    except Exception as e:
        logger.debug("CCD lookup failed for '%s': %s", resname, e)
        return ""


def ligand_pdb_to_smiles(ligand_pdb: Path) -> str:
    """Convert a ligand PDB file to canonical SMILES using RDKit.

    Raises ValueError if conversion fails.
    """
    from rdkit import Chem

    mol = Chem.MolFromPDBFile(str(ligand_pdb), removeHs=True, sanitize=True)
    if mol is None:
        # Try without sanitization then sanitize manually
        mol = Chem.MolFromPDBFile(str(ligand_pdb), removeHs=True, sanitize=False)
        if mol is not None:
            try:
                Chem.SanitizeMol(mol)
            except Exception:
                raise ValueError(f"RDKit could not sanitize ligand from {ligand_pdb}")
        else:
            raise ValueError(f"RDKit could not parse ligand PDB: {ligand_pdb}")

    smiles = Chem.MolToSmiles(mol)
    if not smiles:
        raise ValueError("RDKit produced empty SMILES")

    return smiles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_coords(pdb_lines: List[str]) -> List[Tuple[float, float, float]]:
    """Extract (x, y, z) from ATOM/HETATM lines."""
    coords = []
    for line in pdb_lines:
        record = line[:6].strip()
        if record in ("ATOM", "HETATM"):
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
                coords.append((x, y, z))
            except (ValueError, IndexError):
                continue
    return coords


def _parse_coords_from_pdb(pdb_path: Path) -> List[Tuple[float, float, float]]:
    """Parse coordinates from a PDB file."""
    raw = pdb_path.read_bytes().decode("utf-8", errors="replace")
    return _parse_coords(raw.splitlines())


def _parse_water_coords(water_lines: List[str]) -> List[Tuple[float, float, float]]:
    """Parse oxygen coordinates from HOH HETATM lines."""
    coords = []
    for line in water_lines:
        # Only take the oxygen atom (element O or atom name starting with O)
        element = _get_element(line).upper()
        atom_name = line[12:16].strip().upper()
        if element == "O" or atom_name.startswith("O"):
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
                coords.append((x, y, z))
            except (ValueError, IndexError):
                continue
    return coords


def _get_element(line: str) -> str:
    """Get element from PDB line columns 77-78 or infer from atom name."""
    if len(line) >= 78:
        el = line[76:78].strip()
        if el:
            return el
    atom_name = line[12:16].strip()
    if not atom_name:
        return "C"
    if atom_name[0].isdigit():
        return "H"
    return atom_name[0]


def _dist3(x1, y1, z1, x2, y2, z2) -> float:
    """Euclidean distance between two 3D points."""
    dx = x1 - x2
    dy = y1 - y2
    dz = z1 - z2
    return math.sqrt(dx * dx + dy * dy + dz * dz)
