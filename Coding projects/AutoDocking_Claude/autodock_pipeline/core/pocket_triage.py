"""
Pocket Triage: automatic binding-pocket discovery and validation using
P2Rank (ML-based prediction) and Fpocket (geometry-based volume measurement).

Three-step pipeline:
  1. P2Rank locates the top predicted pockets (the "anchor" sites).
  2. Fpocket measures cavity volumes for all detected pockets.
  3. Distance matching cross-references the two tools, then selects the
     highest-ranking P2Rank pocket whose matched Fpocket volume exceeds
     a user-specified threshold (min_pocket_volume).

Designed for peptides that use an "anchor and lip" binding strategy:
a deep hole for a bulky sidechain plus adjacent surface area.
"""

import csv
import logging
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .gnina import _build_cmd, _wsl_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class P2RankPocket:
    """A single pocket predicted by P2Rank."""
    rank: int
    score: float
    center_x: float
    center_y: float
    center_z: float


@dataclass
class FpocketCavity:
    """A single cavity detected by Fpocket."""
    index: int
    volume: float        # Angstroms^3
    center_x: float
    center_y: float
    center_z: float


@dataclass
class TriageResult:
    """The winning pocket after cross-referencing P2Rank and Fpocket."""
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    p2rank_rank: int
    p2rank_score: float
    fpocket_volume: float
    pocket_label: str    # human-readable description


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _euclidean_distance(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def _box_size_from_volume(volume: float) -> float:
    """Estimate a uniform docking-box side length from cavity volume.

    Uses the cube-root of volume as a diameter estimate, adds 4 A padding
    on each side, and enforces a minimum of 20 A.
    """
    side = 2.0 * (volume ** (1.0 / 3.0)) + 4.0
    return max(20.0, round(side, 1))


# ---------------------------------------------------------------------------
# P2Rank
# ---------------------------------------------------------------------------

def run_p2rank(
    receptor_pdb: Path,
    p2rank_executable: str,
    output_dir: Path,
    top_n: int = 3,
) -> List[P2RankPocket]:
    """Run P2Rank pocket prediction and return the top N pockets.

    P2Rank writes ``<output_dir>/<basename>.pdb_predictions.csv``
    with columns including ``rank, score, center_x, center_y, center_z``.
    """
    if not p2rank_executable:
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdb_path = Path(receptor_pdb).resolve()
    out_path = output_dir.resolve()

    cmd = _build_cmd(p2rank_executable, [
        "predict",
        "-f", str(pdb_path),
        "-o", str(out_path),
    ])

    logger.info("Running P2Rank: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error("P2Rank failed (exit %d):\n%s",
                         result.returncode, result.stderr[:1000])
            return []

    except FileNotFoundError:
        logger.error("P2Rank executable not found: %s", p2rank_executable)
        return []
    except subprocess.TimeoutExpired:
        logger.error("P2Rank timed out (300 s)")
        return []
    except Exception as e:
        logger.error("P2Rank error: %s", e)
        return []

    # Locate the predictions CSV.
    # P2Rank writes to <output_dir>/<basename>.pdb_predictions.csv
    basename = pdb_path.stem
    predictions_csv = None
    for candidate in [
        out_path / "{}.pdb_predictions.csv".format(basename),
        out_path / "{}_predictions.csv".format(basename),
    ]:
        if candidate.exists():
            predictions_csv = candidate
            break

    # Also search subdirectories (P2Rank may create a predict_* subdir)
    if predictions_csv is None:
        for f in out_path.rglob("*_predictions.csv"):
            predictions_csv = f
            break

    if predictions_csv is None:
        logger.error("P2Rank predictions CSV not found in %s", out_path)
        return []

    return _parse_p2rank_csv(predictions_csv, top_n)


def _parse_p2rank_csv(csv_path: Path, top_n: int) -> List[P2RankPocket]:
    """Parse P2Rank predictions CSV and return top N pockets."""
    pockets = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            # P2Rank CSV columns may have leading spaces; strip them
            if reader.fieldnames:
                reader.fieldnames = [f.strip() for f in reader.fieldnames]
            for row in reader:
                row = {k.strip(): v.strip() for k, v in row.items()}
                try:
                    pocket = P2RankPocket(
                        rank=int(row.get("rank", 0)),
                        score=float(row.get("score", 0)),
                        center_x=float(row.get("center_x", 0)),
                        center_y=float(row.get("center_y", 0)),
                        center_z=float(row.get("center_z", 0)),
                    )
                    pockets.append(pocket)
                except (ValueError, KeyError) as e:
                    logger.warning("Skipping P2Rank row: %s", e)
                    continue
    except Exception as e:
        logger.error("Failed to parse P2Rank CSV %s: %s", csv_path, e)
        return []

    pockets.sort(key=lambda p: p.rank)
    logger.info("P2Rank found %d pockets, returning top %d", len(pockets), min(top_n, len(pockets)))
    return pockets[:top_n]


# ---------------------------------------------------------------------------
# Fpocket
# ---------------------------------------------------------------------------

def run_fpocket(
    receptor_pdb: Path,
    fpocket_executable: str,
    output_dir: Path,
) -> List[FpocketCavity]:
    """Run Fpocket cavity detection and return all cavities with volumes.

    Fpocket creates ``<name>_out/`` next to the input PDB, containing:
      - ``<name>_info.txt`` with pocket descriptors (including Volume)
      - ``pockets/pocket<N>_vert.pqr`` with alpha sphere coordinates

    Note: When running via WSL, fpocket cannot read files on /mnt/c/ paths.
    We copy the PDB to a WSL-native temp directory, run fpocket there,
    then copy results back to output_dir.
    """
    if not fpocket_executable:
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdb_path = Path(receptor_pdb).resolve()
    basename = pdb_path.stem
    is_wsl = fpocket_executable.lower().startswith("wsl ")

    if is_wsl:
        # Fpocket can't read /mnt/c/ paths — use a WSL-native temp dir
        wsl_exe = fpocket_executable[4:].strip()
        wsl_tmpdir_cmd = subprocess.run(
            ["wsl", "mktemp", "-d"],
            capture_output=True, text=True, timeout=10,
        )
        wsl_tmpdir = wsl_tmpdir_cmd.stdout.strip()
        if not wsl_tmpdir:
            logger.error("Failed to create WSL temp directory")
            return []

        # Copy PDB into WSL temp dir
        wsl_pdb = "{}/{}".format(wsl_tmpdir, pdb_path.name)
        subprocess.run(
            ["wsl", "cp", _wsl_path(str(pdb_path)), wsl_pdb],
            capture_output=True, timeout=30,
        )

        # Run fpocket inside WSL
        cmd = ["wsl", "bash", "-c",
               "cd {} && {} -f {}".format(wsl_tmpdir, wsl_exe, pdb_path.name)]
        logger.info("Running Fpocket (WSL native): %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                logger.error("Fpocket failed (exit %d):\n%s",
                             result.returncode, result.stderr[:1000])
                return []
        except FileNotFoundError:
            logger.error("Fpocket executable not found: %s", fpocket_executable)
            return []
        except subprocess.TimeoutExpired:
            logger.error("Fpocket timed out (300 s)")
            return []
        except Exception as e:
            logger.error("Fpocket error: %s", e)
            return []

        # Copy results back from WSL temp to Windows output_dir
        wsl_out = "{}/{}_out".format(wsl_tmpdir, basename)
        win_out = str(output_dir / "{}_out".format(basename))
        subprocess.run(
            ["wsl", "cp", "-r", wsl_out, _wsl_path(win_out)],
            capture_output=True, timeout=60,
        )
        # Cleanup WSL temp
        subprocess.run(
            ["wsl", "rm", "-rf", wsl_tmpdir],
            capture_output=True, timeout=10,
        )
    else:
        # Native Linux: copy PDB into output_dir and run locally
        local_pdb = output_dir / pdb_path.name
        shutil.copy2(str(pdb_path), str(local_pdb))
        cmd = [fpocket_executable, "-f", str(local_pdb)]
        logger.info("Running Fpocket: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=str(output_dir),
            )
            if result.returncode != 0:
                logger.error("Fpocket failed (exit %d):\n%s",
                             result.returncode, result.stderr[:1000])
                return []
        except FileNotFoundError:
            logger.error("Fpocket executable not found: %s", fpocket_executable)
            return []
        except subprocess.TimeoutExpired:
            logger.error("Fpocket timed out (300 s)")
            return []
        except Exception as e:
            logger.error("Fpocket error: %s", e)
            return []

    # Locate the output directory
    fpocket_out = output_dir / "{}_out".format(basename)
    if not fpocket_out.exists():
        logger.error("Fpocket output directory not found: expected %s", fpocket_out)
        return []

    # Parse volumes from _info.txt
    info_file = fpocket_out / "{}_info.txt".format(basename)
    if not info_file.exists():
        logger.error("Fpocket info file not found: %s", info_file)
        return []

    volumes = _parse_fpocket_info(info_file)

    # Parse centers from pocket PQR files
    pockets_dir = fpocket_out / "pockets"
    cavities = []

    for idx, volume in sorted(volumes.items()):
        # Fpocket names pocket files as pocket<N>_vert.pqr (1-indexed)
        pqr_file = pockets_dir / "pocket{}_vert.pqr".format(idx)
        if not pqr_file.exists():
            logger.warning("Fpocket PQR not found for pocket %d: %s", idx, pqr_file)
            continue

        center = _parse_pqr_center(pqr_file)
        if center is None:
            logger.warning("Could not compute center for Fpocket pocket %d", idx)
            continue

        cavities.append(FpocketCavity(
            index=idx,
            volume=volume,
            center_x=center[0],
            center_y=center[1],
            center_z=center[2],
        ))

    logger.info("Fpocket found %d cavities with valid centers", len(cavities))
    return cavities


def _parse_fpocket_info(info_path: Path) -> dict:
    """Parse Fpocket _info.txt for pocket volumes.

    The file contains sections like:
        Pocket 1 :
            Score :          0.490
            ...
            Volume :         270.934
            ...

    Returns dict mapping pocket index (int) to volume (float).
    """
    volumes = {}
    current_pocket = None

    try:
        text = info_path.read_text(errors="replace")
    except Exception as e:
        logger.error("Cannot read Fpocket info file %s: %s", info_path, e)
        return volumes

    for line in text.splitlines():
        # Match "Pocket N :"
        m = re.match(r'Pocket\s+(\d+)\s*:', line)
        if m:
            current_pocket = int(m.group(1))
            continue

        # Match "Volume : <value>"
        if current_pocket is not None:
            m = re.match(r'\s*Volume\s*:\s*([\d.]+)', line)
            if m:
                volumes[current_pocket] = float(m.group(1))

    return volumes


def _parse_pqr_center(pqr_path: Path) -> Optional[Tuple[float, float, float]]:
    """Compute the center of mass of alpha spheres in a Fpocket PQR file.

    PQR format has coordinates at columns 31-54 (x: 31-38, y: 39-46, z: 47-54)
    for ATOM/HETATM records.
    """
    coords = []
    try:
        for line in pqr_path.read_text(errors="replace").splitlines():
            record = line[:6].strip()
            if record not in ("ATOM", "HETATM"):
                continue
            try:
                # PQR format: coordinates are space-delimited after atom name
                # Safer to split by whitespace for PQR files
                parts = line.split()
                # PQR: record, serial, name, resname, (chain), resid, x, y, z, charge, radius
                # Find the x,y,z fields - they are the first three floats after residue info
                # Typical PQR: ATOM  1  STP STP  1  x y z charge radius
                x = float(parts[-5])
                y = float(parts[-4])
                z = float(parts[-3])
                coords.append((x, y, z))
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.error("Cannot read PQR file %s: %s", pqr_path, e)
        return None

    if not coords:
        return None

    n = len(coords)
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    cz = sum(c[2] for c in coords) / n
    return (round(cx, 3), round(cy, 3), round(cz, 3))


# ---------------------------------------------------------------------------
# Triage: cross-reference P2Rank and Fpocket
# ---------------------------------------------------------------------------

def run_pocket_triage(
    receptor_pdb: Path,
    p2rank_executable: str,
    fpocket_executable: str,
    output_dir: Path,
    min_pocket_volume: float = 300.0,
    distance_threshold: float = 8.0,
) -> Optional[TriageResult]:
    """Run the full pocket triage pipeline.

    1. P2Rank predicts top 3 pockets (ranked by ML score).
    2. Fpocket detects all cavities with volumes.
    3. Cross-reference by Euclidean distance; select the highest-ranking
       P2Rank pocket whose matched Fpocket cavity volume >= min_pocket_volume.

    Args:
        receptor_pdb: Path to the receptor PDB file.
        p2rank_executable: P2Rank executable (e.g. "wsl /opt/p2rank/prank").
        fpocket_executable: Fpocket executable (e.g. "wsl fpocket").
        output_dir: Directory for intermediate output files.
        min_pocket_volume: Minimum Fpocket volume (A^3) to accept a pocket.
            Reference volumes:
              Small amino acid (Gly/Ala): ~60 - 90 A^3
              Bulky amino acid (Trp/Arg): ~170 - 230 A^3
              Unnatural bulky sidechains:  ~250+ A^3
              Recommended for tetrapeptide anchor: ~300 - 500 A^3
        distance_threshold: Max Euclidean distance (A) for matching P2Rank
            and Fpocket pockets (default 8.0 A).

    Returns:
        TriageResult with the winning pocket's center and box size,
        or None if no pocket passed the volume threshold.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: P2Rank
    logger.info("=== Pocket Triage Step 1: P2Rank (Locate the Anchor) ===")
    p2rank_dir = output_dir / "p2rank"
    p2rank_pockets = run_p2rank(receptor_pdb, p2rank_executable, p2rank_dir)

    if not p2rank_pockets:
        logger.error("Pocket Triage: P2Rank found no pockets")
        return None

    for p in p2rank_pockets:
        logger.info("  P2Rank pocket #%d: score=%.2f, center=(%.1f, %.1f, %.1f)",
                     p.rank, p.score, p.center_x, p.center_y, p.center_z)

    # Step 2: Fpocket
    logger.info("=== Pocket Triage Step 2: Fpocket (Measure the Volume) ===")
    fpocket_dir = output_dir / "fpocket"
    fpocket_cavities = run_fpocket(receptor_pdb, fpocket_executable, fpocket_dir)

    if not fpocket_cavities:
        logger.error("Pocket Triage: Fpocket found no cavities")
        return None

    for c in fpocket_cavities:
        logger.info("  Fpocket cavity #%d: vol=%.1f A^3, center=(%.1f, %.1f, %.1f)",
                     c.index, c.volume, c.center_x, c.center_y, c.center_z)

    # Step 3: Distance matching and triage
    logger.info("=== Pocket Triage Step 3: Distance Matching & Triage ===")
    logger.info("  Volume threshold: %.0f A^3, distance threshold: %.1f A",
                min_pocket_volume, distance_threshold)

    for p2pocket in p2rank_pockets:
        p2_center = (p2pocket.center_x, p2pocket.center_y, p2pocket.center_z)

        # Find closest Fpocket cavity
        best_match = None
        best_dist = float("inf")
        for cavity in fpocket_cavities:
            fp_center = (cavity.center_x, cavity.center_y, cavity.center_z)
            dist = _euclidean_distance(p2_center, fp_center)
            if dist < best_dist:
                best_dist = dist
                best_match = cavity

        if best_match is None or best_dist > distance_threshold:
            logger.info("  P2Rank #%d (score=%.2f): no Fpocket match within %.1f A -- SKIP",
                        p2pocket.rank, p2pocket.score, distance_threshold)
            continue

        vol_pass = best_match.volume >= min_pocket_volume
        status = "PASS" if vol_pass else "FAIL (vol < {:.0f})".format(min_pocket_volume)
        logger.info("  P2Rank #%d (score=%.2f) <-> Fpocket #%d (vol=%.1f A^3, dist=%.1f A) -- %s",
                     p2pocket.rank, p2pocket.score,
                     best_match.index, best_match.volume, best_dist, status)

        if vol_pass:
            box_side = _box_size_from_volume(best_match.volume)
            label = "P2Rank #{} (score={:.2f}) + Fpocket #{} (vol={:.0f} A^3)".format(
                p2pocket.rank, p2pocket.score, best_match.index, best_match.volume)
            logger.info("  >>> SELECTED: %s", label)
            return TriageResult(
                center=p2_center,
                size=(box_side, box_side, box_side),
                p2rank_rank=p2pocket.rank,
                p2rank_score=p2pocket.score,
                fpocket_volume=best_match.volume,
                pocket_label=label,
            )

    # No pocket passed the filter
    all_volumes = [c.volume for c in fpocket_cavities]
    logger.warning(
        "Pocket Triage: no P2Rank pocket passed the volume threshold (%.0f A^3). "
        "Fpocket volumes found: %s",
        min_pocket_volume,
        ", ".join("{:.0f}".format(v) for v in sorted(all_volumes, reverse=True)),
    )
    return None
