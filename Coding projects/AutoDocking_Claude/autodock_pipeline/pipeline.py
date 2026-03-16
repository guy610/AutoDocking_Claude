"""
Main pipeline orchestrator.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

from .config import PipelineConfig
from .core.docking import DockingResult, run_vina
from .core.ligand import smiles_to_pdbqt, smiles_to_3d
from .core.receptor import clean_pdb, prepare_receptor_pdbqt
from .core.checkpoint import interactive_checkpoint
from .core.pocket import find_pocket_center
from .core.validators import (
    validate_ligand, check_binding_quality,
    print_validation_alerts, print_binding_alerts,
)
from .utils.io_utils import ensure_dir, generate_complex_pdb
from .utils.reporting import results_to_records, generate_csv_report, generate_markdown_report

logger = logging.getLogger(__name__)


class DockingPipeline:

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.all_results: List[DockingResult] = []
        self.original_score: Optional[float] = None
        self.original_result: Optional[DockingResult] = None
        self.receptor_pdbqt: Optional[Path] = None
        self.receptor_clean_pdb: Optional[Path] = None
        self.checkpoint_handler = None  # Set for web mode
        self.time_per_dock = 0.0  # Seconds per dock, measured from initial dock
        self.estimated_end_time = 0.0  # Unix timestamp of estimated completion
        self.estimated_total_docks = 0  # Total estimated docking operations
        self.completed_docks = 0  # Docks completed so far

    def prepare_receptor(self) -> Path:
        logger.info("Preparing receptor from: %s", self.config.receptor_pdb)
        self.receptor_clean_pdb = clean_pdb(self.config)
        return prepare_receptor_pdbqt(self.receptor_clean_pdb, self.config)

    def dock_initial_ligand(self) -> DockingResult:
        from .core.ligand import adjust_protonation

        logger.info("Preparing initial ligand: %s", self.config.ligand_name)

        # Adjust protonation for physiological pH 7.3
        adjusted_smiles = adjust_protonation(self.config.ligand_smiles, pH=7.3)

        val = validate_ligand(adjusted_smiles, name=self.config.ligand_name,
                              max_residues=self.config.optimization.max_residues)
        print_validation_alerts(val)
        if not val.is_valid:
            raise ValueError("Ligand validation failed: " + "; ".join(val.errors))

        out_dir = ensure_dir(self.config.output_dir / "initial")
        smiles_to_3d(adjusted_smiles, name=self.config.ligand_name, output_dir=out_dir)
        lig_pdbqt = smiles_to_pdbqt(adjusted_smiles, name=self.config.ligand_name, output_dir=out_dir)
        dock_start = time.time()
        result = run_vina(
            receptor_pdbqt=self.receptor_pdbqt,
            ligand_pdbqt=lig_pdbqt,
            ligand_name=self.config.ligand_name,
            smiles=adjusted_smiles,
            docking_params=self.config.docking,
            output_dir=out_dir,
            vina_executable=self.config.vina_executable,
            origin="initial",
        )
        self.time_per_dock = time.time() - dock_start
        logger.info("Initial dock completed in %.1f sec", self.time_per_dock)
        self.all_results.append(result)
        return result

    def _run_stage_with_checkpoint(self, stage_name, stage_func, seed_results):
        stage_key = stage_name.lower().replace(" ", "_").replace("-", "_")
        out_dir = ensure_dir(self.config.output_dir / stage_key)
        results = stage_func(self.config, self.receptor_pdbqt, seed_results, self.original_score, time_per_dock=self.time_per_dock)
        self.all_results.extend(results)
        top = sorted(seed_results + results, key=lambda r: r.best_energy)[:self.config.optimization.top_n_select]
        if self.checkpoint_handler:
            action, top, branch = self.checkpoint_handler.interactive_checkpoint(
                top, stage_name, self.config, self.receptor_pdbqt, out_dir)
        else:
            action, top, branch = interactive_checkpoint(top, stage_name, self.config, self.receptor_pdbqt, out_dir)
        if action == "rerun":
            return self._run_stage_with_checkpoint(stage_name, stage_func, seed_results)
        self.all_results.extend([r for r in top if r not in self.all_results])
        return top

    def run_sidechain_stage(self, seed_results):
        from .stages.sidechain import run_sidechain_optimization
        return self._run_stage_with_checkpoint("Side-Chain Optimization", run_sidechain_optimization, seed_results)

    def run_backbone_stage(self, seed_results):
        from .stages.backbone import run_backbone_optimization
        return self._run_stage_with_checkpoint("Backbone Optimization", run_backbone_optimization, seed_results)

    def run_minimization_stage(self, seed_results):
        from .stages.minimize import run_minimization
        return self._run_stage_with_checkpoint("Sequence Minimization", run_minimization, seed_results)

    def dock_user_smiles(self) -> List[DockingResult]:
        out_dir = ensure_dir(self.config.output_dir / "user_specified")
        results = []
        for i, smi in enumerate(self.config.user_smiles):
            name = "user_" + str(i + 1)
            try:
                val = validate_ligand(smi, name=name, max_residues=self.config.optimization.max_residues)
                print_validation_alerts(val)
                if not val.is_valid:
                    logger.error("Skipping invalid user SMILES %d: %s", i + 1, "; ".join(val.errors))
                    continue
                lig_pdbqt = smiles_to_pdbqt(smi, name=name, output_dir=out_dir)
                result = run_vina(receptor_pdbqt=self.receptor_pdbqt, ligand_pdbqt=lig_pdbqt, ligand_name=name, smiles=smi, docking_params=self.config.docking, output_dir=out_dir, vina_executable=self.config.vina_executable, origin="user")
                results.append(result)
                self.all_results.append(result)
                bw = check_binding_quality(result.best_energy, name=name, poor_binding_threshold=self.config.optimization.poor_binding_threshold)
                print_binding_alerts(bw)
                logger.info("User SMILES %d: %s -> %.2f kcal/mol", i + 1, smi, result.best_energy)
            except Exception as e:
                logger.error("Failed to dock user SMILES %d (%s): %s", i + 1, smi, e)
        return results

    def generate_report(self):
        """Generate CSV and markdown reports for all docked candidates."""
        records = results_to_records(self.all_results)
        original_rec = None
        if self.original_result:
            recs = results_to_records([self.original_result])
            if recs:
                original_rec = recs[0]
        csv_path = self.config.output_dir / "results_summary.csv"
        generate_csv_report(records, csv_path)
        md_path = self.config.output_dir / "results_report.md"
        generate_markdown_report(records, original_rec, md_path,
                                 top_n=self.config.optimization.top_n_select)
        logger.info("Reports written: %s, %s", csv_path, md_path)

        # Generate complex PDB with best candidate docked to receptor
        if self.all_results and self.receptor_clean_pdb:
            best = sorted(self.all_results, key=lambda r: r.best_energy)[0]
            if best.best_pose_pdb and best.best_pose_pdb.exists():
                complex_path = self.config.output_dir / "best_complex.pdb"
                generate_complex_pdb(
                    self.receptor_clean_pdb, best.best_pose_pdb,
                    complex_path, ligand_name=best.ligand_name,
                )
                logger.info("Complex PDB (receptor + best ligand): %s", complex_path)
                logger.info("Best candidate: %s (%.2f kcal/mol)",
                            best.ligand_name, best.best_energy)

            # Generate QC complex PDBs for backbone modification categories
            self._generate_qc_complexes()

    def _generate_qc_complexes(self):
        """Generate QC complex PDBs for best D-amino acid, beta-amino acid,
        and unnatural amino acid candidates.

        These complexes let users visually verify that backbone modifications
        and unnatural residues are docking correctly.
        """
        if not self.receptor_clean_pdb or not self.receptor_clean_pdb.exists():
            return

        qc_dir = ensure_dir(self.config.output_dir / "qc_complexes")

        # Collect custom UAA names for identification
        custom_uaa_names = set()
        for name in getattr(self.config.optimization, 'sc_custom_sidechains', {}):
            custom_uaa_names.add(name.upper())

        # Categorize results by modification type using annotation
        best_d_amino = None      # Best D-amino acid result
        best_beta = None         # Best beta-amino acid result
        best_uaa = None          # Best unnatural amino acid result
        best_cterm_amide = None  # Best C-terminal amide result
        best_nterm_methyl = None # Best N-terminal methylated result
        best_nterm_acyl = None   # Best N-terminal acylated result
        best_nterm_custom = None # Best N-terminal custom mod result

        for r in self.all_results:
            ann = getattr(r, 'annotation', '').lower()
            if not ann:
                continue

            # D-amino acid detection
            if 'd-amino' in ann:
                if best_d_amino is None or r.best_energy < best_d_amino.best_energy:
                    best_d_amino = r

            # Beta-amino acid detection (beta-2 or beta-3)
            if 'beta-2' in ann or 'beta-3' in ann or 'beta' in ann:
                if best_beta is None or r.best_energy < best_beta.best_energy:
                    best_beta = r

            # C-terminal amide detection
            if 'c-term amide' in ann:
                if best_cterm_amide is None or r.best_energy < best_cterm_amide.best_energy:
                    best_cterm_amide = r

            # N-terminal methylation detection
            if 'n-term methylation' in ann or 'n-term dimethyl' in ann:
                if best_nterm_methyl is None or r.best_energy < best_nterm_methyl.best_energy:
                    best_nterm_methyl = r

            # N-terminal acylation detection
            if 'n-term acetyl' in ann or 'n-term propionyl' in ann or 'n-term palmitoyl' in ann or ('n-term c' in ann and '-acyl' in ann):
                if best_nterm_acyl is None or r.best_energy < best_nterm_acyl.best_energy:
                    best_nterm_acyl = r

            # N-terminal custom modification detection
            if 'n-term custom' in ann:
                if best_nterm_custom is None or r.best_energy < best_nterm_custom.best_energy:
                    best_nterm_custom = r

            # Unnatural amino acid detection:
            # Check if annotation references any custom UAA name
            if custom_uaa_names:
                ann_upper = getattr(r, 'annotation', '').upper()
                for uaa_name in custom_uaa_names:
                    if uaa_name in ann_upper:
                        if best_uaa is None or r.best_energy < best_uaa.best_energy:
                            best_uaa = r
                        break

        # Generate QC complexes
        qc_entries = [
            (best_d_amino, "qc_best_d_amino_acid_complex.pdb", "D-amino acid"),
            (best_beta, "qc_best_beta_amino_acid_complex.pdb", "Beta-amino acid"),
            (best_uaa, "qc_best_unnatural_aa_complex.pdb", "Unnatural amino acid"),
            (best_cterm_amide, "qc_best_cterm_amide_complex.pdb", "C-term amide"),
            (best_nterm_methyl, "qc_best_nterm_methyl_complex.pdb", "N-term methylated"),
            (best_nterm_acyl, "qc_best_nterm_acyl_complex.pdb", "N-term acylated"),
            (best_nterm_custom, "qc_best_nterm_custom_complex.pdb", "N-term custom"),
        ]

        generated = []
        for result, filename, label in qc_entries:
            if result and result.best_pose_pdb and result.best_pose_pdb.exists():
                complex_path = qc_dir / filename
                generate_complex_pdb(
                    self.receptor_clean_pdb, result.best_pose_pdb,
                    complex_path, ligand_name=result.ligand_name,
                )
                generated.append(label)
                logger.info("QC complex (%s): %s -> %s (%.2f kcal/mol, %s)",
                            label, result.ligand_name, complex_path,
                            result.best_energy, getattr(result, 'annotation', ''))

        if generated:
            logger.info("=== QC Complexes generated: %s ===", ", ".join(generated))
        else:
            logger.info("No QC complexes generated (no backbone/UAA modifications found)")

    def estimate_total_docks(self) -> int:
        """Estimate total number of docking operations for the full pipeline.

        Uses peptide length and allowed AAs to estimate candidates per stage.
        Returns total estimated docks across all stages.
        """
        from rdkit import Chem
        # Count residues in the ligand
        n_residues = 0
        if self.config.ligand_sequence:
            n_residues = len(self.config.ligand_sequence)
        elif self.config.ligand_smiles:
            mol = Chem.MolFromSmiles(self.config.ligand_smiles)
            if mol:
                amide_pat = Chem.MolFromSmarts('[C](=O)[NH]')
                if amide_pat:
                    n_residues = len(mol.GetSubstructMatches(amide_pat)) + 1

        if n_residues == 0:
            n_residues = 3  # fallback

        n_allowed = len(self.config.optimization.sc_allowed_residues)
        n_custom = len(getattr(self.config.optimization, 'sc_custom_sidechains', {}))
        n_total_aas = n_allowed + n_custom
        max_rounds = self.config.optimization.max_rounds
        max_cand = self.config.optimization.max_candidates_per_round
        top_n = self.config.optimization.top_n_select

        total = 1  # initial dock

        if 'sidechain' in self.config.stages:
            sc_per_round = min(n_residues * n_total_aas, max_cand)
            total += sc_per_round * max_rounds

        if 'backbone' in self.config.stages:
            bb_pos = min(self.config.optimization.bb_max_positions, n_residues)
            bb_per_round = 4 * bb_pos * top_n  # 4 modification types
            total += bb_per_round * max_rounds

        if 'minimize' in self.config.stages:
            min_del = min(self.config.optimization.min_max_deletions, n_residues)
            min_per_round = 2 * min_del * top_n  # Gly + Ala replacements
            total += min_per_round * max_rounds

        if self.config.user_smiles:
            total += len(self.config.user_smiles)

        return total

    def run(self):
        logger.info("Starting Stephen Docking v0.4.0")
        logger.info("Run mode: %s", self.config.run_mode)
        logger.info("Receptor: %s", self.config.receptor_pdb)
        logger.info("Ligand SMILES: %s", self.config.ligand_smiles)
        self.receptor_pdbqt = self.prepare_receptor()
        # Auto-calculate docking box from pocket residues if specified
        if self.config.pocket_residues:
            center, size = find_pocket_center(
                self.config.receptor_pdb, self.config.pocket_residues
            )
            self.config.docking.center_x = center[0]
            self.config.docking.center_y = center[1]
            self.config.docking.center_z = center[2]
            self.config.docking.size_x = size[0]
            self.config.docking.size_y = size[1]
            self.config.docking.size_z = size[2]
            logger.info("Docking box set from pocket residues: center=(%.1f, %.1f, %.1f), size=(%.1f, %.1f, %.1f)",
                        center[0], center[1], center[2], size[0], size[1], size[2])

        initial_result = self.dock_initial_ligand()
        self.original_score = initial_result.best_energy
        self.original_result = initial_result
        current_best = [initial_result]
        score_str = str(initial_result.ligand_name) + " = " + str(round(initial_result.best_energy, 2)) + " kcal/mol"
        print("\n  Initial docking: " + score_str)
        binding_warnings = check_binding_quality(initial_result.best_energy, name=initial_result.ligand_name, poor_binding_threshold=self.config.optimization.poor_binding_threshold)
        print_binding_alerts(binding_warnings)

        # Global time estimation
        if self.time_per_dock > 0 and self.config.run_mode != "single_dock":
            total_docks = self.estimate_total_docks()
            est_total_sec = total_docks * self.time_per_dock
            if est_total_sec < 60:
                est_str = "{:.0f} sec".format(est_total_sec)
            elif est_total_sec < 3600:
                est_str = "{:.1f} min".format(est_total_sec / 60)
            else:
                est_str = "{:.1f} hr".format(est_total_sec / 3600)
            logger.info("=== Global Estimate: ~%d docks total, ~%s at %.1f sec/dock ===",
                        total_docks, est_str, self.time_per_dock)
            self.estimated_end_time = time.time() + est_total_sec
            self.estimated_total_docks = total_docks
            self.completed_docks = 1  # initial dock done

        if self.config.run_mode == "single_dock":
            if self.config.user_smiles:
                self.dock_user_smiles()
            self.generate_report()
            print("\n  Single-dock mode complete. Results in: " + str(self.config.output_dir))
            return
        if "sidechain" in self.config.stages:
            logger.info("=== Stage 1: Side-Chain Optimization ===")
            current_best = self.run_sidechain_stage(current_best)
        if "backbone" in self.config.stages:
            logger.info("=== Stage 2: Backbone Optimization ===")
            current_best = self.run_backbone_stage(current_best)
        if "minimize" in self.config.stages:
            logger.info("=== Stage 3: Sequence Minimization ===")
            current_best = self.run_minimization_stage(current_best)
        if self.config.user_smiles:
            self.dock_user_smiles()
        self.generate_report()
        logger.info("Pipeline complete. All results in: %s", self.config.output_dir)
