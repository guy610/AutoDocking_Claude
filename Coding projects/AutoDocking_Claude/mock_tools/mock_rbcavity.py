#!/usr/bin/env python3
"""Mock rbcavity executable for testing RxDock cavity preparation.

Mimics rbcavity's behavior: reads the .prm file and creates a dummy .as grid file.
"""
import sys
from pathlib import Path


def main():
    # Parse args to find the .prm file
    args = sys.argv[1:]
    prm_file = ""
    for i, arg in enumerate(args):
        if arg == "-r" and i + 1 < len(args):
            prm_file = args[i + 1]

    if not prm_file:
        print("ERROR: No parameter file specified", file=sys.stderr)
        sys.exit(1)

    prm_path = Path(prm_file)
    if not prm_path.exists():
        print("ERROR: Parameter file not found: {}".format(prm_file), file=sys.stderr)
        sys.exit(1)

    # Read the .prm file to acknowledge it
    content = prm_path.read_text()
    print("RbtSphereSiteMapper: Reading parameter file: {}".format(prm_file))
    print("Cavity detection running...")

    # Create the .as grid file that RxDock expects
    as_path = prm_path.with_suffix(".as")
    as_path.write_text("MOCK_CAVITY_GRID\n")
    print("Cavity grid written to: {}".format(as_path))
    print("1 cavity found, volume = 1250.0 A^3")
    print("Done.")


if __name__ == "__main__":
    main()
