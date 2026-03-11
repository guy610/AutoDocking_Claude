"""
Interaction metric computation: H-bonds, polar contacts,
backbone vs side-chain classification.

Uses pure coordinate-based distance/angle criteria (no GPL tools):
  - H-bond: donor-acceptor distance <= 3.5 A, with polar atoms (N, O, S)
  - Polar contact: distance <= 4.0 A between polar atoms
  - Classifies by backbone vs side-chain on both ligand and receptor sides.
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

POLAR_ELEMENTS = {"N", "O", "S"}
BACKBONE_NAMES = {"N", "CA", "C", "O", "H", "HN", "HA", "OXT"}


@dataclass
class AtomRecord:
    """Minimal atom record parsed from PDB/PDBQT."""
    serial: int
    name: str
    res_name: str
    chain: str
    res_num: int
    x: float
    y: float
    z: float
    element: str = ""

    @property
    def is_polar(self) -> bool:
        return self.element.upper().strip() in POLAR_ELEMENTS


@dataclass
class ContactInfo:
    """A single ligand-receptor contact."""
    lig_atom: str
    lig_res: str
    lig_atom_class: str   # "backbone" or "sidechain"
    rec_atom: str
    rec_res: str
    rec_res_num: int
    rec_chain: str
    rec_atom_class: str   # "backbone" or "sidechain"
    distance: float
    contact_type: str     # "hbond" or "polar"


@dataclass
class InteractionMetrics:
    """Summary of ligand-protein interactions for a docked pose."""
    n_hbonds: int = 0
    n_polar_contacts: int = 0
    n_backbone_interactions: int = 0
    n_sidechain_interactions: int = 0
    n_backbone_mutations: int = 0
    interacting_residues: List[Tuple[str, int]] = field(default_factory=list)
    per_residue_position: Dict[int, dict] = field(default_factory=dict)
    details: List[dict] = field(default_factory=list)


def parse_atoms_from_pdb(pdb_path: Path) -> List[AtomRecord]:
    """Parse ATOM/HETATM records from a PDB file."""
    atoms = []
    with open(pdb_path, "r") as f:
        for line in f:
            record = line[:6].strip()
            if record not in ("ATOM", "HETATM"):
                continue
            try:
                serial = int(line[6:11].strip())
                name = line[12:16].strip()
                res_name = line[17:20].strip()
                chain = line[21].strip() if len(line) > 21 else ""
                res_num = int(line[22:26].strip())
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
                element = line[76:78].strip() if len(line) >= 78 else ""
                if not element:
                    element = _infer_element(name)
                atoms.append(AtomRecord(
                    serial=serial, name=name, res_name=res_name,
                    chain=chain, res_num=res_num, x=x, y=y, z=z,
                    element=element,
                ))
            except (ValueError, IndexError):
                continue
    return atoms


def _infer_element(atom_name: str) -> str:
    """Infer element from atom name."""
    name = atom_name.strip()
    if not name:
        return "C"
    if name[0].isdigit():
        return "H"
    return name[0]


def _distance(a: AtomRecord, b: AtomRecord) -> float:
    """Euclidean distance between two atoms."""
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def classify_ligand_atom(atom_name: str) -> str:
    """Classify a ligand atom as 'backbone' or 'sidechain'."""
    return "backbone" if atom_name.strip() in BACKBONE_NAMES else "sidechain"


def classify_receptor_atom(atom_name: str) -> str:
    """Classify a receptor atom as 'backbone' or 'sidechain'."""
    return "backbone" if atom_name.strip() in BACKBONE_NAMES else "sidechain"


def compute_interactions(ligand_pdb: Path,
                         receptor_pdb: Path,
                         hbond_cutoff: float = 3.5,
                         polar_cutoff: float = 4.0) -> InteractionMetrics:
    """Compute H-bond and polar-contact metrics between ligand and receptor.

    Uses distance criteria:
      - H-bond: donor-acceptor distance <= hbond_cutoff (3.5 A default)
        where both atoms are polar (N, O, S)
      - Polar contact: distance <= polar_cutoff (4.0 A) between polar atoms
        that don't qualify as H-bonds

    Classifies interactions by ligand backbone vs side-chain atoms and
    tracks per-residue interaction counts.
    """
    lig_atoms = parse_atoms_from_pdb(ligand_pdb)
    rec_atoms = parse_atoms_from_pdb(receptor_pdb)

    if not lig_atoms:
        logger.warning("No atoms found in ligand PDB: %s", ligand_pdb)
        return InteractionMetrics()
    if not rec_atoms:
        logger.warning("No atoms found in receptor PDB: %s", receptor_pdb)
        return InteractionMetrics()

    contacts = []
    residue_interactions = {}

    for la in lig_atoms:
        if not la.is_polar:
            continue
        for ra in rec_atoms:
            if not ra.is_polar:
                continue
            dist = _distance(la, ra)

            contact_type = None
            if dist <= hbond_cutoff:
                contact_type = "hbond"
            elif dist <= polar_cutoff:
                contact_type = "polar"
            else:
                continue

            lig_class = classify_ligand_atom(la.name)
            rec_class = classify_receptor_atom(ra.name)

            contact = ContactInfo(
                lig_atom=la.name, lig_res=la.res_name,
                lig_atom_class=lig_class,
                rec_atom=ra.name, rec_res=ra.res_name,
                rec_res_num=ra.res_num, rec_chain=ra.chain,
                rec_atom_class=rec_class,
                distance=dist, contact_type=contact_type,
            )
            contacts.append(contact)

            key = (ra.chain, ra.res_num)
            if key not in residue_interactions:
                residue_interactions[key] = {
                    "res_name": ra.res_name, "chain": ra.chain,
                    "res_num": ra.res_num,
                    "n_hbonds": 0, "n_polar": 0,
                    "n_backbone": 0, "n_sidechain": 0,
                }
            entry = residue_interactions[key]
            if contact_type == "hbond":
                entry["n_hbonds"] += 1
            else:
                entry["n_polar"] += 1
            if rec_class == "backbone":
                entry["n_backbone"] += 1
            else:
                entry["n_sidechain"] += 1

    n_hbonds = sum(1 for c in contacts if c.contact_type == "hbond")
    n_polar = sum(1 for c in contacts if c.contact_type == "polar")
    n_bb = sum(1 for c in contacts if c.rec_atom_class == "backbone")
    n_sc = sum(1 for c in contacts if c.rec_atom_class == "sidechain")

    interacting_residues = sorted(
        [(v["res_name"], v["res_num"]) for v in residue_interactions.values()]
    )

    details = [
        {
            "lig_atom": c.lig_atom, "lig_res": c.lig_res,
            "lig_class": c.lig_atom_class,
            "rec_atom": c.rec_atom, "rec_res": c.rec_res,
            "rec_num": c.rec_res_num, "rec_chain": c.rec_chain,
            "rec_class": c.rec_atom_class,
            "distance": round(c.distance, 2),
            "type": c.contact_type,
        }
        for c in contacts
    ]

    # Build per-residue position map keyed by ligand residue index
    per_residue = {}
    lig_residue_nums = sorted(set(la.res_num for la in lig_atoms))
    for i, lrn in enumerate(lig_residue_nums):
        per_residue[i] = {
            "res_num": lrn,
            "n_bb_interactions": 0,
            "n_sc_interactions": 0,
            "n_total": 0,
        }

    for c in contacts:
        for la in lig_atoms:
            if la.name == c.lig_atom and la.res_name == c.lig_res:
                for i, lrn in enumerate(lig_residue_nums):
                    if la.res_num == lrn:
                        if c.rec_atom_class == "backbone":
                            per_residue[i]["n_bb_interactions"] += 1
                        else:
                            per_residue[i]["n_sc_interactions"] += 1
                        per_residue[i]["n_total"] += 1
                        break
                break

    metrics = InteractionMetrics(
        n_hbonds=n_hbonds,
        n_polar_contacts=n_polar,
        n_backbone_interactions=n_bb,
        n_sidechain_interactions=n_sc,
        interacting_residues=interacting_residues,
        per_residue_position=per_residue,
        details=details,
    )

    logger.info(
        "Interactions: %d H-bonds, %d polar contacts, %d backbone, %d sidechain",
        n_hbonds, n_polar, n_bb, n_sc,
    )
    return metrics
