"""
GNINA rescoring: CNN-based pose evaluation of Vina docking poses.

Uses GNINA's --score_only mode to evaluate existing Vina output poses
with a convolutional neural network, producing:
  - CNN Pose Score (probability that the pose is correct, 0-1)
  - CNN Affinity (predicted binding affinity in pKd units)
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


def _wsl_path(win_path: str) -> str:
    """Convert a Windows path to WSL format: C:\\Users\\... -> /mnt/c/Users/..."""
    p = str(win_path).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        p = "/mnt/{}/{}".format(drive, p[3:])
    return p


def _build_cmd(executable: str, args: List[str]) -> List[str]:
    """Build subprocess command, handling 'wsl' prefix for WSL executables.

    If executable starts with 'wsl ' (e.g. 'wsl gnina'), converts all
    Windows file paths in args to WSL /mnt/ format.
    """
    if executable.lower().startswith("wsl "):
        wsl_exe = executable[4:].strip()
        wsl_args = []
        for arg in args:
            # Convert Windows-style paths to WSL paths
            if os.path.sep == "\\" and (
                "\\" in arg or (len(arg) >= 2 and arg[1] == ":")
            ):
                wsl_args.append(_wsl_path(arg))
            else:
                wsl_args.append(arg)
        return ["wsl", wsl_exe] + wsl_args
    return [executable] + args


@dataclass
class GninaResult:
    """Stores GNINA rescoring output for a single ligand."""
    cnn_affinity: float       # Predicted affinity (higher = stronger binding)
    cnn_pose_score: float     # Pose probability (0-1, higher = more confident)


def run_gnina_rescore(
    receptor_pdbqt: Path,
    ligand_docked_pdbqt: Path,
    gnina_executable: str,
    ligand_name: str = "",
) -> Optional[GninaResult]:
    """Rescore a Vina-docked pose using GNINA's CNN scoring.

    Takes the docked PDBQT output from Vina (multi-model file) and rescores
    the best pose (first model) with GNINA's convolutional neural network.

    Args:
        receptor_pdbqt: Path to prepared receptor PDBQT.
        ligand_docked_pdbqt: Path to Vina output PDBQT (contains docked poses).
        gnina_executable: Path to GNINA binary.
        ligand_name: Name for logging.

    Returns:
        GninaResult with CNN affinity and pose score, or None on failure.
    """
    if not gnina_executable:
        return None

    if not ligand_docked_pdbqt.exists():
        logger.warning("GNINA: docked PDBQT not found: %s", ligand_docked_pdbqt)
        return None

    cmd = _build_cmd(gnina_executable, [
        "--receptor", str(receptor_pdbqt),
        "--ligand", str(ligand_docked_pdbqt),
        "--score_only",
    ])

    logger.info("GNINA rescoring: %s", ligand_name or ligand_docked_pdbqt.stem)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("GNINA failed (exit %d) for %s:\n%s",
                         result.returncode, ligand_name, result.stderr[:500])
            return None

        # Parse GNINA output for CNN scores
        # GNINA outputs lines like:
        #   CNNscore: 0.742
        #   CNNaffinity: 6.234
        # or in table format:
        #   -7.3  0  0  0.742  6.234
        cnn_affinity = None
        cnn_pose_score = None

        stdout = result.stdout

        # Try named output format first
        aff_match = re.search(r'CNNaffinity:\s*([\d.]+)', stdout)
        if aff_match:
            cnn_affinity = float(aff_match.group(1))

        score_match = re.search(r'CNNscore:\s*([\d.]+)', stdout)
        if score_match:
            cnn_pose_score = float(score_match.group(1))

        # Try table format if named format not found
        # Table header: ## Name Vina CNNscore CNNaffinity
        # Table row:    ligand -7.3 0.742 6.234
        if cnn_affinity is None or cnn_pose_score is None:
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        # Try parsing: name vina_score cnn_score cnn_affinity
                        # or: vina_score lb ub cnn_score cnn_affinity
                        for i in range(len(parts) - 1):
                            val = float(parts[i])
                            if 0 <= val <= 1 and cnn_pose_score is None:
                                cnn_pose_score = val
                                if i + 1 < len(parts):
                                    cnn_affinity = float(parts[i + 1])
                                break
                    except (ValueError, IndexError):
                        continue

        if cnn_affinity is not None and cnn_pose_score is not None:
            logger.info("GNINA %s: affinity=%.2f, pose_score=%.3f",
                        ligand_name, cnn_affinity, cnn_pose_score)
            return GninaResult(
                cnn_affinity=cnn_affinity,
                cnn_pose_score=cnn_pose_score,
            )
        else:
            logger.warning("GNINA: could not parse scores for %s from output:\n%s",
                           ligand_name, stdout[:500])
            return None

    except FileNotFoundError:
        logger.error("GNINA executable not found: %s", gnina_executable)
        return None
    except subprocess.TimeoutExpired:
        logger.error("GNINA timed out for %s", ligand_name)
        return None
    except Exception as e:
        logger.error("GNINA error for %s: %s", ligand_name, e)
        return None
