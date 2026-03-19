"""
Web-compatible pipeline runner with checkpoint handler and log streaming.
"""

import logging
import queue
import threading
import traceback
from pathlib import Path
from typing import Dict, List, Optional

from ..config import PipelineConfig, DockingParams, OptimizationParams
from ..pipeline import DockingPipeline
from ..core.docking import DockingResult, run_vina
from ..core.validators import (
    validate_ligand, check_binding_quality,
    print_validation_alerts, print_binding_alerts,
)
from ..utils.reporting import results_to_records

logger = logging.getLogger(__name__)


def _detect_wsl_tool(check_commands: list, fallback: str = "") -> str:
    """Try to find a tool in WSL by running a series of check commands.

    Each command is run via 'wsl bash -c "..."'. If any succeeds (exit 0)
    and returns a non-empty path, return 'wsl <path>'. Otherwise return fallback.
    """
    import subprocess
    for check in check_commands:
        try:
            result = subprocess.run(
                ["wsl", "bash", "-c", check],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path:
                    return "wsl " + path
        except Exception:
            continue
    return fallback


class QueueLogHandler(logging.Handler):
    """Logging handler that pushes records into a queue for SSE streaming."""

    def __init__(self, event_queue: queue.Queue):
        super().__init__()
        self.event_queue = event_queue

    def emit(self, record):
        try:
            self.event_queue.put({
                "type": "log",
                "level": record.levelname,
                "message": self.format(record),
                "timestamp": record.created,
            })
        except Exception:
            pass


class WebCheckpointHandler:
    """Replaces terminal interactive_checkpoint for web mode.

    Pushes checkpoint events to a queue and blocks until
    the frontend responds via threading.Event.
    """

    def __init__(self, event_queue: queue.Queue):
        self.event_queue = event_queue
        self.response_event = threading.Event()
        self.response_data: Dict = {}

    def interactive_checkpoint(self, results, stage_name, config, receptor_pdbqt, output_dir):
        """Web-compatible checkpoint: push event, block, return decision."""
        candidates = []
        for i, r in enumerate(results):
            candidates.append({
                "rank": i + 1,
                "name": r.ligand_name,
                "score": round(r.best_energy, 2),
                "origin": r.origin,
                "smiles": r.smiles,
            })

        self.event_queue.put({
            "type": "checkpoint",
            "stage": stage_name,
            "candidates": candidates,
            "output_dir": str(output_dir),
        })

        # Block until frontend responds
        self.response_event.wait()
        self.response_event.clear()

        action = self.response_data.get("action", "continue")
        inject_smiles = self.response_data.get("smiles", [])

        # If user injected SMILES, dock them
        if inject_smiles:
            results = self._dock_and_merge(
                inject_smiles, results, config, receptor_pdbqt, output_dir
            )

        top = sorted(results, key=lambda r: r.best_energy)[
            : config.optimization.top_n_select
        ]
        return action, top, None

    def _dock_and_merge(self, smiles_list, existing_results, config,
                        receptor_pdbqt, output_dir):
        """Dock user-provided SMILES and merge into results."""
        from ..core.ligand import smiles_to_pdbqt

        all_results = list(existing_results)
        for i, smi in enumerate(smiles_list):
            name = "web_inject_{}".format(len(all_results) + 1)
            try:
                val = validate_ligand(
                    smi, name=name,
                    max_residues=config.optimization.max_residues,
                )
                print_validation_alerts(val)
                if not val.is_valid:
                    logger.warning("Skipping invalid injected SMILES: %s", smi)
                    continue
                lig_pdbqt = smiles_to_pdbqt(smi, name=name, output_dir=output_dir)
                result = run_vina(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=lig_pdbqt,
                    ligand_name=name,
                    smiles=smi,
                    docking_params=config.docking,
                    output_dir=output_dir,
                    vina_executable=config.vina_executable,
                    origin="web-inject",
                )
                all_results.append(result)
                logger.info("Injected %s: %.2f kcal/mol", name, result.best_energy)
            except Exception as e:
                logger.error("Failed to dock injected SMILES %s: %s", smi, e)
        return all_results


class PipelineRunner:
    """Manages running the docking pipeline in a background thread."""

    def __init__(self, config_data: dict):
        self.config_data = config_data
        self.event_queue: queue.Queue = queue.Queue()
        self.checkpoint_handler = WebCheckpointHandler(self.event_queue)
        self.results: Optional[List[dict]] = None
        self.is_running = False
        self.is_complete = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.is_running = True
        self._thread.start()

    def _build_config(self) -> PipelineConfig:
        d = self.config_data
        docking = DockingParams(
            center_x=float(d.get("center_x", 0)),
            center_y=float(d.get("center_y", 0)),
            center_z=float(d.get("center_z", 0)),
            size_x=float(d.get("size_x", 20)),
            size_y=float(d.get("size_y", 20)),
            size_z=float(d.get("size_z", 20)),
            exhaustiveness=int(d.get("exhaustiveness", 8)),
            num_modes=int(d.get("num_modes", 9)),
            energy_range=int(d.get("energy_range", 3)),
        )
        # Parse allowed residues from web form (if provided)
        allowed_residues = d.get("sc_allowed_residues", [])
        if isinstance(allowed_residues, str):
            allowed_residues = [s.strip() for s in allowed_residues.split(",") if s.strip()]

        # Parse custom UAA sidechains
        custom_sidechains = {}
        for key, val in d.items():
            if key.startswith("uaa_name_") and val:
                idx = key.split("_")[-1]
                smi_key = "uaa_smiles_" + idx
                smi_val = d.get(smi_key, "")
                if smi_val:
                    custom_sidechains[val.strip()] = smi_val.strip()

        optimization = OptimizationParams(
            max_rounds=int(d.get("max_rounds", 3)),
            top_n_select=int(d.get("top_n", 5)),
            delta_affinity_threshold=float(d.get("delta_threshold", 0.5)),
            max_residues=int(d.get("max_residues", 5)),
            poor_binding_threshold=float(d.get("poor_binding", -4.0)),
        )
        if allowed_residues:
            optimization.sc_allowed_residues = allowed_residues
        if custom_sidechains:
            optimization.sc_custom_sidechains = custom_sidechains
        if d.get("scan_cterm_caps", False):
            optimization.scan_cterm_caps = True
        if d.get("nterm_dimethyl", False):
            optimization.nterm_dimethyl = True
        if d.get("nterm_acyl", False):
            optimization.nterm_acyl = True
            optimization.nterm_acyl_carbons = int(d.get("nterm_acyl_carbons", 2))
        nterm_custom = d.get("nterm_custom_smiles", "").strip()
        if nterm_custom:
            optimization.nterm_custom_smiles = nterm_custom
        mode = d.get("run_mode", "full")
        if mode == "single_dock":
            stages = []
        elif mode == "sidechain":
            stages = ["sidechain"]
        elif mode == "backbone":
            stages = ["backbone"]
        elif mode == "minimize":
            stages = ["minimize"]
        elif mode == "hierarchical":
            stages = ["sidechain", "backbone", "minimize"]
        else:
            stages = ["sidechain", "backbone", "minimize"]

        pocket_residues = []
        pr = d.get("pocket_residues", "")
        if pr:
            pocket_residues = [s.strip() for s in pr.split(",") if s.strip()]

        # Pocket Triage (auto_consensus) parameters
        box_mode = d.get("box_mode", "default")
        if box_mode == "pocket" and not pocket_residues:
            box_mode = "default"  # fall back if no residues provided
        min_pocket_volume = float(d.get("min_pocket_volume", 300.0))
        p2rank_executable = d.get("p2rank_executable", "").strip()
        fpocket_executable = d.get("fpocket_executable", "").strip()

        # Auto-detect P2Rank/Fpocket in WSL if user left fields empty
        if box_mode == "auto_consensus":
            if not p2rank_executable:
                p2rank_executable = _detect_wsl_tool(
                    ["ls /opt/p2rank_2.5.1/prank", "ls /opt/p2rank/prank",
                     "which prank"],
                    fallback="wsl /opt/p2rank_2.5.1/prank",
                )
                if p2rank_executable:
                    logger.info("Auto-detected P2Rank: %s", p2rank_executable)
            if not fpocket_executable:
                fpocket_executable = _detect_wsl_tool(
                    ["which fpocket"],
                    fallback="wsl fpocket",
                )
                if fpocket_executable:
                    logger.info("Auto-detected Fpocket: %s", fpocket_executable)

        user_smiles = []
        us = d.get("user_smiles", "")
        if us:
            user_smiles = [s.strip() for s in us.strip().splitlines() if s.strip()]

        # Convert peptide sequence to SMILES if sequence mode was used
        ligand_smiles = d.get("ligand_smiles", "")
        ligand_sequence = d.get("ligand_sequence", "")
        if not ligand_smiles and ligand_sequence:
            try:
                from rdkit import Chem
                mol = Chem.MolFromSequence(ligand_sequence)
                if mol is not None:
                    ligand_smiles = Chem.MolToSmiles(mol)
                    logger.info("Converted sequence '%s' to SMILES: %s",
                                ligand_sequence, ligand_smiles)
                else:
                    raise ValueError("RDKit cannot parse sequence: " + ligand_sequence)
            except Exception as e:
                raise ValueError("Failed to convert sequence to SMILES: " + str(e))

        return PipelineConfig(
            receptor_pdb=Path(d["receptor_path"]),
            ligand_smiles=ligand_smiles,
            ligand_name=d.get("ligand_name", "ligand"),
            ligand_sequence=ligand_sequence,
            user_smiles=user_smiles,
            pocket_residues=pocket_residues,
            docking=docking,
            optimization=optimization,
            output_dir=Path(d.get("output_dir", "output")),
            vina_executable=d.get("vina_executable", "vina"),
            gnina_executable=d.get("gnina_executable", ""),
            rxdock_executable=d.get("rxdock_executable", ""),
            hierarchical_top_n=int(d.get("hierarchical_top_n", 20)),
            p2rank_executable=p2rank_executable,
            fpocket_executable=fpocket_executable,
            min_pocket_volume=min_pocket_volume,
            box_mode=box_mode,
            remove_waters=d.get("remove_waters", True),
            remove_heteroatoms=d.get("remove_heteroatoms", True),
            run_mode=mode,
            stages=stages,
        )

    def _build_sm_config(self):
        """Build SmallMoleculeConfig from web form data."""
        from ..config import SmallMoleculeConfig, DockingParams
        d = self.config_data

        docking = DockingParams(
            exhaustiveness=int(d.get("sm_exhaustiveness", 16)),
            num_modes=int(d.get("sm_num_modes", 9)),
            energy_range=int(d.get("sm_energy_range", 3)),
        )

        sm_mode = d.get("sm_run_mode", "full")

        # Auto-detect Vina in WSL if empty
        vina_exec = d.get("sm_vina_executable", "").strip()
        if not vina_exec:
            vina_exec = d.get("vina_executable", "vina")

        return SmallMoleculeConfig(
            crystal_pdb=Path(d["receptor_path"]),  # reuses same upload field
            ligand_resname=d.get("sm_ligand_resname", "").strip(),
            ligand_chain=d.get("sm_ligand_chain", "").strip(),
            autobox_padding=float(d.get("sm_autobox_padding", 4.0)),
            max_analogs=int(d.get("sm_max_analogs", 50)),
            enable_bioisosteres=d.get("sm_enable_bioisosteres", True),
            enable_extensions=d.get("sm_enable_extensions", True),
            enable_removals=d.get("sm_enable_removals", True),
            # v0.9.1: Multi-round optimization
            max_rounds=int(d.get("sm_max_rounds", 3)),
            delta_threshold=float(d.get("sm_delta_threshold", 0.3)),
            max_combos_per_round=int(d.get("sm_max_combos_per_round", 100)),
            # v0.9.1: Property target window
            property_target=d.get("sm_property_target", "cosmetic"),
            target_logp_min=float(d.get("sm_target_logp_min", 1.0)),
            target_logp_max=float(d.get("sm_target_logp_max", 3.0)),
            target_mw_max=float(d.get("sm_target_mw_max", 350.0)),
            target_psa_max=float(d.get("sm_target_psa_max", 70.0)),
            target_hbd_max=int(d.get("sm_target_hbd_max", 2)),
            target_hba_max=int(d.get("sm_target_hba_max", 5)),
            # v0.9.1: Pro-drug esters & cyclization
            enable_prodrug_esters=d.get("sm_enable_prodrug_esters", True),
            enable_cyclization_detection=d.get("sm_enable_cyclization_detection", True),
            # v0.9.2: SAR enhancements
            enable_stereoisomer_enum=d.get("sm_enable_stereoisomer_enum", True),
            stereo_max_centers=int(d.get("sm_stereo_max_centers", 4)),
            stereo_final_top_n=int(d.get("sm_stereo_final_top_n", 5)),
            enable_thioether_detection=d.get("sm_enable_thioether_detection", True),
            enable_metabolic_blocking=d.get("sm_enable_metabolic_blocking", True),
            enable_scaffold_hopping=d.get("sm_enable_scaffold_hopping", False),
            max_scaffold_hops=int(d.get("sm_max_scaffold_hops", 10)),
            enable_mmp_tracking=d.get("sm_enable_mmp_tracking", True),
            enable_torsion_filter=d.get("sm_enable_torsion_filter", True),
            torsion_amide_tolerance=float(d.get("sm_torsion_amide_tolerance", 30.0)),
            target_rotatable_max=int(d.get("sm_target_rotatable_max", -1)),
            docking=docking,
            run_mode=sm_mode,
            gnina_executable=d.get("sm_gnina_executable", "").strip(),
            rxdock_executable=d.get("sm_rxdock_executable", "").strip(),
            hierarchical_top_n=int(d.get("sm_hierarchical_top_n", 20)),
            output_dir=Path(d.get("output_dir", "output_sm")),
            vina_executable=vina_exec,
            remove_waters=d.get("sm_remove_waters", True),
        )

    def _run(self):
        # Set up logging to queue
        root_logger = logging.getLogger("autodock_pipeline")
        handler = QueueLogHandler(self.event_queue)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

        try:
            pipeline_type = self.config_data.get("pipeline_type", "peptide")

            if pipeline_type == "small_molecule":
                self._run_sm_pipeline()
            else:
                self._run_peptide_pipeline()

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Pipeline failed: %s", e)
            self.event_queue.put({
                "type": "error",
                "message": str(e),
                "traceback": tb,
            })
        finally:
            self.is_running = False
            self.is_complete = True
            root_logger.removeHandler(handler)

    def _run_peptide_pipeline(self):
        """Run the peptide optimization pipeline (existing behavior)."""
        import time as _time

        config = self._build_config()
        pipeline = DockingPipeline(config)
        pipeline.checkpoint_handler = self.checkpoint_handler

        self._pipeline = pipeline

        def _emit_progress():
            while self.is_running and not self.is_complete:
                if pipeline.estimated_end_time > 0:
                    remaining = max(0, pipeline.estimated_end_time - _time.time())
                    self.event_queue.put({
                        "type": "progress",
                        "estimated_remaining_sec": round(remaining, 1),
                        "completed_docks": pipeline.completed_docks,
                        "total_docks": pipeline.estimated_total_docks,
                        "time_per_dock": round(pipeline.time_per_dock, 1),
                    })
                _time.sleep(3)

        progress_thread = threading.Thread(target=_emit_progress, daemon=True)
        progress_thread.start()

        pipeline.run()

        # Collect results
        records = results_to_records(pipeline.all_results)
        self.results = []
        for i, rec in enumerate(
            sorted(records, key=lambda r: r.docking_score)
        ):
            d = {"rank": i + 1, "ligand_name": rec.uid,
                 "docking_score": rec.docking_score,
                 "origin": rec.origin, "smiles": rec.smiles,
                 "stereo": rec.stereo,
                 "score": rec.docking_score}
            self.results.append(d)

        self.event_queue.put({
            "type": "complete",
            "results": self.results,
            "output_dir": str(config.output_dir),
        })

    def _run_sm_pipeline(self):
        """Run the small molecule optimization pipeline."""
        import time as _time
        from ..sm_pipeline import SmallMoleculePipeline

        sm_config = self._build_sm_config()
        pipeline = SmallMoleculePipeline(sm_config)
        pipeline.checkpoint_handler = self.checkpoint_handler

        self._pipeline = pipeline

        def _emit_progress():
            while self.is_running and not self.is_complete:
                if pipeline.estimated_end_time > 0:
                    remaining = max(0, pipeline.estimated_end_time - _time.time())
                    self.event_queue.put({
                        "type": "progress",
                        "estimated_remaining_sec": round(remaining, 1),
                        "completed_docks": pipeline.completed_docks,
                        "total_docks": pipeline.estimated_total_docks,
                        "time_per_dock": round(pipeline.time_per_dock, 1),
                    })
                _time.sleep(3)

        progress_thread = threading.Thread(target=_emit_progress, daemon=True)
        progress_thread.start()

        pipeline.run()

        # Collect results
        records = results_to_records(pipeline.all_results)
        self.results = []
        for i, rec in enumerate(
            sorted(records, key=lambda r: r.docking_score)
        ):
            d = {"rank": i + 1, "ligand_name": rec.uid,
                 "docking_score": rec.docking_score,
                 "origin": rec.origin, "smiles": rec.smiles,
                 "stereo": getattr(rec, "stereo", ""),
                 "score": rec.docking_score}
            self.results.append(d)

        self.event_queue.put({
            "type": "complete",
            "results": self.results,
            "output_dir": str(sm_config.output_dir),
            "pipeline_type": "small_molecule",
        })
