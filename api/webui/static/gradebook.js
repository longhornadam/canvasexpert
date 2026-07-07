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
    postForm:      postForm,
    collectHolidays: collectHolidays,
    // Mutable state for feature files
    get sweepEntries() { return sweepEntries; },
    set sweepEntries(v) { sweepEntries = v; },
    get curveResults() { return curveResults; },
    set curveResults(v) { curveResults = v; },
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

  function _activateGradebookTab(tabName) {
    const tab = [...document.querySelectorAll(".gb-tab")].find(t => t.dataset.tab === tabName);
    if (!tab) return false;
    document.querySelectorAll(".gb-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".gb-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    const panel = document.getElementById("gb-tab-" + tabName);
    if (panel) panel.classList.add("active");
    _autoloadTab(tabName);
    return true;
  }

  document.querySelectorAll(".gb-tab").forEach(tab => {
    tab.addEventListener("click", function () {
      _activateGradebookTab(this.dataset.tab);
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

  // ── Course picker: all courses auto-load, bookmarked pinned on top ─────

  (async function loadAllCoursesIntoPicker() {
    const sel = document.getElementById("gb-course-sel");
    if (!sel) return;
    const bookmarked = [...sel.options].filter(o => o.value).map(o => ({
      id: o.value, name: o.dataset.name || o.text, nick: o.text,
    }));
    try {
      const d = await fetch("/api/courses").then(r => r.json());
      if (!d.ok || !d.courses?.length) return;   // offline/no token → keep bookmarks
      const cur = sel.value;
      const bmIds = new Set(bookmarked.map(b => b.id));
      sel.innerHTML = '<option value="">— pick a course —</option>';
      if (bookmarked.length) {
        const og = document.createElement("optgroup");
        og.label = "★ Bookmarked";
        bookmarked.forEach(b => {
          const o = new Option(b.nick, b.id);
          o.dataset.name = b.name;
          og.appendChild(o);
        });
        sel.appendChild(og);
      }
      const rest = d.courses.filter(c => !bmIds.has(c.id));
      if (rest.length) {
        const og = document.createElement("optgroup");
        og.label = "All courses";
        rest.forEach(c => {
          const o = new Option(c.name, c.id);
          o.dataset.name = c.name;
          og.appendChild(o);
        });
        sel.appendChild(og);
      }
      if (cur) sel.value = cur;
    } catch (e) { /* keep server-rendered bookmarks */ }
  })();

  // ── Course change: reset + auto-load active tab ────────────────────────

  document.getElementById("gb-course-sel")?.addEventListener("change", () => {
    Object.keys(_loadedFor).forEach(k => delete _loadedFor[k]);
    _resetGradebookState();
    const active = document.querySelector(".gb-tab.active")?.dataset.tab;
    if (active) _autoloadTab(active);
  });

  function _resetGradebookState() {
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
  }

  // ── Init ───────────────────────────────────────────────────────────────

  _buildPeriodChips();
  _initSweepDateRange();

  // Auto-load the first course if one is already selected (e.g. saved_courses populated)
  if (gbCourseId()) {
    const active = document.querySelector(".gb-tab.active")?.dataset.tab;
    if (active) _autoloadTab(active);
  }

})();
