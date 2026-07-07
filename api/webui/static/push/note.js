(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = [
    "postForm",
    "showLog",
    "hideBanner",
    "moduleChoice",
    "pushContent",
    "generatePhysical",
  ].every(function (name) { return typeof push[name] === "function"; }) &&
    typeof window.localToISO === "function";

  function requireReady() {
    if (ready) return true;
    alert("NoteForge push controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function getLog() {
    return document.getElementById("nf-log");
  }

  function getBanner() {
    return document.getElementById("nf-banner");
  }

  function fileStem(path) {
    var name = String(path || "").split(/[\\/]/).pop() || "";
    return name.replace(/\.[^.]+$/, "").replace(/_/g, " ");
  }

  function syncNoteAttachControls() {
    var printable = window.CE_LAST_NOTE_PRINTABLE || {};
    var pdfPath = printable.pdf_path || document.getElementById("nf-pdf-path")?.value || "";
    var pdfInput = document.getElementById("nf-pdf-path");
    var titleInput = document.getElementById("nf-attach-title");
    var attachBtn = document.getElementById("btn-nf-attach");
    if (pdfInput) pdfInput.value = pdfPath;
    if (titleInput && !titleInput.value && pdfPath) {
      titleInput.value = printable.title || window.CE_LAST_NOTE_TITLE || fileStem(pdfPath);
    }
    if (attachBtn) attachBtn.disabled = !pdfPath;
  }

  document.getElementById("btn-nf-validate")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("nf-file")?.value;
    if (!path) return alert("Pick a NoteForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    log("Validating...\n");
    push.postForm("/api/nf/validate", { path: path }).then(function (d) {
      (d.problems || []).forEach(function (p) { log("✗ " + p); });
      if (d.error) log("ERROR: " + d.error);
      var s = d.summary;
      if (s) {
        window.CE_LAST_NOTE_TITLE = s.title || "";
        log((d.ok ? "✓ VALID" : "✗ INVALID") + " - " + s.type + ': "' + s.title + '"');
        log("  mode: " + s.mode);
        log("  blanks: " + s.slot_count);
      }
    }).catch(function (e) { log("ERROR: " + e); });
  });

  document.getElementById("btn-nf-generate")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var path = document.getElementById("nf-file")?.value;
    if (!path) return alert("Pick a NoteForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    this.disabled = true;
    try {
      await push.generatePhysical(path, log, getBanner(), "note");
      if (window.CE_LAST_NOTE_PRINTABLE) {
        window.CE_LAST_NOTE_PRINTABLE.title =
          window.CE_LAST_NOTE_PRINTABLE.title || window.CE_LAST_NOTE_TITLE || "";
      }
      syncNoteAttachControls();
    } finally {
      this.disabled = false;
    }
  });

  document.getElementById("btn-nf-attach")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var pdfPath = document.getElementById("nf-pdf-path")?.value ||
      window.CE_LAST_NOTE_PRINTABLE?.pdf_path || "";
    if (!pdfPath) return alert("Generate printable notes first.");

    var title = document.getElementById("nf-attach-title")?.value.trim() ||
      window.CE_LAST_NOTE_PRINTABLE?.title || fileStem(pdfPath) || "Printable notes";
    var payload = {
      pdf_path: pdfPath,
      name: title,
      description: document.getElementById("nf-description")?.value.trim() || "",
      points: parseFloat(document.getElementById("nf-points")?.value || "0") || 0,
      published: document.getElementById("nf-publish")?.checked,
    };
    var due = window.localToISO(document.getElementById("nf-due")?.value);
    var unlock = window.localToISO(document.getElementById("nf-unlock")?.value);
    var lock = window.localToISO(document.getElementById("nf-lock")?.value);
    if (due) payload.due_at = due;
    if (unlock) payload.unlock_at = unlock;
    if (lock) payload.lock_at = lock;
    var agSel = document.getElementById("nf-aggroup");
    if (agSel?.value) payload.assignment_group_name = agSel.selectedOptions[0].text;
    var mod = push.moduleChoice("nf-module");
    if (mod) payload.module_name = mod;

    push.pushContent("printable", payload,
      document.getElementById("nf-log"), document.getElementById("nf-banner"), this,
      `Attach printable PDF "${pdfPath.split(/[\\/]/).pop()}" as assignment "${title}"`);
  });

  syncNoteAttachControls();
})();
