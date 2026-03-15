/* Stephen Docking - Web UI JavaScript */

(function () {
    "use strict";

    // ==================== DOM References ====================
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const formView = $("#form-view");
    const runningView = $("#running-view");
    const resultsView = $("#results-view");
    const errorView = $("#error-view");
    const checkpointModal = $("#checkpoint-modal");

    const dropZone = $("#drop-zone");
    const receptorFile = $("#receptor-file");
    const uploadStatus = $("#upload-status");
    const uploadFilename = $("#upload-filename");
    const receptorPath = $("#receptor-path");

    const startBtn = $("#start-btn");
    const logViewer = $("#log-viewer");

    let currentResults = [];
    let sortCol = null;
    let sortAsc = true;

    // ==================== Init ====================
    document.addEventListener("DOMContentLoaded", function () {
        detectVina();
        setupDropZone();
        setupRadioToggles();
        setupAdvancedToggle();
        setupStartButton();
        setupCheckpointButtons();
        setupResultsSort();
        setupNewRunButtons();
    });

    // ==================== Auto-detect Vina ====================
    function detectVina() {
        fetch("/api/detect_vina")
            .then((r) => r.json())
            .then((data) => {
                if (data.found) {
                    $("#vina-path").value = data.found;
                }
            })
            .catch(() => {});
    }

    $("#detect-vina-btn").addEventListener("click", detectVina);

    // ==================== File Upload / Drop Zone ====================
    function setupDropZone() {
        dropZone.addEventListener("click", function () {
            receptorFile.click();
        });

        dropZone.addEventListener("dragover", function (e) {
            e.preventDefault();
            dropZone.classList.add("drag-over");
        });

        dropZone.addEventListener("dragleave", function () {
            dropZone.classList.remove("drag-over");
        });

        dropZone.addEventListener("drop", function (e) {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
            if (e.dataTransfer.files.length > 0) {
                handleFile(e.dataTransfer.files[0]);
            }
        });

        receptorFile.addEventListener("change", function () {
            if (receptorFile.files.length > 0) {
                handleFile(receptorFile.files[0]);
            }
        });
    }

    function handleFile(file) {
        var formData = new FormData();
        formData.append("receptor", file);
        dropZone.innerHTML = "<p>Uploading...</p>";

        fetch("/api/upload", { method: "POST", body: formData })
            .then((r) => r.json())
            .then((data) => {
                if (data.error) {
                    dropZone.innerHTML =
                        '<p style="color:#ef4444">Upload failed: ' +
                        data.error +
                        "</p>";
                    return;
                }
                receptorPath.value = data.path;
                uploadFilename.textContent = data.filename;
                uploadStatus.style.display = "block";
                dropZone.innerHTML =
                    "<p>&#10003; " + data.filename + "</p><p class='small'>Click to change</p>";
            })
            .catch((err) => {
                dropZone.innerHTML =
                    '<p style="color:#ef4444">Upload error: ' + err + "</p>";
            });
    }

    // ==================== Radio Toggles ====================
    function setupRadioToggles() {
        // Ligand mode toggle
        $$('input[name="ligand_mode"]').forEach(function (r) {
            r.addEventListener("change", function () {
                if (r.value === "sequence") {
                    $("#ligand-sequence-input").style.display = "block";
                    $("#ligand-smiles-input").style.display = "none";
                } else {
                    $("#ligand-sequence-input").style.display = "none";
                    $("#ligand-smiles-input").style.display = "block";
                }
            });
        });

        // Box mode toggle
        $$('input[name="box_mode"]').forEach(function (r) {
            r.addEventListener("change", function () {
                $("#pocket-input").style.display =
                    r.value === "pocket" ? "block" : "none";
                $("#manual-input").style.display =
                    r.value === "manual" ? "block" : "none";
            });
        });
    }

    // ==================== Advanced Toggle ====================
    function setupAdvancedToggle() {
        var toggle = $("#advanced-toggle");
        var settings = $("#advanced-settings");
        var icon = toggle.querySelector(".collapse-icon");

        toggle.addEventListener("click", function () {
            var visible = settings.style.display !== "none";
            settings.style.display = visible ? "none" : "block";
            icon.classList.toggle("open", !visible);
        });
    }

    // ==================== Collect Form Data ====================
    function collectFormData() {
        var ligandMode = document.querySelector(
            'input[name="ligand_mode"]:checked'
        ).value;
        var boxMode = document.querySelector(
            'input[name="box_mode"]:checked'
        ).value;
        var runMode = document.querySelector(
            'input[name="run_mode"]:checked'
        ).value;

        var data = {
            receptor_path: receptorPath.value,
            ligand_name: $("#ligand-name").value || "ligand",
            run_mode: runMode,
            exhaustiveness: $("#exhaustiveness").value,
            num_modes: $("#num-modes").value,
            max_rounds: $("#max-rounds").value,
            top_n: $("#top-n").value,
            delta_threshold: $("#delta-threshold").value,
            max_residues: $("#max-residues").value,
            poor_binding: $("#poor-binding").value,
            vina_executable: $("#vina-path").value,
            output_dir: $("#output-dir").value || "./output",
            user_smiles: $("#user-smiles").value,
        };

        if (ligandMode === "sequence") {
            data.ligand_sequence = $("#ligand-sequence").value;
            data.ligand_smiles = "";
        } else {
            data.ligand_smiles = $("#ligand-smiles").value;
            data.ligand_sequence = "";
        }

        if (boxMode === "pocket") {
            data.pocket_residues = $("#pocket-residues").value;
        } else if (boxMode === "manual") {
            data.center_x = $("#center-x").value;
            data.center_y = $("#center-y").value;
            data.center_z = $("#center-z").value;
            data.size_x = $("#size-x").value;
            data.size_y = $("#size-y").value;
            data.size_z = $("#size-z").value;
        }
        // default box: no coords needed, pipeline uses defaults

        return data;
    }

    // ==================== Validate ====================
    function validate() {
        if (!receptorPath.value) {
            alert("Please upload a receptor PDB file (Step 1).");
            return false;
        }
        var ligandMode = document.querySelector(
            'input[name="ligand_mode"]:checked'
        ).value;
        if (ligandMode === "sequence" && !$("#ligand-sequence").value.trim()) {
            alert("Please enter a peptide sequence (Step 2).");
            return false;
        }
        if (ligandMode === "smiles" && !$("#ligand-smiles").value.trim()) {
            alert("Please enter a SMILES string (Step 2).");
            return false;
        }
        return true;
    }

    // ==================== Start Pipeline ====================
    function setupStartButton() {
        startBtn.addEventListener("click", function () {
            if (!validate()) return;

            var data = collectFormData();
            startBtn.disabled = true;
            startBtn.textContent = "Starting...";

            fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            })
                .then((r) => r.json())
                .then((resp) => {
                    if (resp.error) {
                        alert("Error: " + resp.error);
                        startBtn.disabled = false;
                        startBtn.textContent = "Start Pipeline";
                        return;
                    }
                    showRunningView();
                    startSSE();
                })
                .catch((err) => {
                    alert("Failed to start: " + err);
                    startBtn.disabled = false;
                    startBtn.textContent = "Start Pipeline";
                });
        });
    }

    // ==================== Views ====================
    function showRunningView() {
        formView.style.display = "none";
        runningView.style.display = "block";
        resultsView.style.display = "none";
        errorView.style.display = "none";
        logViewer.innerHTML = "";
    }

    function showResultsView() {
        runningView.style.display = "none";
        resultsView.style.display = "block";
    }

    function showErrorView(message, traceback) {
        runningView.style.display = "none";
        errorView.style.display = "block";
        $("#error-message").textContent = message;
        $("#error-traceback").textContent = traceback || "";
    }

    // ==================== SSE Streaming ====================
    function startSSE() {
        var source = new EventSource("/api/stream");

        source.addEventListener("log", function (e) {
            var data = JSON.parse(e.data);
            appendLog(data.level, data.message);
            updateStageFromLog(data.message);
        });

        source.addEventListener("checkpoint", function (e) {
            var data = JSON.parse(e.data);
            showCheckpoint(data);
        });

        source.addEventListener("complete", function (e) {
            var data = JSON.parse(e.data);
            source.close();
            currentResults = data.results || [];
            appendLog("INFO", "--- Pipeline Complete ---");
            renderResults(currentResults);
            showResultsView();
        });

        source.addEventListener("error", function (e) {
            if (e.data) {
                var data = JSON.parse(e.data);
                source.close();
                showErrorView(data.message, data.traceback);
            }
        });

        source.onerror = function () {
            appendLog("ERROR", "Connection to server lost.");
        };
    }

    function appendLog(level, message) {
        var line = document.createElement("div");
        line.className = "log-line log-" + level;
        line.textContent = message;
        logViewer.appendChild(line);
        logViewer.scrollTop = logViewer.scrollHeight;
    }

    function updateStageFromLog(message) {
        var msg = message.toLowerCase();
        var stages = $$(".stage");
        if (msg.indexOf("preparing receptor") >= 0 || msg.indexOf("preparation") >= 0) {
            setActiveStage("prep");
        } else if (msg.indexOf("initial dock") >= 0 || msg.indexOf("running initial") >= 0) {
            setActiveStage("initial");
        } else if (msg.indexOf("sidechain") >= 0) {
            setActiveStage("sidechain");
        } else if (msg.indexOf("backbone") >= 0) {
            setActiveStage("backbone");
        } else if (msg.indexOf("minim") >= 0) {
            setActiveStage("minimize");
        }
    }

    function setActiveStage(stageName) {
        var stages = $$(".stage");
        var found = false;
        stages.forEach(function (el) {
            if (el.dataset.stage === stageName) {
                el.className = "stage active";
                found = true;
            } else if (!found) {
                el.className = "stage done";
            } else {
                el.className = "stage";
            }
        });
    }

    // ==================== Checkpoint ====================
    function showCheckpoint(data) {
        $("#checkpoint-stage").textContent = data.stage;
        var tbody = $("#checkpoint-table tbody");
        tbody.innerHTML = "";

        (data.candidates || []).forEach(function (c) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + c.rank + "</td>" +
                "<td>" + esc(c.name) + "</td>" +
                "<td>" + c.score + "</td>" +
                "<td>" + esc(c.origin) + "</td>" +
                "<td title='" + esc(c.smiles || "") + "'>" +
                esc((c.smiles || "").substring(0, 40)) +
                "</td>";
            tbody.appendChild(tr);
        });

        $("#cp-inject-area").style.display = "none";
        checkpointModal.style.display = "flex";
    }

    function setupCheckpointButtons() {
        $("#cp-continue").addEventListener("click", function () {
            sendCheckpoint({ action: "continue" });
        });

        $("#cp-rerun").addEventListener("click", function () {
            sendCheckpoint({ action: "rerun" });
        });

        $("#cp-inject-toggle").addEventListener("click", function () {
            var area = $("#cp-inject-area");
            area.style.display = area.style.display === "none" ? "block" : "none";
        });

        $("#cp-inject-submit").addEventListener("click", function () {
            var raw = $("#cp-inject-smiles").value.trim();
            var smiles = raw
                .split("\n")
                .map(function (s) {
                    return s.trim();
                })
                .filter(function (s) {
                    return s.length > 0;
                });
            sendCheckpoint({ action: "continue", smiles: smiles });
        });
    }

    function sendCheckpoint(data) {
        checkpointModal.style.display = "none";
        appendLog("INFO", "Checkpoint response: " + data.action);
        fetch("/api/checkpoint", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        }).catch(function (err) {
            appendLog("ERROR", "Failed to send checkpoint: " + err);
        });
    }

    // ==================== Results ====================
    function renderResults(results) {
        var tbody = $("#results-table tbody");
        tbody.innerHTML = "";

        if (!results || results.length === 0) {
            tbody.innerHTML = "<tr><td colspan='5'>No results</td></tr>";
            return;
        }

        // Summary
        var best = results[0];
        var worst = results[results.length - 1];
        $("#results-summary").innerHTML =
            "<strong>" + results.length + " results</strong> | " +
            "Best: " + (best.docking_score || best.score || "N/A") + " kcal/mol (" +
            esc(best.ligand_name || best.name || "") + ") | " +
            "Worst: " + (worst.docking_score || worst.score || "N/A") + " kcal/mol";

        results.forEach(function (r) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + (r.rank || "") + "</td>" +
                "<td>" + esc(r.ligand_name || r.name || "") + "</td>" +
                "<td>" + (r.docking_score || r.score || "") + "</td>" +
                "<td>" + esc(r.origin || "") + "</td>" +
                "<td title='" + esc(r.smiles || "") + "'>" +
                esc((r.smiles || "").substring(0, 50)) +
                "</td>";
            tbody.appendChild(tr);
        });
    }

    function setupResultsSort() {
        $$("#results-table th.sortable").forEach(function (th) {
            th.addEventListener("click", function () {
                var col = th.dataset.col;
                if (sortCol === col) {
                    sortAsc = !sortAsc;
                } else {
                    sortCol = col;
                    sortAsc = true;
                }

                // Update header classes
                $$("#results-table th").forEach(function (h) {
                    h.classList.remove("sort-asc", "sort-desc");
                });
                th.classList.add(sortAsc ? "sort-asc" : "sort-desc");

                // Sort
                currentResults.sort(function (a, b) {
                    var va = a[col] || a.ligand_name || "";
                    var vb = b[col] || b.ligand_name || "";
                    if (typeof va === "number" && typeof vb === "number") {
                        return sortAsc ? va - vb : vb - va;
                    }
                    va = String(va).toLowerCase();
                    vb = String(vb).toLowerCase();
                    if (va < vb) return sortAsc ? -1 : 1;
                    if (va > vb) return sortAsc ? 1 : -1;
                    return 0;
                });

                renderResults(currentResults);
            });
        });
    }

    // ==================== New Run ====================
    function setupNewRunButtons() {
        $("#new-run-btn").addEventListener("click", function () {
            window.location.reload();
        });
        $("#error-new-run").addEventListener("click", function () {
            window.location.reload();
        });
    }

    // ==================== Utility ====================
    function esc(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
