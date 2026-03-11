"""
Report generation: CSV summary and markdown report.

Generates a comprehensive summary of all docked candidates across all
optimization stages, including scores, origins, and interaction metrics.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CandidateRecord:
    """A single row in the final report."""
    uid: str
    origin: str
    smiles: str
    docking_score: float
    n_hbonds: int = 0
    n_polar_contacts: int = 0
    n_backbone_mutations: int = 0
    n_backbone_interactions: int = 0
    n_sidechain_interactions: int = 0


def results_to_records(results, original_smiles: str = "") -> List[CandidateRecord]:
    """Convert DockingResult list to CandidateRecord list."""
    records = []
    for r in results:
        records.append(CandidateRecord(
            uid=r.ligand_name,
            origin=r.origin,
            smiles=r.smiles,
            docking_score=r.best_energy,
        ))
    return records


def generate_csv_report(records: List[CandidateRecord],
                        output_path: Path) -> Path:
    """Write the summary CSV file with all candidates."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "rank", "uid", "origin", "smiles", "docking_score",
        "n_hbonds", "n_polar_contacts",
        "n_backbone_interactions", "n_sidechain_interactions",
    ]

    # Sort by score (best first)
    sorted_records = sorted(records, key=lambda r: r.docking_score)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, rec in enumerate(sorted_records, 1):
            writer.writerow({
                "rank": i,
                "uid": rec.uid,
                "origin": rec.origin,
                "smiles": rec.smiles,
                "docking_score": round(rec.docking_score, 2),
                "n_hbonds": rec.n_hbonds,
                "n_polar_contacts": rec.n_polar_contacts,
                "n_backbone_interactions": rec.n_backbone_interactions,
                "n_sidechain_interactions": rec.n_sidechain_interactions,
            })

    logger.info("CSV report written: %s (%d candidates)", output_path, len(records))
    return output_path


def generate_markdown_report(records: List[CandidateRecord],
                             original_record: Optional[CandidateRecord],
                             output_path: Path,
                             top_n: int = 10) -> Path:
    """Write a human-readable markdown summary."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_records = sorted(records, key=lambda r: r.docking_score)
    top = sorted_records[:top_n]

    lines = []
    lines.append("# AutoDock Pipeline - Optimization Report")
    lines.append("")
    lines.append("Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("")

    # Original ligand summary
    if original_record:
        lines.append("## Original Ligand")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append("| Name | {} |".format(original_record.uid))
        lines.append("| SMILES | `{}` |".format(original_record.smiles))
        lines.append("| Docking Score | {:.2f} kcal/mol |".format(original_record.docking_score))
        lines.append("")

    # Top candidates
    lines.append("## Top {} Candidates".format(len(top)))
    lines.append("")
    lines.append("| Rank | Name | Score (kcal/mol) | Origin | SMILES |")
    lines.append("|------|------|-----------------|--------|--------|")
    for i, rec in enumerate(top, 1):
        delta = ""
        if original_record:
            d = rec.docking_score - original_record.docking_score
            delta = " ({:+.2f})".format(d)
        lines.append("| {} | {} | {:.2f}{} | {} | `{}` |".format(
            i, rec.uid, rec.docking_score, delta, rec.origin,
            rec.smiles[:50] + "..." if len(rec.smiles) > 50 else rec.smiles,
        ))
    lines.append("")

    # Stage breakdown
    lines.append("## Candidates by Stage")
    lines.append("")
    stages = {}
    for rec in sorted_records:
        stages.setdefault(rec.origin, []).append(rec)
    for stage, stage_recs in stages.items():
        scores = [r.docking_score for r in stage_recs]
        lines.append("### {} ({} candidates)".format(stage.title(), len(stage_recs)))
        lines.append("")
        lines.append("- Best score: {:.2f} kcal/mol".format(min(scores)))
        lines.append("- Worst score: {:.2f} kcal/mol".format(max(scores)))
        lines.append("- Mean score: {:.2f} kcal/mol".format(sum(scores) / len(scores)))
        lines.append("")

    # Summary statistics
    lines.append("## Summary")
    lines.append("")
    lines.append("- Total candidates docked: {}".format(len(records)))
    all_scores = [r.docking_score for r in records]
    lines.append("- Best score overall: {:.2f} kcal/mol ({})".format(
        min(all_scores), sorted_records[0].uid))
    if original_record:
        improvement = original_record.docking_score - min(all_scores)
        lines.append("- Improvement over original: {:.2f} kcal/mol".format(improvement))
    lines.append("")

    content = "\n".join(lines)
    output_path.write_text(content)
    logger.info("Markdown report written: %s", output_path)
    return output_path

