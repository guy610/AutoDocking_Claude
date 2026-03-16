#!/usr/bin/env python3
"""Mock GNINA executable for testing Phase 2 rescoring.

Mimics GNINA's --score_only output format.
Produces deterministic but varied CNN scores based on a hash of the ligand filename.
"""
import sys
import hashlib


def main():
    # Parse args to find ligand file
    args = sys.argv[1:]
    ligand_file = ""
    for i, arg in enumerate(args):
        if arg == "--ligand" and i + 1 < len(args):
            ligand_file = args[i + 1]

    # Generate deterministic scores from filename hash
    h = int(hashlib.md5(ligand_file.encode()).hexdigest(), 16)
    cnn_score = 0.3 + (h % 700) / 1000.0     # 0.30 - 0.99
    cnn_affinity = 3.0 + (h % 5000) / 1000.0  # 3.0 - 8.0

    # Output in GNINA's named format
    print("   _______  _   _ _____ _   _    _")
    print("  / ____| \\| | | |_   _| \\ | |  / \\")
    print(" | |  _|  \\  | |   | | |  \\| | / _ \\")
    print(" | |_| | |\\  | |   | | | |\\  |/ ___ \\")
    print("  \\____|_| \\_|_|  |_| |_| \\_/_/   \\_\\")
    print()
    print("GNINA v1.3.2 (mock)")
    print("Rescoring mode: --score_only")
    print()
    print("Using receptor from command line")
    print("Using ligand: {}".format(ligand_file))
    print()
    print("CNNscore: {:.3f}".format(cnn_score))
    print("CNNaffinity: {:.3f}".format(cnn_affinity))
    print()
    print("Done.")


if __name__ == "__main__":
    main()
