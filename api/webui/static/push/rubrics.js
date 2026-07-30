(function () {
  "use strict";

  var afRubricSel = document.getElementById("af-rubric");
  var afRubricControls = document.getElementById("af-rubric-controls");
  var afRubricMode = document.getElementById("af-rubric-mode");
  var afRubricLink = document.getElementById("af-rubric-link");
  var afRubricStatus = document.getElementById("af-rubric-status");
  var rfFileSel = document.getElementById("rf-file");

  function setRubricStatus(msg, kind) {
    if (!afRubricStatus) return;
    afRubricStatus.textContent = msg || "";
    afRubricStatus.className = kind ? "hint " + kind : "hint";
  }

  function syncRubricControls() {
    var hasRubric = !!afRubricSel?.value;
    if (afRubricControls) afRubricControls.hidden = !hasRubric;
    if (hasRubric) {
      if (afRubricMode && !afRubricMode.value) afRubricMode.value = "grading";
      if (afRubricLink && afRubricLink.checked == null) afRubricLink.checked = true;
    }
  }

  async function loadRubricFiles() {
    if (!afRubricSel && !rfFileSel) return;
    try {
      var data = await fetch("/api/rf/files").then(function (r) { return r.json(); });
      var files = data.files || [];
      if (afRubricSel) {
        var current = afRubricSel.value;
        afRubricSel.innerHTML = '<option value="">No rubric</option>';
        files.forEach(function (f) { afRubricSel.appendChild(new Option(f.label, f.path)); });
        if (current) afRubricSel.value = current;
      }
      if (rfFileSel) {
        var currentRf = rfFileSel.value;
        rfFileSel.innerHTML = '<option value="">— select —</option>';
        files.forEach(function (f) { rfFileSel.appendChild(new Option(f.label, f.path)); });
        if (currentRf) rfFileSel.value = currentRf;
      }
      syncRubricControls();
    } catch (e) {
      setRubricStatus("Could not load rubric files", "error");
    }
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    setRubricStatus: setRubricStatus,
    syncRubricControls: syncRubricControls,
    loadRubricFiles: loadRubricFiles,
  });
})();
