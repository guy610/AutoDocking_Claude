"""
Checkpoint / resume system for long-running docking pipelines.

After every successful dock, the result is appended to a JSONL checkpoint
file.  If the run is interrupted (laptop sleep, crash, reboot), restarting
the same run will skip all already-completed docks and continue from where
it left off.

Usage in stages:
    if checkpoint and checkpoint.has_result("sidechain", smi):
        result = checkpoint.reconstruct_result("sidechain", smi)
    else:
        result = run_vina(...)
        if checkpoint:
            checkpoint.save_result("sidechain", result)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RunCheckpoint:
    """Manages checkpoint save / load for docking runs."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.output_dir / ".checkpoint_results.jsonl"
        self.state_file = self.output_dir / ".checkpoint_state.json"
        self._cache: Dict[str, dict] = {}  # key -> serialised DockingResult
        self._load()

    # ------------------------------------------------------------------ #
    #  Key = "stage|smiles"  (unique per candidate per stage)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_key(stage: str, smiles: str) -> str:
        return "{}|{}".format(stage, smiles)

    # ------------------------------------------------------------------ #
    #  Load existing checkpoint
    # ------------------------------------------------------------------ #
    def _load(self):
        if not self.results_file.exists():
            return
        count = 0
        for line in self.results_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                key = self._make_key(entry["_stage"], entry["smiles"])
                self._cache[key] = entry
                count += 1
            except (json.JSONDecodeError, KeyError):
                continue
        if count:
            logger.info("Checkpoint: loaded %d cached dock results from %s",
                        count, self.results_file.name)

    # ------------------------------------------------------------------ #
    #  Query
    # ------------------------------------------------------------------ #
    def has_result(self, stage: str, smiles: str) -> bool:
        return self._make_key(stage, smiles) in self._cache

    def get_cached_dict(self, stage: str, smiles: str) -> Optional[dict]:
        return self._cache.get(self._make_key(stage, smiles))

    # ------------------------------------------------------------------ #
    #  Save one result (append)
    # ------------------------------------------------------------------ #
    def save_result(self, stage: str, result) -> None:
        """Append a DockingResult to the checkpoint JSONL file.

        *result* is a DockingResult dataclass instance.
        """
        entry = _result_to_dict(result)
        entry["_stage"] = stage
        key = self._make_key(stage, entry["smiles"])
        self._cache[key] = entry
        with open(self.results_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ------------------------------------------------------------------ #
    #  Reconstruct a DockingResult from cache
    # ------------------------------------------------------------------ #
    def reconstruct_result(self, stage: str, smiles: str):
        """Return a DockingResult rebuilt from checkpoint data, or None."""
        d = self.get_cached_dict(stage, smiles)
        if d is None:
            return None
        return _dict_to_result(d)

    # ------------------------------------------------------------------ #
    #  Pipeline-level state (which stage/round we were in)
    # ------------------------------------------------------------------ #
    def save_state(self, state: dict) -> None:
        self.state_file.write_text(json.dumps(state, indent=2),
                                   encoding="utf-8")

    def load_state(self) -> Optional[dict]:
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    @property
    def n_cached(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """Delete checkpoint files (fresh start)."""
        if self.results_file.exists():
            self.results_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()
        self._cache.clear()
        logger.info("Checkpoint cleared")


# ====================================================================== #
#  Serialisation helpers for DockingResult
# ====================================================================== #

def _result_to_dict(result) -> dict:
    """Serialise a DockingResult to a JSON-safe dict."""
    return {
        "ligand_name": result.ligand_name,
        "smiles": result.smiles,
        "best_energy": result.best_energy,
        "output_pdbqt": str(result.output_pdbqt) if result.output_pdbqt else "",
        "all_energies": list(result.all_energies),
        "log_path": str(result.log_path) if result.log_path else "",
        "best_pose_pdb": str(result.best_pose_pdb) if result.best_pose_pdb else "",
        "origin": result.origin,
        "annotation": getattr(result, "annotation", ""),
    }


def _dict_to_result(d: dict):
    """Reconstruct a DockingResult from a serialised dict."""
    from .docking import DockingResult

    output_pdbqt = Path(d["output_pdbqt"]) if d.get("output_pdbqt") else None
    log_path = Path(d["log_path"]) if d.get("log_path") else None
    best_pose_pdb = Path(d["best_pose_pdb"]) if d.get("best_pose_pdb") else None

    result = DockingResult(
        ligand_name=d["ligand_name"],
        smiles=d["smiles"],
        best_energy=d["best_energy"],
        output_pdbqt=output_pdbqt,
        all_energies=d.get("all_energies", []),
        log_path=log_path,
        best_pose_pdb=best_pose_pdb,
        origin=d.get("origin", ""),
        annotation=d.get("annotation", ""),
    )
    return result
