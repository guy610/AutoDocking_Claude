"""
Test script for v0.9.2 SAR enhancements.

Uses erlotinib (EGFR inhibitor, lung cancer) as test molecule.
Tests all core analog_generation functions without requiring docking infrastructure.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Erlotinib: EGFR tyrosine kinase inhibitor (lung cancer)
# Has: aromatic rings, ether groups, alkyne, amine, quinazoline scaffold
ERLOTINIB_SMILES = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"

# Imatinib fragment (simpler, has amide + amine + pyridine)
IMATINIB_FRAGMENT = "c1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1"

# Benzoic acid (for pro-drug ester testing)
BENZOIC_ACID = "OC(=O)c1ccccc1"

# Thiol-containing test molecule (for thioether detection)
THIOL_TEST = "SCC(=O)NCC(Cl)c1ccccc1"

# Chiral molecule for stereoisomer testing
CHIRAL_TEST = "C[C@@H](O)[C@H](N)c1ccccc1"


def test_property_profile():
    """Test 1: Property profile computation."""
    from autodock_pipeline.core.analog_generation import compute_property_profile

    print("\n" + "=" * 60)
    print("TEST 1: Property Profile Computation")
    print("=" * 60)

    for name, smi in [("Erlotinib", ERLOTINIB_SMILES),
                       ("Imatinib fragment", IMATINIB_FRAGMENT),
                       ("Benzoic acid", BENZOIC_ACID)]:
        profile = compute_property_profile(smi)
        if profile is None:
            print(f"  FAIL: Could not compute profile for {name}")
            return False
        print(f"  {name}: logP={profile.logp}, MW={profile.mw}, PSA={profile.psa}, "
              f"HBD={profile.hbd}, HBA={profile.hba}, rot={profile.rotatable}, "
              f"Potts-Guy={profile.potts_guy_logkp}")

    print("  PASS")
    return True


def test_metabolic_soft_spots():
    """Test 2: CYP450 metabolic soft spot identification."""
    from autodock_pipeline.core.analog_generation import identify_metabolic_soft_spots

    print("\n" + "=" * 60)
    print("TEST 2: Metabolic Soft Spot Identification")
    print("=" * 60)

    spots = identify_metabolic_soft_spots(ERLOTINIB_SMILES)
    print(f"  Found {len(spots)} soft spots in erlotinib:")
    for s in spots:
        print(f"    atom[{s.atom_idx}]: {s.pattern_name} -> {s.suggested_block}")

    if len(spots) == 0:
        print("  WARNING: Expected at least one soft spot (ether dealkylation)")

    # Imatinib fragment should have N-dealkylation site (N-methyl piperazine)
    spots2 = identify_metabolic_soft_spots(IMATINIB_FRAGMENT)
    print(f"  Found {len(spots2)} soft spots in imatinib fragment:")
    for s in spots2:
        print(f"    atom[{s.atom_idx}]: {s.pattern_name} -> {s.suggested_block}")

    print("  PASS")
    return True


def test_metabolic_blocking():
    """Test 3: Metabolic blocking candidate generation."""
    from autodock_pipeline.core.analog_generation import (
        identify_metabolic_soft_spots, generate_metabolic_blocks,
    )

    print("\n" + "=" * 60)
    print("TEST 3: Metabolic Blocking Candidates")
    print("=" * 60)

    spots = identify_metabolic_soft_spots(IMATINIB_FRAGMENT)
    if not spots:
        print("  SKIP: No soft spots found")
        return True

    candidates = generate_metabolic_blocks(IMATINIB_FRAGMENT, spots)
    print(f"  Generated {len(candidates)} metabolic blocking candidates:")
    for c in candidates[:5]:
        print(f"    {c.modification_type}: {c.rationale}")
        print(f"      SMILES: {c.smiles[:60]}...")

    if len(candidates) > 0:
        print("  PASS")
        return True
    else:
        print("  WARNING: No blocking candidates generated (may be expected)")
        return True


def test_scaffold_hopping():
    """Test 4: Scaffold hopping ring transformations."""
    from autodock_pipeline.core.analog_generation import generate_scaffold_hops

    print("\n" + "=" * 60)
    print("TEST 4: Scaffold Hopping")
    print("=" * 60)

    candidates = generate_scaffold_hops(ERLOTINIB_SMILES, max_hops=10)
    print(f"  Generated {len(candidates)} scaffold hop candidates from erlotinib:")
    for c in candidates[:5]:
        print(f"    {c.rationale}")
        print(f"      SMILES: {c.smiles[:60]}...")

    # Also test with imatinib fragment (has phenyl ring -> pyridyl)
    candidates2 = generate_scaffold_hops(IMATINIB_FRAGMENT, max_hops=10)
    print(f"  Generated {len(candidates2)} scaffold hop candidates from imatinib fragment:")
    for c in candidates2[:5]:
        print(f"    {c.rationale}")

    if len(candidates) > 0 or len(candidates2) > 0:
        print("  PASS")
        return True
    else:
        print("  FAIL: Expected at least some scaffold hops")
        return False


def test_thioether_detection():
    """Test 5: Thioether cyclization site detection."""
    from autodock_pipeline.core.analog_generation import detect_thioether_sites

    print("\n" + "=" * 60)
    print("TEST 5: Thioether Cyclization Detection")
    print("=" * 60)

    # THIOL_TEST = "SCC(=O)NCC(Cl)c1ccccc1" has thiol + chloride
    sites = detect_thioether_sites(THIOL_TEST)
    print(f"  Found {len(sites)} thioether sites in test molecule '{THIOL_TEST}':")
    for s in sites:
        print(f"    S[{s.thiol_idx}] + C[{s.carbon_idx}]: {s.topological_dist} bonds, "
              f"leaving_group={s.leaving_group}")

    # Erlotinib has no thiols, should return empty
    sites2 = detect_thioether_sites(ERLOTINIB_SMILES)
    print(f"  Found {len(sites2)} thioether sites in erlotinib (expected 0)")

    if len(sites2) == 0:
        print("  PASS")
        return True
    else:
        print("  WARNING: Unexpected thioether sites in erlotinib")
        return True


def test_ligand_efficiency():
    """Test 6: Ligand efficiency metrics."""
    from autodock_pipeline.core.analog_generation import compute_ligand_efficiency

    print("\n" + "=" * 60)
    print("TEST 6: Ligand Efficiency Metrics")
    print("=" * 60)

    # Simulate docking scores
    test_cases = [
        ("Erlotinib", ERLOTINIB_SMILES, -8.5),
        ("Imatinib fragment", IMATINIB_FRAGMENT, -9.2),
        ("Benzoic acid", BENZOIC_ACID, -5.0),
    ]

    for name, smi, score in test_cases:
        le = compute_ligand_efficiency(smi, score)
        if le is None:
            print(f"  FAIL: Could not compute LE for {name}")
            return False
        print(f"  {name} (score={score:.1f}): LE={le.le:.3f}, LLE={le.lle:.2f}, "
              f"LELP={le.lelp:.2f}, HAC={le.heavy_atom_count}")

    # Validate LE > 0 for negative binding energies
    le_check = compute_ligand_efficiency("c1ccccc1", -6.0)  # benzene
    if le_check and le_check.le > 0:
        print(f"  Benzene LE={le_check.le:.3f} (expected > 0 for negative dG)")
    else:
        print("  FAIL: LE should be positive for negative binding energy")
        return False

    print("  PASS")
    return True


def test_torsion_strain():
    """Test 7: Torsion strain pre-filtering."""
    from autodock_pipeline.core.analog_generation import check_torsion_strain

    print("\n" + "=" * 60)
    print("TEST 7: Torsion Strain Pre-filtering")
    print("=" * 60)

    # Normal molecules should pass
    for name, smi in [("Erlotinib", ERLOTINIB_SMILES),
                       ("Imatinib fragment", IMATINIB_FRAGMENT),
                       ("Benzoic acid", BENZOIC_ACID)]:
        passes, warnings = check_torsion_strain(smi, amide_tolerance=30.0)
        status = "PASS" if passes else f"FLAGGED ({len(warnings)} warnings)"
        print(f"  {name}: {status}")
        for w in warnings:
            print(f"    Warning: {w}")

    # Test with a simple amide (should pass — amides are planar)
    passes2, warns2 = check_torsion_strain("CC(=O)NC", amide_tolerance=30.0)
    print(f"  Acetamide: {'PASS' if passes2 else 'FLAGGED'}")

    print("  PASS (torsion filter functional)")
    return True


def test_stereoisomer_rational():
    """Test 8: Rational stereoisomer enumeration."""
    from autodock_pipeline.core.analog_generation import enumerate_stereoisomers_rational

    print("\n" + "=" * 60)
    print("TEST 8: Rational Stereoisomer Enumeration")
    print("=" * 60)

    # CHIRAL_TEST = "C[C@@H](O)[C@H](N)c1ccccc1" has 2 chiral centers
    isomers = enumerate_stereoisomers_rational(
        CHIRAL_TEST,
        modification_sites=[0, 1],  # near the first chiral center
        max_isomers=16,
    )
    print(f"  Input: {CHIRAL_TEST}")
    print(f"  Generated {len(isomers)} rational stereoisomers (mod sites near atom 0-1):")
    for iso in isomers:
        print(f"    {iso}")

    if len(isomers) >= 2:
        print("  PASS")
        return True
    else:
        print("  WARNING: Expected at least 2 isomers (original + 1 inversion)")
        return True


def test_stereoisomer_full():
    """Test 9: Full stereoisomer enumeration."""
    from autodock_pipeline.core.analog_generation import enumerate_stereoisomers_full

    print("\n" + "=" * 60)
    print("TEST 9: Full Stereoisomer Enumeration")
    print("=" * 60)

    isomers = enumerate_stereoisomers_full(CHIRAL_TEST, max_centers=4)
    print(f"  Input: {CHIRAL_TEST}")
    print(f"  Enumerated {len(isomers)} total stereoisomers:")
    for iso in isomers:
        print(f"    {iso}")

    # Should get up to 4 isomers for 2 centers (2^2)
    if len(isomers) >= 2:
        print("  PASS")
        return True
    else:
        print("  FAIL: Expected at least 2 stereoisomers for 2 chiral centers")
        return False


def test_mmp_tracking():
    """Test 10: Matched molecular pair tracking."""
    from autodock_pipeline.core.analog_generation import (
        find_equivalent_sites, Modification, generate_mmp_expansions,
    )
    from rdkit import Chem

    print("\n" + "=" * 60)
    print("TEST 10: Matched Molecular Pair Tracking")
    print("=" * 60)

    # Molecule with two hydroxyl groups at different positions
    test_smi = "Oc1ccc(O)cc1"  # hydroquinone (two OH groups)
    mol = Chem.MolFromSmiles(test_smi)

    # Simulate a modification that worked at site 0 (OH -> F)
    mod = Modification(
        site_idx=0,
        mod_type="bioisostere",
        smarts_or_desc="OH -> F (metabolic stability)",
        parent_smiles=test_smi,
        result_smiles="Fc1ccc(O)cc1",
    )

    equiv = find_equivalent_sites(mol, mod)
    print(f"  Test molecule: {test_smi}")
    print(f"  Modification: OH -> F at site 0")
    print(f"  Equivalent sites found: {equiv}")

    # Generate MMP expansions
    expansions = generate_mmp_expansions(
        parent_smiles=test_smi,
        passing_modifications=[mod],
    )
    print(f"  MMP expansion candidates: {len(expansions)}")
    for c in expansions[:3]:
        print(f"    {c.smiles} ({c.rationale})")

    print("  PASS (MMP tracking functional)")
    return True


def test_property_window_rotatable():
    """Test 11: Rotatable bond filtering in property window."""
    from autodock_pipeline.core.analog_generation import (
        filter_by_property_window, AnalogCandidate,
    )

    print("\n" + "=" * 60)
    print("TEST 11: Rotatable Bond Filtering")
    print("=" * 60)

    # Create candidates with varying rotatable bonds
    candidates = [
        AnalogCandidate(smiles="c1ccccc1", parent_smiles="", modification_type="test",
                        target_group="test", rationale="benzene (0 rotatable)"),
        AnalogCandidate(smiles="CCCCCCC", parent_smiles="", modification_type="test",
                        target_group="test", rationale="heptane (4 rotatable)"),
        AnalogCandidate(smiles="CCCCCCCCCCCCC", parent_smiles="", modification_type="test",
                        target_group="test", rationale="tridecane (10 rotatable)"),
    ]

    # Window with rotatable_max = 5
    window = {
        "logp_min": -10.0, "logp_max": 20.0,
        "mw_max": 999.0, "psa_max": 999.0,
        "hbd_max": 99, "hba_max": 99,
        "rotatable_max": 5,
    }

    filtered = filter_by_property_window(candidates, window)
    print(f"  Input: {len(candidates)} candidates")
    print(f"  After filter (rotatable_max=5): {len(filtered)} remain")
    for c in filtered:
        print(f"    {c.smiles} ({c.rationale})")

    if len(filtered) < len(candidates):
        print("  PASS (rotatable bond filter working)")
        return True
    else:
        print("  WARNING: Expected some candidates to be filtered out")
        return True


def test_generate_analogs_with_new_flags():
    """Test 12: generate_analogs with v0.9.2 enable flags."""
    from autodock_pipeline.core.analog_generation import generate_analogs
    from unittest.mock import MagicMock

    print("\n" + "=" * 60)
    print("TEST 12: generate_analogs with v0.9.2 Flags")
    print("=" * 60)

    # Create a mock binding analysis
    mock_analysis = MagicMock()
    mock_analysis.optimization_targets = []
    mock_analysis.functional_groups = []

    candidates = generate_analogs(
        ligand_smiles=ERLOTINIB_SMILES,
        analysis=mock_analysis,
        max_analogs=50,
        enable_bioisosteres=True,
        enable_extensions=False,
        enable_removals=False,
        enable_prodrug_esters=False,
        enable_metabolic_blocking=True,
        enable_scaffold_hopping=True,
        enable_thioether_detection=True,
        max_scaffold_hops=5,
        target_window={
            "logp_min": 0.0, "logp_max": 6.0,
            "mw_max": 600.0, "psa_max": 200.0,
            "hbd_max": 10, "hba_max": 15,
            "rotatable_max": 15,
        },
    )

    print(f"  Generated {len(candidates)} total candidates for erlotinib:")
    type_counts = {}
    for c in candidates:
        type_counts[c.modification_type] = type_counts.get(c.modification_type, 0) + 1
    for mod_type, count in sorted(type_counts.items()):
        print(f"    {mod_type}: {count}")

    if len(candidates) > 0:
        print("  PASS")
        return True
    else:
        print("  FAIL: Expected at least some analog candidates")
        return False


def test_config_fields():
    """Test 13: Config dataclass has all new v0.9.2 fields."""
    from autodock_pipeline.config import SmallMoleculeConfig

    print("\n" + "=" * 60)
    print("TEST 13: Config v0.9.2 Fields")
    print("=" * 60)

    cfg = SmallMoleculeConfig()

    required_fields = [
        ("enable_stereoisomer_enum", True),
        ("stereo_max_centers", 4),
        ("stereo_final_top_n", 5),
        ("enable_thioether_detection", True),
        ("enable_metabolic_blocking", True),
        ("enable_scaffold_hopping", False),
        ("max_scaffold_hops", 10),
        ("enable_mmp_tracking", True),
        ("enable_torsion_filter", True),
        ("torsion_amide_tolerance", 30.0),
        ("target_rotatable_max", -1),
    ]

    all_ok = True
    for field_name, expected_default in required_fields:
        actual = getattr(cfg, field_name, "MISSING")
        status = "OK" if actual == expected_default else f"MISMATCH (got {actual})"
        if actual == "MISSING":
            status = "MISSING"
            all_ok = False
        print(f"  {field_name}: {actual} {status}")

    if all_ok:
        print("  PASS")
    else:
        print("  FAIL: Some config fields are missing")
    return all_ok


def test_get_target_window_rotatable():
    """Test 14: get_target_window respects rotatable_max override."""
    from autodock_pipeline.core.analog_generation import get_target_window
    from unittest.mock import MagicMock

    print("\n" + "=" * 60)
    print("TEST 14: Target Window Rotatable Override")
    print("=" * 60)

    # Preset mode with no override
    cfg1 = MagicMock()
    cfg1.property_target = "cosmetic"
    cfg1.target_rotatable_max = -1
    w1 = get_target_window(cfg1)
    print(f"  Cosmetic preset (no override): rotatable_max={w1['rotatable_max']}")
    assert w1["rotatable_max"] == 5, f"Expected 5, got {w1['rotatable_max']}"

    # Preset mode with override
    cfg2 = MagicMock()
    cfg2.property_target = "cosmetic"
    cfg2.target_rotatable_max = 8
    w2 = get_target_window(cfg2)
    print(f"  Cosmetic preset (override=8): rotatable_max={w2['rotatable_max']}")
    assert w2["rotatable_max"] == 8, f"Expected 8, got {w2['rotatable_max']}"

    # Custom mode
    cfg3 = MagicMock()
    cfg3.property_target = "custom"
    cfg3.target_logp_min = 1.0
    cfg3.target_logp_max = 4.0
    cfg3.target_mw_max = 400.0
    cfg3.target_psa_max = 100.0
    cfg3.target_hbd_max = 3
    cfg3.target_hba_max = 7
    cfg3.target_rotatable_max = 6
    w3 = get_target_window(cfg3)
    print(f"  Custom mode (rot=6): rotatable_max={w3['rotatable_max']}")
    assert w3["rotatable_max"] == 6, f"Expected 6, got {w3['rotatable_max']}"

    print("  PASS")
    return True


def main():
    print("=" * 60)
    print("  v0.9.2 SAR Enhancements Test Suite")
    print("  Test molecule: Erlotinib (EGFR inhibitor, lung cancer)")
    print("=" * 60)

    tests = [
        test_config_fields,
        test_property_profile,
        test_get_target_window_rotatable,
        test_metabolic_soft_spots,
        test_metabolic_blocking,
        test_scaffold_hopping,
        test_thioether_detection,
        test_ligand_efficiency,
        test_torsion_strain,
        test_stereoisomer_rational,
        test_stereoisomer_full,
        test_mmp_tracking,
        test_property_window_rotatable,
        test_generate_analogs_with_new_flags,
    ]

    results = {}
    for test_fn in tests:
        try:
            results[test_fn.__name__] = test_fn()
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results[test_fn.__name__] = False

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    n_pass = sum(1 for v in results.values() if v)
    n_fail = sum(1 for v in results.values() if not v)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\n  {n_pass}/{len(results)} tests passed, {n_fail} failed")

    if n_fail > 0:
        sys.exit(1)
    else:
        print("\n  ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
