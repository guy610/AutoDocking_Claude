"""
Stage 2 - Backbone optimization.

Modify backbone geometry at positions with few backbone-mediated
interactions and that are relatively solvent-exposed.
"""

from typing import List

from ..config import PipelineConfig
from ..core.docking import DockingResult
from ..core.interactions import InteractionMetrics


def identify_backbone_candidates(metrics: InteractionMetrics,
                                 config: PipelineConfig) -> List[int]:
    """Identify residue positions eligible for backbone modifications."""
    # TODO: Step 5 – implement
    raise NotImplementedError


def generate_backbone_variants(smiles: str,
                               candidate_positions: List[int],
                               config: PipelineConfig) -> List[str]:
    """Generate backbone-modified candidate SMILES."""
    # TODO: Step 5 – implement
    raise NotImplementedError


def run_backbone_optimization(config: PipelineConfig,
                              receptor_pdbqt,
                              initial_results: List[DockingResult],
                              original_score: float) -> List[DockingResult]:
    """Execute the iterative backbone optimization loop."""
    # TODO: Step 5 – implement
    raise NotImplementedError
