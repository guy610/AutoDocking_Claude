#!/usr/bin/env python3
"""
Interactive CLI Wizard for Stephen Docking - Peptide Optimization Pipeline.
Run with: python wizard.py
"""

import os, sys, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from autodock_pipeline.config import PipelineConfig, DockingParams, OptimizationParams
from autodock_pipeline.pipeline import DockingPipeline


BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


# Path to optional background/banner image (JPG/PNG)
BANNER_IMAGE = Path(__file__).parent / "stephen_docking_banner.jpg"


def _show_banner_image():
    """Try to display the banner image in the terminal (iTerm2/Kitty)."""
    if not BANNER_IMAGE.exists():
        return False
    try:
        import base64
        data = BANNER_IMAGE.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        term = os.environ.get("TERM_PROGRAM", "")
        if "iTerm" in term or os.environ.get("ITERM_SESSION_ID"):
            esc = chr(27)
            bel = chr(7)
            sys.stdout.write(esc + "]1337;File=inline=1;width=64;preserveAspectRatio=1:")
            sys.stdout.write(b64)
            sys.stdout.write(bel + chr(10))
            sys.stdout.flush()
            return True
        if "kitty" in term.lower():
            esc = chr(27)
            sys.stdout.write(esc + "_Gf=100,a=T,t=d;")
            sys.stdout.write(b64)
            sys.stdout.write(esc + chr(92) + chr(10))
            sys.stdout.flush()
            return True
    except Exception:
        pass
    return False


def banner():
    sep = "=" * 64
    print("")
    _show_banner_image()
    print(BOLD + BLUE + sep)
    print("   Stephen Docking - Peptide Optimization Pipeline")
    print("   Interactive Setup Wizard")
    print(sep + RESET)
    if BANNER_IMAGE.exists():
        print(DIM + "   [Banner: " + BANNER_IMAGE.name + "]" + RESET)
    print("")


def section(title):
    print("")
    print(BOLD + GREEN + "--- " + title + " ---" + RESET)
    print("")


def info(msg):
    print("  " + DIM + msg + RESET)


def warn(msg):
    print("  " + YELLOW + "[!] " + msg + RESET)


def error(msg):
    print("  " + RED + "[ERROR] " + msg + RESET)


def success(msg):
    print("  " + GREEN + "[OK] " + msg + RESET)


def ask(prompt, default=None):
    if default is not None:
        display = "  " + prompt + " [" + str(default) + "]: "
    else:
        display = "  " + prompt + ": "
    val = input(display).strip()
    if not val and default is not None:
        return str(default)
    return val


