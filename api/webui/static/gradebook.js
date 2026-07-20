(function () {
  "use strict";

  // ── Course selector helpers ────────────────────────────────────────────

  function gbCourseId() {
    return document.getElementById("gb-course-sel")?.value || "";
  }

  function gbCourseName() {
    const sel = document.getElementById("gb-course-sel");
    if (!sel || !sel.value) return "";
    return sel.selectedOptions[0]?.dataset.name || sel.selectedOptions[0]?.text || "";
  }

  function gbTargets() {
    const id = gbCourseId();
    if (!id) return [];
    return [{ id, name: gbCourseName() }];
  }

  // ── Auto-load tracking ─────────────────────────────────────────────────
  // Tracks which course was last loaded per tab so we don't double-fetch.
  const _loadedFor = {};

  function _markLoaded(tab) { _loadedFor[tab] = gbCourseId(); }
  function _needsLoad(tab)  { return _loadedFor[tab] !== gbCourseId(); }

  // ── Common helpers ─────────────────────────────────────────────────────

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",
                                   '"':"&quot;","'":"&#39;"}[c]));
  }

  function showLog(el) {
    el.hidden = false;
    el.textContent = "";
    return (line) => { el.textContent += line + "\n"; el.scrollTop = el.scrollHeight; };
  }

  function hideBanner(el) {
    if (el) { el.hidden = true; el.className = "push-banner"; el.innerHTML = ""; }
  }

  function showBanner(el, kind, html) {
    if (!el) return;
    el.hidden = false;
    el.className = "push-banner " + kind;
    el.innerHTML = html;
  }

  async function postForm(url, fields) {
    return fetch(url, { method: "POST", body: new URLSearchParams(fields) })
      .then(r => r.json());
  }

  function _renderBanner(el, results, exitOk) {
    if (!el) return;
    if (!results.length && !exitOk) {
      showBanner(el, "fail", "✗ Failed — check the log above.");
      return;
    }
    if (!results.length) return;
    const allOk = results.every(r => r.ok);
    const kind  = allOk && exitOk ? "ok" : "warn";
    const lines = results.map(r => {
      const link = r.url
        ? ` — <a href="${esc(r.url)}" target="_blank" rel="noopener">Open in Canvas ↗</a>`
        : "";
      return `${r.ok ? "✓" : "⚠"} <strong>${esc(r.title)}</strong>${link}`;
    }).join("<br>");
    showBanner(el, kind, lines);
  }

  function _clearStatus(id) {
    const el = document.getElementById(id);
    if (el) { el.className = "status hint"; el.textContent = ""; }
  }

  function _clearLoaded(tab) { delete _loadedFor[tab]; }

  // ── Shared state for feature files ─────────────────────────────────────

  function syncGradebookReadiness() {
    var hasCourse = !!gbCourseId();
    var courseName = gbCourseName();
    var msg = document.getElementById("gb-readiness-msg");
    var policyBtn = document.getElementById("btn-apply-policy");
    var sweepBtn = document.getElementById("btn-sweep-preview");
    var sweepApply = document.getElementById("btn-sweep-apply");

    if (!hasCourse) {
      if (policyBtn) policyBtn.disabled = true;
      if (sweepBtn) sweepBtn.disabled = true;
      if (sweepApply) { sweepApply.hidden = true; sweepApply.disabled = true; }
      if (msg) {
        msg.hidden = false;
        msg.innerHTML = '<p class="hint" style="margin:0">No course selected. Gradebook changes are unavailable.</p>';
      }
    } else {
      if (policyBtn) policyBtn.disabled = false;
      if (sweepBtn) sweepBtn.disabled = false;
      if (msg) {
        msg.hidden = false;
        msg.innerHTML = '<strong>Working in:</strong> ' + esc(courseName) + '. Changes on this page affect this course only.';
      }
    }
  }

  var sweepEntries = [];
  var curveResults = [];

  function collectHolidays() {
    return (document.getElementById("sw-holidays")?.value || "")
      .split(/[\n,]/).map(s => s.trim())
      .filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
  }

  // ── Shared namespace for feature files ────────────────────────────────

  window.CE_GRADEBOOK = {
    gbCourseId:    gbCourseId,
    gbCourseName:  gbCourseName,
    gbTargets:     gbTargets,
    _markLoaded:   _markLoaded,
    _needsLoad:    _needsLoad,
    _clearLoaded:  _clearLoaded,
    _renderBanner: _renderBanner,
    _clearStatus:  _clearStatus,
    esc:           esc,
    showLog:       showLog,
    hideBanner:    hideBanner,
    showBanner:    showBanner,
    canvasWriteReview: window.CE_WRITE_REVIEW.confirm,
    postForm:      postForm,
    collectHolidays: collectHolidays,
    // Mutable state for feature files
    get sweepEntries() { return sweepEntries; },
    set sweepEntries(v) { sweepEntries = v; },
    get curveResults() { return curveResults; },
    set curveResults(v) { curveResults = v; },
    syncReadiness: syncGradebookReadiness,
  };

  // ── Sweep date-range presets ───────────────────────────────────────────

  function _applySweepPreset(preset, gpStart, gpEnd) {
    const fromEl = document.getElementById("sw-from");
    const toEl   = document.getElementById("sw-to");
    if (!fromEl || !toEl) return;
    const now = new Date();
    switch (preset) {
      case "month": {
        const y = now.getFullYear(), m = now.getMonth();
        fromEl.value = `${y}-${String(m + 1).padStart(2, "0")}-01`;
        toEl.value   = now.toISOString().slice(0, 10);
        break;
      }
      case "30d": {
        const d = new Date(now); d.setDate(d.getDate() - 30);
        fromEl.value = d.toISOString().slice(0, 10);
        toEl.value   = now.toISOString().slice(0, 10);
        break;
      }
      case "year": {
        const yr = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1;
        fromEl.value = `${yr}-08-01`;
        toEl.value   = `${yr + 1}-06-01`;
        break;
      }
      default: // gp-N
        if (gpStart && gpEnd) { fromEl.value = gpStart; toEl.value = gpEnd; }
    }
  }

  function _buildPeriodChips() {
    const chips = document.getElementById("sw-period-chips");
    if (!chips) return;
    chips.innerHTML = "";

    // Grading period chips first (prepend)
    const gps      = window.GB_GRADING_PERIODS || [];
    const years    = new Set(gps.map(gp => gp.year).filter(Boolean));
    const multiYr  = years.size > 1;
    gps.forEach((gp, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip sw-preset-chip";
      btn.dataset.preset = `gp-${i}`;
      btn.dataset.start  = gp.start;
      btn.dataset.end    = gp.end;
      // Use code if present (e.g. "T1"), otherwise abbreviate verbose names
      const label = gp.code
        ? gp.code
        : gp.name
            .replace(" Grading Period", " GP")
            .replace(/ \/ Report Card \d+/, "");
      btn.textContent = (multiYr && gp.year) ? `${label} (${gp.year})` : label;
      chips.appendChild(btn);
    });

    // Generic presets
    [{ label: "This month", preset: "month" },
     { label: "Last 30d",   preset: "30d"   },
     { label: "School year", preset: "year" }].forEach(p => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip sw-preset-chip";
      btn.dataset.preset = p.preset;
      btn.textContent    = p.label;
      chips.appendChild(btn);
    });

    chips.addEventListener("click", e => {
      const btn = e.target.closest(".sw-preset-chip");
      if (!btn) return;
      _applySweepPreset(btn.dataset.preset, btn.dataset.start, btn.dataset.end);
      chips.querySelectorAll(".sw-preset-chip").forEach(b =>
        b.classList.toggle("chip-active", b === btn));
    });
  }

  function _initSweepDateRange() {
    // Default: last 30 days (grading-period chips remain one click away).
    _applySweepPreset("30d");
    const c30 = document.querySelector('[data-preset="30d"]');
    if (c30) c30.classList.add("chip-active");
  }

  // ── Tab switching ──────────────────────────────────────────────────────

  function _gradebookTabs() {
    return [...document.querySelectorAll(".gb-tab[role='tab']")];
  }

  function _activateGradebookTab(tabName, options) {
    const tab = _gradebookTabs().find(t => t.dataset.tab === tabName);
    if (!tab) return false;
    document.querySelectorAll(".gb-tab").forEach(t => {
      const isActive = t === tab;
      t.classList.toggle("active", isActive);
      t.setAttribute("aria-selected", isActive ? "true" : "false");
      t.tabIndex = isActive ? 0 : -1;
    });
    document.querySelectorAll(".gb-panel").forEach(p => {
      const isActive = p.id === "gb-tab-" + tabName;
      p.classList.toggle("active", isActive);
      p.hidden = !isActive;
      p.inert = !isActive;
    });
    if (options?.focus) tab.focus();
    _autoloadTab(tabName);
    return true;
  }

  _gradebookTabs().forEach(tab => {
    tab.addEventListener("click", function () {
      _activateGradebookTab(this.dataset.tab);
    });
    tab.addEventListener("keydown", function (event) {
      const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const tabs = _gradebookTabs();
      const currentIndex = tabs.indexOf(tab);
      let nextIndex = currentIndex;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (currentIndex + 1) % tabs.length;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      _activateGradebookTab(tabs[nextIndex].dataset.tab, { focus: true });
    });
  });

  (function () {
    const params = new URLSearchParams(location.search);
    const tab = params.get("tab") || location.hash.replace("#", "");
    if (tab) _activateGradebookTab(tab);
  })();

  function _autoloadTab(tab) {
    if (!gbCourseId()) return;
    if (!_needsLoad(tab)) return;
    switch (tab) {
      case "policy":     window.CE_GRADEBOOK.loadPolicy();     break;
      case "extra-time": window.CE_GRADEBOOK.loadRoster();     break;
      case "extensions": window.CE_GRADEBOOK.loadExtensions(); break;
      case "curves":     window.CE_GRADEBOOK.loadCurveAssignments(); break;
    }
  }

  // ── Course change: reset + auto-load active tab ────────────────────────

  document.getElementById("gb-course-sel")?.addEventListener("change", () => {
    Object.keys(_loadedFor).forEach(k => delete _loadedFor[k]);
    _resetGradebookState();
    const active = document.querySelector(".gb-tab.active")?.dataset.tab;
    if (active) _autoloadTab(active);
  });

  function _resetGradebookState() {
    syncGradebookReadiness();
    // Snapshot
    const sum = document.getElementById("gb-summary");
    const tbl = document.getElementById("gb-tables");
    const btn = document.getElementById("btn-load-gradebook");
    const lnk = document.getElementById("gb-canvas-link");
    if (sum) sum.hidden = true;
    if (tbl) tbl.hidden = true;
    if (btn) btn.textContent = "Load gradebook…";
    if (lnk) lnk.hidden = true;
    _clearStatus("gb-status");
    // Late policy
    _clearStatus("lp-status");
    hideBanner(document.getElementById("lp-banner"));
    // Extra-time
    const xl = document.getElementById("xt-list");
    if (xl) xl.innerHTML = '<p class="hint" style="margin:0; padding:10px 0">Loading…</p>';
    _clearStatus("xt-status");
    const sb = document.getElementById("btn-save-roster");
    if (sb) sb.hidden = true;
    // Extensions
    const es = document.getElementById("ext-students");
    if (es) es.innerHTML = "";
    const ea = document.getElementById("ext-assignment");
    if (ea) { ea.innerHTML = '<option value="">— loading —</option>'; ea.disabled = true; }
    const eh = document.getElementById("ext-hint");
    if (eh) eh.textContent = "(loading…)";
    const eb = document.getElementById("btn-ext-apply");
    if (eb) eb.hidden = true;
    _clearStatus("ext-status");
    hideBanner(document.getElementById("ext-banner"));
    // Sweep
    sweepEntries = [];
    const sw = document.getElementById("sw-table-wrap");
    if (sw) sw.hidden = true;
    const swl = document.getElementById("sw-log");
    if (swl) swl.hidden = true;
    _clearStatus("sw-status");
    hideBanner(document.getElementById("sw-banner"));
    const sab = document.getElementById("btn-sweep-apply");
    if (sab) sab.hidden = true;
    // Curves
    curveResults = [];
    const cvw = document.getElementById("cv-preview-wrap");
    if (cvw) cvw.hidden = true;
    const cvl = document.getElementById("cv-log");
    if (cvl) cvl.hidden = true;
    _clearStatus("cv-status");
    hideBanner(document.getElementById("cv-banner"));
    const cvb = document.getElementById("btn-curve-apply");
    if (cvb) cvb.hidden = true;
    const cva = document.getElementById("cv-assignment");
    if (cva) { cva.innerHTML = '<option value="">— loading —</option>'; cva.disabled = true; }
    const cvh = document.getElementById("cv-assign-hint");
    if (cvh) cvh.textContent = "(loading…)";
    syncGradebookReadiness();
  }

  // ── Init ───────────────────────────────────────────────────────────────

  _buildPeriodChips();
  _initSweepDateRange();

  // Auto-load the first course if one is already selected (e.g. saved_courses populated)
  if (gbCourseId()) {
    const active = document.querySelector(".gb-tab.active")?.dataset.tab;
    if (active) _autoloadTab(active);
  }
  syncGradebookReadiness();

})();
