"""
Analog generation for small-molecule optimization (v0.9.3).

Given a ligand and binding analysis results, enumerates modifications:
  - Bioisostere replacements (COOH->tetrazole, NH->NCH3, etc.)
  - Functional group extensions (add methyl, hydroxyl, ring)
  - Group removal (replace non-contributing groups with H)
  - Pro-drug ester generation for carboxylates
  - Permeability-focused modifications (N-methylation, fluorination, oxetane)
  - Cyclization site detection (amine + carboxylate proximity)
  - Thioether cyclization detection (thiol + alkyl halide/methyl proximity)
  - Metabolic soft spot blocking (CYP450 oxidation-prone sites)
  - Scaffold hopping (ring transformations)
  - Matched molecular pair (MMP) tracking
  - Stereoisomer enumeration (rational + full)
  - Torsion strain pre-filtering
  - Ligand efficiency metrics (LE, LLE, LELP)
  - Property-biased filtering (logP, MW, PSA, HBD, HBA, rotatable bonds)
  - Combinatorial expansion of passing single-site modifications
"""

import itertools
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Property target window presets
# ---------------------------------------------------------------------------

PROPERTY_PRESETS = {
    "cosmetic": {
        "logp_min": 1.0, "logp_max": 3.0,
        "mw_max": 350.0, "psa_max": 70.0,
        "hbd_max": 2, "hba_max": 5,
        "rotatable_max": 5,
    },
    "drug_like": {
        "logp_min": 1.0, "logp_max": 5.0,
        "mw_max": 500.0, "psa_max": 140.0,
        "hbd_max": 5, "hba_max": 10,
        "rotatable_max": 10,
    },
}


# ---------------------------------------------------------------------------
# Bioisostere replacement library
# ---------------------------------------------------------------------------

# Each entry: (query_SMARTS, replacement_SMILES, description)
BIOISOSTERE_TABLE = [
    # Carboxylic acid replacements
    ("[CX3](=O)[OH]",    "c1nn[nH]n1",   "COOH -> tetrazole"),
    ("[CX3](=O)[OH]",    "C(=O)NS(=O)=O", "COOH -> acyl sulfonamide"),
    ("[CX3](=O)[OH]",    "P(=O)(O)O",     "COOH -> phosphonate"),

    # Amide replacements
    ("[NX3H1][CX3](=O)", "[NH]S(=O)=O",   "amide -> sulfonamide"),
    ("[CX3](=O)[NX3H1]", "C(=O)N(C)",          "amide -> N-methyl amide (reduce HBD)"),

    # Amine modifications
    ("[NH2]",             "[NH]C",          "NH2 -> NHCH3"),
    ("[NH2]",             "N(C)C",          "NH2 -> N(CH3)2"),

    # Hydroxyl replacements
    ("[OH]",              "F",              "OH -> F (metabolic stability)"),
    ("[OH]",              "[NH2]",          "OH -> NH2"),
    ("[OH]",              "OC",             "OH -> OCH3"),

    # Halogen swaps
    ("[F]",               "[Cl]",           "F -> Cl"),
    ("[Cl]",              "[F]",            "Cl -> F"),
    ("[Cl]",              "C(F)(F)F",       "Cl -> CF3"),
    ("[Br]",              "[Cl]",           "Br -> Cl"),

    # Aromatic ring replacements
    ("c1ccccc1",          "c1ccncc1",       "phenyl -> pyridyl"),
    ("c1ccccc1",          "c1ccsc1",        "phenyl -> thienyl"),
    ("c1ccccc1",          "c1ccc(F)cc1",    "phenyl -> 4-fluorophenyl"),

    # Ether/thioether
    ("[OX2]([C])[C]",     "CSC",             "ether -> thioether"),
    ("[SX2]([C])[C]",     "COC",             "thioether -> ether"),

    # Ester -> amide (metabolic stability)
    ("[CX3](=O)[OX2][C]", "C(=O)NC",           "ester -> amide"),

    # Thiol modifications
    ("[SH]",              "SC",             "SH -> SCH3"),
    ("[SH]",              "[OH]",           "SH -> OH"),

    # Methyl group modifications
    ("[CH3]",             "C(F)(F)F",       "CH3 -> CF3"),
    ("[CH3]",             "C(C)C",          "CH3 -> isopropyl"),

    # Permeability-focused modifications
    ("[CH3]",             "[CH2]F",         "CH3 -> CH2F (metabolic block)"),
    ("[NX3H1][CX3](=O)", "N(C)C(=O)",          "amide N-methylation (reduce HBD, permeability)"),
]

# ---------------------------------------------------------------------------
# Catechol-specific SAR transformations (v0.9.3)
# ---------------------------------------------------------------------------
# Catechol (1,2-dihydroxybenzene) is a common pharmacophore in natural products
# (rosmarinic acid, caffeic acid, EGCG, quercetin) but has poor skin
# permeability due to high PSA and HBD. These transformations reduce
# polarity while preserving binding contacts.
CATECHOL_TRANSFORMS = [
    # (query_SMARTS, replacement_SMILES, description)
    # Catechol -> fluorocatechol (replace one OH with F)
    ("c1cc(O)c(O)cc1",   "c1cc(F)c(O)cc1",          "catechol -> 3-fluoro-4-hydroxyphenyl (PSA -20, HBD -1)"),
    ("c1cc(O)c(O)cc1",   "c1cc(O)c(F)cc1",          "catechol -> 4-fluoro-3-hydroxyphenyl (PSA -20, HBD -1)"),
    # Catechol -> methylenedioxy (fused dioxole ring, e.g. safrole/piperine)
    ("c1cc(O)c(O)cc1",   "c1cc2c(cc1)OCO2",         "catechol -> methylenedioxy (PSA -12, HBD -2)"),
    # Catechol -> mono-hydroxyl (remove one OH entirely)
    ("c1cc(O)c(O)cc1",   "c1cc(O)ccc1",             "catechol -> mono-OH para (PSA -20, HBD -1)"),
    ("c1cc(O)c(O)cc1",   "c1ccc(O)cc1",             "catechol -> mono-OH meta (PSA -20, HBD -1)"),
    # Catechol -> methoxy + hydroxyl (selectively methylate one OH)
    ("c1cc(O)c(O)cc1",   "c1cc(OC)c(O)cc1",         "catechol -> 3-methoxy-4-hydroxyphenyl (HBD -1, guaiacol)"),
    ("c1cc(O)c(O)cc1",   "c1cc(O)c(OC)cc1",         "catechol -> 4-methoxy-3-hydroxyphenyl (HBD -1, isovanillin)"),
    # Catechol -> difluoro (replace both OHs with F)
    ("c1cc(O)c(O)cc1",   "c1cc(F)c(F)cc1",          "catechol -> 3,4-difluorophenyl (PSA -40, HBD -2)"),
    # Catechol -> chloro + hydroxyl
    ("c1cc(O)c(O)cc1",   "c1cc(Cl)c(O)cc1",         "catechol -> 3-chloro-4-hydroxyphenyl (PSA -20, HBD -1)"),
]

# ---------------------------------------------------------------------------
# Permeability-focused modification prioritization (v0.9.3)
# ---------------------------------------------------------------------------
# These modifications specifically reduce PSA/HBD to improve skin permeability.
# They are applied before other modifications when permeability is a concern.
PERMEABILITY_MODIFICATIONS = [
    # (query_SMARTS, replacement_SMILES, description, psa_reduction_est)
    ("[OH]",              "F",              "OH -> F (PSA -20, HBD -1)",             20.0),
    ("[OH]",              "[H]",            "OH removal (PSA -20, HBD -1)",          20.0),
    ("[NH2]",             "[NH]C",          "NH2 -> NHMe (HBD -1)",                  9.0),
    ("[NH2]",             "N(C)C",          "NH2 -> NMe2 (HBD -2)",                 18.0),
    ("[NH1;!$(NC=O)]",    "N(C)",           "NH -> NMe (HBD -1)",                    9.0),
    ("[CX3](=O)[OH]",    "C(=O)OCC",       "COOH -> ethyl ester (PSA -17, HBD -1)", 17.0),
    ("[CX3](=O)[OH]",    "C(=O)OC(C)C",    "COOH -> isopropyl ester (PSA -17, HBD -1)", 17.0),
]


# Extension fragments: (SMARTS_anchor, added_SMILES, description)
EXTENSION_FRAGMENTS = [
    ("methyl",    "C",      "add methyl"),
    ("hydroxyl",  "O",      "add hydroxyl"),
    ("amino",     "N",      "add amino"),
    ("fluoro",    "F",      "add fluorine"),
    ("cyano",     "C#N",    "add cyano"),
    ("methoxy",   "OC",     "add methoxy"),
]

# Pro-drug ester library: (name, replacement_SMILES for COOH, description)
# The replacement SMILES replaces the matched carboxylate [CX3](=O)[OH/O-]
PRODRUG_ESTERS = [
    ("ethyl_ester",       "C(=O)OCC",                       "ethyl ester pro-drug"),
    ("isopropyl_ester",   "C(=O)OC(C)C",                   "isopropyl ester pro-drug"),
    ("pom_ester",         "C(=O)OCOC(=O)C(C)(C)C",         "POM ester pro-drug"),
    ("acetoxymethyl",     "C(=O)OCOC(=O)C",                "acetoxymethyl ester pro-drug"),
]


