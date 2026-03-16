#!/usr/bin/env python3
"""
Stephen Docking - Web Interface

Launch with: python web_app.py
Opens automatically in your browser at http://127.0.0.1:5000
"""

import sys
import os
import io

# Force UTF-8 everywhere - prevents Windows cp1252 issues
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.dont_write_bytecode = True

# Force UTF-8 on all standard streams
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Monkey-patch builtins.open to always default to UTF-8
import builtins
_original_open = builtins.open
def _utf8_open(*args, **kwargs):
    # If mode is text (no 'b') and no encoding specified, force utf-8
    mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
    if "b" not in str(mode) and "encoding" not in kwargs:
        kwargs["encoding"] = "utf-8"
        kwargs.setdefault("errors", "replace")
    return _original_open(*args, **kwargs)
builtins.open = _utf8_open

import json
import logging
import queue
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, render_template, request, jsonify, Response, send_from_directory

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from autodock_pipeline.web.runner import PipelineRunner

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

UPLOAD_DIR = Path(__file__).parent / "uploads"
BANNER_DIR = Path(__file__).parent / "Banner"

# Global pipeline runner (single-user tool)
runner = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/banner/<path:filename>")
def banner(filename):
    return send_from_directory(str(BANNER_DIR), filename)


@app.route("/api/upload", methods=["POST"])
def upload():
    if "receptor" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["receptor"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / f.filename
    f.save(str(dest))
    return jsonify({"path": str(dest), "filename": f.filename})


@app.route("/api/detect_vina")
def detect_vina():
    """Auto-detect Vina executable in the project directory."""
    project_dir = Path(__file__).parent
    for pattern in ["vina*.exe", "vina*exe*", "vina"]:
        hits = list(project_dir.glob(pattern))
        if hits:
            return jsonify({"found": str(hits[0])})
    return jsonify({"found": None})


@app.route("/api/detect_gnina")
def detect_gnina():
    """Auto-detect GNINA executable in the project directory."""
    project_dir = Path(__file__).parent
    for pattern in ["gnina*.exe", "gnina*exe*", "gnina"]:
        hits = list(project_dir.glob(pattern))
        if hits:
            return jsonify({"found": str(hits[0])})
    return jsonify({"found": None})


@app.route("/api/detect_rxdock")
def detect_rxdock():
    """Auto-detect RxDock (rbdock) executable in the project directory."""
    project_dir = Path(__file__).parent
    for pattern in ["rbdock*.exe", "rbdock*exe*", "rbdock"]:
        hits = list(project_dir.glob(pattern))
        if hits:
            return jsonify({"found": str(hits[0])})
    return jsonify({"found": None})


@app.route("/api/start", methods=["POST"])
def start():
    global runner
    if runner and runner.is_running:
        return jsonify({"error": "Pipeline already running"}), 409
    config_data = request.json
    runner = PipelineRunner(config_data)
    runner.start()
    return jsonify({"status": "started"})


@app.route("/api/stream")
def stream():
    """Server-Sent Events endpoint for live log streaming."""
    def generate():
        if runner is None:
            yield "event: error\ndata: {\"type\":\"error\",\"message\":\"No pipeline running\"}\n\n"
            return
        while True:
            try:
                event = runner.event_queue.get(timeout=2.0)
                event_type = event.get("type", "log")
                yield "event: {}\ndata: {}\n\n".format(event_type, json.dumps(event))
                if event_type in ("complete", "error"):
                    break
            except queue.Empty:
                # Send keepalive comment
                yield ": keepalive\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/checkpoint", methods=["POST"])
def checkpoint_response():
    """Receive user's checkpoint decision and unblock the pipeline."""
    if runner is None:
        return jsonify({"error": "No pipeline running"}), 400
    data = request.json
    runner.checkpoint_handler.response_data = data
    runner.checkpoint_handler.response_event.set()
    return jsonify({"status": "ok"})


@app.route("/api/status")
def status():
    """Return current pipeline status so the browser can reconnect."""
    if runner is None:
        return jsonify({"state": "idle"})
    if runner.is_running and not runner.is_complete:
        return jsonify({"state": "running"})
    if runner.is_complete and runner.results:
        return jsonify({"state": "complete", "results": runner.results})
    if runner.is_complete and not runner.results:
        return jsonify({"state": "error"})
    return jsonify({"state": "idle"})


