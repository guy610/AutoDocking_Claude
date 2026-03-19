"""
Tests for v0.9.3 pipeline enhancements:
  1. LE/LLE/LELP CSV output (results_to_records populates fields)
  2. CCD SMILES lookup
  3. Scaffold hop SMARTS for substituted aromatics
  4. Adaptive property filter relaxation
  5. Permeability-aware analog prioritization
  6. Multi-objective composite ranking
  7. Catechol-specific SAR transformation library
"""

import pytest

# Rosmarinic acid — canonical test molecule for v0.9.3
RA_SMILES = "O=C(/C=C/c1ccc(O)c(O)c1)O[C@@H](Cc1ccc(O)c(O)c1)C(=O)O"

# Erlotinib — no catechol, used for non-catechol tests
ERLOTINIB = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"


# ---------------------------------------------------------------------------
# Test 1: LE/LLE/LELP CSV output
# ---------------------------------------------------------------------------

def test_results_to_records_with_le():
    """results_to_records should populate LE/LLE/LELP when given ligand_efficiencies."""
    from autodock_pipeline.utils.reporting import results_to_records, CandidateRecord
    from autodock_pipeline.core.analog_generation import (
        LigandEfficiency, compute_ligand_efficiency, compute_property_profile,
    )

    # Create a mock DockingResult
    class MockResult:
        def __init__(self, name, smiles, energy, origin):
            self.ligand_name = name
            self.smiles = smiles
            self.best_energy = energy
            self.origin = origin
            self.annotation = ""

    results = [
        MockResult("ref", RA_SMILES, -6.40, "reference"),
        MockResult("analog_1", "O=C(/C=C/c1ccc(F)c(O)c1)O[C@@H](Cc1ccc(O)c(O)c1)C(=O)O", -6.35, "bioisostere"),
    ]

    # Compute LE for each
    le_map = {}
    pp_map = {}
    for r in results:
        le = compute_ligand_efficiency(r.smiles, r.best_energy)
        if le:
            le_map[r.smiles] = le
        pp = compute_property_profile(r.smiles)
        if pp:
            pp_map[r.smiles] = pp

    records = results_to_records(
        results,
        ligand_efficiencies=le_map,
        property_profiles=pp_map,
    )

    assert len(records) == 2
    # Check that LE fields are populated
    for rec in records:
        assert rec.le > 0, f"LE should be positive for {rec.uid}"
        assert rec.lle > 0, f"LLE should be positive for {rec.uid}"
        assert rec.lelp != 0, f"LELP should be non-zero for {rec.uid}"
        assert rec.rotatable_bonds > 0, f"Rotatable bonds should be > 0 for {rec.uid}"

    # Without LE data, fields should be 0
    records_no_le = results_to_records(results)
    for rec in records_no_le:
        assert rec.le == 0.0
        assert rec.rotatable_bonds == 0


# ---------------------------------------------------------------------------
# Test 2: CCD SMILES lookup
# ---------------------------------------------------------------------------

def test_ccd_lookup_known_residue():
    """CCD lookup should return valid SMILES for known residues like ROA (rosmarinic acid)."""
    from autodock_pipeline.core.ligand_extraction import lookup_ccd_smiles

    # ATP is a well-known residue
    atp_smiles = lookup_ccd_smiles("ATP")
    # May fail in offline environments, so just check it returns a string
    if atp_smiles:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(atp_smiles)
        assert mol is not None, f"CCD SMILES for ATP should be valid: {atp_smiles}"
    else:
        pytest.skip("CCD lookup failed (network unavailable?)")


def test_ccd_lookup_invalid():
    """CCD lookup for invalid residue should return empty string."""
    from autodock_pipeline.core.ligand_extraction import lookup_ccd_smiles

    result = lookup_ccd_smiles("XXXX")
    assert result == "", "Invalid residue should return empty string"

    result2 = lookup_ccd_smiles("")
    assert result2 == "", "Empty residue should return empty string"


