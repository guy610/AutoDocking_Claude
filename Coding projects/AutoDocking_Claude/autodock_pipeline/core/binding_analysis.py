"""
Binding interface analysis for small-molecule optimization.

Analyses the co-crystal structure to identify:
  - Functional groups and their interaction contributions
  - Steric clashes and charge repulsion
  - Unmatched H-bond partners on the receptor
  - Solvent-exposed groups
  - Desolvation penalty hotspots
  - Exit vectors for safe modifications
  - Bridging crystallographic waters
  - Ligand strain energy
  - Pi-stacking opportunities
  - Ranked optimization targets
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Van der Waals radii (Angstroms)
# ---------------------------------------------------------------------------
VDW_RADII = {
    "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47,
    "S": 1.80, "P": 1.80, "CL": 1.75, "BR": 1.85, "I": 1.98,
}

# Charged residues
POS_CHARGED_RES = {"ARG", "LYS", "HIS", "HIP"}
NEG_CHARGED_RES = {"ASP", "GLU"}

# Aromatic residues and their ring atom names
AROMATIC_RESIDUES = {
    "PHE": {"CG", "CD1", "CD2", "CE1", "CE2", "CZ"},
    "TYR": {"CG", "CD1", "CD2", "CE1", "CE2", "CZ"},
    "TRP": {"CG", "CD1", "CD2", "NE1", "CE2", "CE3", "CZ2", "CZ3", "CH2"},
    "HIS": {"CG", "ND1", "CD2", "CE1", "NE2"},
}

# SMARTS patterns for functional group identification
FUNCTIONAL_GROUP_SMARTS = {
    "primary_amine":    "[NH2;!$([NH2]C=O)]",
    "secondary_amine":  "[NH1;!$([NH1]C=O);!$([nH1])]",
    "tertiary_amine":   "[NX3;H0;!$([NX3]C=O);!$(n)]",
    "hydroxyl":         "[OX2H1;!$([OX2H1]C=O)]",
    "thiol":            "[SH1]",
    "carboxylic_acid":  "[CX3](=O)[OX2H1,OX1-]",
    "amide":            "[NX3][CX3](=[OX1])",
    "ester":            "[CX3](=O)[OX2][C]",
    "ether":            "[OX2]([CX4])[CX4]",
    "halogen_F":        "[F]",
    "halogen_Cl":       "[Cl]",
    "halogen_Br":       "[Br]",
    "halogen_I":        "[I]",
    "nitro":            "[NX3](=O)=O",
    "sulfonamide":      "[SX4](=O)(=O)[NX3]",
    "sulfoxide":        "[SX3](=O)",
    "alkene":           "[CX3]=[CX3]",
    "alkyne":           "[CX2]#[CX2]",
    "nitrile":          "[CX2]#[NX1]",
    "ketone":           "[CX3](=O)([C])[C]",
    "aldehyde":         "[CX3H1](=O)",
    "aromatic_ring":    "c1ccccc1",
    "heteroaromatic":   "[nR1,oR1,sR1]",
    "phosphate":        "[PX4](=O)([O])([O])[O]",
    "methyl":           "[CH3;$([CH3][!H])]",
}

POLAR_ELEMENTS = {"N", "O", "S"}
HYDROPHOBIC_ELEMENTS = {"C"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AtomInfo:
    """Minimal atom info parsed from PDB."""
    serial: int
    name: str
    res_name: str
    chain: str
    res_num: int
    x: float
    y: float
    z: float
    element: str

    @property
    def is_polar(self) -> bool:
        return self.element.upper() in POLAR_ELEMENTS

    @property
    def is_hydrophobic(self) -> bool:
        return self.element.upper() in HYDROPHOBIC_ELEMENTS


@dataclass
class FunctionalGroup:
    """A functional group identified in the ligand."""
    group_type: str                    # e.g., "hydroxyl", "primary_amine"
    atom_indices: List[int]            # RDKit atom indices
    smarts: str                        # SMARTS pattern matched
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    interaction_score: float = 0.0     # sum of all interaction contributions
    n_hbonds: int = 0
    n_hydrophobic: int = 0
    n_pi_stacking: int = 0
    n_salt_bridges: int = 0
    is_optimization_target: bool = False
    rank: int = 0


@dataclass
class StericClash:
    """A steric clash between ligand and receptor atoms."""
    lig_atom_idx: int
    lig_element: str
    rec_atom_name: str
    rec_res_name: str
    rec_res_num: int
    rec_chain: str
    distance: float
    vdw_sum: float
    overlap: float     # vdw_sum - distance


@dataclass
class ChargeRepulsion:
    """Like-charged groups in close proximity."""
    lig_atom_idx: int
    lig_element: str
    rec_atom_name: str
    rec_res_name: str
    rec_res_num: int
    distance: float
    charge_type: str   # "positive-positive" or "negative-negative"


@dataclass
class UnmatchedHBond:
    """Receptor H-bond donor/acceptor without a ligand partner."""
    rec_atom_name: str
    rec_res_name: str
    rec_res_num: int
    rec_chain: str
    rec_x: float
    rec_y: float
    rec_z: float
    donor_or_acceptor: str  # "donor" or "acceptor"
    distance_to_nearest_lig_polar: float


@dataclass
class SolventExposedGroup:
    """A functional group pointing away from the binding pocket."""
    group_idx: int
    group_type: str
    n_receptor_contacts: int
    direction: str  # "outward" or "partially_exposed"


@dataclass
class DesolvationHotspot:
    """A buried polar atom without compensating H-bonds."""
    lig_atom_idx: int
    element: str
    n_nearby_hydrophobic: int
    n_compensating_hbonds: int
    burial_score: float  # higher = more buried


@dataclass
class ExitVector:
    """A direction from a ligand atom where modifications won't clash."""
    origin_atom_idx: int
    direction: Tuple[float, float, float]  # unit vector
    clearance: float  # distance to nearest receptor atom in this direction


