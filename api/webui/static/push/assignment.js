(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = [
    "postForm",
    "showLog",
    "hideBanner",
    "moduleChoice",
    "pushContent",
    "setRubricStatus",
    "syncRubricControls",
  ].every(function (name) { return typeof push[name] === "function"; }) &&
    typeof window.localToISO === "function";

  var afRubricSel = document.getElementById("af-rubric");
  var afRubricMode = document.getElementById("af-rubric-mode");
  var afRubricLink = document.getElementById("af-rubric-link");
  var afAutoScore = document.getElementById("af-autoscore");
  var afAutoPush = document.getElementById("af-autoscore-push");
  var afAutoScoreHint = document.getElementById("af-autoscore-hint");
  var afScheduledGrading = document.getElementById("af-scheduled-grading");

  function requireReady() {
    if (ready) return true;
    alert("AssignmentForge push controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function getLog() {
    return document.getElementById("af-log");
  }

  function getBanner() {
    return document.getElementById("af-banner");
  }

  function syncAfAutoscoreControls() {
    if (!afAutoScore) return;
    var hasDue = !!document.getElementById("af-due")?.value;
    afAutoScore.disabled = !hasDue;
    if (!hasDue) afAutoScore.checked = false;
    var canAutoPush = hasDue && afAutoScore.checked;
    if (afAutoPush) {
      afAutoPush.disabled = !canAutoPush;
      if (!canAutoPush) afAutoPush.checked = false;
    }
    if (afScheduledGrading) {
      afScheduledGrading.classList.toggle("is-disabled", !hasDue);
    }
    if (afAutoScoreHint) {
      if (!hasDue) {
        afAutoScoreHint.textContent = "Requires a due date. Add one above to enable these per-assignment opt-ins.";
      } else if (afAutoScore.checked) {
        afAutoScoreHint.textContent = "Scheduled Auto-Score will create draft AI suggestions after the due date. Auto-post remains limited to eligible cases only.";
      } else {
        afAutoScoreHint.textContent = "Optional per-assignment controls. They are never enabled globally or by default.";
      }
    }
  }

  afRubricSel?.addEventListener("change", function () {
    if (!requireReady()) return;
    push.syncRubricControls();
  });
  document.getElementById("af-autoscore")?.addEventListener("change", syncAfAutoscoreControls);
  document.getElementById("af-due")?.addEventListener("change", syncAfAutoscoreControls);
  document.getElementById("af-due")?.addEventListener("input", syncAfAutoscoreControls);
  syncAfAutoscoreControls();

  document.getElementById("btn-af-validate")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("af-file")?.value;
    if (!path) return alert("Pick an AssignmentForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    log("Validating…\n");
    push.postForm("/api/af/validate", { path: path }).then(function (d) {
      // A failed request comes back as {ok:false, error} with no problems and
      // no summary, so without this the log would just stop at "Validating…".
      if (d.error) { log("ERROR: " + d.error); return; }
      if (d.problems?.length) d.problems.forEach(function (p) { log("✗ " + p); });
      var s = d.summary;
      if (s) {
        log((d.ok ? "✓ VALID" : "✗ INVALID") + " — " + s.type + ': "' + s.title + '" (' + s.points + " pts)");
        log("  submission: " + s.submission_types.join(", "));
        if (s.tiers.length) {
          s.tiers.forEach(function (t) {
            log("  tier " + t.label + ' → group "' + t.group + '"' +
              (t.scaffolded ? " (scaffolded)" : ""));
          });
        } else {
          log("  whole-class (no tiers)");
        }
        (s.placeholders || []).forEach(function (p) {
          log("  placeholder {{" + p + "}} — resolved per course at push");
        });
      }
    }).catch(function (e) { log("ERROR: " + e); });
  });

  document.getElementById("btn-af-copy-prompt")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var path = afRubricSel?.value;
    if (!path) return;
    push.setRubricStatus("Copying…", "");
    try {
      var resp = await fetch("/api/rf/scoring-prompt?path=" + encodeURIComponent(path));
      var text = await resp.text();
      if (!resp.ok) throw new Error(text || "Could not load prompt");
      await navigator.clipboard.writeText(text);
      push.setRubricStatus("Copied — paste into MagicSchool or Copilot", "ok");
    } catch (e) {
      push.setRubricStatus(String(e), "error");
    }
  });

  document.getElementById("btn-af-push")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("af-file")?.value;
    if (!path) return alert("Pick an AssignmentForge file.");
    var payload = {
      path: path,
      post_to_sis: document.getElementById("af-sis")?.checked,
      published: document.getElementById("af-publish")?.checked,
    };
    if (afRubricSel?.value) {
      payload.rubric_path = afRubricSel.value;
      payload.rubric_mode = afRubricMode?.value || "grading";
      payload.rubric_link_page = afRubricLink?.checked !== false;
    }
    if (afAutoScore?.checked) payload.autoscore_schedule = true;
    if (afAutoPush?.checked && !afAutoPush.disabled) payload.autoscore_auto_push = true;
    var due = window.localToISO(document.getElementById("af-due")?.value);
    var unlock = window.localToISO(document.getElementById("af-unlock")?.value);
    var lock = window.localToISO(document.getElementById("af-lock")?.value);
    if (due) payload.due_at = due;
    if (unlock) payload.unlock_at = unlock;
    if (lock) payload.lock_at = lock;
    var agSel = document.getElementById("af-aggroup");
    if (agSel?.value) payload.assignment_group_name = agSel.selectedOptions[0].text;
    var mod = push.moduleChoice("af-module");
    if (mod) payload.module_name = mod;
    push.pushContent("af", payload,
      getLog(), getBanner(), this,
      'Push AssignmentForge file "' + path.split(/[\\/]/).pop() + '"' +
      (payload.published ? " (PUBLISHED)" : " (unpublished)"));
  });
})();
