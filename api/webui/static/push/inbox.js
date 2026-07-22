(function () {
  "use strict";

  // Slice D of author-and-stage: shows assistant-staged Inbox drafts (Slice C's
  // marker-gated per-kind folders) as a distinct "pending review" section on
  // each push tab. Fetches /api/inbox-files?kind=<kind> (pre-validated by the
  // same validators the existing /api/validate, /api/af/validate, /api/pf/validate,
  // /api/rf/validate routes use), then "Use this draft" hands a valid draft's
  // path to the matching <select>'s existing file_sources.js seam
  // (wrapper.ceFileSource.setTempOption/setMode) so the teacher runs the
  // existing Validate / Push controls unchanged.

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderList(listEl, files) {
    if (!files.length) {
      listEl.innerHTML = '<p class="hint inbox-pending-empty">No drafts staged.</p>';
      return;
    }
    listEl.innerHTML = files.map(function (f) {
      var status = f.ok
        ? '<span class="inbox-pending-status ok">Valid</span>'
        : '<span class="inbox-pending-status err">Needs fixes</span>';
      var problems = (!f.ok && f.problems && f.problems.length)
        ? '<ul class="inbox-pending-problems">' +
          f.problems.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") +
          "</ul>"
        : "";
      var action = f.ok
        ? '<button type="button" class="small inbox-pending-use" data-path="' +
          esc(f.path) + '" data-label="' + esc(f.label) + '">Use this draft</button>'
        : "";
      return '<div class="inbox-pending-row">' +
        '<div class="inbox-pending-label">' + esc(f.label) + " " + status + "</div>" +
        problems + action +
        "</div>";
    }).join("");
  }

  function initInboxSection(root) {
    if (!root || root.dataset.inboxBound === "1") return;
    root.dataset.inboxBound = "1";

    var kind = root.dataset.inboxKind;
    var selectId = root.dataset.inboxSelect;
    var listEl = root.querySelector(".inbox-pending-list");
    var refreshBtn = root.querySelector(".inbox-pending-refresh");
    if (!kind || !listEl) return;

    function load() {
      listEl.innerHTML = '<p class="hint">Loading…</p>';
      fetch("/api/inbox-files?kind=" + encodeURIComponent(kind))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            listEl.innerHTML = '<p class="hint err">' + esc(d.error || "Could not load drafts.") + "</p>";
            return;
          }
          renderList(listEl, d.files || []);
        })
        .catch(function () {
          listEl.innerHTML = '<p class="hint err">Could not load drafts.</p>';
        });
    }

    if (refreshBtn) refreshBtn.addEventListener("click", load);

    listEl.addEventListener("click", function (event) {
      var btn = event.target.closest(".inbox-pending-use");
      if (!btn) return;
      var sel = selectId && document.getElementById(selectId);
      var wrapper = sel && sel.closest(".file-source");
      if (!wrapper || !wrapper.ceFileSource) return;
      wrapper.ceFileSource.setTempOption(btn.dataset.path, "Assistant draft: " + btn.dataset.label);
      wrapper.ceFileSource.setMode("select");
    });

    load();
  }

  function bindInboxSections() {
    document.querySelectorAll("[data-inbox-kind]").forEach(initInboxSection);
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    initInboxSection: initInboxSection,
    bindInboxSections: bindInboxSections,
  });
})();