@dataclass
class BridgingWater:
    """A crystallographic water bridging ligand and receptor."""
    water_xyz: Tuple[float, float, float]
    lig_contact_atom: int
    lig_contact_dist: float
    rec_contact_atom: str
    rec_contact_res: str
    rec_contact_dist: float


@dataclass
class PiStackOpportunity:
    """Aromatic receptor residue near non-aromatic ligand atoms."""
    rec_res_name: str
    rec_res_num: int
    rec_chain: str
    rec_ring_center: Tuple[float, float, float]
    lig_nearest_atom_idx: int
    distance: float


@dataclass
class OptimizationTarget:
    """A ranked optimization target — a functional group worth modifying."""
    group_idx: int
    group_type: str
    score: float           # higher = better target for optimization
    rationale: str         # human-readable explanation
    exit_vectors: List[ExitVector] = field(default_factory=list)


@dataclass
class BindingAnalysisResult:
    """Complete binding analysis output."""
    ligand_smiles: str
    functional_groups: List[FunctionalGroup]
    steric_clashes: List[StericClash]
    charge_repulsions: List[ChargeRepulsion]
    unmatched_hbond_partners: List[UnmatchedHBond]
    solvent_exposed_groups: List[SolventExposedGroup]
    desolvation_hotspots: List[DesolvationHotspot]
    exit_vectors: List[ExitVector]
    bridging_waters: List[BridgingWater]
    strain_energy: float
    pi_stacking_opportunities: List[PiStackOpportunity]
    optimization_targets: List[OptimizationTarget]
    # v0.9.1 additions
    cyclization_sites: List = field(default_factory=list)      # List of CyclizationSite
    prodrug_ester_sites: List[int] = field(default_factory=list)  # atom indices of carboxylate carbons
    # v0.9.2 additions
    thioether_sites: List = field(default_factory=list)        # List of ThioetherSite
    metabolic_soft_spots: List = field(default_factory=list)   # List of MetabolicSite


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_binding_analysis(
    ligand_pdb: Path,
    receptor_pdb: Path,
    ligand_smiles: str = "",
    crystal_waters: Optional[List[Tuple[float, float, float]]] = None,
) -> BindingAnalysisResult:
    """Run full binding interface analysis.

    Parameters
    ----------
    ligand_pdb : Path
        PDB file containing only the co-crystallized ligand.
    receptor_pdb : Path
        PDB file containing the receptor protein.
    ligand_smiles : str
        Canonical SMILES of the ligand (for RDKit functional group detection).
    crystal_waters : list of (x, y, z), optional
        Coordinates of bridging crystal waters.

    Returns
    -------
    BindingAnalysisResult
        Comprehensive analysis of the binding interface.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    logger.info("=== Binding Interface Analysis ===")

    # Parse receptor atoms
    rec_atoms = _parse_atoms(receptor_pdb)
    lig_atoms = _parse_atoms(ligand_pdb)
    logger.info("Receptor: %d atoms, Ligand: %d atoms", len(rec_atoms), len(lig_atoms))

    # Get RDKit mol for functional group analysis
    lig_mol = None
    if ligand_smiles:
        lig_mol = Chem.MolFromSmiles(ligand_smiles)
        if lig_mol is not None:
            lig_mol = Chem.AddHs(lig_mol)
            try:
                AllChem.EmbedMolecule(lig_mol, randomSeed=42)
            except Exception:
                pass
    if lig_mol is None:
        lig_mol = Chem.MolFromPDBFile(str(ligand_pdb), removeHs=False, sanitize=True)
    if lig_mol is None:
        lig_mol = Chem.MolFromPDBFile(str(ligand_pdb), removeHs=False, sanitize=False)

    # Step 1: Identify functional groups
    func_groups = _identify_functional_groups(lig_mol, lig_atoms)
    logger.info("Found %d functional groups", len(func_groups))

    # Step 2: Compute per-group interactions
    _compute_all_group_interactions(func_groups, lig_atoms, rec_atoms)

    # Step 3: Steric clashes
    clashes = _detect_steric_clashes(lig_atoms, rec_atoms)
    logger.info("Found %d steric clashes", len(clashes))

    # Step 4: Charge repulsion
    repulsions = _detect_charge_repulsion(lig_atoms, rec_atoms)
    logger.info("Found %d charge repulsions", len(repulsions))

    # Step 5: Unmatched H-bond partners
    unmatched = _find_unmatched_hbond_partners(lig_atoms, rec_atoms)
    logger.info("Found %d unmatched H-bond partners on receptor", len(unmatched))

    # Step 6: Solvent-exposed groups
    exposed = _identify_solvent_exposed(func_groups, lig_atoms, rec_atoms)
    logger.info("Found %d solvent-exposed groups", len(exposed))

    # Step 7: Desolvation hotspots
    desolv = _find_desolvation_hotspots(lig_atoms, rec_atoms)
    logger.info("Found %d desolvation hotspots", len(desolv))

    # Step 8: Exit vectors
    exits = _calculate_exit_vectors(func_groups, lig_atoms, rec_atoms)
    logger.info("Found %d exit vectors", len(exits))

    # Step 9: Bridging waters
    bridging = _find_bridging_waters(crystal_waters or [], lig_atoms, rec_atoms)
    logger.info("Found %d bridging waters", len(bridging))

    # Step 10: Strain energy
    strain = _calculate_strain_energy(lig_mol)
    logger.info("Ligand strain energy: %.2f kcal/mol", strain)

    # Step 11: Pi-stacking opportunities
    pi_opps = _find_pi_stacking_opportunities(lig_atoms, rec_atoms)
    logger.info("Found %d pi-stacking opportunities", len(pi_opps))

    # Step 12: Rank optimization targets
    targets = _rank_optimization_targets(
        func_groups, clashes, repulsions, exposed, desolv, exits
    )
    logger.info("Ranked %d optimization targets", len(targets))

    # Step 13: Cyclization site detection (v0.9.1)
    cyclization_sites = []
    try:
        from .analog_generation import detect_cyclization_sites
        if ligand_smiles:
            cyclization_sites = detect_cyclization_sites(ligand_smiles)
            logger.info("Found %d potential cyclization sites", len(cyclization_sites))
    except Exception as e:
        logger.debug("Cyclization detection failed: %s", e)

    # Step 14: Pro-drug ester site detection (v0.9.1)
    prodrug_sites = []
    try:
        from rdkit import Chem as _Chem
        if ligand_smiles:
            _mol = _Chem.MolFromSmiles(ligand_smiles)
            if _mol:
                acid_pat = _Chem.MolFromSmarts("[CX3](=O)[OX2H1,OX1-]")
                if acid_pat:
                    for match in _mol.GetSubstructMatches(acid_pat):
                        prodrug_sites.append(match[0])
            logger.info("Found %d pro-drug ester sites (carboxylates)", len(prodrug_sites))
    except Exception as e:
        logger.debug("Pro-drug site detection failed: %s", e)

    # Step 15: Thioether cyclization site detection (v0.9.2)
    thioether_sites = []
    try:
        from .analog_generation import detect_thioether_sites
        if ligand_smiles:
            thioether_sites = detect_thioether_sites(ligand_smiles)
            logger.info("Found %d potential thioether cyclization sites", len(thioether_sites))
    except Exception as e:
        logger.debug("Thioether site detection failed: %s", e)

    # Step 16: Metabolic soft spot identification (v0.9.2)
    metabolic_spots = []
    try:
        from .analog_generation import identify_metabolic_soft_spots
        if ligand_smiles:
            metabolic_spots = identify_metabolic_soft_spots(ligand_smiles)
            logger.info("Found %d metabolic soft spots (CYP450)", len(metabolic_spots))
    except Exception as e:
        logger.debug("Metabolic soft spot identification failed: %s", e)

    return BindingAnalysisResult(
        ligand_smiles=ligand_smiles or "",
        functional_groups=func_groups,
        steric_clashes=clashes,
        charge_repulsions=repulsions,
        unmatched_hbond_partners=unmatched,
        solvent_exposed_groups=exposed,
        desolvation_hotspots=desolv,
        exit_vectors=exits,
        bridging_waters=bridging,
        strain_energy=strain,
        pi_stacking_opportunities=pi_opps,
        optimization_targets=targets,
        cyclization_sites=cyclization_sites,
        prodrug_ester_sites=prodrug_sites,
        thioether_sites=thioether_sites,
        metabolic_soft_spots=metabolic_spots,
    )


# ---------------------------------------------------------------------------
# Step 1: Functional group identification
# ---------------------------------------------------------------------------

def _identify_functional_groups(
    mol,  # RDKit Mol
    lig_atoms: List[AtomInfo],
) -> List[FunctionalGroup]:
    """Identify functional groups using SMARTS patterns."""
    from rdkit import Chem

    groups = []
    if mol is None:
        logger.warning("No RDKit mol available for functional group detection")
        return groups

    # Remove Hs for SMARTS matching
    mol_no_h = Chem.RemoveHs(mol) if mol.GetNumAtoms() > 0 else mol

    for group_type, smarts in FUNCTIONAL_GROUP_SMARTS.items():
        try:
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:
                continue
            matches = mol_no_h.GetSubstructMatches(pattern)
            for match in matches:
                atom_indices = list(match)
                # Compute center from ligand PDB atoms if possible
                center = _group_center(atom_indices, lig_atoms)
                groups.append(FunctionalGroup(
                    group_type=group_type,
                    atom_indices=atom_indices,
                    smarts=smarts,
                    center=center,
                ))
        except Exception as e:
            logger.debug("SMARTS match failed for %s: %s", group_type, e)

    return groups


def _group_center(
    atom_indices: List[int],
    lig_atoms: List[AtomInfo],
) -> Tuple[float, float, float]:
    """Compute center of mass for a group of atom indices."""
    if not atom_indices or not lig_atoms:
        return (0.0, 0.0, 0.0)

    xs, ys, zs = [], [], []
    for idx in atom_indices:
        if idx < len(lig_atoms):
            a = lig_atoms[idx]
            xs.append(a.x)
            ys.append(a.y)
            zs.append(a.z)

    if not xs:
        return (0.0, 0.0, 0.0)
    return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))


# ---------------------------------------------------------------------------
# Step 2: Per-group interactions
# ---------------------------------------------------------------------------

def _compute_all_group_interactions(
    groups: List[FunctionalGroup],
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
) -> None:
    """Compute interaction contributions for each functional group in place."""
    for grp in groups:
        n_hb, n_hydro, n_sb = 0, 0, 0
        for aidx in grp.atom_indices:
            if aidx >= len(lig_atoms):
                continue
            la = lig_atoms[aidx]
            for ra in rec_atoms:
                d = _dist(la, ra)
                # H-bond
                if d <= 3.5 and la.is_polar and ra.is_polar:
                    n_hb += 1
                # Hydrophobic contact
                elif d <= 4.5 and la.is_hydrophobic and ra.is_hydrophobic:
                    n_hydro += 1
                # Salt bridge (simplified: opposite charge within 4A)
                if d <= 4.0 and la.is_polar and ra.is_polar:
                    if _is_salt_bridge(la, ra):
                        n_sb += 1

        grp.n_hbonds = n_hb
        grp.n_hydrophobic = n_hydro
        grp.n_salt_bridges = n_sb
        # Weighted interaction score: H-bonds most valuable
        grp.interaction_score = n_hb * 3.0 + n_hydro * 1.0 + n_sb * 4.0


def _is_salt_bridge(la: AtomInfo, ra: AtomInfo) -> bool:
    """Check if two atoms could form a salt bridge (simplified)."""
    lig_positive = la.element.upper() == "N"
    lig_negative = la.element.upper() in ("O", "S")
    rec_positive = ra.res_name in POS_CHARGED_RES and ra.element.upper() == "N"
    rec_negative = ra.res_name in NEG_CHARGED_RES and ra.element.upper() == "O"
    return (lig_positive and rec_negative) or (lig_negative and rec_positive)


# ---------------------------------------------------------------------------
# Step 3: Steric clashes
# ---------------------------------------------------------------------------

def _detect_steric_clashes(
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    vdw_scale: float = 0.75,
) -> List[StericClash]:
    """Detect atoms closer than scaled van der Waals sum."""
    clashes = []
    for i, la in enumerate(lig_atoms):
        if la.element.upper() == "H":
            continue
        r1 = VDW_RADII.get(la.element.upper(), 1.70)
        for ra in rec_atoms:
            if ra.element.upper() == "H":
                continue
            r2 = VDW_RADII.get(ra.element.upper(), 1.70)
            vdw_sum = r1 + r2
            d = _dist(la, ra)
            if d < vdw_sum * vdw_scale:
                clashes.append(StericClash(
                    lig_atom_idx=i,
                    lig_element=la.element,
                    rec_atom_name=ra.name,
                    rec_res_name=ra.res_name,
                    rec_res_num=ra.res_num,
                    rec_chain=ra.chain,
                    distance=round(d, 2),
                    vdw_sum=round(vdw_sum, 2),
                    overlap=round(vdw_sum - d, 2),
                ))
    return clashes


# ---------------------------------------------------------------------------
# Step 4: Charge repulsion
# ---------------------------------------------------------------------------

def _detect_charge_repulsion(
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    cutoff: float = 4.0,
) -> List[ChargeRepulsion]:
    """Find like-charged atom pairs within cutoff."""
    repulsions = []
    for i, la in enumerate(lig_atoms):
        lig_charge = _atom_charge_sign(la)
        if lig_charge == 0:
            continue
        for ra in rec_atoms:
            rec_charge = _atom_charge_sign(ra)
            if rec_charge == 0 or rec_charge != lig_charge:
                continue
            d = _dist(la, ra)
            if d <= cutoff:
                charge_type = "positive-positive" if lig_charge > 0 else "negative-negative"
                repulsions.append(ChargeRepulsion(
                    lig_atom_idx=i,
                    lig_element=la.element,
                    rec_atom_name=ra.name,
                    rec_res_name=ra.res_name,
                    rec_res_num=ra.res_num,
                    distance=round(d, 2),
                    charge_type=charge_type,
                ))
    return repulsions


def _atom_charge_sign(atom: AtomInfo) -> int:
    """Estimate charge sign from residue context. 0 = neutral."""
    if atom.res_name in POS_CHARGED_RES:
        if atom.element.upper() == "N" and atom.name in ("NH1", "NH2", "NZ", "NE", "ND1", "NE2"):
            return 1
    if atom.res_name in NEG_CHARGED_RES:
        if atom.element.upper() == "O" and atom.name in ("OD1", "OD2", "OE1", "OE2"):
            return -1
    return 0


# ---------------------------------------------------------------------------
# Step 5: Unmatched H-bond partners
# ---------------------------------------------------------------------------

def _find_unmatched_hbond_partners(
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    cutoff: float = 4.0,
    hbond_cutoff: float = 3.5,
) -> List[UnmatchedHBond]:
    """Find receptor polar atoms near the ligand that lack an H-bond partner."""
    unmatched = []
    lig_polar = [a for a in lig_atoms if a.is_polar]

    for ra in rec_atoms:
        if not ra.is_polar:
            continue
        # Check if this receptor atom is near the ligand at all
        min_dist_to_lig = min((_dist(ra, la) for la in lig_atoms), default=999.0)
        if min_dist_to_lig > cutoff:
            continue

        # Check if it has an H-bond partner on the ligand
        min_polar_dist = min(
            (_dist(ra, lp) for lp in lig_polar), default=999.0
        )
        has_hbond = min_polar_dist <= hbond_cutoff

        if not has_hbond:
            donor_or_acc = "donor" if ra.element.upper() == "N" else "acceptor"
            unmatched.append(UnmatchedHBond(
                rec_atom_name=ra.name,
                rec_res_name=ra.res_name,
                rec_res_num=ra.res_num,
                rec_chain=ra.chain,
                rec_x=ra.x, rec_y=ra.y, rec_z=ra.z,
                donor_or_acceptor=donor_or_acc,
                distance_to_nearest_lig_polar=round(min_polar_dist, 2),
            ))

    return unmatched


# ---------------------------------------------------------------------------
# Step 6: Solvent-exposed groups
# ---------------------------------------------------------------------------

def _identify_solvent_exposed(
    groups: List[FunctionalGroup],
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    contact_cutoff: float = 4.5,
) -> List[SolventExposedGroup]:
    """Identify functional groups with few receptor contacts."""
    exposed = []
    for i, grp in enumerate(groups):
        n_contacts = 0
        for aidx in grp.atom_indices:
            if aidx >= len(lig_atoms):
                continue
            la = lig_atoms[aidx]
            for ra in rec_atoms:
                if _dist(la, ra) <= contact_cutoff:
                    n_contacts += 1

        if n_contacts <= 2:
            direction = "outward" if n_contacts == 0 else "partially_exposed"
            grp.is_optimization_target = True
            exposed.append(SolventExposedGroup(
                group_idx=i,
                group_type=grp.group_type,
                n_receptor_contacts=n_contacts,
                direction=direction,
            ))

    return exposed


# ---------------------------------------------------------------------------
# Step 7: Desolvation hotspots
# ---------------------------------------------------------------------------

def _find_desolvation_hotspots(
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    burial_cutoff: float = 5.0,
    hbond_cutoff: float = 3.5,
) -> List[DesolvationHotspot]:
    """Find buried polar ligand atoms without compensating H-bonds."""
    hotspots = []
    for i, la in enumerate(lig_atoms):
        if not la.is_polar:
            continue

        # Count nearby hydrophobic receptor atoms (burial proxy)
        n_hydrophobic = sum(
            1 for ra in rec_atoms
            if ra.is_hydrophobic and _dist(la, ra) <= burial_cutoff
        )

        # Count compensating H-bonds
        n_hbonds = sum(
            1 for ra in rec_atoms
            if ra.is_polar and _dist(la, ra) <= hbond_cutoff
        )

        # Buried polar without H-bonds = desolvation penalty
        if n_hydrophobic >= 3 and n_hbonds == 0:
            hotspots.append(DesolvationHotspot(
                lig_atom_idx=i,
                element=la.element,
                n_nearby_hydrophobic=n_hydrophobic,
                n_compensating_hbonds=n_hbonds,
                burial_score=float(n_hydrophobic),
            ))

    return hotspots


# ---------------------------------------------------------------------------
# Step 8: Exit vectors
# ---------------------------------------------------------------------------

# 26 directions: 3x3x3 cube minus center
_DIRECTIONS = [
    (dx, dy, dz)
    for dx in (-1, 0, 1)
    for dy in (-1, 0, 1)
    for dz in (-1, 0, 1)
    if not (dx == 0 and dy == 0 and dz == 0)
]


def _calculate_exit_vectors(
    groups: List[FunctionalGroup],
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    clearance_threshold: float = 2.5,
    ray_length: float = 8.0,
) -> List[ExitVector]:
    """Calculate exit vectors for each functional group atom.

    Casts 26 rays and checks for receptor atom clearance.
    """
    exits = []
    for grp in groups:
        for aidx in grp.atom_indices:
            if aidx >= len(lig_atoms):
                continue
            origin = lig_atoms[aidx]

            for dx, dy, dz in _DIRECTIONS:
                norm = math.sqrt(dx * dx + dy * dy + dz * dz)
                ux, uy, uz = dx / norm, dy / norm, dz / norm

                # Check clearance along this ray
                min_clearance = ray_length
                for ra in rec_atoms:
                    # Project receptor atom onto ray
                    vx = ra.x - origin.x
                    vy = ra.y - origin.y
                    vz = ra.z - origin.z
                    proj = vx * ux + vy * uy + vz * uz
                    if proj < 0 or proj > ray_length:
                        continue
                    # Perpendicular distance to ray
                    px = origin.x + proj * ux
                    py = origin.y + proj * uy
                    pz = origin.z + proj * uz
                    perp_dist = math.sqrt(
                        (ra.x - px) ** 2 + (ra.y - py) ** 2 + (ra.z - pz) ** 2
                    )
                    if perp_dist < min_clearance:
                        min_clearance = perp_dist

                if min_clearance >= clearance_threshold:
                    exits.append(ExitVector(
                        origin_atom_idx=aidx,
                        direction=(round(ux, 3), round(uy, 3), round(uz, 3)),
                        clearance=round(min_clearance, 2),
                    ))

    return exits


# ---------------------------------------------------------------------------
# Step 9: Bridging waters
# ---------------------------------------------------------------------------

def _find_bridging_waters(
    water_coords: List[Tuple[float, float, float]],
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    cutoff: float = 3.5,
) -> List[BridgingWater]:
    """Find crystal waters bridging ligand and receptor."""
    bridging = []
    for wx, wy, wz in water_coords:
        # Find closest ligand polar atom
        best_lig_idx, best_lig_dist = -1, 999.0
        for i, la in enumerate(lig_atoms):
            if la.is_polar:
                d = _dist3(wx, wy, wz, la.x, la.y, la.z)
                if d < best_lig_dist:
                    best_lig_idx, best_lig_dist = i, d

        # Find closest receptor polar atom
        best_rec, best_rec_dist = None, 999.0
        for ra in rec_atoms:
            if ra.is_polar:
                d = _dist3(wx, wy, wz, ra.x, ra.y, ra.z)
                if d < best_rec_dist:
                    best_rec, best_rec_dist = ra, d

        if best_lig_dist <= cutoff and best_rec_dist <= cutoff and best_rec is not None:
            bridging.append(BridgingWater(
                water_xyz=(wx, wy, wz),
                lig_contact_atom=best_lig_idx,
                lig_contact_dist=round(best_lig_dist, 2),
                rec_contact_atom=best_rec.name,
                rec_contact_res=f"{best_rec.res_name}{best_rec.res_num}",
                rec_contact_dist=round(best_rec_dist, 2),
            ))

    return bridging


# ---------------------------------------------------------------------------
# Step 10: Strain energy
# ---------------------------------------------------------------------------

def _calculate_strain_energy(mol) -> float:
    """Calculate ligand strain energy (bound vs relaxed conformation).

    Returns energy difference in kcal/mol. Returns 0 if calculation fails.
    """
    if mol is None:
        return 0.0

    try:
        from rdkit.Chem import AllChem
        import copy

        if mol.GetNumConformers() == 0:
            return 0.0

        # Energy of bound conformation
        props = AllChem.MMFFGetMoleculeProperties(mol)
        if props is None:
            return 0.0
        ff_bound = AllChem.MMFFGetMoleculeForceField(mol, props, confId=0)
        if ff_bound is None:
            return 0.0
        bound_energy = ff_bound.CalcEnergy()

        # Minimize a copy
        mol_copy = copy.deepcopy(mol)
        result = AllChem.MMFFOptimizeMolecule(mol_copy, maxIters=500)
        if result == -1:
            return 0.0
        props2 = AllChem.MMFFGetMoleculeProperties(mol_copy)
        if props2 is None:
            return 0.0
        ff_relaxed = AllChem.MMFFGetMoleculeForceField(mol_copy, props2, confId=0)
        if ff_relaxed is None:
            return 0.0
        relaxed_energy = ff_relaxed.CalcEnergy()

        strain = bound_energy - relaxed_energy
        return round(max(0.0, strain), 2)

    except Exception as e:
        logger.debug("Strain energy calculation failed: %s", e)
        return 0.0


# ---------------------------------------------------------------------------
# Step 11: Pi-stacking opportunities
# ---------------------------------------------------------------------------

def _find_pi_stacking_opportunities(
    lig_atoms: List[AtomInfo],
    rec_atoms: List[AtomInfo],
    distance_cutoff: float = 6.0,
) -> List[PiStackOpportunity]:
    """Find aromatic receptor residues near non-aromatic ligand atoms."""
    opportunities = []

    # Group receptor aromatic ring atoms by residue
    aromatic_rings: Dict[Tuple[str, int, str], List[AtomInfo]] = {}
    for ra in rec_atoms:
        if ra.res_name in AROMATIC_RESIDUES:
            ring_atoms = AROMATIC_RESIDUES[ra.res_name]
            if ra.name in ring_atoms:
                key = (ra.res_name, ra.res_num, ra.chain)
                aromatic_rings.setdefault(key, []).append(ra)

    # For each aromatic ring, find nearest ligand atom
    for (res_name, res_num, chain), ring_atoms in aromatic_rings.items():
        if len(ring_atoms) < 3:  # need enough atoms to define a ring
            continue

        # Ring center
        cx = sum(a.x for a in ring_atoms) / len(ring_atoms)
        cy = sum(a.y for a in ring_atoms) / len(ring_atoms)
        cz = sum(a.z for a in ring_atoms) / len(ring_atoms)

        # Find nearest non-hydrogen ligand atom
        best_idx, best_dist = -1, 999.0
        for i, la in enumerate(lig_atoms):
            if la.element.upper() == "H":
                continue
            d = _dist3(cx, cy, cz, la.x, la.y, la.z)
            if d < best_dist:
                best_idx, best_dist = i, d

        if best_dist <= distance_cutoff and best_idx >= 0:
            opportunities.append(PiStackOpportunity(
                rec_res_name=res_name,
                rec_res_num=res_num,
                rec_chain=chain,
                rec_ring_center=(round(cx, 2), round(cy, 2), round(cz, 2)),
                lig_nearest_atom_idx=best_idx,
                distance=round(best_dist, 2),
            ))

    return opportunities


# ---------------------------------------------------------------------------
# Step 12: Rank optimization targets
# ---------------------------------------------------------------------------

def _rank_optimization_targets(
    groups: List[FunctionalGroup],
    clashes: List[StericClash],
    repulsions: List[ChargeRepulsion],
    exposed: List[SolventExposedGroup],
    hotspots: List[DesolvationHotspot],
    exit_vectors: List[ExitVector],
) -> List[OptimizationTarget]:
    """Rank functional groups by optimization potential.

    Higher score = better candidate for modification.

    Scoring factors:
    - Low interaction score (weak binding contribution) → higher priority
    - Steric clashes involving the group → higher priority
    - Charge repulsion → higher priority
    - Solvent exposure → higher priority (easy to modify)
    - Desolvation penalty → higher priority
    - Available exit vectors → higher priority (room to grow)
    """
    # Index clash/repulsion/exposure by ligand atom index for fast lookup
    clash_atoms = set(c.lig_atom_idx for c in clashes)
    repulsion_atoms = set(r.lig_atom_idx for r in repulsions)
    exposed_groups = set(e.group_idx for e in exposed)
    hotspot_atoms = set(h.lig_atom_idx for h in hotspots)
    exits_by_atom: Dict[int, List[ExitVector]] = {}
    for ev in exit_vectors:
        exits_by_atom.setdefault(ev.origin_atom_idx, []).append(ev)

    targets = []
    for i, grp in enumerate(groups):
        score = 0.0
        reasons = []

        # Low interaction = opportunity to improve
        if grp.interaction_score < 2.0:
            score += 3.0
            reasons.append("weak interactions (score=%.1f)" % grp.interaction_score)
        elif grp.interaction_score < 5.0:
            score += 1.0
            reasons.append("moderate interactions")

        # Steric clashes
        n_clashes = sum(1 for aidx in grp.atom_indices if aidx in clash_atoms)
        if n_clashes > 0:
            score += n_clashes * 2.0
            reasons.append("%d steric clash(es)" % n_clashes)

        # Charge repulsion
        n_repulsions = sum(1 for aidx in grp.atom_indices if aidx in repulsion_atoms)
        if n_repulsions > 0:
            score += n_repulsions * 2.5
            reasons.append("%d charge repulsion(s)" % n_repulsions)

        # Solvent exposed
        if i in exposed_groups:
            score += 2.0
            reasons.append("solvent-exposed")

        # Desolvation hotspot
        n_desolv = sum(1 for aidx in grp.atom_indices if aidx in hotspot_atoms)
        if n_desolv > 0:
            score += n_desolv * 1.5
            reasons.append("desolvation penalty")

        # Exit vectors available
        group_exits = []
        for aidx in grp.atom_indices:
            group_exits.extend(exits_by_atom.get(aidx, []))
        if group_exits:
            score += min(len(group_exits) * 0.5, 3.0)
            reasons.append("%d exit vector(s)" % len(group_exits))

        if score > 0:
            targets.append(OptimizationTarget(
                group_idx=i,
                group_type=grp.group_type,
                score=round(score, 2),
                rationale="; ".join(reasons),
                exit_vectors=group_exits[:5],  # top 5 exit vectors
            ))

    # Sort by score descending
    targets.sort(key=lambda t: t.score, reverse=True)

    # Assign ranks
    for rank, t in enumerate(targets, 1):
        groups[t.group_idx].rank = rank

    return targets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_atoms(pdb_path: Path) -> List[AtomInfo]:
    """Parse ATOM/HETATM records from a PDB file."""
    atoms = []
    raw = pdb_path.read_bytes().decode("utf-8", errors="replace")
    for line in raw.splitlines():
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
            atoms.append(AtomInfo(
                serial=serial, name=name, res_name=res_name,
                chain=chain, res_num=res_num,
                x=x, y=y, z=z, element=element,
            ))
        except (ValueError, IndexError):
            continue
    return atoms


def _infer_element(atom_name: str) -> str:
    """Infer element from PDB atom name."""
    name = atom_name.strip()
    if not name:
        return "C"
    if name[0].isdigit():
        return "H"
    if len(name) >= 2 and name[:2] in ("CL", "BR", "FE", "ZN", "MG"):
        return name[:2]
    return name[0]


def _dist(a: AtomInfo, b: AtomInfo) -> float:
    """Euclidean distance between two atoms."""
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _dist3(x1, y1, z1, x2, y2, z2) -> float:
    """Euclidean distance between two 3D points."""
    dx = x1 - x2
    dy = y1 - y2
    dz = z1 - z2
    return math.sqrt(dx * dx + dy * dy + dz * dz)
