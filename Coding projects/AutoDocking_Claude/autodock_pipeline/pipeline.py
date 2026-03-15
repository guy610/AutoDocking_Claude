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

    def run(self):
        logger.info("Starting Stephen Docking v0.2.0")
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
