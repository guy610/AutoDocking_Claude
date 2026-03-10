"""
Report generation: CSV summary and optional markdown report.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class CandidateRecord:
    """A single row in the final report."""
    uid: str
    origin: str          # initial / sidechain / backbone / minimize / user
    smiles: str
    docking_score: float
    n_hbonds: int
    n_polar_contacts: int
    n_backbone_mutations: int
    n_backbone_interactions: int


def generate_csv_report(records: List[dict],
                        output_path: Path) -> Path:
    """Write the summary CSV/TSV file."""
    # TODO: Step 8 – implement
    raise NotImplementedError


def generate_markdown_report(records: List[dict],
                             original_record: dict,
                             output_path: Path,
                             top_n: int = 10) -> Path:
    """Write a human-readable markdown summary."""
    # TODO: Step 8 – implement
    raise NotImplementedError
