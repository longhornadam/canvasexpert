(function () {
  "use strict";

  /* Instrument view — expanded creation preview/delivery comparison.
     Depends on CE_COURSE_EXPERT being initialized by tabs.js. */

  var expert = window.CE_COURSE_EXPERT;
  if (!expert || !expert.activateTab) return;

  /* ── Instrument toggle button ──────────────────────────────────────── */
  function addInstrumentToggle() {
    var center = document.querySelector('[data-ce-hook="course-shell"]');
    if (!center) return;
    var existing = document.getElementById("ce-instrument-toggle");
    if (existing) return;

    var toggle = document.createElement("button");
    toggle.id = "ce-instrument-toggle";
    toggle.type = "button";
    toggle.className = "ce-instrument-toggle";
    toggle.setAttribute("data-instrument-toggle", "");
    toggle.textContent = "🔍 Instrument view";
    toggle.title = "Toggle expanded Instrument view";
    center.insertBefore(toggle, center.firstChild);
  }

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
  addInstrumentToggle();
  updateToggleLabel();
})();
