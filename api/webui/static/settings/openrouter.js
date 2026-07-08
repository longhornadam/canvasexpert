(function () {
  "use strict";

  var CE = window.CE_SETTINGS || {};

  var openrouterForm = document.getElementById("openrouter-form");
  var openrouterKeyInput = document.getElementById("openrouter-key-input");
  var openrouterModel = document.getElementById("openrouter-model-input");
  var openrouterStatus = document.getElementById("openrouter-status");
  var btnReplaceOrKey = document.getElementById("btn-replace-openrouter-key");
  var btnOpenrouterHelp = document.getElementById("btn-openrouter-help");
  var openrouterHelp = document.getElementById("openrouter-help");
  var btnOpenrouterAuto = document.getElementById("btn-openrouter-auto");
  var btnLoadOrModels = document.getElementById("btn-openrouter-load-models");
  var btnTestOpenrouter = document.getElementById("btn-openrouter-test");
  var openrouterModels = document.getElementById("openrouter-model-list");
  var openrouterMajorBox = document.getElementById("openrouter-major-models");
  var openrouterMajorList = document.getElementById("openrouter-major-list");
  var openrouterDefaultModel = document.getElementById("openrouter-card")?.dataset.defaultModel || "deepseek/deepseek-v4-pro";

  function setOpenrouterStatus(msg, kind) {
    CE.setStatus(openrouterStatus, msg, kind);
  }

  function formatPrice(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
    var n = Number(v);
    if (n === 0) return "$0";
    if (n < 0.01) return "$" + n.toFixed(4);
    if (n < 1) return "$" + n.toFixed(3);
    return "$" + n.toFixed(2);
  }

  function formatScenarioCost(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
    var n = Number(v);
    if (n === 0) return "$0";
    if (n < 0.01) return "<$0.01";
    if (n < 1) return "$" + n.toFixed(2);
    return "$" + n.toFixed(2);
  }

  function estimateText(m) {
    if (m.scenario_cost_low !== undefined && m.scenario_cost_high !== undefined &&
        m.scenario_cost_low !== null && m.scenario_cost_high !== null) {
      return formatScenarioCost(m.scenario_cost_low) + "-" + formatScenarioCost(m.scenario_cost_high);
    }
    return formatScenarioCost(m.scenario_cost);
  }

  function renderMajorModels(models, scenario) {
    if (!openrouterMajorBox || !openrouterMajorList) return;
    var rows = models || [];
    if (!rows.length) {
      openrouterMajorBox.hidden = true;
      return;
    }
    var scenarioLabel = scenario?.label || "30 1000-word essays";
    openrouterMajorList.innerHTML =
      '<table class="profiles" style="margin-top:6px">' +
      '<thead><tr><th>Family</th><th>Model</th><th>Estimate</th><th>Reference pricing</th><th></th></tr></thead>' +
      '<tbody>' + rows.map(function (m) {
        return '<tr>' +
          '<td>' + CE.esc(m.family || "") + '</td>' +
          '<td><strong>' + CE.esc(m.name || m.id) + '</strong><br><span class="muted">' + CE.esc(m.id) + '</span><br><span class="muted">' + CE.esc(m.strategy || "") + '</span></td>' +
          '<td><strong>' + estimateText(m) + '</strong><br><span class="muted">' + CE.esc(scenarioLabel) + '</span></td>' +
          '<td><span class="muted">Input ' + formatPrice(m.input_per_mtok) + ' / 1M<br>Output ' + formatPrice(m.output_per_mtok) + ' / 1M</span></td>' +
          '<td><button type="button" class="small" data-openrouter-model="' + CE.esc(m.id) + '">Use</button></td>' +
          '</tr>';
      }).join("") + '</tbody></table>';
    openrouterMajorBox.hidden = false;
  }

  btnReplaceOrKey && btnReplaceOrKey.addEventListener("click", function () {
    var showing = openrouterKeyInput.style.display !== "none";
    openrouterKeyInput.style.display = showing ? "none" : "";
    btnReplaceOrKey.textContent = showing ? "Replace" : "Cancel";
    if (!showing) openrouterKeyInput.focus();
  });

  btnOpenrouterHelp && btnOpenrouterHelp.addEventListener("click", function () {
    if (!openrouterHelp) return;
    openrouterHelp.hidden = !openrouterHelp.hidden;
    btnOpenrouterHelp.textContent = openrouterHelp.hidden ? "What is this?" : "Hide instructions";
  });

  btnOpenrouterAuto && btnOpenrouterAuto.addEventListener("click", function () {
    if (openrouterModel) openrouterModel.value = openrouterDefaultModel;
    setOpenrouterStatus("DeepSeek V4 Pro selected. Save to keep it.", "ok");
  });

  openrouterMajorList && openrouterMajorList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-openrouter-model]");
    if (!btn) return;
    if (openrouterModel) openrouterModel.value = btn.dataset.openrouterModel || "";
    setOpenrouterStatus("Model selected. Save to keep it.", "ok");
  });

  btnLoadOrModels && btnLoadOrModels.addEventListener("click", async function () {
    if (!openrouterModels) return;
    btnLoadOrModels.disabled = true;
    btnLoadOrModels.textContent = "Loading…";
    setOpenrouterStatus("Loading current OpenRouter model IDs and prices…");
    try {
      var d = await fetch("/settings/openrouter/models").then(function (r) { return r.json(); });
      if (!d.ok) {
        setOpenrouterStatus("Could not load models: " + (d.error || "unknown error"), "error");
        return;
      }
      var seen = new Set();
      var options = [];
      Array.from(openrouterModels.querySelectorAll("option")).forEach(function (opt) {
        if (!opt.value || seen.has(opt.value)) return;
        seen.add(opt.value);
        options.push('<option value="' + CE.esc(opt.value) + '" label="' + CE.esc(opt.label || opt.value) + '"></option>');
      });
      if (!seen.has(openrouterDefaultModel)) {
        seen.add(openrouterDefaultModel);
        options.unshift('<option value="' + CE.esc(openrouterDefaultModel) + '" label="DeepSeek V4 Pro — default"></option>');
      }
      (d.models || []).forEach(function (m) {
        if (!m.id || seen.has(m.id)) return;
        seen.add(m.id);
        var label = m.name && m.name !== m.id ? m.name : "";
        options.push('<option value="' + CE.esc(m.id) + '" label="' + CE.esc(label) + '"></option>');
      });
      openrouterModels.innerHTML = options.join("");
      renderMajorModels(d.majors || [], d.scenario || null);
      setOpenrouterStatus("Loaded " + (d.models?.length || 0) + " current model ID(s) and " + (d.majors?.length || 0) + " major model price row(s).", "ok");
      openrouterModel?.focus();
    } catch (e) {
      setOpenrouterStatus("Could not load models: " + e, "error");
    } finally {
      btnLoadOrModels.disabled = false;
      btnLoadOrModels.textContent = "Load current model IDs & prices";
    }
  });

  btnTestOpenrouter && btnTestOpenrouter.addEventListener("click", async function () {
    var apiKey = CE.isHidden(openrouterKeyInput) ? "" : (openrouterKeyInput.value.trim() || "");
    setOpenrouterStatus(apiKey ? "Testing pasted OpenRouter key…" : "Testing saved OpenRouter key…");
    var d = await fetch("/settings/openrouter/test", {
      method: "POST",
      body: new URLSearchParams({ api_key: apiKey }),
    }).then(function (r) { return r.json(); });
    if (d.ok) {
      var label = d.label ? " (" + d.label + ")" : "";
      setOpenrouterStatus("OpenRouter key works" + label + ".", "ok");
    } else {
      setOpenrouterStatus("OpenRouter key failed: " + (d.error || "unknown error"), "error");
    }
  });

  openrouterForm && openrouterForm.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var apiKey = CE.isHidden(openrouterKeyInput) ? "" : (openrouterKeyInput.value.trim() || "");
    var model = openrouterModel ? openrouterModel.value.trim() : "";
    if (!apiKey && !model) return setOpenrouterStatus("Enter a key or model first.", "error");
    setOpenrouterStatus("Saving…");
    var r = await fetch("/settings/openrouter", {
      method: "POST",
      body: new URLSearchParams({ api_key: apiKey, model: model }),
    });
    var d = await r.json();
    if (!d.ok) {
      setOpenrouterStatus(d.error || "Could not save OpenRouter settings.", "error");
      return;
    }
    if (openrouterKeyInput) openrouterKeyInput.value = "";
    if (d.key_valid) {
      var label = d.key_label ? " (" + d.key_label + ")" : "";
      setOpenrouterStatus("Saved and validated OpenRouter key" + label + ".", "ok");
      setTimeout(function () { location.reload(); }, 900);
    } else {
      setOpenrouterStatus("Saved, but OpenRouter validation failed: " + (d.key_error || "unknown error"), "error");
    }
  });
})();