@app.route("/api/results")
def results():
    if runner and runner.results:
        return jsonify(runner.results)
    return jsonify([])


@app.route("/api/download_csv")
def download_csv():
    """Serve the results CSV file."""
    if runner and runner.config_data:
        output_dir = Path(runner.config_data.get("output_dir", "output"))
        csv_path = output_dir / "results_summary.csv"
        if csv_path.exists():
            return send_from_directory(str(csv_path.parent), csv_path.name,
                                       as_attachment=True)
    return jsonify({"error": "No results CSV available"}), 404


@app.route("/api/download_complex")
def download_complex():
    """Serve the best_complex.pdb file."""
    if runner and runner.config_data:
        output_dir = Path(runner.config_data.get("output_dir", "output"))
        pdb_path = output_dir / "best_complex.pdb"
        if pdb_path.exists():
            return send_from_directory(str(pdb_path.parent), pdb_path.name,
                                       as_attachment=True)
    return jsonify({"error": "No complex PDB available"}), 404


@app.route("/api/download_consensus_csv")
def download_consensus_csv():
    """Serve the consensus_summary.csv file from hierarchical screening."""
    if runner and runner.config_data:
        output_dir = Path(runner.config_data.get("output_dir", "output"))
        csv_path = output_dir / "consensus_summary.csv"
        if csv_path.exists():
            return send_from_directory(str(csv_path.parent), csv_path.name,
                                       as_attachment=True)
    return jsonify({"error": "No consensus CSV available (hierarchical screening may not have been run)"}), 404


@app.route("/api/download_qc/<qc_type>")
def download_qc_complex(qc_type):
    """Serve a QC complex PDB file.

    qc_type: 'd_amino' | 'beta_amino' | 'unnatural'
    """
    filenames = {
        "d_amino": "qc_best_d_amino_acid_complex.pdb",
        "beta_amino": "qc_best_beta_amino_acid_complex.pdb",
        "unnatural": "qc_best_unnatural_aa_complex.pdb",
        "cterm_amide": "qc_best_cterm_amide_complex.pdb",
        "nterm_methyl": "qc_best_nterm_methyl_complex.pdb",
        "nterm_acyl": "qc_best_nterm_acyl_complex.pdb",
        "nterm_custom": "qc_best_nterm_custom_complex.pdb",
    }
    if qc_type not in filenames:
        return jsonify({"error": "Unknown QC type: " + qc_type}), 400
    if runner and runner.config_data:
        output_dir = Path(runner.config_data.get("output_dir", "output"))
        pdb_path = output_dir / "qc_complexes" / filenames[qc_type]
        if pdb_path.exists():
            return send_from_directory(str(pdb_path.parent), pdb_path.name,
                                       as_attachment=True)
    return jsonify({"error": "QC complex not available (no " + qc_type.replace("_", " ") + " candidates found)"}), 404


@app.route("/api/qc_status")
def qc_status():
    """Return which QC complexes are available for download."""
    available = {}
    if runner and runner.config_data:
        output_dir = Path(runner.config_data.get("output_dir", "output"))
        qc_dir = output_dir / "qc_complexes"
        checks = {
            "d_amino": "qc_best_d_amino_acid_complex.pdb",
            "beta_amino": "qc_best_beta_amino_acid_complex.pdb",
            "unnatural": "qc_best_unnatural_aa_complex.pdb",
            "cterm_amide": "qc_best_cterm_amide_complex.pdb",
            "nterm_methyl": "qc_best_nterm_methyl_complex.pdb",
            "nterm_acyl": "qc_best_nterm_acyl_complex.pdb",
            "nterm_custom": "qc_best_nterm_custom_complex.pdb",
        }
        for key, fname in checks.items():
            available[key] = (qc_dir / fname).exists()
    return jsonify(available)


def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n  Stephen Docking - Web Interface")
    print("  Opening browser at http://127.0.0.1:5000")
    print("  Press Ctrl+C to stop\n")
    Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
