#!/usr/bin/env python3
"""Mock rbdock executable for testing Phase 3 RxDock docking.

Mimics rbdock's behavior: reads input SDF, produces output SDF with SCORE fields.
Generates deterministic scores based on ligand name hash.
"""
import sys
import hashlib
from pathlib import Path


def main():
    # Parse args
    args = sys.argv[1:]
    input_sdf = ""
    output_prefix = ""
    n_runs = 5

    for i, arg in enumerate(args):
        if arg == "-i" and i + 1 < len(args):
            input_sdf = args[i + 1]
        elif arg == "-o" and i + 1 < len(args):
            output_prefix = args[i + 1]
        elif arg == "-n" and i + 1 < len(args):
            n_runs = int(args[i + 1])

    if not input_sdf or not output_prefix:
        print("ERROR: Missing required arguments", file=sys.stderr)
        sys.exit(1)

    input_path = Path(input_sdf)
    if not input_path.exists():
        print("ERROR: Input SDF not found: {}".format(input_sdf), file=sys.stderr)
        sys.exit(1)

    # Read input SDF
    sdf_content = input_path.read_text(errors="replace")
    print("RxDock (mock) v2013.1")
    print("Reading ligand from: {}".format(input_sdf))
    print("Running {} docking iterations...".format(n_runs))

    # Generate deterministic scores from filename hash
    h = int(hashlib.md5(input_sdf.encode()).hexdigest(), 16)

    # Write output SDF with multiple poses (simulating n_runs results)
    # RxDock output is {prefix}_out.sd
    out_path = Path(output_prefix + "_out.sd")

    lines = []
    for run_idx in range(min(n_runs, 5)):  # Cap at 5 poses for output
        # Vary scores per pose
        inter = -20.0 + ((h + run_idx * 137) % 1500) / 100.0   # -20.0 to -5.0
        intra = 1.0 + ((h + run_idx * 271) % 500) / 100.0      # 1.0 to 6.0
        total = inter + intra

        # Write a minimal SDF molecule entry
        lines.append("ligand_pose_{}".format(run_idx + 1))
        lines.append("  RxDock(mock)          3D")
        lines.append("")
        lines.append("  3  2  0  0  0  0  0  0  0  0999 V2000")
        lines.append("    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0")
        lines.append("    1.5400    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0")
        lines.append("    0.7700    1.3300    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0")
        lines.append("  1  2  1  0  0  0  0")
        lines.append("  1  3  1  0  0  0  0")
        lines.append("M  END")
        lines.append("> <SCORE.INTER>")
        lines.append("{:.4f}".format(inter))
        lines.append("")
        lines.append("> <SCORE.INTRA>")
        lines.append("{:.4f}".format(intra))
        lines.append("")
        lines.append("> <SCORE>")
        lines.append("{:.4f}".format(total))
        lines.append("")
        lines.append("$$$$")

        print("  Pose {}: SCORE.INTER = {:.2f}, SCORE = {:.2f}".format(
            run_idx + 1, inter, total))

    out_path.write_text("\n".join(lines))
    print("Output written to: {}".format(out_path))
    print("Done.")


if __name__ == "__main__":
    main()
