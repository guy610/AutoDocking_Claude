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
        optimization = OptimizationParams(
            max_rounds=int(d.get("max_rounds", 3)),
            top_n_select=int(d.get("top_n", 5)),
            delta_affinity_threshold=float(d.get("delta_threshold", 0.5)),
            max_residues=int(d.get("max_residues", 5)),
            poor_binding_threshold=float(d.get("poor_binding", -4.0)),
        )
        mode = d.get("run_mode", "full")
        if mode == "single_dock":
            stages = []
        elif mode == "sidechain":
            stages = ["sidechain"]
        elif mode == "backbone":
            stages = ["backbone"]
        elif mode == "minimize":
            stages = ["minimize"]
        else:
            stages = ["sidechain", "backbone", "minimize"]

        pocket_residues = []
        pr = d.get("pocket_residues", "")
        if pr:
            pocket_residues = [s.strip() for s in pr.split(",") if s.strip()]

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
            remove_waters=d.get("remove_waters", True),
            remove_heteroatoms=d.get("remove_heteroatoms", True),
            run_mode=mode,
            stages=stages,
        )

    def _run(self):
        # Set up logging to queue
        root_logger = logging.getLogger("autodock_pipeline")
        handler = QueueLogHandler(self.event_queue)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

        try:
            config = self._build_config()
            pipeline = DockingPipeline(config)
            pipeline.checkpoint_handler = self.checkpoint_handler
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
                     "score": rec.docking_score}
                self.results.append(d)

            self.event_queue.put({
                "type": "complete",
                "results": self.results,
                "output_dir": str(config.output_dir),
            })
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
