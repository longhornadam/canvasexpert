(function () {
  "use strict";

  var roster = window.CE_ROSTER;
  if (!roster || typeof roster.toast !== "function" || typeof roster.getCurrentCourseId !== "function" || typeof roster.onCourseLoaded !== "function" || typeof roster.hasLoadedCourse !== "function") {
    window.alert("Roster tools need a page refresh.");
    return;
  }

  var protectedPacksEl = document.getElementById("roster-protected-packs");
  var customProtectedInput = document.getElementById("roster-custom-protected");
  var saveProtectedBtn = document.getElementById("roster-save-protected");
  var scrubText = document.getElementById("roster-scrub-text");
  var scrubRun = document.getElementById("roster-scrub-run");
  var scrubResult = document.getElementById("roster-scrub-result");
  var exportWhoBtn = document.getElementById("roster-export-who");
  var backupVaultBtn = document.getElementById("roster-backup-vault");

  if (!protectedPacksEl || !customProtectedInput || !saveProtectedBtn || !scrubText || !scrubRun || !scrubResult || !exportWhoBtn || !backupVaultBtn) {
    return;
  }

  function renderProtectedPacks(data) {
    protectedPacksEl.innerHTML = "";
    var packs = data.packs || [];
    for (var i = 0; i < packs.length; i++) {
      var label = document.createElement("label");
      label.className = "roster-protected-pack";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = packs[i].enabled;
      cb.dataset.packId = packs[i].id;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + packs[i].title));
      protectedPacksEl.appendChild(label);
    }
  }

  function loadProtected() {
    fetch("/api/names/protected")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderProtectedPacks(data);
        customProtectedInput.value = (data.custom || []).join(", ");
      })
      .catch(function () {});
  }

  function runScrub() {
    var txt = scrubText.value;
    if (!txt) {
      scrubResult.hidden = true;
      return;
    }
    var body = new URLSearchParams();
    body.append("text", txt);
    body.append("course_id", roster.getCurrentCourseId());

    fetch("/api/names/scrub-test", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          scrubResult.textContent = data.scrubbed;
          scrubResult.hidden = false;
        } else {
          scrubResult.textContent = data.error || "Scrub test failed.";
          scrubResult.hidden = false;
        }
      })
      .catch(function (e) { roster.toast("Error: " + e.message, true); });
  }

  function saveProtectedNames() {
    var packStates = {};
    var cbs = protectedPacksEl.querySelectorAll("input[type=checkbox]");
    for (var i = 0; i < cbs.length; i++) {
      packStates[cbs[i].dataset.packId] = cbs[i].checked;
    }
    var custom = customProtectedInput.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);

    var body = new URLSearchParams();
    body.append("data", JSON.stringify({ packs: packStates, custom: custom }));

    fetch("/api/names/protected", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          roster.toast("Protected names saved.", false);
          loadProtected();
        } else {
          roster.toast(data.error || "Save failed.", true);
        }
      })
      .catch(function (e) { roster.toast("Error: " + e.message, true); });
  }

  function exportWhoIsWho() {
    if (!roster.getCurrentCourseId()) {
      return;
    }
    var body = new URLSearchParams();
    body.append("course_id", roster.getCurrentCourseId());

    fetch("/api/names/who-is-who", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          roster.toast("Exported to " + data.path, false);
        } else {
          roster.toast(data.error || "Export failed.", true);
        }
      })
      .catch(function (e) { roster.toast("Error: " + e.message, true); });
  }

  function backupVault() {
    fetch("/api/names/backup-vault", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          roster.toast("Backed up (" + data.entries + " entries).", false);
        } else {
          roster.toast(data.error || "Backup failed.", true);
        }
      })
      .catch(function (e) { roster.toast("Error: " + e.message, true); });
  }

  function rerunScrubIfNeeded() {
    if (scrubText.value) {
      runScrub();
    }
  }

  saveProtectedBtn.addEventListener("click", saveProtectedNames);
  scrubRun.addEventListener("click", runScrub);
  exportWhoBtn.addEventListener("click", exportWhoIsWho);
  backupVaultBtn.addEventListener("click", backupVault);

  roster.onCourseLoaded(rerunScrubIfNeeded);
  loadProtected();
  if (roster.hasLoadedCourse()) {
    rerunScrubIfNeeded();
  }
})();