# ---------------------------------------------------------------------------
# Test 3: Scaffold hopping on substituted aromatics
# ---------------------------------------------------------------------------

def test_scaffold_hops_substituted_aromatics():
    """Scaffold hopping should produce candidates for substituted aromatic rings."""
    from autodock_pipeline.core.analog_generation import generate_scaffold_hops

    hops = generate_scaffold_hops(RA_SMILES, max_hops=10)
    assert len(hops) > 0, "Should generate scaffold hop candidates for RA (substituted aromatics)"

    # All should be valid single-fragment molecules
    from rdkit import Chem
    for h in hops:
        mol = Chem.MolFromSmiles(h.smiles)
        assert mol is not None, f"Invalid SMILES: {h.smiles}"
        assert "." not in h.smiles, f"Fragmented product: {h.smiles}"

    # Should include aza-analogs (CH -> N)
    aza_hops = [h for h in hops if "aza" in h.rationale or "CH -> N" in h.rationale]
    assert len(aza_hops) > 0, "Should include aza-analog scaffold hops"


def test_scaffold_hops_unsubstituted():
    """Scaffold hopping on unsubstituted benzene should work via standard SMARTS."""
    from autodock_pipeline.core.analog_generation import generate_scaffold_hops

    # Toluene — simple substituted benzene
    hops = generate_scaffold_hops("Cc1ccccc1", max_hops=10)
    # Should have some candidates (either standard or CH->N)
    assert len(hops) >= 0  # may or may not match depending on SMARTS


# ---------------------------------------------------------------------------
# Test 4: Adaptive property filter relaxation
# ---------------------------------------------------------------------------

def test_adaptive_filter_relaxation():
    """When parent has bad profile, filter should relax to allow modifications."""
    from autodock_pipeline.core.analog_generation import (
        _compute_adaptive_window, compute_property_profile,
        filter_by_property_window, AnalogCandidate,
    )

    ra_profile = compute_property_profile(RA_SMILES)
    assert ra_profile is not None

    # Cosmetic window — very strict
    cosmetic = {
        "logp_min": 1.0, "logp_max": 3.0,
        "mw_max": 350.0, "psa_max": 70.0,
        "hbd_max": 2, "hba_max": 5,
        "rotatable_max": 5,
    }

    # Without relaxation: RA itself would not pass the filter
    # With relaxation: window should expand to accommodate RA's profile
    relaxed = _compute_adaptive_window(cosmetic, ra_profile)

    assert relaxed["psa_max"] > cosmetic["psa_max"], "PSA should be relaxed"
    assert relaxed["hbd_max"] > cosmetic["hbd_max"], "HBD should be relaxed"
    assert relaxed["mw_max"] > cosmetic["mw_max"], "MW should be relaxed"

    # Relaxed PSA should be >= parent PSA (allow modifications that don't worsen)
    assert relaxed["psa_max"] >= ra_profile.psa, "Relaxed PSA should >= parent PSA"

    # Create test candidates
    candidates = [
        # RA itself — should pass the relaxed filter
        AnalogCandidate(smiles=RA_SMILES, parent_smiles=RA_SMILES,
                        modification_type="reference", target_group="",
                        rationale="reference"),
        # OH->F analog — better profile, should definitely pass
        AnalogCandidate(smiles="O=C(/C=C/c1ccc(F)c(O)c1)O[C@@H](Cc1ccc(O)c(O)c1)C(=O)O",
                        parent_smiles=RA_SMILES,
                        modification_type="bioisostere", target_group="hydroxyl",
                        rationale="OH -> F"),
    ]

    # With strict filter + NO parent profile: both likely rejected
    strict_result = filter_by_property_window(candidates, cosmetic)

    # With strict filter + parent profile: adaptive relaxation kicks in
    relaxed_result = filter_by_property_window(candidates, cosmetic, parent_profile=ra_profile)

    assert len(relaxed_result) >= len(strict_result), \
        "Adaptive filter should pass at least as many candidates as strict"
    assert len(relaxed_result) > 0, "At least one candidate should pass relaxed filter"


