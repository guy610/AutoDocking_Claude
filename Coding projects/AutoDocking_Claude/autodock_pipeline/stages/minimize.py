"""
Stage 3 - Sequence minimization (size reduction).

Remove or replace non-interacting residues/fragments to reduce
ligand size while preserving key binding interactions.
"""

from typing import List

from ..config import PipelineConfig
from ..core.docking import DockingResult
from ..core.interactions import InteractionMetrics


def identify_dispensable_residues(metrics: InteractionMetrics,
                                 config: PipelineConfig) -> List[int]:
    """Identify residues with minimal protein interactions."""
    # TODO: Step 6 – implement
    raise NotImplementedError


def generate_minimized_variants(smiles: str,
                                dispensable_positions: List[int],
                                config: PipelineConfig) -> List[str]:
    """Generate truncated / simplified candidate SMILES."""
    # TODO: Step 6 – implement
    raise NotImplementedError


def run_minimization(config: PipelineConfig,
                     receptor_pdbqt,
                     initial_results: List[DockingResult],
                     original_score: float) -> List[DockingResult]:
    """Execute the iterative sequence-minimization loop."""
    # TODO: Step 6 – implement
    raise NotImplementedError
