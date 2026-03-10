"""
Stage 1 - Side-chain optimization.

Vary amino-acid side chains while preserving the peptide backbone
connectivity and length. Generate mutant SMILES, dock, and select
the best candidates.
"""

from typing import List

from ..config import PipelineConfig
from ..core.docking import DockingResult


def generate_sidechain_variants(smiles: str,
                                config: PipelineConfig) -> List[str]:
    """Generate candidate SMILES with mutated side chains."""
    # TODO: Step 4 – implement
    raise NotImplementedError


def run_sidechain_optimization(config: PipelineConfig,
                               receptor_pdbqt,
                               initial_results: List[DockingResult],
                               original_score: float) -> List[DockingResult]:
    """Execute the iterative side-chain optimization loop."""
    # TODO: Step 4 – implement
    raise NotImplementedError
