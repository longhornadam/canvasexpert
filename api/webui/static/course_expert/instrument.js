(function () {
  "use strict";

  /* Instrument view: expanded creation preview and delivery comparison.
     Developer view, reached with Ctrl+Shift+I. No button on the page.
     Depends on CE_COURSE_EXPERT being initialized by tabs.js. */

  var expert = window.CE_COURSE_EXPERT;
  if (!expert || !expert.activateTab) return;

  /* ── Update toggle label on view change ────────────────────────────── */
  function updateToggleLabel() {
    var toggle = document.getElementById("ce-instrument-toggle");
    if (!toggle) return;
    var view = expert.currentView ? expert.currentView() : "workbench";
    toggle.textContent = view === "instrument"
      ? "◀ Workbench view"
      : "🔍 Instrument view";
  }

  /* ── Keyboard shortcut: Ctrl+Shift+I ───────────────────────────────── */
  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey && event.shiftKey && event.key === "I") {
      event.preventDefault();
      if (expert.toggleInstrument) expert.toggleInstrument();
    }
  });

  /* ── Observe view changes ──────────────────────────────────────────── */
  var origSetView = expert.setView;
  if (origSetView) {
    expert.setView = function (view, options) {
      origSetView(view, options);
      updateToggleLabel();
    };
  }

  /* ── Init ──────────────────────────────────────────────────────────── */
  // No on-page toggle: this view is for development, reached with Ctrl+Shift+I.
  updateToggleLabel();
})();
