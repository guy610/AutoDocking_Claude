"""
Small Molecule Optimization Pipeline (v0.9.3).

Separate from the peptide pipeline. Takes a co-crystal structure, analyses
the binding interface, generates analogs with property-biased filtering,
and iteratively optimizes through multi-round docking with combinatorial expansion.

v0.9.3 additions:
  - Stereoisomer enumeration (rational in intermediate rounds, full in final)
  - Thioether cyclization detection
  - Ligand efficiency metrics (LE, LLE, LELP)
  - Metabolic soft spot blocking (CYP450)
  - Scaffold hopping (ring transformations)
  - Matched molecular pair (MMP) tracking
  - Conformational constraint scoring (rotatable bonds)
  - Torsion strain pre-filtering
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import SmallMoleculeConfig, DockingParams
from .core.docking import DockingResult, run_vina
from .core.ligand import smiles_to_pdbqt, adjust_protonation
from .core.receptor import prepare_receptor_pdbqt
from .core.run_checkpoint import RunCheckpoint
from .core.ligand_extraction import (
    extract_ligand_from_pdb, compute_autobox, ExtractionResult,
)
from .core.binding_analysis import run_binding_analysis, BindingAnalysisResult
from .core.analog_generation import (
    generate_analogs, AnalogCandidate, Modification,
    generate_combinatorial_analogs, extract_modifications,
    compute_property_profile, get_target_window, PropertyProfile,
    detect_cyclization_sites, validate_structure, filter_by_property_window,
    # v0.9.3
    LigandEfficiency, compute_ligand_efficiency, check_torsion_strain,
    enumerate_stereoisomers_rational, enumerate_stereoisomers_full,
    generate_mmp_expansions,
    # v0.9.3
    compute_composite_score,
)
from .utils.io_utils import ensure_dir, generate_complex_pdb

logger = logging.getLogger(__name__)


class SmallMoleculePipeline:
    """Pipeline for small-molecule lead optimization with multi-round iteration."""

    def __init__(self, config: SmallMoleculeConfig):
        self.config = config
        self.all_results: List[DockingResult] = []
        self.original_result: Optional[DockingResult] = None
        self.original_score: Optional[float] = None
        self.receptor_pdbqt: Optional[Path] = None
        self.receptor_clean_pdb: Optional[Path] = None
        self.extraction: Optional[ExtractionResult] = None
        self.binding_analysis: Optional[BindingAnalysisResult] = None
        self.analog_candidates: List[AnalogCandidate] = []
        self.checkpoint_handler = None  # Set for web mode
        self.run_checkpoint: Optional[RunCheckpoint] = None
        self.time_per_dock = 0.0
        self.estimated_end_time = 0.0
        self.estimated_total_docks = 0
        self.completed_docks = 0
        self.consensus_records = []
        # Multi-round tracking
        self.round_summaries: List[Dict] = []
        self.property_profiles: Dict[str, PropertyProfile] = {}
        self.passing_modifications: List[Modification] = []
        self.target_window: Optional[dict] = None
        # v0.9.3 tracking
        self.ligand_efficiencies: Dict[str, LigandEfficiency] = {}
        self.torsion_warnings: Dict[str, List[str]] = {}

    def run(self) -> None:
        """Execute the full small molecule optimization pipeline."""
        logger.info("=" * 60)
        logger.info("Starting Small Molecule Optimization Pipeline v0.9.3")
        logger.info("Crystal PDB: %s", self.config.crystal_pdb)
        logger.info("Run mode: %s", self.config.run_mode)
        logger.info("Property target: %s", self.config.property_target)
        logger.info("Max rounds: %d", self.config.max_rounds)

        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Build target window from config
        self.target_window = get_target_window(self.config)
        logger.info("Target window: logP=%.1f-%.1f, MW<%.0f, PSA<%.0f, HBD<=%d, HBA<=%d",
                     self.target_window["logp_min"], self.target_window["logp_max"],
                     self.target_window["mw_max"], self.target_window["psa_max"],
                     self.target_window["hbd_max"], self.target_window["hba_max"])

        # Initialise checkpoint for resume support
        self.run_checkpoint = RunCheckpoint(self.config.output_dir)
        if self.run_checkpoint.n_cached > 0:
            logger.info("=== RESUMING: found %d cached dock results ===",
                        self.run_checkpoint.n_cached)

        # --- Stage 1: Extract ligand and prepare receptor ---
        logger.info("=" * 60)
        logger.info("=== Stage 1: Ligand Extraction & Receptor Preparation ===")
        self.extraction = self._extract_and_prepare()
        ligand_smiles = self.extraction.ligand_smiles

        # Allow manual SMILES override (PDB extraction can miss aromaticity/bond orders)
        if self.config.ligand_smiles_override:
            extracted = ligand_smiles
            ligand_smiles = self.config.ligand_smiles_override
            logger.info("SMILES override: using provided SMILES instead of extracted")
            logger.info("  Extracted: %s", extracted)
            logger.info("  Override:  %s", ligand_smiles)

        if not ligand_smiles:
            raise ValueError(
                "Could not determine ligand SMILES from the crystal structure. "
                "Ensure the PDB contains valid HETATM records for the co-crystallized ligand."
            )

        logger.info("Ligand: %s (chain=%s, resnum=%d, %d heavy atoms)",
                     self.extraction.ligand_resname, self.extraction.ligand_chain,
                     self.extraction.ligand_resnum, self.extraction.n_ligand_atoms)
        logger.info("Ligand SMILES: %s", ligand_smiles)

        # Compute parent property profile
        parent_profile = compute_property_profile(ligand_smiles)
        if parent_profile:
            self.property_profiles[ligand_smiles] = parent_profile
            logger.info("Parent properties: logP=%.2f, MW=%.1f, PSA=%.1f, HBD=%d, HBA=%d, "
                        "Potts-Guy logKp=%.3f",
                        parent_profile.logp, parent_profile.mw, parent_profile.psa,
                        parent_profile.hbd, parent_profile.hba, parent_profile.potts_guy_logkp)

        # --- Stage 2: Dock reference ligand ---
        logger.info("=" * 60)
        logger.info("=== Stage 2: Reference Ligand Docking ===")

        cached_ref = self.run_checkpoint.reconstruct_result("sm_reference", ligand_smiles)
        if cached_ref is not None:
            logger.info("Using cached reference dock result")
            self.original_result = cached_ref
            self.all_results.append(cached_ref)
            state = self.run_checkpoint.load_state()
            if state and "time_per_dock" in state:
                self.time_per_dock = state["time_per_dock"]
        else:
            self.original_result = self._dock_reference_ligand(ligand_smiles)
            self.all_results.append(self.original_result)
            self.run_checkpoint.save_result("sm_reference", self.original_result)

        self.original_score = self.original_result.best_energy
        logger.info("Reference score: %.2f kcal/mol", self.original_score)

        # --- Stage 3: Binding analysis ---
        logger.info("=" * 60)
        logger.info("=== Stage 3: Binding Interface Analysis ===")
        self.binding_analysis = run_binding_analysis(
            ligand_pdb=self.extraction.ligand_pdb,
            receptor_pdb=self.extraction.receptor_pdb,
            ligand_smiles=ligand_smiles,
            crystal_waters=self.extraction.crystal_waters,
        )
        self._log_analysis_summary()

        # Log cyclization sites and pro-drug sites (v0.9.1)
        if self.binding_analysis.cyclization_sites:
            logger.info("--- Cyclization Sites ---")
            for cs in self.binding_analysis.cyclization_sites:
                logger.info("  amine[%d] + acid[%d]: %d bonds apart, ring_size=%d (%s amine)",
                            cs.amine_idx, cs.acid_idx, cs.topological_dist,
                            cs.ring_size, cs.amine_type)

        if self.binding_analysis.prodrug_ester_sites:
            logger.info("Pro-drug ester sites (carboxylates): %d",
                        len(self.binding_analysis.prodrug_ester_sites))

        # Log v0.9.3 analysis results
        if self.binding_analysis.thioether_sites:
            logger.info("--- Thioether Cyclization Sites ---")
            for ts in self.binding_analysis.thioether_sites:
                logger.info("  S[%d] + C[%d]: %d bonds apart, leaving_group=%s",
                            ts.thiol_idx, ts.carbon_idx, ts.topological_dist,
                            ts.leaving_group)

        if self.binding_analysis.metabolic_soft_spots:
            logger.info("--- Metabolic Soft Spots (CYP450) ---")
            for ms in self.binding_analysis.metabolic_soft_spots:
                logger.info("  atom[%d]: %s (%s)", ms.atom_idx, ms.pattern_name,
                            ms.suggested_block)

        if self.config.run_mode == "analysis_only":
            logger.info("Run mode = analysis_only, skipping analog generation and docking")
            self._generate_report()
            logger.info("=== Pipeline Complete (analysis only) ===")
            return

        # --- Stage 4+5: Multi-round iterative optimization ---
        logger.info("=" * 60)
        logger.info("=== Stage 4: Multi-Round Iterative Optimization ===")
        self._run_iterative_optimization(ligand_smiles)

        # --- Stage 6: Optional hierarchical screening ---
        if self.config.run_mode == "hierarchical":
            logger.info("=" * 60)
            logger.info("=== Stage 6: Hierarchical Screening ===")
            self._run_hierarchical_screening()

        # --- Stage 7: Report ---
        logger.info("=" * 60)
        logger.info("=== Stage 7: Report Generation ===")
        self._generate_report()

        # Generate complex PDB for best result
        self._generate_best_complex()

        logger.info("=" * 60)
        logger.info("=== Small Molecule Pipeline Complete ===")
        logger.info("Total results: %d", len(self.all_results))
        if self.all_results:
            best = min(self.all_results, key=lambda r: r.best_energy)
            delta = best.best_energy - self.original_score
            logger.info("Best: %s (%.2f kcal/mol, delta=%.2f from reference)",
                        best.ligand_name, best.best_energy, delta)

    # ------------------------------------------------------------------
    # Stage 1: Extract and prepare
    # ------------------------------------------------------------------

    def _extract_and_prepare(self) -> ExtractionResult:
        """Extract ligand from crystal PDB and prepare receptor."""
        extract_dir = ensure_dir(self.config.output_dir / "extraction")

        extraction = extract_ligand_from_pdb(
            pdb_path=self.config.crystal_pdb,
            output_dir=extract_dir,
            ligand_resname=self.config.ligand_resname,
            ligand_chain=self.config.ligand_chain,
        )

        # Compute docking box from ligand position
        center, size = compute_autobox(
            extraction.ligand_pdb,
            padding=self.config.autobox_padding,
        )
        self.config.docking.center_x = center[0]
        self.config.docking.center_y = center[1]
        self.config.docking.center_z = center[2]
        self.config.docking.size_x = size[0]
        self.config.docking.size_y = size[1]
        self.config.docking.size_z = size[2]

        # Store receptor PDB and prepare PDBQT
        self.receptor_clean_pdb = extraction.receptor_pdb

        from .config import PipelineConfig
        temp_config = PipelineConfig(
            receptor_pdb=extraction.receptor_pdb,
            output_dir=self.config.output_dir,
            remove_waters=False,
            remove_heteroatoms=False,
        )
        self.receptor_pdbqt = prepare_receptor_pdbqt(
            extraction.receptor_pdb, temp_config
        )

        logger.info("Receptor PDBQT: %s", self.receptor_pdbqt)
        logger.info("Docking box: center=(%.1f, %.1f, %.1f), size=(%.1f, %.1f, %.1f)",
                     center[0], center[1], center[2], size[0], size[1], size[2])

        return extraction

    # ------------------------------------------------------------------
    # Stage 2: Dock reference ligand
    # ------------------------------------------------------------------

    def _dock_reference_ligand(self, ligand_smiles: str) -> DockingResult:
        """Dock the co-crystallized ligand to establish baseline score."""
        dock_dir = ensure_dir(self.config.output_dir / "reference_dock")

        logger.info("Preparing reference ligand for docking...")
        adjusted_smiles = adjust_protonation(ligand_smiles)
        ligand_pdbqt = smiles_to_pdbqt(
            adjusted_smiles, "reference", dock_dir,
        )

        logger.info("Docking reference ligand...")
        t0 = time.time()
        result = run_vina(
            receptor_pdbqt=self.receptor_pdbqt,
            ligand_pdbqt=ligand_pdbqt,
            ligand_name="reference",
            smiles=ligand_smiles,
            docking_params=self.config.docking,
            output_dir=dock_dir,
            vina_executable=self.config.vina_executable,
            origin="reference",
        )
        self.time_per_dock = time.time() - t0
        logger.info("Reference dock: %.2f kcal/mol (%.1f sec)",
                     result.best_energy, self.time_per_dock)

        self.run_checkpoint.save_state({
            "time_per_dock": self.time_per_dock,
            "reference_smiles": ligand_smiles,
        })

        return result

    # ------------------------------------------------------------------
    # Stage 4+5: Multi-round iterative optimization
    # ------------------------------------------------------------------

    def _run_iterative_optimization(self, ligand_smiles: str) -> None:
        """Run multi-round iterative analog generation and docking.

        Round 1: single-site modifications only.
        Round N+1: combinatorial expansion of passing modifications from
                   different sites, plus new single-site modifications.
        """
        max_rounds = self.config.max_rounds
        delta_threshold = self.config.delta_threshold
        best_score = self.original_score
        current_best_smiles = ligand_smiles

        for round_num in range(1, max_rounds + 1):
            logger.info("=" * 50)
            logger.info("=== Optimization Round %d/%d ===", round_num, max_rounds)

            # Compute property profile of current best
            profile = compute_property_profile(current_best_smiles)
            if profile:
                self.property_profiles[current_best_smiles] = profile
                logger.info("Current best properties: logP=%.2f, MW=%.1f, PSA=%.1f",
                            profile.logp, profile.mw, profile.psa)

            # Generate candidates
            # v0.9.3/9.3: pass enable flags and parent profile for adaptive filtering
            gen_kwargs = dict(
                enable_bioisosteres=self.config.enable_bioisosteres,
                enable_extensions=self.config.enable_extensions,
                enable_removals=self.config.enable_removals,
                enable_prodrug_esters=self.config.enable_prodrug_esters,
                enable_metabolic_blocking=self.config.enable_metabolic_blocking,
                enable_scaffold_hopping=self.config.enable_scaffold_hopping,
                enable_thioether_detection=self.config.enable_thioether_detection,
                max_scaffold_hops=self.config.max_scaffold_hops,
                target_window=self.target_window,
                parent_profile=profile,  # v0.9.3: adaptive filter relaxation
            )

            if round_num == 1:
                # Single modifications only
                candidates = generate_analogs(
                    ligand_smiles=current_best_smiles,
                    analysis=self.binding_analysis,
                    max_analogs=self.config.max_analogs,
                    **gen_kwargs,
                )
            else:
                # Combinatorial expansion of passing modifications
                combo_candidates = generate_combinatorial_analogs(
                    parent_smiles=ligand_smiles,
                    passing_modifications=self.passing_modifications,
                    analysis=self.binding_analysis,
                    max_combos=self.config.max_combos_per_round,
                    combo_size=min(round_num, 3),
                    target_window=self.target_window,
                    parent_profile=profile,  # v0.9.3: adaptive filter relaxation
                )

                # MMP expansion: apply passing modifications at equivalent sites (v0.9.3)
                if self.config.enable_mmp_tracking and self.passing_modifications:
                    mmp_candidates = generate_mmp_expansions(
                        parent_smiles=ligand_smiles,
                        passing_modifications=self.passing_modifications,
                        analysis=self.binding_analysis,
                        target_window=self.target_window,
                    )
                    combo_candidates.extend(mmp_candidates)
                    logger.info("Added %d MMP expansion candidates", len(mmp_candidates))

                # Also generate new single-site modifications from current best
                single_candidates = generate_analogs(
                    ligand_smiles=current_best_smiles,
                    analysis=self.binding_analysis,
                    max_analogs=self.config.max_analogs // 2,
                    **gen_kwargs,
                )
                candidates = combo_candidates + single_candidates

            # Validate structures
            candidates = [c for c in candidates if validate_structure(c.smiles)]

            # v0.9.3: Torsion strain pre-filter
            if self.config.enable_torsion_filter:
                torsion_ok = []
                for c in candidates:
                    passes, warnings = check_torsion_strain(
                        c.smiles, self.config.torsion_amide_tolerance)
                    if passes:
                        torsion_ok.append(c)
                    else:
                        self.torsion_warnings[c.smiles] = warnings
                n_rejected = len(candidates) - len(torsion_ok)
                if n_rejected > 0:
                    logger.info("Torsion filter: rejected %d/%d candidates",
                                n_rejected, len(candidates))
                candidates = torsion_ok

            # v0.9.3: Rational stereoisomer addition (intermediate rounds only)
            if (self.config.enable_stereoisomer_enum
                    and round_num < max_rounds
                    and candidates):
                stereo_additions = []
                for c in candidates:
                    mod_sites = [c.target_group_idx] if c.target_group_idx >= 0 else []
                    if not mod_sites:
                        continue
                    isomers = enumerate_stereoisomers_rational(
                        c.smiles, mod_sites,
                        max_isomers=self.config.stereo_max_centers ** 2,
                    )
                    for iso_smi in isomers:
                        if iso_smi != c.smiles and validate_structure(iso_smi):
                            stereo_additions.append(AnalogCandidate(
                                smiles=iso_smi,
                                parent_smiles=c.parent_smiles,
                                modification_type="stereo_inversion",
                                target_group=c.target_group,
                                target_group_idx=c.target_group_idx,
                                rationale=f"chiral inversion of {c.rationale[:40]}",
                                estimated_impact="stereoisomer",
                            ))
                if stereo_additions:
                    logger.info("Added %d rational stereoisomers", len(stereo_additions))
                    candidates.extend(stereo_additions)

            self.analog_candidates.extend(candidates)
            logger.info("Round %d: %d candidates to dock", round_num, len(candidates))

            if not candidates:
                logger.info("No candidates generated in round %d, stopping", round_num)
                break

            # Estimate time
            n_to_dock = len(candidates)
            self.estimated_total_docks += n_to_dock
            if self.time_per_dock > 0:
                est_seconds = n_to_dock * self.time_per_dock
                self.estimated_end_time = time.time() + est_seconds
                logger.info("Estimated docking time: %.0f min for %d analogs",
                            est_seconds / 60, n_to_dock)

            # Dock all candidates
            round_results = self._dock_candidate_list(candidates, round_num)

            # Compute property profiles and ligand efficiencies for docked results
            for analog, result in round_results:
                prof = compute_property_profile(analog.smiles)
                if prof:
                    self.property_profiles[analog.smiles] = prof
                # v0.9.3: Ligand efficiency metrics
                le = compute_ligand_efficiency(analog.smiles, result.best_energy)
                if le:
                    self.ligand_efficiencies[analog.smiles] = le

            # Filter by improvement threshold
            passing = [
                (analog, result) for analog, result in round_results
                if result.best_energy <= best_score - delta_threshold
            ]

            round_best = min((r.best_energy for _, r in round_results), default=best_score)

            # Round summary
            summary = {
                "round": round_num,
                "n_candidates": len(candidates),
                "n_docked": len(round_results),
                "n_passing": len(passing),
                "best_score": round_best,
                "delta_from_ref": round_best - self.original_score,
            }
            self.round_summaries.append(summary)
            logger.info("Round %d summary: %d candidates, %d passing (delta threshold=%.2f), "
                        "best=%.2f (delta=%+.2f)",
                        round_num, len(candidates), len(passing), delta_threshold,
                        round_best, round_best - self.original_score)

            if not passing:
                logger.info("No improvements in round %d, stopping optimization", round_num)
                break

            # Track which modifications passed for combinatorial expansion
            new_mods = extract_modifications(passing, ligand_smiles)
            self.passing_modifications.extend(new_mods)
            logger.info("Accumulated %d passing modifications for combinatorial expansion",
                        len(self.passing_modifications))

            # Update best score and best SMILES
            best_passing = min(passing, key=lambda x: x[1].best_energy)
            best_score = best_passing[1].best_energy
            current_best_smiles = best_passing[0].smiles
            logger.info("New best: %s (%.2f kcal/mol)", current_best_smiles, best_score)

        # v0.9.3: Post-loop full stereoisomer enumeration of top binders
        if self.config.enable_stereoisomer_enum and len(self.all_results) > 1:
            logger.info("=" * 50)
            logger.info("=== Final Stereoisomer Enumeration ===")
            sorted_results = sorted(self.all_results, key=lambda r: r.best_energy)
            top_n = self.config.stereo_final_top_n
            top_results = sorted_results[:top_n]

            stereo_to_dock = []
            seen_stereo = set()
            for r in top_results:
                isomers = enumerate_stereoisomers_full(
                    r.smiles, self.config.stereo_max_centers)
                for iso_smi in isomers:
                    if (iso_smi != r.smiles
                            and iso_smi not in seen_stereo
                            and validate_structure(iso_smi)):
                        seen_stereo.add(iso_smi)
                        stereo_to_dock.append(AnalogCandidate(
                            smiles=iso_smi,
                            parent_smiles=r.smiles,
                            modification_type="stereo_full_enum",
                            target_group="all_centers",
                            rationale=f"full stereoisomer of {r.ligand_name}",
                            estimated_impact="stereoisomer",
                        ))

            if stereo_to_dock:
                logger.info("Docking %d final stereoisomers from top %d binders",
                            len(stereo_to_dock), len(top_results))
                final_round = len(self.round_summaries) + 1
                stereo_results = self._dock_candidate_list(stereo_to_dock, final_round)

                # Compute LE for stereoisomers
                for analog, result in stereo_results:
                    prof = compute_property_profile(analog.smiles)
                    if prof:
                        self.property_profiles[analog.smiles] = prof
                    le = compute_ligand_efficiency(analog.smiles, result.best_energy)
                    if le:
                        self.ligand_efficiencies[analog.smiles] = le

                stereo_best = min((r.best_energy for _, r in stereo_results),
                                  default=best_score)
                self.round_summaries.append({
                    "round": final_round,
                    "n_candidates": len(stereo_to_dock),
                    "n_docked": len(stereo_results),
                    "n_passing": sum(1 for _, r in stereo_results
                                     if r.best_energy <= best_score),
                    "best_score": stereo_best,
                    "delta_from_ref": stereo_best - self.original_score,
                    "note": "stereoisomer enumeration",
                })
                logger.info("Stereoisomer enumeration: %d docked, best=%.2f kcal/mol",
                            len(stereo_results), stereo_best)
            else:
                logger.info("No new stereoisomers to enumerate")

        logger.info("Iterative optimization complete: %d rounds, %d total results",
                     len(self.round_summaries), len(self.all_results))

    def _dock_candidate_list(
        self,
        candidates: List[AnalogCandidate],
        round_num: int,
    ) -> List[Tuple[AnalogCandidate, DockingResult]]:
        """Dock a list of candidates with checkpoint support. Returns (analog, result) pairs."""
        dock_dir = ensure_dir(self.config.output_dir / f"round_{round_num:02d}_docks")
        n_total = len(candidates)
        round_results = []

        for i, analog in enumerate(candidates):
            name = f"r{round_num:02d}_analog_{i + 1:03d}"
            logger.info("Docking %d/%d: %s (%s: %s)",
                        i + 1, n_total, name, analog.modification_type,
                        analog.rationale[:60])

            # Check checkpoint
            cache_key = f"sm_r{round_num}_{analog.smiles}"
            if self.run_checkpoint.has_result("sm_analog", analog.smiles):
                result = self.run_checkpoint.reconstruct_result("sm_analog", analog.smiles)
                if result:
                    logger.info("  [cached] %.2f kcal/mol", result.best_energy)
                    self.all_results.append(result)
                    round_results.append((analog, result))
                    self.completed_docks += 1
                    continue

            try:
                adjusted = adjust_protonation(analog.smiles)
                ligand_pdbqt = smiles_to_pdbqt(
                    adjusted, name, dock_dir,
                )

                result = run_vina(
                    receptor_pdbqt=self.receptor_pdbqt,
                    ligand_pdbqt=ligand_pdbqt,
                    ligand_name=name,
                    smiles=analog.smiles,
                    docking_params=self.config.docking,
                    output_dir=dock_dir,
                    vina_executable=self.config.vina_executable,
                    origin=analog.modification_type,
                )
                result.annotation = f"{analog.modification_type}: {analog.rationale}"

                self.all_results.append(result)
                self.run_checkpoint.save_result("sm_analog", result)
                round_results.append((analog, result))
                self.completed_docks += 1

                delta = result.best_energy - self.original_score
                logger.info("  %.2f kcal/mol (delta=%+.2f)", result.best_energy, delta)

            except Exception as e:
                logger.error("  Failed: %s", e)
                self.completed_docks += 1

        return round_results

    # ------------------------------------------------------------------
    # Stage 6: Hierarchical screening (reuses peptide pipeline logic)
    # ------------------------------------------------------------------

    def _run_hierarchical_screening(self) -> None:
        """Run GNINA + RxDock consensus scoring on top analogs."""
        from .core.gnina import run_gnina_rescore
        from .core.rxdock import (
            run_rxdock, prepare_rxdock_cavity, smiles_to_sdf,
        )
        from .utils.reporting import (
            get_stereo_annotation, ConsensusRecord, generate_consensus_csv,
        )

        sorted_results = sorted(self.all_results, key=lambda r: r.best_energy)
        top_n = self.config.hierarchical_top_n
        top_candidates = sorted_results[:top_n]
        n_cands = len(top_candidates)

        gnina_results = {}
        rxdock_results = {}

        # Phase 2: GNINA
        if self.config.gnina_executable:
            logger.info("=== GNINA CNN Rescoring (%d candidates) ===", n_cands)
            for i, cand in enumerate(top_candidates):
                logger.info("GNINA %d/%d: %s", i + 1, n_cands, cand.ligand_name)
                pdbqt_path = Path(cand.output_pdbqt) if cand.output_pdbqt else None
                if pdbqt_path and pdbqt_path.exists():
                    gresult = run_gnina_rescore(
                        receptor_pdbqt=self.receptor_pdbqt,
                        ligand_docked_pdbqt=pdbqt_path,
                        gnina_executable=self.config.gnina_executable,
                        ligand_name=cand.ligand_name,
                    )
                    if gresult:
                        gnina_results[cand.ligand_name] = gresult

        # Phase 3: RxDock
        if self.config.rxdock_executable:
            logger.info("=== RxDock Orthogonal Docking (%d candidates) ===", n_cands)
            rxdock_dir = ensure_dir(self.config.output_dir / "rxdock")
            center = (
                self.config.docking.center_x,
                self.config.docking.center_y,
                self.config.docking.center_z,
            )
            size = (
                self.config.docking.size_x,
                self.config.docking.size_y,
                self.config.docking.size_z,
            )
            prm_path = prepare_rxdock_cavity(
                receptor_pdb=self.receptor_clean_pdb,
                center=center, size=size,
                output_dir=rxdock_dir,
                rxdock_executable=self.config.rxdock_executable,
            )
            if prm_path:
                for i, cand in enumerate(top_candidates):
                    try:
                        sdf_path = smiles_to_sdf(
                            cand.smiles, cand.ligand_name, rxdock_dir
                        )
                        rresult = run_rxdock(
                            prm_path=prm_path,
                            ligand_sdf=sdf_path,
                            rxdock_executable=self.config.rxdock_executable,
                            output_dir=rxdock_dir,
                            ligand_name=cand.ligand_name,
                        )
                        if rresult:
                            rxdock_results[cand.ligand_name] = rresult
                    except Exception as e:
                        logger.error("RxDock failed for %s: %s", cand.ligand_name, e)

        # Consensus ranking
        logger.info("=== Consensus Ranking ===")
        n = len(top_candidates)
        vina_sorted = sorted(top_candidates, key=lambda r: r.best_energy)
        vina_rank = {r.ligand_name: i + 1 for i, r in enumerate(vina_sorted)}

        gnina_rank = {}
        if gnina_results:
            gs = sorted(gnina_results.keys(),
                        key=lambda nm: gnina_results[nm].cnn_affinity, reverse=True)
            gnina_rank = {nm: i + 1 for i, nm in enumerate(gs)}

        rxdock_rank = {}
        if rxdock_results:
            rs = sorted(rxdock_results.keys(),
                        key=lambda nm: rxdock_results[nm].inter_score)
            rxdock_rank = {nm: i + 1 for i, nm in enumerate(rs)}

        records = []
        for cand in top_candidates:
            name = cand.ligand_name
            v_rank = vina_rank.get(name, n)
            g_result = gnina_results.get(name)
            g_rank = gnina_rank.get(name)
            r_result = rxdock_results.get(name)
            r_rank = rxdock_rank.get(name)

            available = [v_rank]
            if g_rank is not None:
                available.append(g_rank)
            if r_rank is not None:
                available.append(r_rank)
            consensus = sum(available) / len(available)

            rank_var = abs(v_rank - r_rank) if r_rank is not None else None
            pose_flag = ""
            if g_result and g_result.cnn_pose_score < 0.5:
                pose_flag = "Low Confidence Pose"

            records.append(ConsensusRecord(
                rank=0,
                uid=name,
                smiles=cand.smiles,
                origin=cand.origin,
                annotation=getattr(cand, "annotation", ""),
                stereo="",
                vina_score=cand.best_energy,
                vina_rank=v_rank,
                rxdock_score=r_result.inter_score if r_result else None,
                rxdock_rank=r_rank,
                gnina_cnn_affinity=g_result.cnn_affinity if g_result else None,
                gnina_pose_confidence=g_result.cnn_pose_score if g_result else None,
                pose_confidence_flag=pose_flag,
                rank_variance=rank_var,
                consensus_score=consensus,
            ))

        records.sort(key=lambda r: r.consensus_score)
        for i, rec in enumerate(records):
            rec.rank = i + 1

        self.consensus_records = records
        consensus_path = self.config.output_dir / "consensus_summary.csv"
        generate_consensus_csv(records, consensus_path)
        logger.info("Consensus ranking saved: %s", consensus_path)

        for rec in records[:5]:
            logger.info("  #%d %s: consensus=%.1f, vina=%.2f",
                        rec.rank, rec.uid, rec.consensus_score, rec.vina_score)

    # ------------------------------------------------------------------
    # Analysis summary logging
    # ------------------------------------------------------------------

    def _log_analysis_summary(self) -> None:
        """Log a summary of the binding analysis for SSE display."""
        a = self.binding_analysis
        if a is None:
            return

        logger.info("--- Binding Analysis Summary ---")
        logger.info("Functional groups: %d", len(a.functional_groups))
        for grp in a.functional_groups[:10]:
            logger.info("  %s: score=%.1f (hbonds=%d, hydrophobic=%d, salt_bridges=%d)",
                        grp.group_type, grp.interaction_score,
                        grp.n_hbonds, grp.n_hydrophobic, grp.n_salt_bridges)

        logger.info("Steric clashes: %d", len(a.steric_clashes))
        for c in a.steric_clashes[:5]:
            logger.info("  lig[%d]-%s %s%d: dist=%.2fA (overlap=%.2fA)",
                        c.lig_atom_idx, c.rec_atom_name, c.rec_res_name,
                        c.rec_res_num, c.distance, c.overlap)

        logger.info("Charge repulsions: %d", len(a.charge_repulsions))
        logger.info("Unmatched H-bond partners: %d", len(a.unmatched_hbond_partners))
        logger.info("Solvent-exposed groups: %d", len(a.solvent_exposed_groups))
        logger.info("Desolvation hotspots: %d", len(a.desolvation_hotspots))
        logger.info("Bridging waters: %d", len(a.bridging_waters))
        logger.info("Strain energy: %.2f kcal/mol", a.strain_energy)
        logger.info("Pi-stacking opportunities: %d", len(a.pi_stacking_opportunities))

        logger.info("--- Top Optimization Targets ---")
        for t in a.optimization_targets[:5]:
            logger.info("  #%d %s (score=%.1f): %s",
                        t.group_idx + 1, t.group_type, t.score, t.rationale)

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def _generate_report(self) -> None:
        """Generate CSV and markdown reports."""
        from .utils.reporting import (
            results_to_records, generate_csv_report,
        )

        # Sort results by score
        self.all_results.sort(key=lambda r: r.best_energy)

        # CSV report — pass ligand efficiencies and property profiles for v0.9.3
        records = results_to_records(
            self.all_results,
            ligand_efficiencies=self.ligand_efficiencies,
            property_profiles=self.property_profiles,
        )
        csv_path = self.config.output_dir / "results.csv"
        generate_csv_report(records, csv_path)
        logger.info("CSV report: %s", csv_path)

        # Markdown report (SM-specific)
        md_path = self.config.output_dir / "report.md"
        self._generate_sm_markdown(md_path)
        logger.info("Markdown report: %s", md_path)

    def _generate_sm_markdown(self, output_path: Path) -> None:
        """Generate a small-molecule-specific markdown report with v0.9.3 enhancements."""
        lines = []
        lines.append("# Small Molecule Optimization Report (v0.9.3)")
        lines.append("")

        # Configuration summary
        lines.append("## Configuration")
        lines.append(f"- **Property target**: {self.config.property_target}")
        tw = self.target_window or {}
        lines.append(f"- **logP range**: {tw.get('logp_min', '?')}-{tw.get('logp_max', '?')}")
        lines.append(f"- **MW max**: {tw.get('mw_max', '?')}")
        lines.append(f"- **PSA max**: {tw.get('psa_max', '?')}")
        lines.append(f"- **HBD max**: {tw.get('hbd_max', '?')}, HBA max: {tw.get('hba_max', '?')}")
        lines.append(f"- **Max rounds**: {self.config.max_rounds}")
        lines.append(f"- **Delta threshold**: {self.config.delta_threshold} kcal/mol")
        lines.append(f"- **Pro-drug esters**: {'enabled' if self.config.enable_prodrug_esters else 'disabled'}")
        lines.append(f"- **Cyclization detection**: {'enabled' if self.config.enable_cyclization_detection else 'disabled'}")
        lines.append(f"- **Stereoisomer enumeration**: {'enabled' if self.config.enable_stereoisomer_enum else 'disabled'}")
        lines.append(f"- **Thioether detection**: {'enabled' if self.config.enable_thioether_detection else 'disabled'}")
        lines.append(f"- **Metabolic blocking**: {'enabled' if self.config.enable_metabolic_blocking else 'disabled'}")
        lines.append(f"- **Scaffold hopping**: {'enabled' if self.config.enable_scaffold_hopping else 'disabled'}")
        lines.append(f"- **MMP tracking**: {'enabled' if self.config.enable_mmp_tracking else 'disabled'}")
        lines.append(f"- **Torsion filter**: {'enabled' if self.config.enable_torsion_filter else 'disabled'}")
        lines.append("")

        # Crystal structure
        lines.append("## Crystal Structure")
        lines.append(f"- **PDB**: {self.config.crystal_pdb.name}")
        if self.extraction:
            lines.append(f"- **Ligand**: {self.extraction.ligand_resname} "
                         f"(chain {self.extraction.ligand_chain}, "
                         f"residue {self.extraction.ligand_resnum})")
            lines.append(f"- **Heavy atoms**: {self.extraction.n_ligand_atoms}")
            lines.append(f"- **SMILES**: `{self.extraction.ligand_smiles}`")
            lines.append(f"- **Bridging waters**: {len(self.extraction.crystal_waters)}")
        lines.append("")

        # Parent property profile
        if self.extraction and self.extraction.ligand_smiles in self.property_profiles:
            pp = self.property_profiles[self.extraction.ligand_smiles]
            lines.append("## Parent Property Profile")
            lines.append("")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| logP | {pp.logp} |")
            lines.append(f"| MW | {pp.mw} |")
            lines.append(f"| PSA | {pp.psa} |")
            lines.append(f"| HBD | {pp.hbd} |")
            lines.append(f"| HBA | {pp.hba} |")
            lines.append(f"| Rotatable bonds | {pp.rotatable} |")
            lines.append(f"| Potts-Guy log Kp | {pp.potts_guy_logkp} |")
            lines.append("")

        # Reference docking
        if self.original_result:
            lines.append("## Reference Docking")
            lines.append(f"- **Vina score**: {self.original_result.best_energy:.2f} kcal/mol")
            lines.append("")

        # Binding analysis
        a = self.binding_analysis
        if a:
            lines.append("## Binding Interface Analysis")
            lines.append("")
            lines.append(f"- **Strain energy**: {a.strain_energy:.2f} kcal/mol")
            lines.append(f"- **Steric clashes**: {len(a.steric_clashes)}")
            lines.append(f"- **Charge repulsions**: {len(a.charge_repulsions)}")
            lines.append(f"- **Unmatched H-bond partners**: {len(a.unmatched_hbond_partners)}")
            lines.append(f"- **Solvent-exposed groups**: {len(a.solvent_exposed_groups)}")
            lines.append(f"- **Desolvation hotspots**: {len(a.desolvation_hotspots)}")
            lines.append(f"- **Bridging waters**: {len(a.bridging_waters)}")
            lines.append(f"- **Pi-stacking opportunities**: {len(a.pi_stacking_opportunities)}")
            lines.append("")

            # Functional groups table
            lines.append("### Functional Groups")
            lines.append("")
            lines.append("| # | Type | H-bonds | Hydrophobic | Salt bridges | Score | Target? |")
            lines.append("|---|------|---------|-------------|-------------|-------|---------|")
            for i, grp in enumerate(a.functional_groups):
                target = "YES" if grp.is_optimization_target else ""
                lines.append(
                    f"| {i + 1} | {grp.group_type} | {grp.n_hbonds} | "
                    f"{grp.n_hydrophobic} | {grp.n_salt_bridges} | "
                    f"{grp.interaction_score:.1f} | {target} |"
                )
            lines.append("")

            # Optimization targets
            if a.optimization_targets:
                lines.append("### Optimization Targets (ranked)")
                lines.append("")
                lines.append("| Rank | Group | Score | Rationale |")
                lines.append("|------|-------|-------|-----------|")
                for t in a.optimization_targets:
                    lines.append(
                        f"| {t.group_idx + 1} | {t.group_type} | "
                        f"{t.score:.1f} | {t.rationale} |"
                    )
                lines.append("")

            # Steric clashes detail
            if a.steric_clashes:
                lines.append("### Steric Clashes")
                lines.append("")
                lines.append("| Lig atom | Rec atom | Residue | Distance (A) | Overlap (A) |")
                lines.append("|----------|----------|---------|-------------|-------------|")
                for c in a.steric_clashes[:10]:
                    lines.append(
                        f"| {c.lig_atom_idx} ({c.lig_element}) | "
                        f"{c.rec_atom_name} | {c.rec_res_name}{c.rec_res_num} | "
                        f"{c.distance:.2f} | {c.overlap:.2f} |"
                    )
                lines.append("")

            # Cyclization sites (v0.9.1)
            if hasattr(a, "cyclization_sites") and a.cyclization_sites:
                lines.append("### Cyclization Sites (Potential Lactam Formation)")
                lines.append("")
                lines.append("| Amine Atom | Acid Atom | Bonds Apart | Ring Size | Amine Type |")
                lines.append("|-----------|-----------|-------------|-----------|------------|")
                for cs in a.cyclization_sites:
                    lines.append(
                        f"| {cs.amine_idx} | {cs.acid_idx} | "
                        f"{cs.topological_dist} | {cs.ring_size} | {cs.amine_type} |"
                    )
                lines.append("")

            # Pro-drug ester sites (v0.9.1)
            if hasattr(a, "prodrug_ester_sites") and a.prodrug_ester_sites:
                lines.append("### Pro-drug Ester Sites")
                lines.append(f"- {len(a.prodrug_ester_sites)} carboxylate(s) detected "
                             f"at atom indices: {a.prodrug_ester_sites}")
                lines.append("- Ester variants: ethyl, isopropyl, POM, acetoxymethyl")
                lines.append("")

            # Thioether cyclization sites (v0.9.3)
            if hasattr(a, "thioether_sites") and a.thioether_sites:
                lines.append("### Thioether Cyclization Sites")
                lines.append("")
                lines.append("| S Atom | C Atom | Bonds Apart | Leaving Group |")
                lines.append("|--------|--------|-------------|--------------|")
                for ts in a.thioether_sites:
                    lines.append(
                        f"| {ts.thiol_idx} | {ts.carbon_idx} | "
                        f"{ts.topological_dist} | {ts.leaving_group} |"
                    )
                lines.append("")

            # Metabolic soft spots (v0.9.3)
            if hasattr(a, "metabolic_soft_spots") and a.metabolic_soft_spots:
                lines.append("### Metabolic Soft Spots (CYP450)")
                lines.append("")
                lines.append("| Atom | Pattern | Suggested Block |")
                lines.append("|------|---------|----------------|")
                for ms in a.metabolic_soft_spots:
                    lines.append(
                        f"| {ms.atom_idx} | {ms.pattern_name} | {ms.suggested_block} |"
                    )
                lines.append("")

        # Round summaries (v0.9.1)
        if self.round_summaries:
            lines.append("## Optimization Rounds")
            lines.append("")
            lines.append("| Round | Candidates | Docked | Passing | Best Score | Delta |")
            lines.append("|-------|-----------|--------|---------|-----------|-------|")
            for rs in self.round_summaries:
                lines.append(
                    f"| {rs['round']} | {rs['n_candidates']} | {rs['n_docked']} | "
                    f"{rs['n_passing']} | {rs['best_score']:.2f} | "
                    f"{rs['delta_from_ref']:+.2f} |"
                )
            lines.append("")

        # Analog results with property profiles and ligand efficiency (v0.9.3)
        if len(self.all_results) > 1:
            lines.append("## Analog Docking Results (Top 20)")
            lines.append("")
            lines.append("| Rank | Name | Score | Delta | logP | MW | PSA | LE | LLE | Type | Rationale |")
            lines.append("|------|------|-------|-------|------|-----|-----|-----|-----|------|-----------|")
            for rank, r in enumerate(self.all_results[:20], 1):
                delta = r.best_energy - self.original_score if self.original_score else 0
                ann = getattr(r, "annotation", "") or ""
                parts = ann.split(": ", 1) if ann else ["", ""]
                mod_type = parts[0] if len(parts) > 1 else r.origin
                rationale = parts[1] if len(parts) > 1 else ann

                # Property profile
                pp = self.property_profiles.get(r.smiles)
                logp_str = f"{pp.logp:.1f}" if pp else "-"
                mw_str = f"{pp.mw:.0f}" if pp else "-"
                psa_str = f"{pp.psa:.0f}" if pp else "-"

                # Ligand efficiency (v0.9.3)
                le_data = self.ligand_efficiencies.get(r.smiles)
                le_str = f"{le_data.le:.2f}" if le_data else "-"
                lle_str = f"{le_data.lle:.1f}" if le_data else "-"

                lines.append(
                    f"| {rank} | {r.ligand_name} | {r.best_energy:.2f} | "
                    f"{delta:+.2f} | {logp_str} | {mw_str} | {psa_str} | "
                    f"{le_str} | {lle_str} | "
                    f"{mod_type} | {rationale[:50]} |"
                )
            lines.append("")

        # Composite ranking (v0.9.3) — multi-objective ranking
        if len(self.all_results) > 1 and self.property_profiles:
            composite_data = []
            for r in self.all_results:
                pp = self.property_profiles.get(r.smiles)
                cs = compute_composite_score(r.best_energy, pp)
                composite_data.append((r, cs, pp))

            composite_data.sort(key=lambda x: x[1])
            lines.append("## Multi-Objective Ranking (Binding + Permeability)")
            lines.append("")
            lines.append("| Rank | Name | Composite | Binding | logKp | PSA | Type |")
            lines.append("|------|------|-----------|---------|-------|-----|------|")
            for rank, (r, cs, pp) in enumerate(composite_data[:15], 1):
                logkp_str = f"{pp.potts_guy_logkp:.2f}" if pp else "-"
                psa_str = f"{pp.psa:.0f}" if pp else "-"
                lines.append(
                    f"| {rank} | {r.ligand_name} | {cs:.2f} | "
                    f"{r.best_energy:.2f} | {logkp_str} | {psa_str} | "
                    f"{r.origin} |"
                )
            lines.append("")

        # Torsion strain warnings (v0.9.3)
        if self.torsion_warnings:
            lines.append("## Torsion Strain Warnings")
            lines.append(f"- {len(self.torsion_warnings)} candidates rejected by torsion filter")
            for smi, warnings in list(self.torsion_warnings.items())[:5]:
                lines.append(f"  - `{smi[:40]}...`: {'; '.join(warnings)}")
            lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # Generate best complex PDB
    # ------------------------------------------------------------------

    def _generate_best_complex(self) -> None:
        """Generate a complex PDB for the best result."""
        if not self.all_results or not self.receptor_clean_pdb:
            return

        best = min(self.all_results, key=lambda r: r.best_energy)
        if best.best_pose_pdb and Path(best.best_pose_pdb).exists():
            complex_path = self.config.output_dir / "best_complex.pdb"
            try:
                generate_complex_pdb(
                    receptor_pdb=self.receptor_clean_pdb,
                    ligand_pdb=Path(best.best_pose_pdb),
                    output_path=complex_path,
                )
                logger.info("Best complex PDB: %s", complex_path)
            except Exception as e:
                logger.warning("Could not generate complex PDB: %s", e)