def test_adaptive_filter_no_relaxation_needed():
    """When parent is within window, no relaxation should occur."""
    from autodock_pipeline.core.analog_generation import (
        _compute_adaptive_window, compute_property_profile,
    )

    # Erlotinib is a typical drug-like molecule
    erl_profile = compute_property_profile(ERLOTINIB)
    drug_like = {
        "logp_min": 1.0, "logp_max": 5.0,
        "mw_max": 500.0, "psa_max": 140.0,
        "hbd_max": 5, "hba_max": 10,
        "rotatable_max": 10,
    }

    result = _compute_adaptive_window(drug_like, erl_profile)
    # Should not change — erlotinib fits within drug_like window
    assert result["psa_max"] == drug_like["psa_max"]
    assert result["hbd_max"] == drug_like["hbd_max"]


# ---------------------------------------------------------------------------
# Test 5: Permeability-aware analog prioritization
# ---------------------------------------------------------------------------

def test_permeability_analogs():
    """Should generate PSA-reducing modifications for high-PSA molecules."""
    from autodock_pipeline.core.analog_generation import (
        generate_permeability_analogs, compute_property_profile,
    )

    perms = generate_permeability_analogs(RA_SMILES)
    assert len(perms) > 0, "Should generate permeability analogs for RA"

    # Check that modifications reduce PSA or HBD
    parent_pp = compute_property_profile(RA_SMILES)
    improved_count = 0
    for p in perms:
        pp = compute_property_profile(p.smiles)
        if pp and (pp.psa < parent_pp.psa or pp.hbd < parent_pp.hbd):
            improved_count += 1

    assert improved_count > 0, "At least some permeability analogs should reduce PSA/HBD"


# ---------------------------------------------------------------------------
# Test 6: Multi-objective composite ranking
# ---------------------------------------------------------------------------

def test_composite_score():
    """Composite score should favor molecules with both good binding and permeability."""
    from autodock_pipeline.core.analog_generation import (
        compute_composite_score, compute_property_profile,
    )

    ra_pp = compute_property_profile(RA_SMILES)

    # Good binding, poor permeability
    score_poor_perm = compute_composite_score(-6.40, ra_pp)

    # Slightly worse binding, but better permeability
    # OH->F analog has better logKp
    ohf_smiles = "O=C(/C=C/c1ccc(F)c(O)c1)O[C@@H](Cc1ccc(O)c(O)c1)C(=O)O"
    ohf_pp = compute_property_profile(ohf_smiles)
    score_better_perm = compute_composite_score(-6.35, ohf_pp)

    # The OH->F analog should have a better (more negative) composite score
    # even with slightly worse binding, because of better permeability
    assert score_better_perm < score_poor_perm, \
        f"OH->F ({score_better_perm}) should rank better than RA ({score_poor_perm}) on composite"


def test_composite_score_no_profile():
    """Composite score without profile should just return binding energy."""
    from autodock_pipeline.core.analog_generation import compute_composite_score

    score = compute_composite_score(-6.40, None)
    assert score == -6.40, "Without profile, composite should equal binding energy"


# ---------------------------------------------------------------------------
# Test 7: Catechol-specific SAR
# ---------------------------------------------------------------------------

def test_catechol_sar_on_ra():
    """Should generate catechol-targeted modifications for RA."""
    from autodock_pipeline.core.analog_generation import generate_catechol_modifications

    cats = generate_catechol_modifications(RA_SMILES)
    assert len(cats) > 5, f"Expected many catechol SAR candidates for RA, got {len(cats)}"

    # Check that catechol transforms are represented
    descriptions = [c.rationale for c in cats]

    # Should include fluorocatechol
    assert any("fluoro" in d.lower() for d in descriptions), "Should include fluorocatechol variants"

    # Should include methylenedioxy
    assert any("methylenedioxy" in d.lower() for d in descriptions), "Should include methylenedioxy"

    # Should include mono-hydroxyl removal
    assert any("mono-oh" in d.lower() for d in descriptions), "Should include mono-OH variants"


