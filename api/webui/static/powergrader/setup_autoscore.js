(function () {
  "use strict";

  var pg = window.CE_POWERGRADER_SETUP || {};
  var ready = [
    "esc",
    "currentMode",
    "defaultModel",
    "getForm",
    "getElement",
    "setAiLabelText",
    "setStatus",
  ].every(function (name) {
    return typeof pg[name] === "function" || typeof pg[name] === "string";
  });

  function requireReady() {
    if (ready) return true;
    alert("PowerGrader setup controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  var setupConfig = window.POWERGRADER_SETUP_CONFIG || {};
  var modelPresets = setupConfig.modelPresets || [];
  var modelOptions = [];

  function getElement(id) {
    return pg.getElement(id);
  }

  function modelScenarioText(m) {
    if (m.scenario_cost === null || m.scenario_cost === undefined || isNaN(Number(m.scenario_cost))) return "";
    var n = Number(m.scenario_cost);
    return "30 essays est. " + (n < 0.01 ? "<$0.01" : "$" + n.toFixed(2));
  }

  function priceText(v) {
    if (v === null || v === undefined || isNaN(Number(v))) return "n/a";
    var n = Number(v);
    if (n === 0) return "$0";
    if (n < 1) return "$" + n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
    return "$" + n.toFixed(2);
  }

  function whole(n) {
    var x = Number(n || 0);
    return x.toLocaleString();
  }

  function costTier(cost) {
    var n = Number(cost);
    if (isNaN(n)) return "$?";
    if (n < 0.10) return "$";
    if (n < 0.50) return "$$";
    return "$$$";
  }

  function tierClass(tier) {
    return tier === "$$$" ? " high" : (tier === "$$" ? " mid" : (tier === "$?" ? " unknown" : ""));
  }

  function modelCostText(m) {
    if (!m) return "";
    var price = "Input " + priceText(m.input_per_mtok) + "/M · Output " + priceText(m.output_per_mtok) + "/M";
    if (m.image_capable) price += " · image input";
    var scenario = modelScenarioText(m);
    return price + (scenario ? " · " + scenario : "");
  }

  function normalizeModelOption(m, source) {
    var scenario = m.scenario_cost;
    return {
      id: m.id || "",
      label: m.label || m.name || m.id || "",
      note: m.note || (source === "live" ? "Current OpenRouter listing" : ""),
      input_per_mtok: m.input_per_mtok,
      output_per_mtok: m.output_per_mtok,
      input_modalities: m.input_modalities || [],
      image_capable: !!m.image_capable || (m.input_modalities || []).indexOf("image") !== -1,
      image_per_mtok: m.image_per_mtok,
      scenario_cost: scenario,
      cost_tier: m.cost_tier || costTier(scenario),
      source: source || m.source || "preset"
    };
  }

  function resetModelOptions() {
    modelOptions = (modelPresets || []).map(function (m) { return normalizeModelOption(m, "preset"); });
    modelOptions.push({
      id: "openrouter/auto",
      label: "Auto Router",
      note: "Advanced; variable cost; exact estimate unavailable",
      input_per_mtok: null,
      output_per_mtok: null,
      scenario_cost: null,
      cost_tier: "$?",
      source: "special"
    });
  }

  function mergeModelOptions(rows, source) {
    var byId = {};
    modelOptions.forEach(function (m) { byId[m.id] = m; });
    (rows || []).forEach(function (row) {
      if (!row || !row.id) return;
      var live = normalizeModelOption(row, source || "live");
      if (byId[live.id]) {
        Object.assign(byId[live.id], {
          input_per_mtok: live.input_per_mtok,
          output_per_mtok: live.output_per_mtok,
          scenario_cost: live.scenario_cost,
          cost_tier: live.cost_tier
        });
      } else {
        modelOptions.push(live);
        byId[live.id] = live;
      }
    });
    modelOptions.sort(function (a, b) {
      var aLatest = a.id.indexOf("latest") !== -1 ? 0 : 1;
      var bLatest = b.id.indexOf("latest") !== -1 ? 0 : 1;
      if (a.source === "preset" && b.source !== "preset") return -1;
      if (b.source === "preset" && a.source !== "preset") return 1;
      if (aLatest !== bLatest) return aLatest - bLatest;
      return a.label.localeCompare(b.label);
    });
  }

  function findModelOption(id) {
    return modelOptions.find(function (m) { return m.id === id; }) || null;
  }

  function updateModelCost() {
    var modelCost = getElement("pg-model-cost");
    var modelEl = getElement("pg-model");
    if (!modelCost || !modelEl) return;
    var m = findModelOption(modelEl.value);
    if (!m) {
      modelCost.textContent = "Custom model ID. Cost guard will verify live pricing before sending.";
      return;
    }
    modelCost.textContent = m.cost_tier + " · " + modelCostText(m) +
      (m.cost_tier === "$$$" ? " · premium; review before class-scale scoring" : "");
  }

  function renderModelOptions(query) {
    var modelList = getElement("pg-model-listbox");
    var modelEl = getElement("pg-model");
    if (!modelList) return;
    var q = String(query || "").trim().toLowerCase();
    var rows = modelOptions.filter(function (m) {
      if (!q) return true;
      return (m.id + " " + m.label + " " + m.note).toLowerCase().indexOf(q) !== -1;
    }).slice(0, 80);
    if (!rows.length) {
      modelList.innerHTML = '<div class="pg-model-empty">No preset matches. You can still type an exact OpenRouter model ID.</div>';
      return;
    }
    modelList.innerHTML = rows.map(function (m) {
      var selected = modelEl && modelEl.value === m.id;
      var tier = m.cost_tier || costTier(m.scenario_cost);
      var pill = '<span class="pg-model-pill' + tierClass(tier) + '">' + pg.esc(tier) + '</span>';
      return '<button type="button" class="pg-model-row' + (selected ? ' is-selected' : '') + '" role="option" data-model-id="' + pg.esc(m.id) + '">' +
        '<strong>' + pg.esc(m.label || m.id) + pill + '</strong>' +
        '<div class="pg-model-id">' + pg.esc(m.id) + '</div>' +
        '<div class="pg-model-meta">' + pg.esc(modelCostText(m)) + '</div>' +
        (m.note ? '<div class="pg-model-meta">' + pg.esc(m.note) + '</div>' : '') +
        '</button>';
    }).join("");
  }

  function setModelPanel(open, query) {
    var modelPanel = getElement("pg-model-panel");
    var modelEl = getElement("pg-model");
    if (!modelPanel || !modelEl) return;
    if (open) renderModelOptions(query || "");
    modelPanel.hidden = !open;
    modelEl.setAttribute("aria-expanded", open ? "true" : "false");
  }

  var aiPacketPrivacyPlan = [
    { id: "download", label: "Download submitted work from Canvas", status: "running", detail: "Fetching only this assignment." },
    { id: "source_context", label: "Load shared source material", status: "pending", detail: "Excerpts are sent once as shared context for the batch." },
    { id: "pseudonymize", label: "Assign pseudonyms and separate identities", status: "pending", detail: "Real names stay in the local vault." },
    { id: "safety_scan", label: "Scan for real names before any LLM call", status: "pending", detail: "Hard matches become yellow or red before sending." },
    { id: "safe_private", label: "Write Safe AI Packet and Private decoder", status: "pending", detail: "The packet uses fake names. The decoder stays local." },
    { id: "safe_ai_packet", label: "Create Safe AI Packet ZIP", status: "pending", detail: "Ready for your AI chat or the API route." }
  ];

  var apiPrivacyTail = [
    { id: "safe_payload", label: "Load the Safe AI Packet for scoring", status: "pending", detail: "The inspected packet is the LLM payload." },
    { id: "price_check", label: "Verify model price estimate", status: "pending", detail: "Premium models are allowed when pricing is known." },
    { id: "llm_send", label: "Send only the Safe AI Packet to OpenRouter", status: "pending", detail: "No real names are included." },
    { id: "reidentify", label: "Reattach real names locally", status: "pending", detail: "Results are joined back on this machine before review." }
  ];

  function privacyPlanForMode(mode) {
    if (mode === "assisted") return aiPacketPrivacyPlan.concat(apiPrivacyTail);
    if (mode === "packet") {
      return aiPacketPrivacyPlan.concat([
        { id: "manual_ai_chat", label: "Ready for your AI chat", status: "pending", detail: "Nothing is sent automatically." }
      ]);
    }
    return [{ id: "download", label: "Download submitted work from Canvas", status: "running", detail: "Grade Myself stays local and skips AI packet creation." }];
  }

  function renderPrivacySteps(steps) {
    var privacyRun = getElement("pg-privacy-run");
    var privacyList = getElement("pg-privacy-list");
    if (!privacyRun || !privacyList) return;
    privacyRun.hidden = false;
    privacyList.innerHTML = (steps || []).map(function (step) {
      var state = step.status || "pending";
      var light = state === "ok" ? "ok" : (state === "warn" ? "warn" : (state === "failed" ? "failed" : (state === "running" ? "running" : "")));
      var pathButton = step.path
        ? '<div class="pg-privacy-actions-inline"><button type="button" class="small" data-open-path="' + pg.esc(step.path) + '">' + pg.esc(step.action_label || "Open file") + '</button></div>'
        : "";
      return '<div class="pg-privacy-step">' +
        '<span class="pg-light ' + light + '"></span>' +
        '<div><div class="pg-privacy-label">' + pg.esc(step.label || step.id || "Step") + '</div>' +
        (step.detail ? '<div class="pg-privacy-detail">' + pg.esc(step.detail) + '</div>' : "") +
        pathButton +
        '</div></div>';
    }).join("");
  }

  function selectedSourceFiles() {
    var sourceFiles = getElement("pg-source-files");
    if (!sourceFiles) return [];
    return Array.from(sourceFiles.selectedOptions || []).map(function (o) { return o.value; }).filter(Boolean);
  }

  function syncSourceFilesJson() {
    var sourceFilesJson = getElement("pg-source-files-json");
    if (sourceFilesJson) sourceFilesJson.value = JSON.stringify(selectedSourceFiles());
  }

  function renderEstimate(d) {
    var estimatePanel = getElement("pg-estimate-panel");
    if (!estimatePanel) return;
    var t = d.tokens || {};
    var cost = d.estimated_cost_label || "unavailable";
    var materials = (d.materials || []).map(function (m) {
      return '<div>' + pg.esc(m.title || m.source || "Source") + ': ~' + whole(m.tokens_est) + ' tokens</div>';
    }).join("");
    var warnings = (d.warnings || []).map(function (w) { return '<li>' + pg.esc(w) + '</li>'; }).join("");
    estimatePanel.innerHTML =
      '<div class="pg-estimate-grid">' +
        '<div><strong>Students</strong><br>' + whole(d.student_count) + ' <span class="hint">(' + pg.esc(d.count_basis || 'estimate') + ')</span></div>' +
        '<div><strong>Estimated cost</strong><br>' + pg.esc(cost) + '</div>' +
        '<div><strong>Input tokens</strong><br>' + whole(t.estimated_input) + '</div>' +
        '<div><strong>Output tokens</strong><br>' + whole(t.estimated_output) + '</div>' +
        '<div><strong>Source material</strong><br>' + whole(t.source_materials) + '</div>' +
        '<div><strong>Student preset</strong><br>' + pg.esc(d.response_label || '') + '</div>' +
      '</div>' +
      (materials ? '<div class="pg-estimate-materials">' + materials + '</div>' : '') +
      '<p class="hint" style="margin:8px 0 0">' + pg.esc(d.caching_note || '') + '</p>' +
      (warnings ? '<ul class="pg-estimate-warnings">' + warnings + '</ul>' : '');
    estimatePanel.hidden = false;
  }

  function bindEstimate() {
    var btnEstimate = getElement("pg-estimate");
    if (!btnEstimate) return;
    btnEstimate.addEventListener("click", function () {
      if (!requireReady()) return;
      var courseEl = getElement("pg-course");
      var asnEl = getElement("pg-assignment");
      var estimateStatus = getElement("pg-estimate-status");
      var modelEl = getElement("pg-model");
      var responseKind = getElement("pg-response-kind");
      var cid = courseEl ? courseEl.value : "";
      var aid = asnEl ? asnEl.value : "";
      if (!cid || !aid) {
        if (estimateStatus) estimateStatus.textContent = "Select a course and assignment first.";
        return;
      }
      syncSourceFilesJson();
      btnEstimate.disabled = true;
      if (estimateStatus) estimateStatus.textContent = "Estimating...";
      var fd = new FormData(pg.getForm());
      fd.set("course_id", cid);
      fd.set("assignment_id", aid);
      fd.set("model_id", (modelEl && modelEl.value) || pg.defaultModel());
      fd.set("persona_id", getElement("pg-persona")?.value || "sage");
      fd.set("response_kind", responseKind?.value || "scr");
      fetch("/api/powergrader/estimate", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            if (estimateStatus) estimateStatus.textContent = d.error || "Estimate failed.";
            return;
          }
          renderEstimate(d);
          if (estimateStatus) estimateStatus.textContent = "Estimate ready.";
        })
        .catch(function (e) { if (estimateStatus) estimateStatus.textContent = String(e); })
        .finally(function () { btnEstimate.disabled = false; });
    });
  }

  function bindModelPicker() {
    var modelEl = getElement("pg-model");
    var modelPicker = getElement("pg-model-picker");
    var modelPanel = getElement("pg-model-panel");
    var modelList = getElement("pg-model-listbox");
    var btnModelMenu = getElement("pg-model-menu-button");
    var btnModelDefault = getElement("pg-model-default");
    var btnLoadModels = getElement("pg-load-models");
    var modelStatus = getElement("pg-model-status");

    resetModelOptions();
    updateModelCost();

    modelEl && modelEl.addEventListener("input", function () {
      pg.setAiLabelText();
      setModelPanel(true, modelEl.value);
      updateModelCost();
    });

    modelEl && modelEl.addEventListener("focus", function () {
      setModelPanel(true, "");
    });

    btnModelMenu && btnModelMenu.addEventListener("click", function () {
      if (!modelPanel) return;
      var shouldOpen = modelPanel.hidden;
      setModelPanel(shouldOpen, "");
      if (shouldOpen && modelEl) modelEl.focus();
    });

    modelList && modelList.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-model-id]");
      if (!btn || !modelEl) return;
      modelEl.value = btn.getAttribute("data-model-id") || "";
      setModelPanel(false, "");
      updateModelCost();
      pg.setAiLabelText();
      modelEl.focus();
    });

    document.addEventListener("click", function (e) {
      if (modelPicker && !modelPicker.contains(e.target)) setModelPanel(false, "");
    });

    modelEl && modelEl.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setModelPanel(false, "");
    });

    btnModelDefault && btnModelDefault.addEventListener("click", function () {
      if (modelEl) modelEl.value = pg.defaultModel();
      if (modelStatus) modelStatus.textContent = "Default selected.";
      pg.setAiLabelText();
      updateModelCost();
    });

    btnLoadModels && btnLoadModels.addEventListener("click", function () {
      if (!modelList) return;
      btnLoadModels.disabled = true;
      btnLoadModels.textContent = "Loading…";
      if (modelStatus) modelStatus.textContent = "Loading OpenRouter models and latest aliases…";
      Promise.all([
        fetch("/settings/openrouter/models?q=latest&limit=300").then(function (r) { return r.json(); }).catch(function (e) { return { ok: false, error: String(e) }; }),
        fetch("/settings/openrouter/models?limit=300").then(function (r) { return r.json(); }).catch(function (e) { return { ok: false, error: String(e) }; })
      ])
        .then(function (results) {
          var latest = results[0], all = results[1];
          if (!latest.ok && !all.ok) {
            if (modelStatus) modelStatus.textContent = "Could not load models.";
            return;
          }
          resetModelOptions();
          mergeModelOptions((latest.models || []), "live");
          mergeModelOptions((all.models || []), "live");
          renderModelOptions("");
          updateModelCost();
          if (modelStatus) modelStatus.textContent = "Loaded " + (((latest.models || []).length) + ((all.models || []).length)) + " searchable model rows with prices.";
          modelEl && modelEl.focus();
        })
        .catch(function () { if (modelStatus) modelStatus.textContent = "Could not load models."; })
        .finally(function () {
          btnLoadModels.disabled = false;
          btnLoadModels.textContent = "Load latest model list";
        });
    });
  }

  pg.syncSourceFilesJson = syncSourceFilesJson;
  pg.renderPrivacySteps = renderPrivacySteps;
  pg.privacyPlanForMode = privacyPlanForMode;

  bindEstimate();
  bindModelPicker();
})();