def ask_yes_no(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    val = input("  " + prompt + " [" + hint + "]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def ask_choice(prompt, options, default=0):
    print("  " + prompt)
    for i, (label, desc) in enumerate(options):
        marker = " *" if i == default else ""
        line = "    " + str(i+1) + ". " + label + DIM + " - " + desc + RESET + marker
        print(line)
    while True:
        val = input("  Choice [default=" + str(default+1) + "]: ").strip()
        if not val:
            return options[default][0]
        try:
            idx = int(val) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print("  Please enter 1-" + str(len(options)))


def ask_file(prompt, extensions=None, required=True):
    while True:
        raw = input("  " + prompt + ": ").strip().strip(chr(34)).strip(chr(39))
        if not raw and not required:
            return None
        if not raw:
            error("A file path is required.")
            continue
        path = Path(raw)
        if not path.exists():
            cwd_path = Path.cwd() / raw
            if cwd_path.exists():
                path = cwd_path
            else:
                error("File not found: " + raw)
                if extensions:
                    for ext in extensions:
                        found = list(Path.cwd().glob("*" + ext))
                        if found:
                            info("Available " + ext + " files:")
                            for f in found[:10]:
                                print("    - " + f.name)
                continue
        if extensions:
            if path.suffix.lower() not in [e.lower() for e in extensions]:
                warn("Expected: " + ", ".join(extensions) + ", got: " + path.suffix)
                if not ask_yes_no("Use anyway?", default=False):
                    continue
        success("Found: " + str(path))
        return path


def step_receptor():
    section("Step 1: Receptor Protein")
    info("Provide the target protein structure as a PDB file.")
    info("Pipeline will clean it and convert to PDBQT for Vina.")
    print()
    pdb_files = list(Path.cwd().glob("*.pdb"))
    if pdb_files:
        info("PDB files in current directory:")
        for f in pdb_files:
            kb = int(f.stat().st_size / 1024)
            print("    - " + f.name + " (" + str(kb) + " KB)")
        print()
    receptor = ask_file("Path to receptor PDB", extensions=[".pdb"])
    keep_w = ask_yes_no("Keep water molecules?", default=False)
    keep_h = ask_yes_no("Keep heteroatoms (ligands, ions)?", default=False)
    return receptor, keep_w, keep_h


def step_ligand():
    section("Step 2: Ligand (Peptide)")
    info("Provide the peptide or small molecule to dock.")
    info("Options: SMILES string or peptide sequence (auto-converted)")
    print()
    fmt = ask_choice("Input format:", [
        ("smiles", "Enter a SMILES string directly"),
        ("sequence", "Enter peptide sequence (1-letter codes, e.g. AGFK)"),
    ])
    if fmt == "sequence":
        seq = ask("Peptide sequence (1-letter codes)")
        if not seq:
            error("No sequence provided")
            sys.exit(1)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSequence(seq)
            if mol is None:
                error("RDKit cannot parse: " + seq)
                smiles = ask("Enter SMILES directly")
            else:
                smiles = Chem.MolToSmiles(mol)
                success("Converted to SMILES: " + smiles)
        except Exception as e:
            error("Conversion failed: " + str(e))
            smiles = ask("Enter SMILES directly")
    else:
        smiles = ask("SMILES string")
    name = ask("Ligand name/ID", default="ligand")
    # Return sequence if user entered one (for residue identification)
    original_seq = seq if fmt == "sequence" else ""
    return smiles, name, original_seq


def step_docking_box():
    section("Step 3: Docking Box")
    info("Defines where Vina searches for binding poses.")
    print()
    method = ask_choice("Define docking box:", [
        ("pocket", "Pocket residues (recommended, auto-calculates)"),
        ("manual", "Enter center + size manually"),
        ("full", "Default box at origin (testing only)"),
    ])
    pocket_residues = []
    center = (0.0, 0.0, 0.0)
    box_size = (20.0, 20.0, 20.0)
    if method == "pocket":
        info("Enter residues near the binding site.")
        info("Formats: A:120, 120, A:TYR:120, TYR120")
        info("Separate with spaces or commas.")
        print()
        raw = ask("Pocket residues")
        residues = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
        if not residues:
            warn("No residues, using default box")
        else:
            pocket_residues = residues
            success(str(len(residues)) + " residue(s): " + ", ".join(residues))
    elif method == "manual":
        cx = float(ask("Center X", default="0.0"))
        cy = float(ask("Center Y", default="0.0"))
        cz = float(ask("Center Z", default="0.0"))
        center = (cx, cy, cz)
        sx = float(ask("Size X (Angstroms)", default="20.0"))
        sy = float(ask("Size Y (Angstroms)", default="20.0"))
        sz = float(ask("Size Z (Angstroms)", default="20.0"))
        box_size = (sx, sy, sz)
    return pocket_residues, center, box_size


def step_run_mode():
    section("Step 4: Run Mode")
    return ask_choice("Pipeline mode:", [
        ("single_dock", "Dock only - no optimization"),
        ("sidechain", "Side-chain optimization only"),
        ("full", "Full pipeline - all 3 stages"),
    ], default=0)


def step_advanced():
    section("Step 5: Advanced Settings")
    if not ask_yes_no("Configure advanced settings?", default=False):
        return {}
    s = {}
    print()
    info("Vina parameters:")
    s["exhaustiveness"] = int(ask("Exhaustiveness", default="8"))
    s["num_modes"] = int(ask("Binding modes", default="9"))
    print()
    info("Optimization:")
    s["max_rounds"] = int(ask("Max rounds/stage", default="3"))
    s["top_n"] = int(ask("Top N candidates", default="5"))
    s["delta_threshold"] = float(ask("Min improvement (kcal/mol)", default="0.5"))
    print()
    info("Validation:")
    s["max_residues"] = int(ask("Max peptide residues", default="5"))
    s["poor_binding"] = float(ask("Poor binding threshold", default="-4.0"))
    return s


def step_vina():
    section("Step 6: Vina Executable")
    info("Pipeline needs AutoDock Vina executable.")
    found = None
    for pat in ["vina*exe", "vina"]:
        hits = list(Path.cwd().glob(pat))
        if hits:
            found = str(hits[0])
            break
    if found:
        success("Found: " + found)
        if ask_yes_no("Use this?", default=True):
            return found
    return ask("Path to Vina", default="vina")


def step_output():
    section("Step 7: Output Directory")
    return Path(ask("Output directory", default="./output"))


def step_extra():
    section("Step 8: Additional Ligands (Optional)")
    info("Dock extra SMILES alongside main ligand (no optimization).")
    if not ask_yes_no("Add extra SMILES?", default=False):
        return []
    extra = []
    while True:
        smi = ask("SMILES (or type done)", default="done")
        if smi.lower() == "done":
            break
        extra.append(smi)
        success("Added: " + smi)
    return extra


def main():
    banner()
    receptor, kw, kh = step_receptor()
    smiles, lig_name, lig_seq = step_ligand()
    pocket_res, center, box_size = step_docking_box()
    run_mode = step_run_mode()
    adv = step_advanced()
    vina_exe = step_vina()
    output_dir = step_output()
    extra = step_extra()

    dp = DockingParams(
        center_x=center[0], center_y=center[1], center_z=center[2],
        size_x=box_size[0], size_y=box_size[1], size_z=box_size[2],
        exhaustiveness=adv.get("exhaustiveness", 8),
        num_modes=adv.get("num_modes", 9),
    )
    op = OptimizationParams(
        max_rounds=adv.get("max_rounds", 3),
        top_n_select=adv.get("top_n", 5),
        delta_affinity_threshold=adv.get("delta_threshold", 0.5),
        max_residues=adv.get("max_residues", 5),
        poor_binding_threshold=adv.get("poor_binding", -4.0),
    )
    cfg = PipelineConfig(
        receptor_pdb=receptor,
        ligand_smiles=smiles,
        ligand_name=lig_name,
        ligand_sequence=lig_seq,
        user_smiles=extra,
        pocket_residues=pocket_res,
        docking=dp, optimization=op,
        output_dir=output_dir,
        vina_executable=vina_exe,
        remove_waters=not kw,
        remove_heteroatoms=not kh,
        run_mode=run_mode,
    )
    if run_mode == "sidechain":
        cfg.stages = ["sidechain"]
    elif run_mode == "full":
        cfg.stages = ["sidechain", "backbone", "minimize"]

    section("Review Configuration")
    sd = smiles if len(smiles) <= 55 else smiles[:52] + "..."
    pd = ", ".join(pocket_res) if pocket_res else "(manual/default)"
    items = [
        ("Receptor", str(receptor)),
        ("Ligand SMILES", sd),
        ("Ligand Name", lig_name),
        ("Run Mode", run_mode),
        ("Pocket Residues", pd),
        ("Exhaustiveness", str(dp.exhaustiveness)),
        ("Max Residues", str(op.max_residues)),
        ("Vina", vina_exe),
        ("Output", str(output_dir)),
        ("Extra SMILES", str(len(extra))),
    ]
    for k, v in items:
        print("  {:<24} {}".format(k, v))
    print()

    if not ask_yes_no("Start the pipeline?", default=True):
        print("  Cancelled.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(output_dir / "pipeline.log")),
        ],
    )
    print("")
    print(BOLD + GREEN + "Starting pipeline..." + RESET)
    print("")
    try:
        pipeline = DockingPipeline(cfg)
        pipeline.run()
        print("")
        sep = "=" * 64
        print(BOLD + GREEN + sep)
        print("  Stephen Docking complete!")
        print("  Results in: " + str(output_dir))
        print("  Reports: results_summary.csv, results_report.md")
        print(sep + RESET)
    except KeyboardInterrupt:
        print(YELLOW + "Interrupted by user." + RESET)
    except Exception as e:
        error("Pipeline failed: " + str(e))
        logging.exception("Pipeline error")
        raise


if __name__ == "__main__":
    main()