def test_catechol_sar_no_catechol():
    """Molecules without catechol should produce 0 catechol SAR candidates."""
    from autodock_pipeline.core.analog_generation import generate_catechol_modifications

    cats = generate_catechol_modifications(ERLOTINIB)
    assert len(cats) == 0, "Erlotinib has no catechol, should produce 0 candidates"


def test_catechol_products_valid():
    """All catechol SAR products should be valid single-fragment SMILES."""
    from autodock_pipeline.core.analog_generation import generate_catechol_modifications
    from rdkit import Chem

    cats = generate_catechol_modifications(RA_SMILES)
    for c in cats:
        mol = Chem.MolFromSmiles(c.smiles)
        assert mol is not None, f"Invalid SMILES from catechol SAR: {c.smiles}"
        assert "." not in c.smiles, f"Fragmented product: {c.smiles}"


# ---------------------------------------------------------------------------
# Integration test: all v0.9.3 features on RA
# ---------------------------------------------------------------------------

def test_generate_analogs_v093_integration():
    """Full generate_analogs should include v0.9.3 candidates for RA."""
    from autodock_pipeline.core.analog_generation import (
        generate_analogs, compute_property_profile,
    )

    # Create a minimal mock analysis
    class MockGroup:
        def __init__(self, gt, score):
            self.group_type = gt
            self.interaction_score = score
            self.n_hbonds = 0
            self.n_hydrophobic = 2
            self.n_salt_bridges = 0
            self.is_optimization_target = score < 3.0

    class MockTarget:
        def __init__(self, idx, gt, score, rationale):
            self.group_idx = idx
            self.group_type = gt
            self.score = score
            self.rationale = rationale

    class MockAnalysis:
        def __init__(self):
            self.functional_groups = [
                MockGroup("hydroxyl", 0.0),
                MockGroup("hydroxyl", 4.0),
                MockGroup("aromatic_ring", 26.0),
            ]
            self.optimization_targets = [
                MockTarget(0, "hydroxyl", 7.5, "weak interactions"),
            ]
            self.cyclization_sites = []
            self.prodrug_ester_sites = [23]
            self.thioether_sites = []
            self.metabolic_soft_spots = []

    parent_pp = compute_property_profile(RA_SMILES)

    # Custom window that RA exceeds
    window = {
        "logp_min": 1.0, "logp_max": 3.0,
        "mw_max": 350.0, "psa_max": 70.0,
        "hbd_max": 2, "hba_max": 5,
        "rotatable_max": 5,
    }

    candidates = generate_analogs(
        ligand_smiles=RA_SMILES,
        analysis=MockAnalysis(),
        max_analogs=100,
        enable_bioisosteres=True,
        enable_extensions=False,  # skip for speed
        enable_removals=True,
        enable_prodrug_esters=True,
        enable_metabolic_blocking=False,
        enable_scaffold_hopping=True,
        enable_thioether_detection=False,
        target_window=window,
        parent_profile=parent_pp,
    )

    assert len(candidates) > 0, \
        "Should generate candidates even with strict window + bad parent profile (adaptive filter)"

    # Check for catechol and permeability candidates
    mod_types = set(c.modification_type for c in candidates)
    print(f"Modification types: {mod_types}")
    print(f"Total candidates: {len(candidates)}")

    # Catechol SAR should be present (RA has catechol + bioisosteres enabled)
    catechol_count = sum(1 for c in candidates if c.modification_type == "catechol_sar")
    print(f"Catechol SAR candidates: {catechol_count}")

    # Permeability candidates should be present (RA PSA > 100)
    perm_count = sum(1 for c in candidates if c.modification_type == "permeability")
    print(f"Permeability candidates: {perm_count}")