# ---------------------------------------------------------------------------
# CYP450 metabolic soft spot patterns (v0.9.2)
# ---------------------------------------------------------------------------

# Each entry: (SMARTS, pattern_name, suggested_blocking_strategy)
CYP450_SOFT_SPOTS = [
    ("[cH1]~[CH2]",                 "benzylic_CH",     "add F or gem-dimethyl at benzylic position"),
    ("[C]=[C]~[CH2]",               "allylic_CH",      "add F at allylic position"),
    ("[NH2]c1ccc([#1,#6])cc1",      "para_aniline",    "add F or Cl at para position"),
    ("[NX3;!$(NC=O)][CH3]",         "n_dealkylation",  "replace N-CH3 (covered by bioisosteres)"),
    ("[OX2][CH3]",                  "o_dealkylation",  "replace O-CH3 with O-CHF2 or O-cyclopropyl"),
    ("c1cc([H])ccc1",              "unsubst_para",    "add F at unsubstituted para position"),
]


# ---------------------------------------------------------------------------
# Scaffold hopping ring transformations (v0.9.2)
# ---------------------------------------------------------------------------

# Each entry: (name, query_SMARTS, replacement_SMILES, description)
# Note: aromatic ring SMARTS use [c] wildcard patterns to match substituted rings
# (e.g. catechol c1ccc(O)c(O)c1 was not matched by bare c1ccccc1).
SCAFFOLD_HOP_TRANSFORMS = [
    # Aromatic ring transforms — use permissive SMARTS that match substituted aromatics
    ("phenyl_to_pyridyl",          "[cR1]1[cR1][cR1][cR1][cR1][cR1]1",    "c1ccncc1",    "phenyl -> 3-pyridyl (reduce logP)"),
    ("phenyl_to_pyrimidyl",        "[cR1]1[cR1][cR1][cR1][cR1][cR1]1",    "c1ncncn1",    "phenyl -> pyrimidyl (reduce logP)"),
    ("phenyl_to_cyclohexane",      "[cR1]1[cR1][cR1][cR1][cR1][cR1]1",    "C1CCCCC1",    "phenyl -> cyclohexane (saturate, reduce planarity)"),
    ("phenyl_to_cyclohexene",      "[cR1]1[cR1][cR1][cR1][cR1][cR1]1",    "C1CC=CCC1",   "phenyl -> cyclohexene (partial saturation)"),
    # Saturated ring transforms
    ("cyclopentane_to_cyclohexane", "C1CCCC1",    "C1CCCCC1",    "5-ring -> 6-ring expansion"),
    ("cyclohexane_to_cyclopentane", "C1CCCCC1",   "C1CCCC1",     "6-ring -> 5-ring contraction"),
    # Heteroatom insertion in saturated rings
    ("ch2_in_ring_to_O",           "[CH2;R]",     "[O]",         "ring CH2 -> O (morpholine-type)"),
    ("ch2_in_ring_to_NH",          "[CH2;R]",     "[NH]",        "ring CH2 -> NH (piperazine-type)"),
    ("ch2_in_ring_to_S",           "[CH2;R]",     "[S]",         "ring CH2 -> S (thiomorpholine-type)"),
    # Heteroaromatic transforms
    ("furan_to_thiophene",         "c1ccoc1",     "c1ccsc1",     "furan -> thiophene (metabolic stability)"),
    ("thiophene_to_furan",         "c1ccsc1",     "c1ccoc1",     "thiophene -> furan"),
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AnalogCandidate:
    """A generated analog candidate."""
    smiles: str
    parent_smiles: str
    modification_type: str      # "bioisostere", "extension", "removal", "prodrug_ester", "permeability"
    target_group: str           # functional group type modified
    rationale: str              # human-readable description
    target_group_idx: int = -1  # index into functional_groups list
    estimated_impact: str = ""  # "improved_hbond", "reduced_clash", etc.


@dataclass
class PropertyProfile:
    """Molecular property profile for bias filtering."""
    smiles: str
    logp: float = 0.0
    mw: float = 0.0
    psa: float = 0.0       # topological polar surface area
    hbd: int = 0            # H-bond donors
    hba: int = 0            # H-bond acceptors
    rotatable: int = 0      # rotatable bonds
    potts_guy_logkp: float = 0.0   # skin permeability (Potts-Guy)


@dataclass
class CyclizationSite:
    """Potential lactam cyclization site (amine + carboxylate proximity)."""
    amine_idx: int          # atom index of amine nitrogen
    acid_idx: int           # atom index of carboxylate carbon
    topological_dist: int   # shortest path in bond graph
    ring_size: int          # resulting ring size = topological_dist + 1
    amine_type: str         # "primary" or "secondary"


@dataclass
class Modification:
    """A single-site modification that passed docking in a given round."""
    site_idx: int               # atom/group index of modification site
    mod_type: str               # "bioisostere", "extension", "removal", etc.
    smarts_or_desc: str         # SMARTS pattern or description
    parent_smiles: str
    result_smiles: str


@dataclass
class ThioetherSite:
    """Potential thioether cyclization site (thiol + alkyl halide/methyl proximity)."""
    thiol_idx: int              # atom index of thiol sulfur
    carbon_idx: int             # atom index of carbon (halide-bearing or methyl)
    topological_dist: int       # shortest path in bond graph
    leaving_group: str          # "Cl", "Br", "I", "CH3"


@dataclass
class MetabolicSite:
    """CYP450-vulnerable metabolic soft spot."""
    atom_idx: int               # atom index of the vulnerable position
    pattern_name: str           # e.g. "benzylic_CH", "allylic_CH"
    smarts: str                 # SMARTS that matched
    suggested_block: str        # e.g. "add F or gem-dimethyl"


@dataclass
class LigandEfficiency:
    """Post-docking ligand efficiency metrics."""
    le: float                   # ligand efficiency = -dG / heavy_atom_count
    lle: float                  # lipophilic ligand efficiency = pIC50_est - logP
    lelp: float                 # LE-lipophilicity = logP / LE
    heavy_atom_count: int


# ---------------------------------------------------------------------------
# Property profile computation
# ---------------------------------------------------------------------------

def compute_property_profile(smiles: str) -> Optional[PropertyProfile]:
    """Compute molecular property profile using RDKit descriptors.

    Returns None if SMILES cannot be parsed.
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen, rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    logp = Crippen.MolLogP(mol)
    mw = Descriptors.MolWt(mol)
    psa = rdMolDescriptors.CalcTPSA(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)

    # Potts-Guy skin permeability equation: log Kp = -2.7 + 0.71*logP - 0.0061*MW
    potts_guy = -2.7 + 0.71 * logp - 0.0061 * mw

    return PropertyProfile(
        smiles=smiles,
        logp=round(logp, 2),
        mw=round(mw, 1),
        psa=round(psa, 1),
        hbd=hbd,
        hba=hba,
        rotatable=rotatable,
        potts_guy_logkp=round(potts_guy, 3),
    )


def get_target_window(config) -> dict:
    """Get the property target window from config, applying presets."""
    preset = getattr(config, "property_target", "cosmetic")
    if preset in PROPERTY_PRESETS:
        window = dict(PROPERTY_PRESETS[preset])
        # Allow rotatable_max override even in preset mode
        rot_override = getattr(config, "target_rotatable_max", -1)
        if rot_override >= 0:
            window["rotatable_max"] = rot_override
    else:
        # "custom" mode — read individual fields from config
        rot_max = getattr(config, "target_rotatable_max", -1)
        window = {
            "logp_min": getattr(config, "target_logp_min", 1.0),
            "logp_max": getattr(config, "target_logp_max", 3.0),
            "mw_max": getattr(config, "target_mw_max", 350.0),
            "psa_max": getattr(config, "target_psa_max", 70.0),
            "hbd_max": getattr(config, "target_hbd_max", 2),
            "hba_max": getattr(config, "target_hba_max", 5),
            "rotatable_max": rot_max if rot_max >= 0 else 10,
        }
    return window


def _compute_adaptive_window(
    target_window: dict,
    parent_profile: Optional["PropertyProfile"] = None,
) -> dict:
    """Compute an adaptive property window when the parent has a bad profile.

    When the parent molecule already violates the target window (e.g. RA with
    PSA=144.5 when the cosmetic target is <70), the strict window would reject
    ALL modifications since they can't fix the profile in a single step.

    Adaptive logic: for each property where the parent exceeds the target,
    relax the limit to max(target, parent_value * 1.1), allowing modifications
    that don't make things worse and preferring those that improve the profile.
    For properties where the parent is below the minimum (e.g. logP too low),
    relax the minimum to min(target_min, parent_value * 0.9).

    Parameters
    ----------
    target_window : dict
        Original property target window.
    parent_profile : PropertyProfile, optional
        Property profile of the parent molecule. If None, returns the
        original window unchanged.

    Returns
    -------
    dict
        Potentially relaxed property window.
    """
    if parent_profile is None:
        return dict(target_window)

    window = dict(target_window)
    relaxed = False

    # Relax upper bounds where parent exceeds target
    if parent_profile.psa > window.get("psa_max", 999):
        window["psa_max"] = parent_profile.psa * 1.1
        relaxed = True

    if parent_profile.mw > window.get("mw_max", 999):
        window["mw_max"] = parent_profile.mw * 1.1
        relaxed = True

    if parent_profile.hbd > window.get("hbd_max", 999):
        window["hbd_max"] = parent_profile.hbd + 1
        relaxed = True

    if parent_profile.hba > window.get("hba_max", 999):
        window["hba_max"] = parent_profile.hba + 1
        relaxed = True

    if parent_profile.rotatable > window.get("rotatable_max", 999):
        window["rotatable_max"] = parent_profile.rotatable + 2
        relaxed = True

    # Relax logP bounds
    if parent_profile.logp > window.get("logp_max", 5.0):
        window["logp_max"] = parent_profile.logp * 1.2
        relaxed = True
    if parent_profile.logp < window.get("logp_min", 0.0):
        window["logp_min"] = parent_profile.logp * 0.8
        relaxed = True

    if relaxed:
        logger.info("Adaptive filter relaxation applied (parent profile exceeds target):")
        logger.info("  Relaxed window: logP=%.1f-%.1f, MW<%.0f, PSA<%.0f, HBD<=%d, HBA<=%d, rot<=%d",
                     window.get("logp_min", 0), window.get("logp_max", 5),
                     window.get("mw_max", 500), window.get("psa_max", 140),
                     window.get("hbd_max", 5), window.get("hba_max", 10),
                     window.get("rotatable_max", 999))

    return window


def filter_by_property_window(
    candidates: List[AnalogCandidate],
    target_window: dict,
    parent_profile: Optional["PropertyProfile"] = None,
) -> List[AnalogCandidate]:
    """Filter analog candidates that violate the property target window.

    Computes the property profile of each candidate and rejects those
    that push properties outside the target window.

    When parent_profile is provided and the parent already violates
    the target window, the filter is adaptively relaxed to allow
    modifications that don't worsen the profile (v0.9.3).

    Parameters
    ----------
    candidates : List[AnalogCandidate]
        Candidates to filter.
    target_window : dict
        Property target window (logp_min, logp_max, mw_max, etc.).
    parent_profile : PropertyProfile, optional
        Profile of the parent molecule. If provided, enables adaptive
        relaxation when the parent has a bad property profile.
    """
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

    # v0.9.3: Adaptive relaxation for bad-profile parents
    effective_window = _compute_adaptive_window(target_window, parent_profile)

    filtered = []
    logp_max = effective_window.get("logp_max", 5.0)
    logp_min = effective_window.get("logp_min", 1.0)
    mw_max = effective_window.get("mw_max", 500.0)
    psa_max = effective_window.get("psa_max", 140.0)
    hbd_max = effective_window.get("hbd_max", 5)
    hba_max = effective_window.get("hba_max", 10)

    rotatable_max = effective_window.get("rotatable_max", 999)

    n_rejected = 0
    for cand in candidates:
        mol = Chem.MolFromSmiles(cand.smiles)
        if mol is None:
            continue

        logp = Crippen.MolLogP(mol)
        mw = Descriptors.MolWt(mol)
        psa = rdMolDescriptors.CalcTPSA(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        rot = rdMolDescriptors.CalcNumRotatableBonds(mol)

        # Check bounds
        if logp > logp_max or logp < logp_min:
            n_rejected += 1
            continue
        if mw > mw_max:
            n_rejected += 1
            continue
        if psa > psa_max:
            n_rejected += 1
            continue
        if hbd > hbd_max:
            n_rejected += 1
            continue
        if hba > hba_max:
            n_rejected += 1
            continue
        if rot > rotatable_max:
            n_rejected += 1
            continue

        filtered.append(cand)

    if n_rejected > 0:
        logger.info("Property filter rejected %d/%d candidates (effective window: logP=%.1f-%.1f, "
                     "MW<%.0f, PSA<%.0f, HBD<=%d, HBA<=%d)",
                     n_rejected, len(candidates), logp_min, logp_max,
                     mw_max, psa_max, hbd_max, hba_max)

    return filtered


# ---------------------------------------------------------------------------
# Cyclization site detection
# ---------------------------------------------------------------------------

def detect_cyclization_sites(smiles: str) -> List[CyclizationSite]:
    """Detect potential lactam cyclization sites.

    Finds amine N atoms and carboxylate C atoms within 3-6 bonds
    of each other, which could form lactam rings upon cyclization.
    """
    from rdkit import Chem
    from rdkit.Chem import rdmolops

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    sites = []

    # Find amines: primary (-NH2) and secondary (-NH-)
    amine_smarts = [
        ("[NH2;!$([NH2]C=O)]", "primary"),
        ("[NH1;!$([NH1]C=O);!$([nH1])]", "secondary"),
    ]
    amine_atoms = []
    for sma, atype in amine_smarts:
        pattern = Chem.MolFromSmarts(sma)
        if pattern is None:
            continue
        for match in mol.GetSubstructMatches(pattern):
            amine_atoms.append((match[0], atype))

    # Find carboxylates: COOH or COO-
    acid_pattern = Chem.MolFromSmarts("[CX3](=O)[OX2H1,OX1-]")
    acid_atoms = []
    if acid_pattern:
        for match in mol.GetSubstructMatches(acid_pattern):
            acid_atoms.append(match[0])  # the carbon

    # Check topological distance between each amine-acid pair
    for n_idx, n_type in amine_atoms:
        for c_idx in acid_atoms:
            if n_idx == c_idx:
                continue
            try:
                path = rdmolops.GetShortestPath(mol, n_idx, c_idx)
                topo_dist = len(path) - 1  # number of bonds
                ring_size = topo_dist + 1   # ring formed by closing the bond

                if 3 <= topo_dist <= 6:
                    sites.append(CyclizationSite(
                        amine_idx=n_idx,
                        acid_idx=c_idx,
                        topological_dist=topo_dist,
                        ring_size=ring_size,
                        amine_type=n_type,
                    ))
            except Exception:
                continue

    return sites


# ---------------------------------------------------------------------------
# Thioether cyclization detection (v0.9.2)
# ---------------------------------------------------------------------------

def detect_thioether_sites(smiles: str) -> List[ThioetherSite]:
    """Detect potential thioether cyclization sites.

    Finds thiol (-SH) atoms and nearby carbon atoms bearing leaving groups
    (Cl, Br, I) or methyl groups within 3-6 bonds topological distance.
    These pairs could form thioether bridges (C-S-C) upon cyclization.
    """
    from rdkit import Chem
    from rdkit.Chem import rdmolops

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    sites = []

    # Find thiol sulfur atoms
    thiol_pattern = Chem.MolFromSmarts("[SH1]")
    if thiol_pattern is None:
        return []
    thiol_matches = mol.GetSubstructMatches(thiol_pattern)

    # Find carbon atoms with leaving groups or methyl groups
    leaving_group_patterns = [
        ("[CH2][Cl]", "Cl"),
        ("[CH2][Br]", "Br"),
        ("[CH2][I]",  "I"),
        ("[CH3]",     "CH3"),
    ]

    carbon_targets = []
    for sma, lg_name in leaving_group_patterns:
        pat = Chem.MolFromSmarts(sma)
        if pat is None:
            continue
        for match in mol.GetSubstructMatches(pat):
            carbon_targets.append((match[0], lg_name))  # the carbon atom

    # Check topological distance between each thiol-carbon pair
    for (s_idx,) in thiol_matches:
        for c_idx, lg_name in carbon_targets:
            if s_idx == c_idx:
                continue
            try:
                path = rdmolops.GetShortestPath(mol, s_idx, c_idx)
                topo_dist = len(path) - 1

                if 3 <= topo_dist <= 6:
                    sites.append(ThioetherSite(
                        thiol_idx=s_idx,
                        carbon_idx=c_idx,
                        topological_dist=topo_dist,
                        leaving_group=lg_name,
                    ))
            except Exception:
                continue

    return sites


# ---------------------------------------------------------------------------
# Metabolic soft spot identification (v0.9.2)
# ---------------------------------------------------------------------------

def identify_metabolic_soft_spots(smiles: str) -> List[MetabolicSite]:
    """Identify CYP450 oxidation-prone metabolic soft spots.

    Scans the molecule for known CYP450 substrate patterns (benzylic CH,
    allylic CH, para-anilines, N/O-dealkylation sites) and returns atom
    indices with suggested blocking modifications.
    """
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    sites = []
    for sma, pattern_name, suggested_block in CYP450_SOFT_SPOTS:
        pattern = Chem.MolFromSmarts(sma)
        if pattern is None:
            continue

        for match in mol.GetSubstructMatches(pattern):
            # Use the last atom in the match (the vulnerable carbon/position)
            vulnerable_idx = match[-1] if len(match) > 1 else match[0]
            sites.append(MetabolicSite(
                atom_idx=vulnerable_idx,
                pattern_name=pattern_name,
                smarts=sma,
                suggested_block=suggested_block,
            ))

    if sites:
        logger.info("Found %d metabolic soft spots in %s", len(sites), smiles)

    return sites


def generate_metabolic_blocks(
    smiles: str,
    soft_spots: List[MetabolicSite],
    target_window: Optional[dict] = None,
) -> List[AnalogCandidate]:
    """Generate analogs that block identified metabolic soft spots.

    For each soft spot, applies the suggested blocking modification
    (typically fluorination or gem-dimethyl substitution).
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    candidates = []
    seen_smiles = set()

    for site in soft_spots:
        if site.atom_idx >= mol.GetNumAtoms():
            continue

        # Strategy 1: Add fluorine at vulnerable position
        if "add F" in site.suggested_block:
            new_smi = _add_fragment_at_atom(mol, site.atom_idx, "F")
            if new_smi and new_smi not in seen_smiles and new_smi != smiles:
                if validate_structure(new_smi):
                    seen_smiles.add(new_smi)
                    candidates.append(AnalogCandidate(
                        smiles=new_smi,
                        parent_smiles=smiles,
                        modification_type="metabolic_block",
                        target_group=site.pattern_name,
                        target_group_idx=site.atom_idx,
                        rationale=f"F-block at {site.pattern_name} (CYP450 stability)",
                        estimated_impact="metabolic_stability",
                    ))

        # Strategy 2: Replace CH3 with CF3 (for N/O-dealkylation)
        if "dealkylation" in site.pattern_name:
            ch3_query = Chem.MolFromSmarts("[CH3]")
            cf3_repl = Chem.MolFromSmiles("C(F)(F)F")
            if ch3_query and cf3_repl and mol.HasSubstructMatch(ch3_query):
                products = AllChem.ReplaceSubstructs(mol, ch3_query, cf3_repl)
                for product in products[:1]:
                    try:
                        Chem.SanitizeMol(product)
                        new_smi = Chem.MolToSmiles(product)
                        if new_smi and new_smi not in seen_smiles and new_smi != smiles:
                            if validate_structure(new_smi):
                                seen_smiles.add(new_smi)
                                candidates.append(AnalogCandidate(
                                    smiles=new_smi,
                                    parent_smiles=smiles,
                                    modification_type="metabolic_block",
                                    target_group=site.pattern_name,
                                    target_group_idx=site.atom_idx,
                                    rationale=f"CH3->CF3 at {site.pattern_name} (block dealkylation)",
                                    estimated_impact="metabolic_stability",
                                ))
                    except Exception:
                        continue

    logger.info("Generated %d metabolic blocking candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Catechol-specific SAR generation (v0.9.3)
# ---------------------------------------------------------------------------

def generate_catechol_modifications(
    smiles: str,
    target_window: Optional[dict] = None,
) -> List[AnalogCandidate]:
    """Generate catechol-targeted analogs for improved permeability.

    Catechol (1,2-dihydroxybenzene) is common in natural polyphenols but
    contributes heavily to PSA and HBD count. These transforms reduce
    polarity while preserving some binding capacity.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    candidates = []
    seen_smiles = set()

    for query_smarts, repl_smiles, description in CATECHOL_TRANSFORMS:
        query = Chem.MolFromSmarts(query_smarts)
        replacement = Chem.MolFromSmiles(repl_smiles)
        if query is None or replacement is None:
            continue

        if not mol.HasSubstructMatch(query):
            continue

        try:
            # Apply to all matches (catechol may appear multiple times, e.g. RA)
            products = AllChem.ReplaceSubstructs(mol, query, replacement)
            for product in products:
                try:
                    Chem.SanitizeMol(product)
                    new_smi = Chem.MolToSmiles(product)
                    if (new_smi and new_smi != smiles
                            and new_smi not in seen_smiles
                            and validate_structure(new_smi)):
                        seen_smiles.add(new_smi)
                        candidates.append(AnalogCandidate(
                            smiles=new_smi,
                            parent_smiles=smiles,
                            modification_type="catechol_sar",
                            target_group="catechol",
                            rationale=description,
                            estimated_impact="permeability",
                        ))
                except Exception:
                    continue
        except Exception:
            continue

    logger.info("Generated %d catechol SAR candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Permeability-aware analog generation (v0.9.3)
# ---------------------------------------------------------------------------

def generate_permeability_analogs(
    smiles: str,
    target_window: Optional[dict] = None,
) -> List[AnalogCandidate]:
    """Generate analogs specifically targeting improved skin permeability.

    Prioritizes modifications that reduce PSA and HBD count,
    focusing on OH->F, OH removal, N-methylation, and ester pro-drugs.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    candidates = []
    seen_smiles = set()

    # Sort by PSA reduction impact (highest first)
    sorted_mods = sorted(PERMEABILITY_MODIFICATIONS, key=lambda x: -x[3])

    for query_smarts, repl_smiles, description, _psa_est in sorted_mods:
        query = Chem.MolFromSmarts(query_smarts)
        replacement = Chem.MolFromSmiles(repl_smiles)
        if query is None or replacement is None:
            continue

        if not mol.HasSubstructMatch(query):
            continue

        try:
            products = AllChem.ReplaceSubstructs(mol, query, replacement)
            for product in products:
                try:
                    Chem.SanitizeMol(product)
                    new_smi = Chem.MolToSmiles(product)
                    if (new_smi and new_smi != smiles
                            and new_smi not in seen_smiles
                            and validate_structure(new_smi)):
                        seen_smiles.add(new_smi)
                        candidates.append(AnalogCandidate(
                            smiles=new_smi,
                            parent_smiles=smiles,
                            modification_type="permeability",
                            target_group="polar_group",
                            rationale=description,
                            estimated_impact="permeability",
                        ))
                except Exception:
                    continue
        except Exception:
            continue

    logger.info("Generated %d permeability-focused candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Scaffold hopping (v0.9.2)
# ---------------------------------------------------------------------------

def generate_scaffold_hops(
    smiles: str,
    analysis=None,
    max_hops: int = 10,
) -> List[AnalogCandidate]:
    """Generate scaffold hop analogs via ring transformations.

    Applies SCAFFOLD_HOP_TRANSFORMS to replace ring systems with
    bioisosteric alternatives (phenyl->pyridyl, ring size changes,
    heteroatom insertions, saturation changes).

    For substituted aromatic rings, uses RWMol atom-by-atom replacement
    to preserve substituent connectivity (v0.9.3 fix).
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    candidates = []
    seen_smiles = set()

    for name, query_smarts, repl_smiles, description in SCAFFOLD_HOP_TRANSFORMS:
        query = Chem.MolFromSmarts(query_smarts)
        replacement = Chem.MolFromSmiles(repl_smiles)
        if query is None or replacement is None:
            continue

        if not mol.HasSubstructMatch(query):
            continue

        try:
            # For ring-to-ring transforms, use ReplaceSubstructs with
            # replaceDirScoreSmi=True to try to preserve connectivity
            products = AllChem.ReplaceSubstructs(
                mol, query, replacement, replaceAll=False)

            for product in products:
                try:
                    Chem.SanitizeMol(product)
                    new_smi = Chem.MolToSmiles(product)

                    # Reject fragmented products (disconnected by '.')
                    if not new_smi or "." in new_smi:
                        continue

                    if (new_smi != smiles
                            and new_smi not in seen_smiles
                            and validate_structure(new_smi)):
                        seen_smiles.add(new_smi)
                        candidates.append(AnalogCandidate(
                            smiles=new_smi,
                            parent_smiles=smiles,
                            modification_type="scaffold_hop",
                            target_group=query_smarts,
                            rationale=description,
                            estimated_impact="altered_scaffold",
                        ))
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Scaffold hop failed for %s: %s", name, e)

        if len(candidates) >= max_hops:
            break

    # If no standard hops worked (common for substituted aromatics),
    # try heteroatom insertion approach: replace a ring CH with N
    if not candidates and mol is not None:
        candidates.extend(
            _generate_ring_ch_to_n_hops(mol, smiles, seen_smiles, max_hops))

    logger.info("Generated %d scaffold hop candidates", len(candidates))
    return candidates


def _generate_ring_ch_to_n_hops(
    mol,
    smiles: str,
    seen_smiles: set,
    max_hops: int = 10,
) -> List[AnalogCandidate]:
    """Generate scaffold hops by replacing aromatic C-H with N.

    This handles substituted aromatics that can't be matched by simple
    ring-replacement SMARTS. Instead of replacing the whole ring, we
    replace individual unsubstituted aromatic CH positions with N.
    """
    from rdkit import Chem

    candidates = []

    # Find aromatic CH positions (no substituents other than H)
    aromatic_ch_pattern = Chem.MolFromSmarts("[cH1]")
    if aromatic_ch_pattern is None:
        return candidates

    matches = mol.GetSubstructMatches(aromatic_ch_pattern)
    if not matches:
        return candidates

    for match in matches:
        atom_idx = match[0]
        try:
            rwmol = Chem.RWMol(mol)
            atom = rwmol.GetAtomWithIdx(atom_idx)

            # Replace C with N (and remove one implicit H)
            atom.SetAtomicNum(7)  # nitrogen
            atom.SetNoImplicit(False)
            atom.SetNumExplicitHs(0)

            try:
                Chem.SanitizeMol(rwmol)
                new_smi = Chem.MolToSmiles(rwmol)

                if (new_smi and new_smi != smiles
                        and "." not in new_smi
                        and new_smi not in seen_smiles
                        and validate_structure(new_smi)):
                    seen_smiles.add(new_smi)
                    candidates.append(AnalogCandidate(
                        smiles=new_smi,
                        parent_smiles=smiles,
                        modification_type="scaffold_hop",
                        target_group="aromatic_CH",
                        target_group_idx=atom_idx,
                        rationale=f"aromatic CH -> N at position {atom_idx} (reduce logP, aza-analog)",
                        estimated_impact="altered_scaffold",
                    ))
            except Exception:
                continue

        except Exception:
            continue

        if len(candidates) >= max_hops:
            break

    return candidates


# ---------------------------------------------------------------------------
# Matched molecular pair (MMP) tracking (v0.9.2)
# ---------------------------------------------------------------------------

def find_equivalent_sites(mol, modification: Modification) -> List[int]:
    """Find all equivalent sites for a modification (same functional group pattern).

    Given a modification that was applied at one site, finds all other atom
    indices matching the same SMARTS pattern (excluding the original site).
    """
    from rdkit import Chem

    # Try to interpret the modification's SMARTS from the bioisostere table
    matching_smarts = None
    for query_smarts, repl_smiles, desc in BIOISOSTERE_TABLE:
        if desc == modification.smarts_or_desc or query_smarts == modification.smarts_or_desc:
            matching_smarts = query_smarts
            break

    if matching_smarts is None:
        return []

    pattern = Chem.MolFromSmarts(matching_smarts)
    if pattern is None:
        return []

    matches = mol.GetSubstructMatches(pattern)
    # Return first atom of each match, excluding the original site
    sites = []
    for match in matches:
        first_atom = match[0]
        if first_atom != modification.site_idx:
            sites.append(first_atom)

    return sites


def generate_mmp_expansions(
    parent_smiles: str,
    passing_modifications: List[Modification],
    analysis=None,
    target_window: Optional[dict] = None,
) -> List[AnalogCandidate]:
    """Apply passing modifications at all equivalent sites (matched molecular pair).

    If a modification worked at one site, try applying it at all other
    sites with the same functional group pattern.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(parent_smiles)
    if mol is None:
        return []

    candidates = []
    seen_smiles = set()

    for mod in passing_modifications:
        if mod.mod_type != "bioisostere":
            continue  # MMP expansion primarily for bioisostere transformations

        equiv_sites = find_equivalent_sites(mol, mod)
        if not equiv_sites:
            continue

        # Find the matching bioisostere entry
        for query_smarts, repl_smiles, desc in BIOISOSTERE_TABLE:
            if desc != mod.smarts_or_desc and query_smarts != mod.smarts_or_desc:
                continue

            query = Chem.MolFromSmarts(query_smarts)
            replacement = Chem.MolFromSmiles(repl_smiles)
            if query is None or replacement is None:
                continue

            # Apply to each equivalent site
            matches = mol.GetSubstructMatches(query)
            for match in matches:
                if match[0] == mod.site_idx:
                    continue  # skip original site

                try:
                    products = AllChem.ReplaceSubstructs(mol, query, replacement)
                    # ReplaceSubstructs replaces first match; cycle through
                    for product in products:
                        try:
                            Chem.SanitizeMol(product)
                            new_smi = Chem.MolToSmiles(product)
                            if (new_smi and new_smi != parent_smiles
                                    and new_smi not in seen_smiles
                                    and validate_structure(new_smi)):
                                seen_smiles.add(new_smi)
                                candidates.append(AnalogCandidate(
                                    smiles=new_smi,
                                    parent_smiles=parent_smiles,
                                    modification_type="mmp_expansion",
                                    target_group=query_smarts,
                                    target_group_idx=match[0],
                                    rationale=f"MMP: {desc} at equivalent site {match[0]}",
                                    estimated_impact="mmp_transferred",
                                ))
                        except Exception:
                            continue
                except Exception:
                    continue
            break  # found the matching entry

    logger.info("Generated %d MMP expansion candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Ligand efficiency metrics (v0.9.2)
# ---------------------------------------------------------------------------

def compute_ligand_efficiency(
    smiles: str,
    binding_energy: float,
) -> Optional[LigandEfficiency]:
    """Compute ligand efficiency metrics from binding energy.

    Parameters
    ----------
    smiles : str
        SMILES of the ligand.
    binding_energy : float
        Docking score in kcal/mol (negative = better binding).

    Returns
    -------
    LigandEfficiency or None
        LE, LLE, LELP metrics. None if SMILES cannot be parsed.
    """
    from rdkit import Chem
    from rdkit.Chem import Crippen

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    hac = mol.GetNumHeavyAtoms()
    if hac == 0:
        return None

    logp = Crippen.MolLogP(mol)

    # LE = -dG / HAC (kcal/mol per heavy atom)
    le = -binding_energy / hac

    # LLE = pIC50_est - logP
    # Approximate conversion: pIC50 ~ -dG * 1000 / (R * T * ln(10))
    # At 298K: R*T*ln(10) = 1.3636 kcal/mol
    if binding_energy < 0:
        pic50_est = -binding_energy * 1000.0 / (1.3636 * 298.0)
    else:
        pic50_est = 0.0
    lle = pic50_est - logp

    # LELP = logP / LE
    lelp = logp / le if abs(le) > 1e-6 else 0.0

    return LigandEfficiency(
        le=round(le, 3),
        lle=round(lle, 2),
        lelp=round(lelp, 2),
        heavy_atom_count=hac,
    )


# ---------------------------------------------------------------------------
# Multi-objective composite scoring (v0.9.3)
# ---------------------------------------------------------------------------

def compute_composite_score(
    binding_energy: float,
    profile: Optional["PropertyProfile"] = None,
    permeability_weight: float = 0.3,
    le_weight: float = 0.1,
) -> float:
    """Compute a multi-objective composite score for ranking.

    Combines binding energy with skin permeability (Potts-Guy logKp)
    and ligand efficiency into a single ranking metric.

    Lower (more negative) is better.

    composite = binding_energy + perm_weight * logKp_penalty + le_weight * le_penalty

    logKp_penalty: difference from ideal permeability (-2.5), capped at 0
    le_penalty: penalty for low LE (below 0.3 kcal/mol/atom)

    Parameters
    ----------
    binding_energy : float
        Docking score in kcal/mol.
    profile : PropertyProfile, optional
        Molecular property profile (logKp, PSA, etc.).
    permeability_weight : float
        Weight for permeability term (default 0.3).
    le_weight : float
        Weight for ligand efficiency penalty (default 0.1).

    Returns
    -------
    float
        Composite score (more negative = better).
    """
    score = binding_energy

    if profile is not None:
        # Permeability penalty: penalize molecules far from ideal logKp (-2.5)
        ideal_logkp = -2.5
        logkp_gap = profile.potts_guy_logkp - ideal_logkp  # negative = worse than ideal
        if logkp_gap < 0:
            score += permeability_weight * abs(logkp_gap)

        # PSA penalty: extra penalty for very high PSA (>120)
        if profile.psa > 120:
            score += permeability_weight * (profile.psa - 120) * 0.01

    return round(score, 3)


# ---------------------------------------------------------------------------
# Torsion strain pre-filtering (v0.9.2)
# ---------------------------------------------------------------------------

def check_torsion_strain(
    smiles: str,
    amide_tolerance: float = 30.0,
) -> Tuple[bool, List[str]]:
    """Check for unfavorable torsion angles in a 3D conformer.

    Generates a 3D conformer via MMFF optimization and checks amide/ester
    torsion angles. Amides and esters should be near-planar (0 or 180 deg).

    Parameters
    ----------
    smiles : str
        SMILES of the molecule.
    amide_tolerance : float
        Allowed deviation from planarity in degrees (default 30).

    Returns
    -------
    (passes, warnings) : (bool, List[str])
        passes is True if no severe strain detected.
        warnings is a list of strain descriptions.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolTransforms

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False, ["cannot parse SMILES"]

    mol = Chem.AddHs(mol)

    # Generate 3D conformer
    try:
        result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if result == -1:
            # Fallback with random coordinates
            result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
            if result == -1:
                return True, []  # can't embed, skip check (don't penalize)

        # MMFF optimization
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            pass  # proceed without optimization
    except Exception:
        return True, []  # can't generate conformer, skip check

    mol_noH = Chem.RemoveHs(mol)
    conf = mol.GetConformer()
    warnings = []

    # Check amide torsions: [*]-C(=O)-N-[*]
    amide_pattern = Chem.MolFromSmarts("[*]~[CX3](=O)~[NX3]~[*]")
    if amide_pattern:
        for match in mol.GetSubstructMatches(amide_pattern):
            if len(match) < 4:
                continue
            try:
                dihedral = abs(rdMolTransforms.GetDihedralDeg(conf, match[0], match[1], match[3], match[3]))
                # Check deviation from planarity (0 or 180)
                dev_from_planar = min(abs(dihedral), abs(dihedral - 180.0), abs(dihedral + 180.0))
                if dev_from_planar > amide_tolerance:
                    warnings.append(
                        f"Non-planar amide: atoms {match[1]}-{match[3]}, "
                        f"dihedral={dihedral:.1f}° (deviation={dev_from_planar:.1f}°)"
                    )
            except Exception:
                continue

    # Check ester torsions: [*]-C(=O)-O-[*]
    ester_pattern = Chem.MolFromSmarts("[*]~[CX3](=O)~[OX2]~[*]")
    if ester_pattern:
        for match in mol.GetSubstructMatches(ester_pattern):
            if len(match) < 4:
                continue
            try:
                dihedral = abs(rdMolTransforms.GetDihedralDeg(conf, match[0], match[1], match[3], match[3]))
                dev_from_planar = min(abs(dihedral), abs(dihedral - 180.0), abs(dihedral + 180.0))
                if dev_from_planar > amide_tolerance:
                    warnings.append(
                        f"Non-planar ester: atoms {match[1]}-{match[3]}, "
                        f"dihedral={dihedral:.1f}° (deviation={dev_from_planar:.1f}°)"
                    )
            except Exception:
                continue

    passes = len(warnings) == 0
    return passes, warnings


# ---------------------------------------------------------------------------
# Stereoisomer enumeration (v0.9.2)
# ---------------------------------------------------------------------------

def enumerate_stereoisomers_rational(
    smiles: str,
    modification_sites: List[int],
    max_isomers: int = 16,
) -> List[str]:
    """Enumerate stereoisomers by inverting chiral centers near modification sites.

    For intermediate optimization rounds: only invert stereocenters within
    2 bonds of a modification site, keeping other centers fixed.

    Parameters
    ----------
    smiles : str
        SMILES of the molecule.
    modification_sites : List[int]
        Atom indices where modifications were applied.
    max_isomers : int
        Maximum number of isomers to generate (cap).

    Returns
    -------
    List[str]
        List of stereoisomer SMILES (may include the input SMILES).
    """
    from rdkit import Chem
    from rdkit.Chem import rdmolops

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # Find chiral centers
    chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    if not chiral_centers:
        return []

    # Find which chiral centers are within 2 bonds of a modification site
    nearby_centers = []
    for center_idx, tag in chiral_centers:
        for mod_site in modification_sites:
            if mod_site < 0 or mod_site >= mol.GetNumAtoms():
                continue
            try:
                path = rdmolops.GetShortestPath(mol, center_idx, mod_site)
                if len(path) - 1 <= 2:  # within 2 bonds
                    nearby_centers.append(center_idx)
                    break
            except Exception:
                continue

    if not nearby_centers:
        return []

    # Cap the number of centers to invert to avoid explosion
    if len(nearby_centers) > 4:
        nearby_centers = nearby_centers[:4]

    # Generate all combinations of inversions
    isomers = set()
    isomers.add(smiles)

    for n_invert in range(1, len(nearby_centers) + 1):
        for combo in itertools.combinations(nearby_centers, n_invert):
            try:
                rwmol = Chem.RWMol(Chem.MolFromSmiles(smiles))
                for center_idx in combo:
                    atom = rwmol.GetAtomWithIdx(center_idx)
                    current_tag = atom.GetChiralTag()
                    if current_tag == Chem.ChiralType.CHI_TETRAHEDRAL_CW:
                        atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
                    elif current_tag == Chem.ChiralType.CHI_TETRAHEDRAL_CCW:
                        atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)

                try:
                    Chem.SanitizeMol(rwmol)
                    iso_smi = Chem.MolToSmiles(rwmol)
                    if iso_smi:
                        isomers.add(iso_smi)
                except Exception:
                    continue
            except Exception:
                continue

            if len(isomers) >= max_isomers:
                break
        if len(isomers) >= max_isomers:
            break

    return list(isomers)


def enumerate_stereoisomers_full(
    smiles: str,
    max_centers: int = 4,
) -> List[str]:
    """Enumerate all possible stereoisomers of a molecule.

    For final-round post-optimization: takes top binders and generates
    all stereoisomers using RDKit's EnumerateStereoisomers.

    Parameters
    ----------
    smiles : str
        SMILES of the molecule.
    max_centers : int
        Maximum number of stereocenters to enumerate (cap at 2^max_centers).

    Returns
    -------
    List[str]
        List of all stereoisomer SMILES (includes original).
    """
    from rdkit import Chem
    from rdkit.Chem.EnumerateStereoisomers import (
        EnumerateStereoisomers,
        StereoEnumerationOptions,
    )

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # Check number of stereocenters
    chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    n_centers = len(chiral_centers)

    if n_centers == 0:
        return [smiles]

    # Cap enumeration
    max_isomers = 2 ** min(n_centers, max_centers)

    opts = StereoEnumerationOptions(
        maxIsomers=max_isomers,
        tryEmbedding=False,
        onlyUnassigned=False,
    )

    isomers = []
    try:
        for iso_mol in EnumerateStereoisomers(mol, options=opts):
            try:
                iso_smi = Chem.MolToSmiles(iso_mol)
                if iso_smi:
                    isomers.append(iso_smi)
            except Exception:
                continue
    except Exception as e:
        logger.debug("Stereoisomer enumeration failed for %s: %s", smiles, e)
        return [smiles]

    logger.info("Enumerated %d stereoisomers for %s (%d centers)",
                len(isomers), smiles[:30], n_centers)
    return isomers


# ---------------------------------------------------------------------------
# Pro-drug ester generation
# ---------------------------------------------------------------------------

def generate_prodrug_esters(
    smiles: str,
    target_logp_range: Tuple[float, float] = (1.0, 3.0),
) -> List[AnalogCandidate]:
    """Generate pro-drug ester variants for all carboxylate groups.

    Each carboxylate is esterified with ethyl, isopropyl, POM, and
    acetoxymethyl groups. Results are ranked by logP proximity to
    the target range center.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, Crippen

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    # Check for carboxylate groups
    acid_query = Chem.MolFromSmarts("[CX3](=O)[OX2H1,OX1-]")
    if acid_query is None or not mol.HasSubstructMatch(acid_query):
        return []

    candidates = []
    target_center = (target_logp_range[0] + target_logp_range[1]) / 2.0

    for ester_name, ester_smiles, desc in PRODRUG_ESTERS:
        try:
            replacement = Chem.MolFromSmiles(ester_smiles)
            if replacement is None:
                continue

            products = AllChem.ReplaceSubstructs(mol, acid_query, replacement)
            for product in products[:1]:
                try:
                    Chem.SanitizeMol(product)
                    prod_smi = Chem.MolToSmiles(product)
                    if not prod_smi or prod_smi == smiles:
                        continue

                    # Compute logP of the ester variant
                    prod_mol = Chem.MolFromSmiles(prod_smi)
                    if prod_mol:
                        logp = Crippen.MolLogP(prod_mol)
                    else:
                        logp = 0.0

                    candidates.append(AnalogCandidate(
                        smiles=prod_smi,
                        parent_smiles=smiles,
                        modification_type="prodrug_ester",
                        target_group="carboxylic_acid",
                        rationale=f"{desc} (logP={logp:.1f})",
                        estimated_impact="prodrug_permeability",
                    ))
                except Exception:
                    continue

        except Exception as e:
            logger.debug("Pro-drug ester generation failed for %s: %s", ester_name, e)

    # Sort by logP proximity to target center
    def _logp_distance(c):
        try:
            from rdkit import Chem as _Chem
            from rdkit.Chem import Crippen as _Crippen
            m = _Chem.MolFromSmiles(c.smiles)
            return abs(_Crippen.MolLogP(m) - target_center) if m else 999
        except Exception:
            return 999

    candidates.sort(key=_logp_distance)
    return candidates


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_analogs(
    ligand_smiles: str,
    analysis,  # BindingAnalysisResult
    max_analogs: int = 50,
    enable_bioisosteres: bool = True,
    enable_extensions: bool = True,
    enable_removals: bool = True,
    enable_prodrug_esters: bool = False,
    enable_metabolic_blocking: bool = False,
    enable_scaffold_hopping: bool = False,
    enable_thioether_detection: bool = False,
    max_scaffold_hops: int = 10,
    target_window: Optional[dict] = None,
    parent_profile: Optional["PropertyProfile"] = None,
) -> List[AnalogCandidate]:
    """Generate analog candidates based on binding analysis.

    Focuses modifications on optimization targets (weakly-interacting,
    clashing, or solvent-exposed groups).

    Parameters
    ----------
    ligand_smiles : str
        Canonical SMILES of the parent ligand.
    analysis : BindingAnalysisResult
        Output from run_binding_analysis().
    max_analogs : int
        Maximum number of analogs to generate.
    enable_bioisosteres : bool
        Enable bioisostere replacements.
    enable_extensions : bool
        Enable group extensions.
    enable_removals : bool
        Enable group removal/simplification.
    enable_prodrug_esters : bool
        Enable pro-drug ester generation for carboxylates.
    enable_metabolic_blocking : bool
        Enable CYP450 metabolic soft spot blocking (v0.9.2).
    enable_scaffold_hopping : bool
        Enable scaffold hopping ring transformations (v0.9.2).
    enable_thioether_detection : bool
        Enable thioether cyclization candidate generation (v0.9.2).
    max_scaffold_hops : int
        Maximum scaffold hop candidates to generate.
    target_window : dict, optional
        Property target window for bias filtering. If None, no filtering.

    Returns
    -------
    List[AnalogCandidate]
        Deduplicated, validated analog candidates.
    """
    from rdkit import Chem

    mol = Chem.MolFromSmiles(ligand_smiles)
    if mol is None:
        logger.error("Cannot parse parent SMILES: %s", ligand_smiles)
        return []

    candidates: List[AnalogCandidate] = []

    # Get optimization targets sorted by score
    targets = analysis.optimization_targets
    if not targets:
        logger.warning("No optimization targets identified, generating untargeted analogs")
        targets_to_use = [
            (i, grp.group_type)
            for i, grp in enumerate(analysis.functional_groups)
        ]
    else:
        targets_to_use = [
            (t.group_idx, t.group_type)
            for t in targets
        ]

    logger.info("Generating analogs for %d optimization targets (max=%d)",
                len(targets_to_use), max_analogs)

    # Step 1: Bioisostere replacements
    if enable_bioisosteres:
        bio_candidates = _apply_bioisostere_replacements(mol, ligand_smiles)
        candidates.extend(bio_candidates)
        logger.info("Generated %d bioisostere candidates", len(bio_candidates))

    # Step 2: Group extensions (targeted at optimization targets)
    if enable_extensions:
        ext_candidates = _apply_group_extensions(mol, ligand_smiles, analysis)
        candidates.extend(ext_candidates)
        logger.info("Generated %d extension candidates", len(ext_candidates))

    # Step 3: Group removals (for weakly-interacting groups)
    if enable_removals:
        rem_candidates = _apply_group_removals(mol, ligand_smiles, analysis)
        candidates.extend(rem_candidates)
        logger.info("Generated %d removal candidates", len(rem_candidates))

    # Step 4: Pro-drug esters for carboxylates
    if enable_prodrug_esters:
        logp_range = (
            target_window.get("logp_min", 1.0) if target_window else 1.0,
            target_window.get("logp_max", 3.0) if target_window else 3.0,
        )
        ester_candidates = generate_prodrug_esters(ligand_smiles, logp_range)
        candidates.extend(ester_candidates)
        logger.info("Generated %d pro-drug ester candidates", len(ester_candidates))

    # Step 5: Metabolic soft spot blocking (v0.9.2)
    if enable_metabolic_blocking:
        soft_spots = identify_metabolic_soft_spots(ligand_smiles)
        if soft_spots:
            block_candidates = generate_metabolic_blocks(
                ligand_smiles, soft_spots, target_window)
            candidates.extend(block_candidates)
            logger.info("Generated %d metabolic blocking candidates", len(block_candidates))

    # Step 6: Scaffold hopping (v0.9.2)
    if enable_scaffold_hopping:
        hop_candidates = generate_scaffold_hops(
            ligand_smiles, analysis, max_hops=max_scaffold_hops)
        candidates.extend(hop_candidates)
        logger.info("Generated %d scaffold hop candidates", len(hop_candidates))

    # Step 7: Thioether cyclization candidates (v0.9.2)
    if enable_thioether_detection:
        thioether_sites = detect_thioether_sites(ligand_smiles)
        if thioether_sites:
            logger.info("Found %d thioether cyclization sites", len(thioether_sites))
            # Note: actual thioether ring closure is complex (RWMol bond formation)
            # For now, flag the sites; full generation can be added later
            for site in thioether_sites:
                candidates.append(AnalogCandidate(
                    smiles=ligand_smiles,  # placeholder — actual cyclized product TBD
                    parent_smiles=ligand_smiles,
                    modification_type="thioether_site",
                    target_group="thiol",
                    target_group_idx=site.thiol_idx,
                    rationale=(f"thioether cyclization opportunity: S({site.thiol_idx})-"
                              f"C({site.carbon_idx}), dist={site.topological_dist} bonds, "
                              f"leaving_group={site.leaving_group}"),
                    estimated_impact="cyclization_stability",
                ))

    # Step 8: Catechol-specific SAR (v0.9.3) — auto-detect catechol presence
    if enable_bioisosteres:
        from rdkit import Chem as _Chem_cat
        _catechol_q = _Chem_cat.MolFromSmarts("c1cc(O)c(O)cc1")
        if _catechol_q and mol.HasSubstructMatch(_catechol_q):
            cat_candidates = generate_catechol_modifications(
                ligand_smiles, target_window)
            candidates.extend(cat_candidates)
            logger.info("Generated %d catechol SAR candidates", len(cat_candidates))

    # Step 9: Permeability-aware analogs (v0.9.3) — when parent has high PSA
    _parent_pp = parent_profile or compute_property_profile(ligand_smiles)
    if _parent_pp and _parent_pp.psa > 100:
        perm_candidates = generate_permeability_analogs(
            ligand_smiles, target_window)
        candidates.extend(perm_candidates)
        logger.info("Generated %d permeability-focused candidates (parent PSA=%.1f)",
                     len(perm_candidates), _parent_pp.psa)

    # Deduplicate and validate
    candidates = _deduplicate(candidates)
    candidates = [c for c in candidates if validate_structure(c.smiles)]

    # Property bias filtering (with adaptive relaxation for bad-profile parents, v0.9.3)
    if target_window:
        candidates = filter_by_property_window(candidates, target_window, parent_profile=parent_profile)

    # Trim to max
    if len(candidates) > max_analogs:
        candidates = candidates[:max_analogs]

    logger.info("Final: %d validated analog candidates", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Combinatorial expansion of passing modifications
# ---------------------------------------------------------------------------

def generate_combinatorial_analogs(
    parent_smiles: str,
    passing_modifications: List[Modification],
    analysis,  # BindingAnalysisResult
    max_combos: int = 100,
    combo_size: int = 2,
    target_window: Optional[dict] = None,
    parent_profile: Optional["PropertyProfile"] = None,
) -> List[AnalogCandidate]:
    """Generate combinatorial analogs from passing single-site modifications.

    For round N+1, combines pairs (and triples if combo_size >= 3) of
    modifications from different sites that individually improved affinity.

    Parameters
    ----------
    parent_smiles : str
        Original parent SMILES.
    passing_modifications : List[Modification]
        Modifications that passed in previous rounds.
    analysis : BindingAnalysisResult
        Binding analysis from the parent structure.
    max_combos : int
        Maximum number of combinatorial candidates to generate.
    combo_size : int
        Max number of modifications to combine (2 = pairs, 3 = triples).
    target_window : dict, optional
        Property target window for filtering.

    Returns
    -------
    List[AnalogCandidate]
        Validated combinatorial analog candidates.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    if len(passing_modifications) < 2:
        return []

    # Group modifications by site to avoid combining from the same site
    by_site: Dict[int, List[Modification]] = {}
    for mod in passing_modifications:
        by_site.setdefault(mod.site_idx, []).append(mod)

    if len(by_site) < 2:
        logger.info("All passing modifications are at the same site, skipping combos")
        return []

    site_keys = list(by_site.keys())
    candidates = []

    # Generate combinations of sites
    for combo_n in range(2, min(combo_size, len(site_keys)) + 1):
        for site_combo in itertools.combinations(site_keys, combo_n):
            # For each site combination, pick best modification per site
            mods_to_combine = []
            for site in site_combo:
                mods_to_combine.append(by_site[site][0])  # first = best (already sorted)

            # Apply modifications sequentially to the parent
            current_smiles = parent_smiles
            descriptions = []
            valid = True

            for mod in mods_to_combine:
                new_smi = _apply_single_modification(current_smiles, mod)
                if new_smi is None or new_smi == current_smiles:
                    valid = False
                    break
                current_smiles = new_smi
                descriptions.append(mod.smarts_or_desc)

            if valid and current_smiles != parent_smiles:
                if validate_structure(current_smiles):
                    candidates.append(AnalogCandidate(
                        smiles=current_smiles,
                        parent_smiles=parent_smiles,
                        modification_type="combinatorial",
                        target_group="multi-site",
                        rationale=f"combo: {' + '.join(descriptions)}",
                        estimated_impact="synergistic",
                    ))

            if len(candidates) >= max_combos:
                break
        if len(candidates) >= max_combos:
            break

    # Deduplicate and validate
    candidates = _deduplicate(candidates)
    candidates = [c for c in candidates if validate_structure(c.smiles)]

    # Property filtering
    if target_window:
        candidates = filter_by_property_window(candidates, target_window, parent_profile=parent_profile)

    if len(candidates) > max_combos:
        candidates = candidates[:max_combos]

    logger.info("Generated %d combinatorial candidates from %d passing modifications",
                len(candidates), len(passing_modifications))
    return candidates


def _apply_single_modification(smiles: str, mod: Modification) -> Optional[str]:
    """Re-apply a single modification to a SMILES string.

    This tries the same bioisostere/extension/removal transformation
    that produced mod.result_smiles originally, but on the given SMILES.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    if mod.mod_type == "bioisostere":
        # Try to apply the SMARTS -> replacement
        for query_smarts, repl_smiles, desc in BIOISOSTERE_TABLE:
            if desc == mod.smarts_or_desc or query_smarts == mod.smarts_or_desc:
                query = Chem.MolFromSmarts(query_smarts)
                replacement = Chem.MolFromSmiles(repl_smiles)
                if query is None or replacement is None:
                    continue
                if not mol.HasSubstructMatch(query):
                    continue
                products = AllChem.ReplaceSubstructs(mol, query, replacement)
                for product in products[:1]:
                    try:
                        Chem.SanitizeMol(product)
                        return Chem.MolToSmiles(product)
                    except Exception:
                        continue
        return None

    elif mod.mod_type == "extension":
        # Try adding a fragment at the target site
        for frag_name, frag_smiles, frag_desc in EXTENSION_FRAGMENTS:
            if frag_desc in mod.smarts_or_desc:
                if mod.site_idx < mol.GetNumAtoms():
                    return _add_fragment_at_atom(mol, mod.site_idx, frag_smiles)
        return None

    elif mod.mod_type == "removal":
        # Not easily re-applicable in combo mode
        return None

    return None


def extract_modifications(
    passing_results,  # List of (AnalogCandidate, DockingResult) tuples
    parent_smiles: str,
) -> List[Modification]:
    """Extract Modification objects from passing analog results."""
    mods = []
    for analog, dock_result in passing_results:
        mods.append(Modification(
            site_idx=analog.target_group_idx if analog.target_group_idx >= 0 else 0,
            mod_type=analog.modification_type,
            smarts_or_desc=analog.rationale,
            parent_smiles=parent_smiles,
            result_smiles=analog.smiles,
        ))
    return mods


# ---------------------------------------------------------------------------
# Bioisostere replacements
# ---------------------------------------------------------------------------

def _apply_bioisostere_replacements(
    mol,  # RDKit Mol
    parent_smiles: str,
) -> List[AnalogCandidate]:
    """Apply bioisostere replacements from the table."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    candidates = []

    for query_smarts, repl_smiles, description in BIOISOSTERE_TABLE:
        try:
            query = Chem.MolFromSmarts(query_smarts)
            replacement = Chem.MolFromSmiles(repl_smiles)
            if query is None or replacement is None:
                continue

            matches = mol.GetSubstructMatches(query)
            if not matches:
                continue

            # Apply replacement to first match only (avoid combinatorial explosion)
            products = AllChem.ReplaceSubstructs(mol, query, replacement)
            for product in products[:1]:  # take first product
                try:
                    Chem.SanitizeMol(product)
                    smi = Chem.MolToSmiles(product)
                    if smi and smi != parent_smiles:
                        candidates.append(AnalogCandidate(
                            smiles=smi,
                            parent_smiles=parent_smiles,
                            modification_type="bioisostere",
                            target_group=query_smarts,
                            rationale=description,
                            estimated_impact="altered_interactions",
                        ))
                except Exception:
                    continue

        except Exception as e:
            logger.debug("Bioisostere replacement failed for %s: %s", description, e)

    return candidates


# ---------------------------------------------------------------------------
# Group extensions
# ---------------------------------------------------------------------------

def _apply_group_extensions(
    mol,  # RDKit Mol
    parent_smiles: str,
    analysis,  # BindingAnalysisResult
) -> List[AnalogCandidate]:
    """Add small fragments at sites with exit vectors."""
    from rdkit import Chem

    candidates = []

    # Focus on optimization targets with exit vectors
    for target in analysis.optimization_targets:
        if not target.exit_vectors:
            continue

        group = analysis.functional_groups[target.group_idx]

        # For each atom in the group, try adding fragments
        for aidx in group.atom_indices:
            if aidx >= mol.GetNumAtoms():
                continue

            atom = mol.GetAtomWithIdx(aidx)

            # Only extend atoms with available valence
            max_valence = _max_valence(atom)
            current_valence = atom.GetTotalValence()
            if current_valence >= max_valence:
                continue

            for frag_name, frag_smiles, frag_desc in EXTENSION_FRAGMENTS:
                try:
                    new_smi = _add_fragment_at_atom(mol, aidx, frag_smiles)
                    if new_smi and new_smi != parent_smiles:
                        candidates.append(AnalogCandidate(
                            smiles=new_smi,
                            parent_smiles=parent_smiles,
                            modification_type="extension",
                            target_group=group.group_type,
                            target_group_idx=target.group_idx,
                            rationale=f"{frag_desc} at {group.group_type} ({target.rationale})",
                            estimated_impact="extended_reach",
                        ))
                except Exception:
                    continue

    return candidates


def _add_fragment_at_atom(mol, atom_idx: int, fragment_smiles: str) -> Optional[str]:
    """Add a fragment to a molecule at a specific atom via RWMol."""
    from rdkit import Chem

    rwmol = Chem.RWMol(mol)
    atom = rwmol.GetAtomWithIdx(atom_idx)

    # Check available valence
    max_val = _max_valence(atom)
    curr_val = atom.GetTotalValence()
    if curr_val >= max_val:
        return None

    # Parse fragment
    frag = Chem.MolFromSmiles(fragment_smiles)
    if frag is None:
        return None

    # Add fragment atoms
    atom_map = {}
    for fa in frag.GetAtoms():
        new_idx = rwmol.AddAtom(Chem.Atom(fa.GetAtomicNum()))
        atom_map[fa.GetIdx()] = new_idx

    # Add fragment bonds
    for bond in frag.GetBonds():
        rwmol.AddBond(
            atom_map[bond.GetBeginAtomIdx()],
            atom_map[bond.GetEndAtomIdx()],
            bond.GetBondType(),
        )

    # Connect fragment to target atom (bond to first fragment atom)
    rwmol.AddBond(atom_idx, atom_map[0], Chem.BondType.SINGLE)

    try:
        Chem.SanitizeMol(rwmol)
        return Chem.MolToSmiles(rwmol)
    except Exception:
        return None


def _max_valence(atom) -> int:
    """Get max valence for an atom."""
    valence_table = {6: 4, 7: 3, 8: 2, 9: 1, 15: 5, 16: 6, 17: 1, 35: 1, 53: 1}
    return valence_table.get(atom.GetAtomicNum(), 4)


# ---------------------------------------------------------------------------
# Group removals
# ---------------------------------------------------------------------------

def _apply_group_removals(
    mol,  # RDKit Mol
    parent_smiles: str,
    analysis,  # BindingAnalysisResult
) -> List[AnalogCandidate]:
    """Remove or simplify weakly-interacting functional groups."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    candidates = []

    # Target groups with very low interaction scores
    for target in analysis.optimization_targets:
        group = analysis.functional_groups[target.group_idx]
        if group.interaction_score > 3.0:
            continue  # don't remove groups that contribute significantly

        # Try replacing the group pattern with hydrogen
        try:
            query = Chem.MolFromSmarts(group.smarts)
            if query is None:
                continue

            h_mol = Chem.MolFromSmiles("[H]")
            products = AllChem.ReplaceSubstructs(mol, query, h_mol)

            for product in products[:1]:
                try:
                    # Remove explicit Hs and sanitize
                    product = Chem.RemoveHs(product)
                    Chem.SanitizeMol(product)
                    smi = Chem.MolToSmiles(product)
                    if smi and smi != parent_smiles and len(smi) > 1:
                        candidates.append(AnalogCandidate(
                            smiles=smi,
                            parent_smiles=parent_smiles,
                            modification_type="removal",
                            target_group=group.group_type,
                            target_group_idx=target.group_idx,
                            rationale=f"removed {group.group_type} (interaction_score={group.interaction_score:.1f})",
                            estimated_impact="reduced_size",
                        ))
                except Exception:
                    continue

        except Exception as e:
            logger.debug("Group removal failed for %s: %s", group.group_type, e)

    return candidates


# ---------------------------------------------------------------------------
# Enhanced bond/structure validation
# ---------------------------------------------------------------------------

def validate_structure(smiles: str) -> bool:
    """Validate that an analog SMILES represents a reasonable, synthesizable molecule.

    Checks:
    - Valid SMILES (parseable by RDKit)
    - Sanitization passes (catches valence violations)
    - Non-empty molecule (>0 atoms)
    - No disconnected fragments
    - MW within reasonable range (50-800)
    - No reactive groups (azide, acyl halide, diazo)
    - No impossible ring strain (3-membered rings with sp2 atoms)
    - No atoms with absurd formal charges
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False

    # Non-empty
    if mol.GetNumAtoms() == 0:
        return False

    # Sanitization (catches valence errors)
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return False

    # No disconnected fragments
    frags = Chem.GetMolFrags(mol)
    if len(frags) > 1:
        return False

    # Check MW
    mw = Descriptors.MolWt(mol)
    if mw > 800 or mw < 50:
        return False

    # Check for reactive groups (diazo, azide, acyl halide)
    reactive_smarts = [
        "[N]=[N]=[N]",              # azide
        "[CX3](=O)[F,Cl,Br,I]",    # acyl halide
        "[N]=[N+]=[N-]",            # diazo
    ]
    for sma in reactive_smarts:
        pattern = Chem.MolFromSmarts(sma)
        if pattern and mol.HasSubstructMatch(pattern):
            return False

    # Check for extreme formal charges
    for atom in mol.GetAtoms():
        fc = atom.GetFormalCharge()
        if abs(fc) > 2:
            return False

    # Check for strained 3-membered rings with sp2 atoms
    ring_info = mol.GetRingInfo()
    for ring in ring_info.AtomRings():
        if len(ring) == 3:
            for aidx in ring:
                atom = mol.GetAtomWithIdx(aidx)
                hyb = str(atom.GetHybridization())
                if "SP2" in hyb:
                    return False

    return True


# ---------------------------------------------------------------------------
# Validation and deduplication (legacy wrapper)
# ---------------------------------------------------------------------------

def _validate_analog(smiles: str) -> bool:
    """Legacy wrapper. Use validate_structure() instead."""
    return validate_structure(smiles)


def _deduplicate(candidates: List[AnalogCandidate]) -> List[AnalogCandidate]:
    """Remove duplicate SMILES, keeping first occurrence."""
    from rdkit import Chem

    seen = set()
    unique = []
    for c in candidates:
        mol = Chem.MolFromSmiles(c.smiles)
        if mol is None:
            continue
        canonical = Chem.MolToSmiles(mol)
        if canonical not in seen:
            seen.add(canonical)
            c.smiles = canonical
            unique.append(c)
    return unique
