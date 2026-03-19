/* Stephen Docking - Web UI JavaScript v0.9.0 */

(function () {
    "use strict";

    // ==================== DOM References ====================
    var $ = function(sel) { return document.querySelector(sel); };
    var $$ = function(sel) { return document.querySelectorAll(sel); };

    var formView = $("#form-view");
    var runningView = $("#running-view");
    var resultsView = $("#results-view");
    var errorView = $("#error-view");
    var checkpointModal = $("#checkpoint-modal");

    var dropZone = $("#drop-zone");
    var receptorFile = $("#receptor-file");
    var uploadStatus = $("#upload-status");
    var uploadFilename = $("#upload-filename");
    var receptorPath = $("#receptor-path");

    var startBtn = $("#start-btn");
    var logViewer = $("#log-viewer");

    var currentResults = [];
    var sortCol = null;
    var sortAsc = true;
    var uaaCounter = 0;
    var lastRunConfig = null;  // Stores the config from the last run for rerun
    var currentPipelineType = "peptide";  // "peptide" or "small_molecule"

    // ==================== Amino Acid Data ====================
    var AA_DATA = [
        { code: "ALA", one: "A", name: "Ala", group: "hydrophobic" },
        { code: "VAL", one: "V", name: "Val", group: "hydrophobic" },
        { code: "LEU", one: "L", name: "Leu", group: "hydrophobic" },
        { code: "ILE", one: "I", name: "Ile", group: "hydrophobic" },
        { code: "PRO", one: "P", name: "Pro", group: "hydrophobic" },
        { code: "PHE", one: "F", name: "Phe", group: "hydrophobic" },
        { code: "TRP", one: "W", name: "Trp", group: "hydrophobic" },
        { code: "MET", one: "M", name: "Met", group: "hydrophobic" },
        { code: "GLY", one: "G", name: "Gly", group: "polar" },
        { code: "SER", one: "S", name: "Ser", group: "polar" },
        { code: "THR", one: "T", name: "Thr", group: "polar" },
        { code: "CYS", one: "C", name: "Cys", group: "polar" },
        { code: "TYR", one: "Y", name: "Tyr", group: "polar" },
        { code: "ASN", one: "N", name: "Asn", group: "polar" },
        { code: "GLN", one: "Q", name: "Gln", group: "polar" },
        { code: "ASP", one: "D", name: "Asp", group: "negative" },
        { code: "GLU", one: "E", name: "Glu", group: "negative" },
        { code: "LYS", one: "K", name: "Lys", group: "positive" },
        { code: "ARG", one: "R", name: "Arg", group: "positive" },
        { code: "HIS", one: "H", name: "His", group: "positive" },
    ];

    // Track which AAs are selected (all by default)
    var selectedAAs = {};
    AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = true; });

    // ==================== Init ====================
    document.addEventListener("DOMContentLoaded", function () {
        detectVina();
        setupDropZone();
        setupSmDropZone();
        setupPipelineToggle();
        setupSmRadioToggles();
        setupSmPropertyToggle();
        setupRadioToggles();
        setupAdvancedToggle();
        setupStartButton();
        setupCheckpointButtons();
        setupResultsSort();
        setupNewRunButtons();
        buildAAGrid();
        setupAAActions();
        setupUAAButtons();
        setupResumeButton();
        setupConnectionLostButtons();
        checkSessionReconnect();
    });

    // ==================== Resume Previous Run ====================
    function setupResumeButton() {
        // Check if a previous run checkpoint exists
        fetch("/api/check_resume")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.can_resume) {
                    var banner = $("#resume-banner");
                    if (banner) {
                        banner.style.display = "block";
                        var info = $("#resume-info");
                        if (info) {
                            info.textContent = data.n_cached + " docks cached in " + data.output_dir;
                        }
                    }
                }
            })
            .catch(function() {});

        var resumeBtn = $("#resume-btn");
        if (resumeBtn) {
            resumeBtn.addEventListener("click", function() {
                resumeBtn.disabled = true;
                resumeBtn.textContent = "Resuming...";
                fetch("/api/resume", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                })
                    .then(function(r) { return r.json(); })
                    .then(function(resp) {
                        if (resp.error) {
                            alert("Resume failed: " + resp.error);
                            resumeBtn.disabled = false;
                            resumeBtn.textContent = "Resume Run";
                            return;
                        }
                        $("#resume-banner").style.display = "none";
                        showRunningView();
                        appendLog("INFO", "Resuming previous run (cached docks will be skipped)...");
                        startSSE();
                    })
                    .catch(function(err) {
                        alert("Resume failed: " + err);
                        resumeBtn.disabled = false;
                        resumeBtn.textContent = "Resume Run";
                    });
            });
        }

        var dismissBtn = $("#dismiss-resume");
        if (dismissBtn) {
            dismissBtn.addEventListener("click", function() {
                $("#resume-banner").style.display = "none";
            });
        }
    }

    // ==================== Session Reconnect ====================
    function checkSessionReconnect() {
        fetch("/api/status")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.state === "running") {
                    showRunningView();
                    appendLog("INFO", "Reconnected to running pipeline...");
                    startSSE();
                } else if (data.state === "complete") {
                    currentResults = data.results || [];
                    renderResults(currentResults);
                    showRunningView();
                    appendLog("INFO", "Pipeline completed while disconnected.");
                    showResultsView();
                }
            })
            .catch(function() {});
    }

    // ==================== Auto-detect Executables ====================
    function detectVina() {
        fetch("/api/detect_vina")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.found) {
                    $("#vina-path").value = data.found;
                }
            })
            .catch(function() {});
    }

    function detectGnina() {
        fetch("/api/detect_gnina")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.found && $("#gnina-path")) {
                    $("#gnina-path").value = data.found;
                }
            })
            .catch(function() {});
    }

    function detectRxDock() {
        fetch("/api/detect_rxdock")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.found && $("#rxdock-path")) {
                    $("#rxdock-path").value = data.found;
                }
            })
            .catch(function() {});
    }

    function detectP2Rank() {
        fetch("/api/detect_p2rank")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.found && $("#p2rank-path")) {
                    $("#p2rank-path").value = data.found;
                }
            })
            .catch(function() {});
    }

    function detectFpocket() {
        fetch("/api/detect_fpocket")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.found && $("#fpocket-path")) {
                    $("#fpocket-path").value = data.found;
                }
            })
            .catch(function() {});
    }

    $("#detect-vina-btn").addEventListener("click", detectVina);
    if ($("#detect-gnina-btn")) $("#detect-gnina-btn").addEventListener("click", detectGnina);
    if ($("#detect-rxdock-btn")) $("#detect-rxdock-btn").addEventListener("click", detectRxDock);
    if ($("#detect-p2rank-btn")) $("#detect-p2rank-btn").addEventListener("click", detectP2Rank);
    if ($("#detect-fpocket-btn")) $("#detect-fpocket-btn").addEventListener("click", detectFpocket);

    // SM auto-detect buttons
    if ($("#sm-detect-vina-btn")) {
        $("#sm-detect-vina-btn").addEventListener("click", function() {
            fetch("/api/detect_vina").then(function(r) { return r.json(); })
                .then(function(data) { if (data.found && $("#sm-vina-path")) $("#sm-vina-path").value = data.found; })
                .catch(function() {});
        });
    }
    if ($("#sm-detect-gnina-btn")) {
        $("#sm-detect-gnina-btn").addEventListener("click", function() {
            fetch("/api/detect_gnina").then(function(r) { return r.json(); })
                .then(function(data) { if (data.found && $("#sm-gnina-path")) $("#sm-gnina-path").value = data.found; })
                .catch(function() {});
        });
    }
    if ($("#sm-detect-rxdock-btn")) {
        $("#sm-detect-rxdock-btn").addEventListener("click", function() {
            fetch("/api/detect_rxdock").then(function(r) { return r.json(); })
                .then(function(data) { if (data.found && $("#sm-rxdock-path")) $("#sm-rxdock-path").value = data.found; })
                .catch(function() {});
        });
    }

    // ==================== Pipeline Type Toggle ====================
    function setupPipelineToggle() {
        var peptideBtn = $("#mode-peptide");
        var smBtn = $("#mode-smallmol");
        var peptideForm = $("#peptide-form");
        var smForm = $("#smallmol-form");

        if (!peptideBtn || !smBtn) return;

        peptideBtn.addEventListener("click", function() {
            currentPipelineType = "peptide";
            peptideBtn.classList.remove("btn-secondary");
            peptideBtn.classList.add("btn-primary", "active");
            smBtn.classList.remove("btn-primary", "active");
            smBtn.classList.add("btn-secondary");
            if (peptideForm) peptideForm.style.display = "block";
            if (smForm) smForm.style.display = "none";
        });

        smBtn.addEventListener("click", function() {
            currentPipelineType = "small_molecule";
            smBtn.classList.remove("btn-secondary");
            smBtn.classList.add("btn-primary", "active");
            peptideBtn.classList.remove("btn-primary", "active");
            peptideBtn.classList.add("btn-secondary");
            if (peptideForm) peptideForm.style.display = "none";
            if (smForm) smForm.style.display = "block";
        });
    }

    // ==================== SM Drop Zone ====================
    function setupSmDropZone() {
        var smDrop = $("#sm-drop-zone");
        var smFile = $("#sm-receptor-file");
        if (!smDrop || !smFile) return;

        smDrop.addEventListener("click", function() { smFile.click(); });

        smDrop.addEventListener("dragover", function(e) {
            e.preventDefault();
            smDrop.classList.add("drag-over");
        });

        smDrop.addEventListener("dragleave", function() {
            smDrop.classList.remove("drag-over");
        });

        smDrop.addEventListener("drop", function(e) {
            e.preventDefault();
            smDrop.classList.remove("drag-over");
            if (e.dataTransfer.files.length > 0) {
                handleSmFile(e.dataTransfer.files[0]);
            }
        });

        smFile.addEventListener("change", function() {
            if (smFile.files.length > 0) {
                handleSmFile(smFile.files[0]);
            }
        });
    }

    function handleSmFile(file) {
        var formData = new FormData();
        formData.append("receptor", file);
        var smDrop = $("#sm-drop-zone");
        smDrop.innerHTML = "<p>Uploading...</p>";

        fetch("/api/upload", { method: "POST", body: formData })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    smDrop.innerHTML = '<p style="color:#ef4444">Upload failed: ' + data.error + "</p>";
                    return;
                }
                $("#sm-receptor-path").value = data.path;
                $("#sm-upload-filename").textContent = data.filename;
                $("#sm-upload-status").style.display = "block";
                smDrop.innerHTML = "<p>&#10003; " + data.filename + "</p><p class='small'>Click to change</p>";
            })
            .catch(function(err) {
                smDrop.innerHTML = '<p style="color:#ef4444">Upload error: ' + err + "</p>";
            });
    }

    // ==================== SM Radio Toggles ====================
    function setupSmRadioToggles() {
        $$('input[name="sm_run_mode"]').forEach(function(r) {
            r.addEventListener("change", function() {
                var smHier = $("#sm-hierarchical-options");
                if (smHier) {
                    smHier.style.display = r.value === "hierarchical" ? "block" : "none";
                    if (r.value === "hierarchical") {
                        if ($("#sm-gnina-path") && !$("#sm-gnina-path").value) detectGnina();
                        if ($("#sm-rxdock-path") && !$("#sm-rxdock-path").value) detectRxDock();
                    }
                }
            });
        });
    }

    // ==================== SM Property Target Toggle ====================
    var smPropertyPresets = {
        cosmetic: { logp_min: 1.0, logp_max: 3.0, mw_max: 350, psa_max: 70, hbd_max: 2, hba_max: 5 },
        drug_like: { logp_min: 1.0, logp_max: 5.0, mw_max: 500, psa_max: 140, hbd_max: 5, hba_max: 10 }
    };

    function setupSmPropertyToggle() {
        var cosmeticBtn = $("#sm-target-cosmetic");
        var druglikeBtn = $("#sm-target-druglike");
        var customBtn = $("#sm-target-custom");
        var hiddenField = $("#sm-property-target");
        var hintDiv = $("#sm-target-hint");
        var customDiv = $("#sm-custom-properties");

        if (!cosmeticBtn || !druglikeBtn || !customBtn) return;

        function activate(btn, value) {
            [cosmeticBtn, druglikeBtn, customBtn].forEach(function(b) {
                b.classList.remove("btn-primary", "active");
                b.classList.add("btn-secondary");
            });
            btn.classList.remove("btn-secondary");
            btn.classList.add("btn-primary", "active");
            if (hiddenField) hiddenField.value = value;

            if (value === "custom") {
                if (customDiv) customDiv.style.display = "block";
                if (hintDiv) hintDiv.textContent = "Custom: set your own property limits below.";
            } else {
                if (customDiv) customDiv.style.display = "none";
                var p = smPropertyPresets[value] || smPropertyPresets.cosmetic;
                if (hintDiv) {
                    hintDiv.textContent = (value === "cosmetic" ? "Cosmetic" : "Drug-like") +
                        ": logP " + p.logp_min + "\u2013" + p.logp_max +
                        ", MW <" + p.mw_max +
                        ", PSA <" + p.psa_max +
                        ", HBD \u2264" + p.hbd_max +
                        ", HBA \u2264" + p.hba_max;
                }
                // Sync custom fields to preset values
                if ($("#sm-logp-min")) $("#sm-logp-min").value = p.logp_min;
                if ($("#sm-logp-max")) $("#sm-logp-max").value = p.logp_max;
                if ($("#sm-mw-max")) $("#sm-mw-max").value = p.mw_max;
                if ($("#sm-psa-max")) $("#sm-psa-max").value = p.psa_max;
                if ($("#sm-hbd-max")) $("#sm-hbd-max").value = p.hbd_max;
                if ($("#sm-hba-max")) $("#sm-hba-max").value = p.hba_max;
            }
        }

        cosmeticBtn.addEventListener("click", function() { activate(cosmeticBtn, "cosmetic"); });
        druglikeBtn.addEventListener("click", function() { activate(druglikeBtn, "drug_like"); });
        customBtn.addEventListener("click", function() { activate(customBtn, "custom"); });
    }

    // ==================== SM Form Data Collection ====================
    function collectSmFormData() {
        var smRunMode = "full";
        var smRunRadio = document.querySelector('input[name="sm_run_mode"]:checked');
        if (smRunRadio) smRunMode = smRunRadio.value;

        var propTarget = "cosmetic";
        if ($("#sm-property-target")) propTarget = $("#sm-property-target").value;

        return {
            pipeline_type: "small_molecule",
            receptor_path: $("#sm-receptor-path").value,
            sm_ligand_resname: ($("#sm-ligand-resname").value || "").trim().toUpperCase(),
            sm_ligand_chain: ($("#sm-ligand-chain").value || "").trim(),
            sm_max_analogs: $("#sm-max-analogs").value,
            sm_autobox_padding: $("#sm-autobox-padding").value,
            sm_max_rounds: ($("#sm-max-rounds") ? $("#sm-max-rounds").value : 3),
            sm_delta_threshold: ($("#sm-delta-threshold") ? $("#sm-delta-threshold").value : 0.3),
            sm_enable_bioisosteres: $("#sm-bioisosteres").checked,
            sm_enable_extensions: $("#sm-extensions").checked,
            sm_enable_removals: $("#sm-removals").checked,
            sm_enable_prodrug_esters: ($("#sm-prodrug-esters") ? $("#sm-prodrug-esters").checked : true),
            sm_enable_cyclization_detection: ($("#sm-cyclization-detection") ? $("#sm-cyclization-detection").checked : true),
            sm_property_target: propTarget,
            sm_target_logp_min: ($("#sm-logp-min") ? parseFloat($("#sm-logp-min").value) : 1.0),
            sm_target_logp_max: ($("#sm-logp-max") ? parseFloat($("#sm-logp-max").value) : 3.0),
            sm_target_mw_max: ($("#sm-mw-max") ? parseFloat($("#sm-mw-max").value) : 350),
            sm_target_psa_max: ($("#sm-psa-max") ? parseFloat($("#sm-psa-max").value) : 70),
            sm_target_hbd_max: ($("#sm-hbd-max") ? parseInt($("#sm-hbd-max").value) : 2),
            sm_target_hba_max: ($("#sm-hba-max") ? parseInt($("#sm-hba-max").value) : 5),
            sm_target_rotatable_max: ($("#sm-rotatable-max") ? parseInt($("#sm-rotatable-max").value) : -1),
            // v0.9.2 SAR enhancements
            sm_enable_stereoisomer_enum: ($("#sm-stereoisomer-enum") ? $("#sm-stereoisomer-enum").checked : true),
            sm_enable_thioether_detection: ($("#sm-thioether-detection") ? $("#sm-thioether-detection").checked : true),
            sm_enable_metabolic_blocking: ($("#sm-metabolic-blocking") ? $("#sm-metabolic-blocking").checked : true),
            sm_enable_scaffold_hopping: ($("#sm-scaffold-hopping") ? $("#sm-scaffold-hopping").checked : false),
            sm_enable_mmp_tracking: ($("#sm-mmp-tracking") ? $("#sm-mmp-tracking").checked : true),
            sm_enable_torsion_filter: ($("#sm-torsion-filter") ? $("#sm-torsion-filter").checked : true),
            sm_run_mode: smRunMode,
            sm_exhaustiveness: $("#sm-exhaustiveness").value,
            sm_num_modes: $("#sm-num-modes").value,
            sm_vina_executable: ($("#sm-vina-path").value || "").trim(),
            sm_gnina_executable: ($("#sm-gnina-path") ? $("#sm-gnina-path").value : ""),
            sm_rxdock_executable: ($("#sm-rxdock-path") ? $("#sm-rxdock-path").value : ""),
            output_dir: ($("#sm-output-dir").value || "./output_sm"),
        };
    }

    function validateSm() {
        if (!$("#sm-receptor-path").value) {
            alert("Please upload a co-crystal PDB file (Step 1).");
            return false;
        }
        return true;
    }

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
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    dropZone.innerHTML =
                        '<p style="color:#ef4444">Upload failed: ' +
                        data.error + "</p>";
                    return;
                }
                receptorPath.value = data.path;
                uploadFilename.textContent = data.filename;
                uploadStatus.style.display = "block";
                dropZone.innerHTML =
                    "<p>&#10003; " + data.filename + "</p><p class='small'>Click to change</p>";
            })
            .catch(function(err) {
                dropZone.innerHTML =
                    '<p style="color:#ef4444">Upload error: ' + err + "</p>";
            });
    }

    // ==================== Radio Toggles ====================
    function setupRadioToggles() {
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

        $$('input[name="box_mode"]').forEach(function (r) {
            r.addEventListener("change", function () {
                $("#pocket-input").style.display =
                    r.value === "pocket" ? "block" : "none";
                $("#manual-input").style.display =
                    r.value === "manual" ? "block" : "none";
                var acInput = $("#auto-consensus-input");
                if (acInput) {
                    acInput.style.display =
                        r.value === "auto_consensus" ? "block" : "none";
                    // Auto-detect P2Rank/Fpocket when first selected
                    if (r.value === "auto_consensus") {
                        if ($("#p2rank-path") && !$("#p2rank-path").value) detectP2Rank();
                        if ($("#fpocket-path") && !$("#fpocket-path").value) detectFpocket();
                    }
                }
            });
        });

        // Run mode: show/hide hierarchical options
        $$('input[name="run_mode"]').forEach(function (r) {
            r.addEventListener("change", function () {
                var hierOpts = $("#hierarchical-options");
                if (hierOpts) {
                    hierOpts.style.display = r.value === "hierarchical" ? "block" : "none";
                    // Auto-detect GNINA/RxDock when hierarchical mode is first selected
                    if (r.value === "hierarchical") {
                        if ($("#gnina-path") && !$("#gnina-path").value) detectGnina();
                        if ($("#rxdock-path") && !$("#rxdock-path").value) detectRxDock();
                        // Show hierarchical stage indicators
                        $$(".hierarchical-stage").forEach(function(el) {
                            el.style.display = "inline";
                        });
                    } else {
                        $$(".hierarchical-stage").forEach(function(el) {
                            el.style.display = "none";
                        });
                    }
                }
            });
        });

        // N-terminal acylation: show/hide carbon chain input
        var ntermAcyl = $("#nterm-acyl");
        if (ntermAcyl) {
            ntermAcyl.addEventListener("change", function () {
                $("#nterm-acyl-options").style.display = this.checked ? "block" : "none";
            });
        }

        // N-terminal custom: show/hide SMILES input
        var ntermCustom = $("#nterm-custom");
        if (ntermCustom) {
            ntermCustom.addEventListener("change", function () {
                $("#nterm-custom-options").style.display = this.checked ? "block" : "none";
            });
        }
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

    // ==================== AA Selection Grid ====================
    function buildAAGrid() {
        var grid = $("#aa-grid");
        if (!grid) return;
        grid.innerHTML = "";

        AA_DATA.forEach(function(aa) {
            var div = document.createElement("div");
            div.className = "aa-toggle selected " + aa.group;
            div.dataset.code = aa.code;
            div.innerHTML = '<span class="aa-code">' + aa.one + '</span>' +
                            '<span class="aa-name">' + aa.name + '</span>';
            div.addEventListener("click", function() {
                selectedAAs[aa.code] = !selectedAAs[aa.code];
                div.classList.toggle("selected", selectedAAs[aa.code]);
            });
            grid.appendChild(div);
        });
    }

    function setupAAActions() {
        var selectAll = $("#aa-select-all");
        var selectNone = $("#aa-select-none");
        var selectHydrophobic = $("#aa-select-hydrophobic");
        var selectPolar = $("#aa-select-polar");
        var selectCharged = $("#aa-select-charged");

        if (selectAll) selectAll.addEventListener("click", function() {
            AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = true; });
            updateAAGrid();
        });
        if (selectNone) selectNone.addEventListener("click", function() {
            AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = false; });
            updateAAGrid();
        });
        if (selectHydrophobic) selectHydrophobic.addEventListener("click", function() {
            AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = false; });
            AA_DATA.forEach(function(aa) {
                if (aa.group === "hydrophobic") selectedAAs[aa.code] = true;
            });
            updateAAGrid();
        });
        if (selectPolar) selectPolar.addEventListener("click", function() {
            AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = false; });
            AA_DATA.forEach(function(aa) {
                if (aa.group === "polar") selectedAAs[aa.code] = true;
            });
            updateAAGrid();
        });
        if (selectCharged) selectCharged.addEventListener("click", function() {
            AA_DATA.forEach(function(aa) { selectedAAs[aa.code] = false; });
            AA_DATA.forEach(function(aa) {
                if (aa.group === "positive" || aa.group === "negative") selectedAAs[aa.code] = true;
            });
            updateAAGrid();
        });
    }

    function updateAAGrid() {
        var toggles = $$(".aa-toggle");
        toggles.forEach(function(div) {
            var code = div.dataset.code;
            div.classList.toggle("selected", !!selectedAAs[code]);
        });
    }

    // ==================== UAA (Unnatural AA) Fields ====================
    function setupUAAButtons() {
        var addBtn = $("#add-uaa-btn");
        if (addBtn) {
            addBtn.addEventListener("click", function() {
                addUAARow();
            });
        }
        // Bulk paste toggle
        var bulkToggle = $("#uaa-bulk-toggle");
        if (bulkToggle) {
            bulkToggle.addEventListener("click", function() {
                var area = $("#uaa-bulk-area");
                area.style.display = area.style.display === "none" ? "block" : "none";
            });
        }
        // Bulk import button
        var bulkImport = $("#uaa-bulk-import");
        if (bulkImport) {
            bulkImport.addEventListener("click", function() {
                var text = ($("#uaa-bulk-text").value || "").trim();
                if (!text) return;
                var lines = text.split("\n");
                var imported = 0;
                lines.forEach(function(line) {
                    line = line.trim();
                    if (!line || line.startsWith("#")) return;
                    // Split on tab, multiple spaces, or comma
                    var parts = line.split(/[\t,]+|\s{2,}/);
                    if (parts.length < 2) {
                        // Try single space split as last resort
                        parts = line.split(/\s+/);
                    }
                    if (parts.length >= 2) {
                        var name = parts[0].trim();
                        var smiles = parts.slice(1).join("").trim();
                        addUAARow(name, smiles);
                        imported++;
                    }
                });
                if (imported > 0) {
                    $("#uaa-bulk-text").value = "";
                    $("#uaa-bulk-area").style.display = "none";
                    appendLog("INFO", "Imported " + imported + " custom amino acid(s)");
                }
            });
        }
    }

    function addUAARow(prefillName, prefillSmiles) {
        uaaCounter++;
        var list = $("#uaa-list");
        if (!list) return;
        var row = document.createElement("div");
        row.className = "uaa-row";
        row.id = "uaa-row-" + uaaCounter;
        row.innerHTML =
            '<input type="text" class="uaa-name-input" id="uaa-name-' + uaaCounter +
            '" placeholder="Name (e.g. NLE)">' +
            '<input type="text" class="uaa-smiles-input" id="uaa-smiles-' + uaaCounter +
            '" placeholder="Sidechain SMILES with [*] (e.g. [*]CCCC)">' +
            '<button type="button" class="uaa-remove" data-row="' + uaaCounter +
            '">&#10005;</button>';
        list.appendChild(row);
        if (prefillName) row.querySelector(".uaa-name-input").value = prefillName;
        if (prefillSmiles) row.querySelector(".uaa-smiles-input").value = prefillSmiles;

        row.querySelector(".uaa-remove").addEventListener("click", function() {
            row.remove();
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
            scan_cterm_caps: $("#scan-cterm-caps").checked,
            nterm_dimethyl: $("#nterm-dimethyl").checked,
            nterm_acyl: $("#nterm-acyl").checked,
            nterm_acyl_carbons: $("#nterm-acyl-carbons").value,
            nterm_custom_smiles: $("#nterm-custom-smiles") ? $("#nterm-custom-smiles").value : "",
            vina_executable: $("#vina-path").value,
            gnina_executable: $("#gnina-path") ? $("#gnina-path").value : "",
            rxdock_executable: $("#rxdock-path") ? $("#rxdock-path").value : "",
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

        data.box_mode = boxMode;
        if (boxMode === "pocket") {
            data.pocket_residues = $("#pocket-residues").value;
        } else if (boxMode === "manual") {
            data.center_x = $("#center-x").value;
            data.center_y = $("#center-y").value;
            data.center_z = $("#center-z").value;
            data.size_x = $("#size-x").value;
            data.size_y = $("#size-y").value;
            data.size_z = $("#size-z").value;
        } else if (boxMode === "auto_consensus") {
            data.min_pocket_volume = $("#min-pocket-volume").value;
            data.p2rank_executable = $("#p2rank-path").value;
            data.fpocket_executable = $("#fpocket-path").value;
        }

        // Collect selected AAs
        var allowedAAs = [];
        AA_DATA.forEach(function(aa) {
            if (selectedAAs[aa.code]) allowedAAs.push(aa.code);
        });
        data.sc_allowed_residues = allowedAAs;

        // Collect UAA definitions
        var uaaRows = $$(".uaa-row");
        uaaRows.forEach(function(row) {
            var nameInput = row.querySelector(".uaa-name-input");
            var smilesInput = row.querySelector(".uaa-smiles-input");
            if (nameInput && smilesInput && nameInput.value && smilesInput.value) {
                data["uaa_name_" + nameInput.id.split("-").pop()] = nameInput.value;
                data["uaa_smiles_" + smilesInput.id.split("-").pop()] = smilesInput.value;
            }
        });

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
        // Check at least 1 AA is selected
        var anySelected = false;
        AA_DATA.forEach(function(aa) {
            if (selectedAAs[aa.code]) anySelected = true;
        });
        if (!anySelected) {
            alert("Please select at least one amino acid for optimization (Step 5).");
            return false;
        }
        return true;
    }

    // ==================== Start Pipeline ====================
    function setupStartButton() {
        startBtn.addEventListener("click", function () {
            var data;
            if (currentPipelineType === "small_molecule") {
                if (!validateSm()) return;
                data = collectSmFormData();
            } else {
                if (!validate()) return;
                data = collectFormData();
                data.pipeline_type = "peptide";
            }

            lastRunConfig = data;  // Save for rerun
            startBtn.disabled = true;
            startBtn.textContent = "Starting...";

            fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            })
                .then(function(r) { return r.json(); })
                .then(function(resp) {
                    if (resp.error) {
                        alert("Error: " + resp.error);
                        startBtn.disabled = false;
                        startBtn.textContent = "Start Pipeline";
                        return;
                    }
                    showRunningView();
                    startSSE();
                })
                .catch(function(err) {
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
        // Hide countdown
        var cb = $("#countdown-bar");
        if (cb) cb.style.display = "none";
        // Check for QC complexes
        checkQCStatus();
        // Check for consensus CSV (hierarchical mode)
        checkConsensusCSV();
    }

    function checkConsensusCSV() {
        fetch("/api/download_consensus_csv", { method: "HEAD" })
            .then(function(r) {
                if (r.ok) {
                    var btn = $("#download-consensus-csv");
                    if (btn) btn.style.display = "inline-block";
                }
            })
            .catch(function() {});
    }

    function checkQCStatus() {
        fetch("/api/qc_status")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var anyAvailable = false;
                var qcMap = {
                    "d_amino": "qc-d-amino",
                    "beta_amino": "qc-beta-amino",
                    "unnatural": "qc-unnatural",
                    "cterm_amide": "qc-cterm-amide",
                    "nterm_methyl": "qc-nterm-methyl",
                    "nterm_acyl": "qc-nterm-acyl",
                    "nterm_custom": "qc-nterm-custom",
                };
                for (var key in qcMap) {
                    if (data[key]) {
                        var el = $("#" + qcMap[key]);
                        if (el) el.style.display = "inline-block";
                        anyAvailable = true;
                    }
                }
                var section = $("#qc-section");
                if (section && anyAvailable) {
                    section.style.display = "block";
                }
            })
            .catch(function() {});
    }

    function showErrorView(message, traceback) {
        runningView.style.display = "none";
        errorView.style.display = "block";
        $("#error-message").textContent = message;
        $("#error-traceback").textContent = traceback || "";
    }

    // ==================== Countdown Timer ====================
    function formatCountdown(seconds) {
        if (seconds <= 0) return "Complete!";
        if (seconds < 60) return Math.round(seconds) + " sec remaining";
        if (seconds < 3600) return (seconds / 60).toFixed(1) + " min remaining";
        return (seconds / 3600).toFixed(1) + " hr remaining";
    }

    function updateCountdown(data) {
        var bar = $("#countdown-bar");
        if (!bar) return;
        bar.style.display = "block";

        var remaining = data.estimated_remaining_sec || 0;
        var completed = data.completed_docks || 0;
        var total = data.total_docks || 1;
        var speed = data.time_per_dock || 0;

        $("#countdown-text").textContent = formatCountdown(remaining);
        $("#docks-completed").textContent = completed;
        $("#docks-total").textContent = total;
        $("#dock-speed").textContent = speed > 0 ? speed.toFixed(1) : "-";

        var pct = total > 0 ? Math.min(100, (completed / total) * 100) : 0;
        $("#progress-fill").style.width = pct.toFixed(1) + "%";
    }

    // ==================== SSE Streaming ====================
    function startSSE() {
        var source = new EventSource("/api/stream");

        source.addEventListener("log", function (e) {
            var data = JSON.parse(e.data);
            appendLog(data.level, data.message);
            updateStageFromLog(data.message);
        });

        source.addEventListener("progress", function (e) {
            var data = JSON.parse(e.data);
            updateCountdown(data);
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
            source.close();
            appendLog("ERROR", "Connection to server lost.");
            // Show the connection-lost banner with resume option
            showConnectionLostBanner();
        };
    }

    var sseReconnectAttempts = 0;
    var MAX_RECONNECT_ATTEMPTS = 3;

    function showConnectionLostBanner() {
        var banner = $("#connection-lost-banner");
        if (!banner) return;

        // First, try to silently reconnect a few times (server may just be restarting)
        if (sseReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            sseReconnectAttempts++;
            appendLog("INFO", "Attempting to reconnect (" + sseReconnectAttempts + "/" + MAX_RECONNECT_ATTEMPTS + ")...");
            setTimeout(function() {
                fetch("/api/status")
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.state === "running") {
                            // Server is back and pipeline is still running — reconnect SSE
                            appendLog("INFO", "Reconnected to running pipeline!");
                            sseReconnectAttempts = 0;
                            startSSE();
                        } else if (data.state === "complete") {
                            // Pipeline finished while we were disconnected
                            sseReconnectAttempts = 0;
                            currentResults = data.results || [];
                            appendLog("INFO", "Pipeline completed while disconnected.");
                            renderResults(currentResults);
                            showResultsView();
                        } else {
                            // Server is back but pipeline is not running — show resume banner
                            showConnectionLostBanner();
                        }
                    })
                    .catch(function() {
                        // Server still down — try again
                        showConnectionLostBanner();
                    });
            }, 3000);  // Wait 3 seconds between retries
            return;
        }

        // All retries exhausted — show the banner
        sseReconnectAttempts = 0;
        banner.style.display = "block";
    }

    function setupConnectionLostButtons() {
        var resumeBtn = $("#running-resume-btn");
        if (resumeBtn) {
            resumeBtn.addEventListener("click", function() {
                resumeBtn.disabled = true;
                resumeBtn.textContent = "Resuming...";
                fetch("/api/resume", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                })
                    .then(function(r) { return r.json(); })
                    .then(function(resp) {
                        if (resp.error) {
                            alert("Resume failed: " + resp.error);
                            resumeBtn.disabled = false;
                            resumeBtn.textContent = "Resume Run";
                            return;
                        }
                        $("#connection-lost-banner").style.display = "none";
                        appendLog("INFO", "Resuming run (cached docks will be skipped)...");
                        startSSE();
                        resumeBtn.disabled = false;
                        resumeBtn.textContent = "Resume Run";
                    })
                    .catch(function(err) {
                        alert("Resume failed: " + err);
                        resumeBtn.disabled = false;
                        resumeBtn.textContent = "Resume Run";
                    });
            });
        }

        var newRunBtn = $("#running-new-run-btn");
        if (newRunBtn) {
            newRunBtn.addEventListener("click", function() {
                window.location.reload();
            });
        }
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
        if (msg.indexOf("preparing receptor") >= 0 || msg.indexOf("preparation") >= 0) {
            setActiveStage("prep");
        } else if (msg.indexOf("initial dock") >= 0 || msg.indexOf("running initial") >= 0) {
            setActiveStage("initial");
        } else if (msg.indexOf("phase 2") >= 0 || msg.indexOf("gnina") >= 0) {
            // Show hierarchical stages if not already visible
            $$(".hierarchical-stage").forEach(function(el) { el.style.display = "inline"; });
            setActiveStage("gnina");
        } else if (msg.indexOf("phase 3") >= 0 || msg.indexOf("rxdock") >= 0) {
            setActiveStage("rxdock");
        } else if (msg.indexOf("phase 4") >= 0 || msg.indexOf("consensus") >= 0) {
            setActiveStage("consensus");
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
                .map(function (s) { return s.trim(); })
                .filter(function (s) { return s.length > 0; });
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
            tbody.innerHTML = "<tr><td colspan='6'>No results</td></tr>";
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
                "<td>" + esc(r.stereo || "-") + "</td>" +
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

                $$("#results-table th").forEach(function (h) {
                    h.classList.remove("sort-asc", "sort-desc");
                });
                th.classList.add(sortAsc ? "sort-asc" : "sort-desc");

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

    // ==================== Rerun with Same Settings ====================
    function rerunWithSameSettings(btn) {
        // Try lastRunConfig first (same session), then fall back to saved config on server
        if (lastRunConfig) {
            doRerun(lastRunConfig, btn);
        } else {
            // Fetch the saved config from the server
            fetch("/api/check_resume")
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.config) {
                        lastRunConfig = data.config;
                        doRerun(lastRunConfig, btn);
                    } else {
                        alert("No previous run configuration found. Please start a new run.");
                        btn.disabled = false;
                        btn.textContent = "Rerun Same Settings";
                    }
                })
                .catch(function() {
                    alert("Could not retrieve previous settings. Please start a new run.");
                    btn.disabled = false;
                    btn.textContent = "Rerun Same Settings";
                });
        }
    }

    function doRerun(config, btn) {
        btn.disabled = true;
        btn.textContent = "Starting...";

        fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config),
        })
            .then(function(r) { return r.json(); })
            .then(function(resp) {
                if (resp.error) {
                    alert("Error: " + resp.error);
                    btn.disabled = false;
                    btn.textContent = "Rerun Same Settings";
                    return;
                }
                showRunningView();
                appendLog("INFO", "Rerunning with same settings...");
                startSSE();
            })
            .catch(function(err) {
                alert("Failed to start: " + err);
                btn.disabled = false;
                btn.textContent = "Rerun Same Settings";
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

        // Rerun from results view
        var rerunBtn = $("#rerun-btn");
        if (rerunBtn) {
            rerunBtn.addEventListener("click", function() {
                rerunWithSameSettings(rerunBtn);
            });
        }

        // Rerun from error view
        var errorRerunBtn = $("#error-rerun-btn");
        if (errorRerunBtn) {
            errorRerunBtn.addEventListener("click", function() {
                rerunWithSameSettings(errorRerunBtn);
            });
        }

        // Resume from error view
        var errorResume = $("#error-resume-run");
        if (errorResume) {
            errorResume.addEventListener("click", function() {
                errorResume.disabled = true;
                errorResume.textContent = "Resuming...";
                fetch("/api/resume", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                })
                    .then(function(r) { return r.json(); })
                    .then(function(resp) {
                        if (resp.error) {
                            alert("Resume failed: " + resp.error);
                            errorResume.disabled = false;
                            errorResume.textContent = "Resume Run";
                            return;
                        }
                        errorView.style.display = "none";
                        showRunningView();
                        appendLog("INFO", "Resuming run (cached docks will be skipped)...");
                        startSSE();
                    })
                    .catch(function(err) {
                        alert("Resume failed: " + err);
                        errorResume.disabled = false;
                        errorResume.textContent = "Resume Run";
                    });
            });
        }
    }

    // ==================== Utility ====================
    function esc(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
