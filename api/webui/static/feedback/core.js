(function () {
  "use strict";

  var CE = window.CE_FEEDBACK = window.CE_FEEDBACK || {};
  var state = CE.state = CE.state || {};

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function readJsonScript(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent || "null");
    } catch (e) {
      return fallback;
    }
  }

  function bootstrap() {
    if (state._bootstrapped) return;
    state._bootstrapped = true;
    state.folders = readJsonScript("feedback-folders", {}) || {};
    state.status = null;
    state.statusPromise = null;
    state.rubrics = [];
    state.bundles = [];
  }

  function openPath(url, path) {
    if (!path) return false;
    fetch(url, {
      method: "POST",
      body: new URLSearchParams({ path: path }),
    });
    return true;
  }

  function openFolder(key) {
    bootstrap();
    return openPath("/api/open-folder", state.folders && state.folders[key]);
  }

  function openBundle(name) {
    bootstrap();
    var folder = state.folders && state.folders.forllm;
    return openPath("/api/open-file", folder ? (folder + "\\" + name) : "");
  }

  function runStep(url, btn, statusEl, logEl, after) {
    if (btn) btn.disabled = true;
    if (statusEl) statusEl.textContent = "Working…";
    if (logEl) logEl.hidden = true;
    return fetch(url, { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (logEl && d && d.log && d.log.length) {
          logEl.textContent = d.log.join("\n");
          logEl.hidden = false;
        }
        if (statusEl) {
          statusEl.textContent = d && d.ok ? "Done." : ("Error: " + ((d && d.error) || "failed"));
        }
        if (after) after(d);
        return d;
      })
      .catch(function (e) {
        if (statusEl) statusEl.textContent = "Error: " + e;
        return null;
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function loadRubricOptions(list) {
    return '<option value="">— none —</option>' + list.map(function (r) {
      return '<option value="' + esc(r) + '">' + esc(r) + "</option>";
    }).join("");
  }

  function updateStatusWidgets(d) {
    var rubrics = (d && d.rubrics) || [];
    state.status = d || null;
    state.rubrics = rubrics;
    state.bundles = (d && d.bundles) || [];

    var gfRubric = document.getElementById("gf-rubric");
    if (gfRubric) gfRubric.innerHTML = loadRubricOptions(rubrics);

    var orRubric = document.getElementById("or-rubric");
    if (orRubric) orRubric.innerHTML = loadRubricOptions(rubrics);

    var keyState = document.getElementById("or-key-state");
    if (keyState) keyState.textContent = d && d.has_key ? "✓ saved" : "— not set";

    var modelInp = document.getElementById("or-model");
    if (modelInp && d && d.model && !modelInp.value) modelInp.value = d.model;
  }

  function loadStatus() {
    bootstrap();
    if (state.statusPromise) return state.statusPromise;
    state.statusPromise = fetch("/api/feedback/status")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        updateStatusWidgets(d || {});
        return d;
      })
      .catch(function () {
        return null;
      })
      .finally(function () {
        state.statusPromise = null;
      });
    return state.statusPromise;
  }

  bootstrap();

  CE.esc = CE.esc || esc;
  CE.bootstrap = CE.bootstrap || bootstrap;
  CE.openPath = CE.openPath || openPath;
  CE.openFolder = CE.openFolder || openFolder;
  CE.openBundle = CE.openBundle || openBundle;
  CE.runStep = CE.runStep || runStep;
  CE.loadStatus = CE.loadStatus || loadStatus;
})();
