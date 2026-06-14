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

  document.querySelectorAll(".gb-tab").forEach(tab => {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".gb-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".gb-panel").forEach(p => p.classList.remove("active"));
      this.classList.add("active");
      const panel = document.getElementById("gb-tab-" + this.dataset.tab);
      if (panel) panel.classList.add("active");
      _autoloadTab(this.dataset.tab);
    });
  });

  function _autoloadTab(tab) {
    if (!gbCourseId()) return;
    if (!_needsLoad(tab)) return;
    switch (tab) {
      case "policy":     _loadPolicy();     break;
      case "extra-time": _loadRoster();     break;
      case "extensions": _loadExtensions(); break;
      case "curves":     _loadCurveAssignments(); break;
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

  // ── State ──────────────────────────────────────────────────────────────

  let sweepEntries = [];
  let curveResults = [];

  // ── Late policy (auto-loaded) ──────────────────────────────────────────

  async function _loadPolicy() {
    const id = gbCourseId();
    if (!id) return;
    _markLoaded("policy");
    const st = document.getElementById("lp-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading current policy…"; }
    try {
      const d = await fetch(`/api/late-policy?course_id=${encodeURIComponent(id)}`).then(r => r.json());
      if (!d.ok) {
        if (st) { st.className = "status error"; st.textContent = "Could not load policy: " + d.error; }
        return;
      }
      if (!d.policy) {
        if (st) st.textContent = `${gbCourseName()} has no late policy yet — configure one below.`;
        return;
      }
      const p = d.policy;
      document.getElementById("lp-late-enabled").checked     = !!p.late_submission_deduction_enabled;
      document.getElementById("lp-deduction").value          = p.late_submission_deduction ?? 10;
      document.getElementById("lp-interval").value           = p.late_submission_interval || "day";
      document.getElementById("lp-floor").value              = p.late_submission_minimum_percent ?? 50;
      document.getElementById("lp-missing-enabled").checked  = !!p.missing_submission_deduction_enabled;
      document.getElementById("lp-missing-pct").value        =
        p.missing_submission_deduction != null ? 100 - p.missing_submission_deduction : 0;
      if (st) { st.className = "status ok"; st.textContent = `✓ Loaded current policy for ${gbCourseName()}`; }
    } catch (e) {
      if (st) { st.className = "status error"; st.textContent = String(e); }
    }
  }

  document.getElementById("btn-apply-policy")?.addEventListener("click", async function () {
    const targets = gbTargets();
    if (!targets.length) return alert("Pick a course first.");
    const lateOn = document.getElementById("lp-late-enabled").checked;
    const missOn = document.getElementById("lp-missing-enabled").checked;
    const pct    = parseFloat(document.getElementById("lp-deduction").value) || 0;
    const intv   = document.getElementById("lp-interval").value;
    const floor  = parseFloat(document.getElementById("lp-floor").value) || 0;
    const missAt = parseFloat(document.getElementById("lp-missing-pct").value) || 0;
    const policy = {
      late_submission_deduction_enabled:       lateOn,
      late_submission_deduction:               pct,
      late_submission_interval:                intv,
      late_submission_minimum_percent_enabled: lateOn,
      late_submission_minimum_percent:         floor,
      missing_submission_deduction_enabled:    missOn,
      missing_submission_deduction:            100 - missAt,
    };
    const desc = [
      lateOn ? `late work: −${pct}% per ${intv}, floor ${floor}%` : "late deduction: OFF",
      missOn ? `missing work scored at ${missAt}%` : "missing deduction: OFF",
    ].join("\n  ");
    if (!confirm(
      `Apply this late policy:\n  ${desc}\n\nto: ${gbCourseName()}\n\n` +
      `Canvas will recalculate late grades automatically.\n\nContinue?`
    )) return;
    const banner = document.getElementById("lp-banner");
    hideBanner(banner);
    this.disabled = true;
    try {
      const d = await postForm("/api/late-policy/apply", {
        courses: JSON.stringify(targets), policy: JSON.stringify(policy),
      });
      if (d.error && !d.results) { showBanner(banner, "fail", "✗ " + esc(d.error)); return; }
      _renderBanner(banner, (d.results || []).map(r => ({
        ok:    r.ok,
        title: `${r.course_name} — ${r.ok ? r.title : (r.error || "failed")}`,
        url:   null,
      })), d.ok);
      // Reload to reflect any server-side changes
      delete _loadedFor["policy"];
      _loadPolicy();
    } finally { this.disabled = false; }
  });

  // ── Extra-time roster (auto-loaded) ───────────────────────────────────

  async function _loadRoster() {
    const id = gbCourseId();
    if (!id) return;
    _markLoaded("extra-time");
    const st = document.getElementById("xt-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading…"; }
    const reloadBtn = document.getElementById("btn-reload-roster");
    if (reloadBtn) reloadBtn.disabled = true;
    try {
      const [stu, saved] = await Promise.all([
        fetch(`/api/students/list?course_id=${encodeURIComponent(id)}`).then(r => r.json()),
        fetch(`/api/extra-time?course_id=${encodeURIComponent(id)}`).then(r => r.json()),
      ]);
      if (!stu.ok) {
        if (st) { st.className = "status error"; st.textContent = "Error: " + stu.error; }
        return;
      }
      const savedMap = new Map((saved.students || []).map(e => [String(e.id), e.days || 1]));
      const list = document.getElementById("xt-list");
      if (list) {
        list.innerHTML = "";
        stu.students.forEach(s => {
          const has = savedMap.has(s.id);
          const row = document.createElement("div");
          row.className = "xt-row";
          row.innerHTML =
            `<label class="opt-check xt-name"><input type="checkbox" class="xt-cb" value="${esc(s.id)}"` +
            ` data-name="${esc(s.name)}" ${has ? "checked" : ""}> ${esc(s.name)}</label>` +
            `<span class="xt-days">+<input type="number" class="xt-days-input"` +
            ` value="${has ? savedMap.get(s.id) : 1}" min="1" max="10"> day(s)</span>`;
          list.appendChild(row);
        });
      }
      if (st) {
        st.textContent = savedMap.size
          ? `${savedMap.size} student(s) currently on the roster — check/uncheck and save.`
          : "Check the students who get extra time, set their days, then save.";
      }
      const sb = document.getElementById("btn-save-roster");
      if (sb) sb.hidden = false;
    } finally {
      if (reloadBtn) reloadBtn.disabled = false;
    }
  }

  document.getElementById("btn-reload-roster")?.addEventListener("click", () => {
    delete _loadedFor["extra-time"];
    _loadRoster();
  });

  document.getElementById("btn-save-roster")?.addEventListener("click", async () => {
    const id = gbCourseId();
    if (!id) return;
    const students = [...document.querySelectorAll("#xt-list .xt-row")]
      .filter(r => r.querySelector(".xt-cb").checked)
      .map(r => ({
        id:   r.querySelector(".xt-cb").value,
        name: r.querySelector(".xt-cb").dataset.name,
        days: parseInt(r.querySelector(".xt-days-input").value, 10) || 1,
      }));
    const d  = await postForm("/api/extra-time", { course_id: id, students: JSON.stringify(students) });
    const st = document.getElementById("xt-status");
    if (d.ok) {
      st.className = "status ok";
      st.textContent = `✓ Saved ${students.length} extra-time student(s) for ${gbCourseName()}`;
    } else {
      st.className = "status error";
      st.textContent = "Error: " + d.error;
    }
  });

  // ── Extensions (auto-loaded on tab activate) ───────────────────────────

  function collectHolidays() {
    return (document.getElementById("sw-holidays")?.value || "")
      .split(/[\n,]/).map(s => s.trim())
      .filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s));
  }

  async function _loadExtensions() {
    const id = gbCourseId();
    if (!id) return;
    _markLoaded("extensions");
    const st = document.getElementById("ext-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading assignments and students…"; }
    try {
      const [asg, stu, xt] = await Promise.all([
        fetch(`/api/assignments-full?course_id=${encodeURIComponent(id)}`).then(r => r.json()),
        fetch(`/api/students/list?course_id=${encodeURIComponent(id)}`).then(r => r.json()),
        fetch(`/api/extra-time?course_id=${encodeURIComponent(id)}`).then(r => r.json()),
      ]);
      if (!asg.ok || !stu.ok) {
        if (st) { st.className = "status error"; st.textContent = "Error: " + (asg.error || stu.error); }
        return;
      }
      const sel = document.getElementById("ext-assignment");
      if (sel) {
        sel.innerHTML = "";
        sel.appendChild(new Option("— select an assignment —", ""));
        asg.assignments.filter(a => a.due_at).forEach(a =>
          sel.appendChild(new Option(`${a.name} (due ${a.due_at})`, a.id)));
        sel.disabled = false;
      }
      const eh = document.getElementById("ext-hint");
      if (eh) eh.textContent = `${asg.assignments.filter(a => a.due_at).length} assignments`;
      const savedIds = new Set((xt.students || []).map(e => String(e.id)));
      const box = document.getElementById("ext-students");
      if (box) {
        box.innerHTML = "";
        stu.students.forEach(s => {
          const row = document.createElement("div");
          row.className = "xt-row";
          row.innerHTML =
            `<label class="opt-check xt-name"><input type="checkbox" class="ext-cb"` +
            ` value="${esc(s.id)}" ${savedIds.has(s.id) ? "checked" : ""}> ${esc(s.name)}</label>`;
          box.appendChild(row);
        });
      }
      const eb = document.getElementById("btn-ext-apply");
      if (eb) eb.hidden = false;
      if (st) {
        st.textContent = savedIds.size
          ? "Extra-time roster preselected — adjust as needed, pick an assignment, then grant."
          : "Pick an assignment and the students who get extra time.";
      }
    } catch (e) {
      if (st) { st.className = "status error"; st.textContent = String(e); }
    }
  }

  document.getElementById("btn-ext-reload")?.addEventListener("click", () => {
    delete _loadedFor["extensions"];
    _loadExtensions();
  });

  document.getElementById("btn-ext-apply")?.addEventListener("click", async function () {
    const id   = gbCourseId();
    const aSel = document.getElementById("ext-assignment");
    if (!aSel.value) return alert("Pick an assignment.");
    const sids = [...document.querySelectorAll(".ext-cb:checked")].map(cb => cb.value);
    if (!sids.length) return alert("Select at least one student.");
    const days = parseInt(document.getElementById("ext-days").value, 10) || 1;
    if (!confirm(
      `Give ${sids.length} student(s) +${days} school day(s) on:\n` +
      `  "${aSel.selectedOptions[0].text}"\n\nCourse: ${gbCourseName()}\n\n` +
      `This creates a Canvas assignment override — their due date actually moves.\n\nContinue?`
    )) return;
    const banner = document.getElementById("ext-banner");
    hideBanner(banner);
    this.disabled = true;
    try {
      const d = await postForm("/api/extend-due", {
        course_id:     id,
        assignment_id: aSel.value,
        student_ids:   JSON.stringify(sids),
        days:          String(days),
        skip_weekends: document.getElementById("sw-weekends")?.checked ? "true" : "false",
        holidays:      JSON.stringify(collectHolidays()),
      });
      if (d.ok) {
        showBanner(banner, "ok",
          `✓ ${esc(d.assignment)} — ${d.count} student(s) now due ` +
          `${esc(new Date(d.new_due).toLocaleString())}`);
      } else {
        showBanner(banner, "fail", "✗ " + esc(d.error));
      }
    } finally { this.disabled = false; }
  });

  // ── Late work sweep ────────────────────────────────────────────────────

  function sweepSettings() {
    return {
      skip_weekends:    document.getElementById("sw-weekends").checked,
      holidays:         collectHolidays(),
      honor_extra_time: document.getElementById("sw-extra").checked,
      date_from:        document.getElementById("sw-from")?.value || null,
      date_to:          document.getElementById("sw-to")?.value   || null,
    };
  }

  function updateSweepApplyBtn() {
    const n   = document.querySelectorAll(".sw-cb:checked").length;
    const btn = document.getElementById("btn-sweep-apply");
    if (!btn) return;
    btn.hidden = n === 0;
    btn.textContent = `Set lateness for ${n} submission${n === 1 ? "" : "s"}…`;
  }

  document.getElementById("btn-sweep-preview")?.addEventListener("click", async function () {
    const id = gbCourseId();
    if (!id) return alert("Pick a course first.");
    const st = document.getElementById("sw-status");
    const from = document.getElementById("sw-from")?.value;
    const to   = document.getElementById("sw-to")?.value;
    if (!from && !to) {
      if (!confirm("No date range set — this will scan the entire course history and may be very slow. Continue?")) return;
    }
    st.className = "status hint";
    st.textContent = from
      ? `Scanning late work from ${from} to ${to || "now"}…`
      : "Scanning all late work… (give it a moment)";
    this.disabled = true;
    document.getElementById("sw-table-wrap").hidden = true;
    hideBanner(document.getElementById("sw-banner"));
    try {
      const d = await postForm("/api/sweep/preview",
        { course_id: id, settings: JSON.stringify(sweepSettings()) });
      if (!d.ok) { st.className = "status error"; st.textContent = "Error: " + d.error; return; }
      sweepEntries = d.entries || [];
      if (!sweepEntries.length) {
        st.className = "status ok";
        st.textContent = "✓ No late submissions found in this date range — nothing to correct.";
        updateSweepApplyBtn();
        return;
      }
      st.textContent = `${sweepEntries.length} late submission(s) found` +
        " — uncheck rows you want to skip. No changes yet.";
      const tbody = document.getElementById("sw-tbody");
      tbody.innerHTML = "";
      sweepEntries.forEach((e, i) => {
        const tr = document.createElement("tr");
        const excl = e.excluded || [];
        tr.title = excl.length
          ? `Excluded: ${excl.join(", ")}${e.extra_days ? ` + ${e.extra_days} extra-time day(s)` : ""}`
          : (e.extra_days ? `Extra-time: ${e.extra_days} day(s) excused` : "");
        tr.innerHTML =
          `<td><input type="checkbox" class="sw-cb" data-i="${i}" checked></td>` +
          `<td>${esc(e.student_name)}</td>` +
          `<td>${esc(e.assignment_name)}</td>` +
          `<td class="muted">${esc(e.due)} → ${esc(e.submitted)}</td>` +
          `<td class="muted">${e.canvas_days}</td>` +
          `<td><strong>${e.school_days}</strong></td>` +
          `<td class="muted" style="font-size:12px">${excl.length ? excl.join(", ") : "—"}</td>`;
        tbody.appendChild(tr);
      });
      const all = document.getElementById("sw-check-all");
      if (all) all.checked = true;
      document.getElementById("sw-table-wrap").hidden = false;
      updateSweepApplyBtn();
    } finally { this.disabled = false; }
  });

  document.getElementById("sw-check-all")?.addEventListener("change", function () {
    document.querySelectorAll(".sw-cb").forEach(cb => { cb.checked = this.checked; });
    updateSweepApplyBtn();
  });
  document.getElementById("sw-tbody")?.addEventListener("change", e => {
    if (e.target.classList.contains("sw-cb")) updateSweepApplyBtn();
  });

  document.getElementById("btn-sweep-apply")?.addEventListener("click", async function () {
    const id   = gbCourseId();
    const rows = [...document.querySelectorAll(".sw-cb:checked")]
      .map(cb => sweepEntries[+cb.dataset.i])
      .filter(Boolean);
    if (!rows.length) return;
    if (!confirm(
      `Set lateness overrides for ${rows.length} submission(s) in ${gbCourseName()}?\n\n` +
      `Canvas will recalculate each student's late penalty using the corrected school-day ` +
      `count. No grades are written directly — Canvas applies its own late policy.\n\nContinue?`
    )) return;
    const log = showLog(document.getElementById("sw-log"));
    hideBanner(document.getElementById("sw-banner"));
    this.disabled = true;
    log(`Setting lateness override for ${rows.length} submission(s)…\n`);
    try {
      const d = await postForm("/api/sweep/apply", { course_id: id, entries: JSON.stringify(rows) });
      if (d.error && !d.results) {
        log("ERROR: " + d.error);
        showBanner(document.getElementById("sw-banner"), "fail", "✗ " + esc(d.error));
        return;
      }
      (d.results || []).forEach(r => log(
        `${r.ok ? "✓" : "✗"} ${r.student} — ${r.assignment} → ${r.school_days} school day(s) late` +
        (r.ok ? "" : `  (${r.error})`)));
      const okCount = (d.results || []).filter(r => r.ok).length;
      showBanner(document.getElementById("sw-banner"), d.ok ? "ok" : "warn",
        `${d.ok ? "✓" : "⚠"} ${okCount}/${rows.length} lateness override(s) set — Canvas will apply its late policy.`);
      document.getElementById("sw-table-wrap").hidden = true;
      sweepEntries = [];
      updateSweepApplyBtn();
    } finally { this.disabled = false; }
  });

  // ── Curves (auto-loaded on tab activate) ──────────────────────────────

  async function _loadCurveAssignments() {
    const id = gbCourseId();
    if (!id) return;
    _markLoaded("curves");
    const hint = document.getElementById("cv-assign-hint");
    if (hint) hint.textContent = "loading…";
    const btn = document.getElementById("btn-curve-load");
    if (btn) btn.disabled = true;
    try {
      const d = await fetch(`/api/curve/assignments?course_id=${encodeURIComponent(id)}`).then(r => r.json());
      const sel = document.getElementById("cv-assignment");
      if (sel) {
        sel.innerHTML = '<option value="">— select assignment —</option>';
        (d.assignments || []).forEach(a => {
          const opt = document.createElement("option");
          opt.value = a.id;
          opt.textContent = `${a.name}${a.due_at ? "  (" + a.due_at + ")" : ""}  [${a.points} pts]`;
          sel.appendChild(opt);
        });
        sel.disabled = false;
      }
      if (hint) hint.textContent = `${(d.assignments || []).length} assignments`;
    } catch (e) {
      if (hint) hint.textContent = "error loading";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.getElementById("btn-curve-load")?.addEventListener("click", () => {
    delete _loadedFor["curves"];
    _loadCurveAssignments();
  });

  function syncCurveSettings() {
    const model = document.getElementById("cv-model")?.value || "flat_bump";
    ["flat_bump", "target_average", "proportional", "floor_cap"].forEach(m => {
      const el = document.getElementById(`cv-settings-${m}`);
      if (el) el.style.display = (m === model) ? "" : "none";
    });
  }
  document.getElementById("cv-model")?.addEventListener("change", syncCurveSettings);
  syncCurveSettings();

  function curveSettings() {
    const model = document.getElementById("cv-model")?.value || "flat_bump";
    if (model === "flat_bump") return {
      bump:       parseFloat(document.getElementById("cv-bump").value) || 0,
      cap:        document.getElementById("cv-bump-cap").value || null,
      do_no_harm: document.getElementById("cv-bump-donh").checked,
    };
    if (model === "target_average") return {
      target_avg_pct: parseFloat(document.getElementById("cv-target-avg-pct").value) || 75,
      cap:            document.getElementById("cv-target-cap").value || null,
      do_no_harm:     document.getElementById("cv-target-donh").checked,
    };
    if (model === "proportional") return {
      target_avg_pct: parseFloat(document.getElementById("cv-prop-avg-pct").value) || 75,
      cap:            document.getElementById("cv-prop-cap").value || null,
      do_no_harm:     document.getElementById("cv-prop-donh").checked,
    };
    if (model === "floor_cap") return {
      floor: parseFloat(document.getElementById("cv-floor").value) || 0,
      cap:   document.getElementById("cv-cap").value || null,
    };
    return {};
  }

  function updateCurveApplyBtn() {
    const n   = document.querySelectorAll(".cv-cb:checked").length;
    const btn = document.getElementById("btn-curve-apply");
    if (!btn) return;
    btn.hidden = n === 0;
    btn.textContent = `Apply curve to ${n} student${n === 1 ? "" : "s"}…`;
  }

  document.getElementById("btn-curve-preview")?.addEventListener("click", async function () {
    const id  = gbCourseId();
    const aid = document.getElementById("cv-assignment")?.value;
    if (!id)  return alert("Pick a course first.");
    if (!aid) return alert("Select an assignment first.");
    const model = document.getElementById("cv-model")?.value || "flat_bump";
    const st = document.getElementById("cv-status");
    st.className = "status hint";
    st.textContent = "Loading submissions and computing curve…";
    this.disabled = true;
    document.getElementById("cv-preview-wrap").hidden = true;
    hideBanner(document.getElementById("cv-banner"));
    try {
      const d = await postForm("/api/curve/preview", {
        course_id:     id,
        assignment_id: aid,
        curve_type:    model,
        settings:      JSON.stringify(curveSettings()),
      });
      if (!d.ok) { st.className = "status error"; st.textContent = "Error: " + d.error; return; }
      curveResults = d.results || [];
      if (!curveResults.length) {
        st.className = "status ok";
        st.textContent = "No graded submissions found for this assignment.";
        updateCurveApplyBtn();
        return;
      }
      const sm = d.summary || {};
      const ungraded = sm.ungraded ? ` · ${sm.ungraded} submitted but not yet graded` : "";
      document.getElementById("cv-summary").innerHTML =
        `<strong>${esc(sm.assignment_name)}</strong> · ${sm.n} graded · ` +
        `Avg: <strong>${sm.original_avg ?? "—"}</strong> → <strong>${sm.curved_avg ?? "—"}</strong> ` +
        `(out of ${sm.points}) · ` +
        `<span style="color:var(--forge-green)">${sm.helped} helped</span>` +
        (sm.lowered ? ` · <span style="color:var(--danger)">${sm.lowered} lowered</span>` : "") +
        ` · ${sm.unchanged} unchanged${ungraded}`;
      const tbody = document.getElementById("cv-tbody");
      tbody.innerHTML = "";
      curveResults.forEach((r, i) => {
        const diff = r.curved_score - r.original_score;
        const sign = diff > 0 ? "+" : (diff < 0 ? "" : "±");
        const cls  = diff > 0 ? `style="color:var(--forge-green)"`
                   : diff < 0 ? `class="gb-bad"` : `class="muted"`;
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td><input type="checkbox" class="cv-cb" data-i="${i}" checked></td>` +
          `<td>${esc(r.student_name)}</td>` +
          `<td class="muted">${r.original_score}</td>` +
          `<td><strong>${r.curved_score}</strong></td>` +
          `<td ${cls}>${sign}${Math.round(Math.abs(diff) * 100) / 100}</td>`;
        tbody.appendChild(tr);
      });
      document.getElementById("cv-check-all").checked = true;
      document.getElementById("cv-preview-wrap").hidden = false;
      updateCurveApplyBtn();
      st.textContent = "Preview ready — uncheck students you want to skip. No changes yet.";
    } finally { this.disabled = false; }
  });

  document.getElementById("cv-check-all")?.addEventListener("change", function () {
    document.querySelectorAll(".cv-cb").forEach(cb => { cb.checked = this.checked; });
    updateCurveApplyBtn();
  });
  document.getElementById("cv-tbody")?.addEventListener("change", e => {
    if (e.target.classList.contains("cv-cb")) updateCurveApplyBtn();
  });

  document.getElementById("btn-curve-apply")?.addEventListener("click", async function () {
    const id  = gbCourseId();
    const aid = document.getElementById("cv-assignment")?.value;
    const rows = [...document.querySelectorAll(".cv-cb:checked")]
      .map(cb => curveResults[+cb.dataset.i]).filter(Boolean);
    if (!rows.length) return;
    const model   = document.getElementById("cv-model")?.value || "flat_bump";
    const helped  = rows.filter(r => r.curved_score > r.original_score).length;
    const lowered = rows.filter(r => r.curved_score < r.original_score).length;
    if (!confirm(
      `Apply curve to ${rows.length} student(s) in ${gbCourseName()}?\n\n` +
      `${helped} score(s) will go up${lowered ? `, ${lowered} will go down` : ""} (${model.replace(/_/g, " ")}).\n` +
      `A local revert event is saved — you can undo this.\n\nThis writes REAL scores to Canvas.\n\nContinue?`
    )) return;
    const log = showLog(document.getElementById("cv-log"));
    hideBanner(document.getElementById("cv-banner"));
    this.disabled = true;
    log(`Applying ${rows.length} curved score(s)…\n`);
    try {
      const d = await postForm("/api/curve/apply", {
        course_id:     id,
        assignment_id: aid,
        curve_type:    model,
        settings:      JSON.stringify(curveSettings()),
        results:       JSON.stringify(rows),
      });
      if (d.error && !d.results) {
        log("ERROR: " + d.error);
        showBanner(document.getElementById("cv-banner"), "fail", "✗ " + esc(d.error));
        return;
      }
      (d.results || []).forEach(r => log(
        `${r.ok ? "✓" : "✗"} ${r.student}: ${r.original} → ${r.curved}` +
        (r.ok ? "" : `  (${r.error})`)));
      const okCount = (d.results || []).filter(r => r.ok).length;
      showBanner(document.getElementById("cv-banner"), d.ok ? "ok" : "warn",
        `${d.ok ? "✓" : "⚠"} ${okCount}/${rows.length} score(s) curved. ` +
        `Event ${d.event_id} saved — use "Curve history" below to revert.`);
      document.getElementById("cv-preview-wrap").hidden = true;
      curveResults = [];
      updateCurveApplyBtn();
    } finally { this.disabled = false; }
  });

  document.getElementById("btn-curve-events")?.addEventListener("click", async function () {
    const id  = gbCourseId();
    const aid = document.getElementById("cv-assignment")?.value;
    if (!id) return alert("Pick a course first.");
    const es   = document.getElementById("cv-events-status");
    const list = document.getElementById("cv-events-list");
    es.className = "status hint";
    es.textContent = "Loading…";
    list.innerHTML = "";
    try {
      const url = `/api/curve/events?course_id=${encodeURIComponent(id)}` +
        (aid ? `&assignment_id=${encodeURIComponent(aid)}` : "");
      const d = await fetch(url).then(r => r.json());
      if (!d.ok) { es.className = "status error"; es.textContent = "Error: " + d.error; return; }
      const events = d.events || [];
      if (!events.length) {
        es.textContent = aid ? "No curve events for this assignment." : "No curve events for this course.";
        return;
      }
      es.textContent = "";
      events.forEach(ev => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex; align-items:baseline; gap:12px; padding:8px 0; border-bottom:1px solid var(--line); font-size:13.5px";
        const applied    = ev.applied_at ? ev.applied_at.replace("T", " ") : "";
        const modelLabel = ev.curve_type?.replace(/_/g, " ") || "";
        row.innerHTML =
          `<span style="flex:1"><strong>${esc(ev.assignment_name)}</strong> — ${esc(modelLabel)}</span>` +
          `<span class="muted" style="font-size:12px">${esc(applied)}</span>` +
          `<button class="small cv-revert-btn" data-event-id="${esc(ev.id)}" data-course="${esc(id)}">Revert…</button>`;
        list.appendChild(row);
      });
    } catch (e) { es.className = "status error"; es.textContent = String(e); }
  });

  document.getElementById("cv-events-list")?.addEventListener("click", async function (e) {
    const btn = e.target.closest(".cv-revert-btn");
    if (!btn) return;
    const eventId  = btn.dataset.eventId;
    const courseId = btn.dataset.course;
    if (!confirm(`Revert this curve event for ALL students?\n\nThis writes original scores back to Canvas.\n\nContinue?`)) return;
    btn.disabled = true;
    const es = document.getElementById("cv-events-status");
    es.className = "status hint";
    es.textContent = "Reverting…";
    try {
      const d = await postForm("/api/curve/revert", { event_id: eventId, course_id: courseId });
      if (d.error && !d.results) { es.className = "status error"; es.textContent = "Error: " + d.error; return; }
      const okCount = (d.results || []).filter(r => r.ok).length;
      const drifted = (d.results || []).filter(r => r.warned_drift).length;
      es.className   = d.ok ? "status ok" : "status error";
      es.textContent = `${d.ok ? "✓" : "⚠"} ${okCount}/${(d.results || []).length} score(s) reverted` +
        (drifted ? ` · ${drifted} had changed since the curve — check manually` : "");
      btn.closest("div").remove();
    } finally { btn.disabled = false; }
  });

  // ── Snapshot ───────────────────────────────────────────────────────────

  document.getElementById("btn-load-gradebook")?.addEventListener("click", async function () {
    const id   = gbCourseId();
    const name = gbCourseName();
    if (!id) return alert("Pick a course first.");
    const status = document.getElementById("gb-status");
    status.className = "status hint";
    status.textContent = `Loading gradebook for ${name}… (pulls every submission — give it a moment)`;
    this.disabled = true;
    try {
      const d = await fetch(`/api/gradebook?course_id=${encodeURIComponent(id)}`).then(r => r.json());
      if (!d.ok) { status.className = "status error"; status.textContent = "Error: " + d.error; return; }
      status.textContent = "";
      const link = document.getElementById("gb-canvas-link");
      link.hidden = false;
      link.href = `${window.GB_CANVAS_BASE}/courses/${id}/gradebook`;

      document.getElementById("gb-avg").textContent      = d.class_avg != null ? d.class_avg + "%" : "—";
      document.getElementById("gb-missing").textContent  = d.total_missing;
      document.getElementById("gb-ungraded").textContent = d.total_ungraded;
      document.getElementById("gb-students").textContent = d.student_count;
      document.getElementById("gb-summary").hidden = false;

      const stb = document.getElementById("gb-student-tbody");
      stb.innerHTML = "";
      [...d.students]
        .sort((a, b) => b.missing - a.missing || a.name.localeCompare(b.name))
        .forEach(s => {
          const tr = document.createElement("tr");
          tr.innerHTML =
            `<td>${esc(s.name)}</td>` +
            `<td class="${s.missing ? "gb-bad" : "muted"}">${s.missing || "—"}</td>` +
            `<td class="muted">${s.late || "—"}</td>` +
            `<td class="muted">${s.ungraded || "—"}</td>` +
            `<td>${s.pct != null ? s.pct + "%" : "—"}</td>`;
          stb.appendChild(tr);
        });

      const atb = document.getElementById("gb-assign-tbody");
      atb.innerHTML = "";
      d.assignments.forEach(a => {
        const nm = a.html_url
          ? `<a href="${esc(a.html_url)}" target="_blank" rel="noopener">${esc(a.name)}</a>`
          : esc(a.name);
        const ungraded = a.submitted - a.graded;
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td>${nm}</td>` +
          `<td class="muted">${esc(a.due_at || "—")}</td>` +
          `<td class="muted">${a.points ?? "—"}</td>` +
          `<td>${a.submitted}</td>` +
          `<td>${a.graded}${ungraded > 0 ? ` <span class="gb-warn">+${ungraded} to grade</span>` : ""}</td>` +
          `<td class="${a.missing ? "gb-bad" : "muted"}">${a.missing || "—"}</td>` +
          `<td>${a.avg_pct != null ? a.avg_pct + "%" : "—"}</td>`;
        atb.appendChild(tr);
      });
      document.getElementById("gb-tables").hidden = false;
      this.textContent = "↻ Reload gradebook";
    } catch (e) {
      status.className  = "status error";
      status.textContent = String(e);
    } finally { this.disabled = false; }
  });

  // ── Init ───────────────────────────────────────────────────────────────

  _buildPeriodChips();
  _initSweepDateRange();

  // Auto-load the first course if one is already selected (e.g. saved_courses populated)
  if (gbCourseId()) {
    const active = document.querySelector(".gb-tab.active")?.dataset.tab;
    if (active) _autoloadTab(active);
  }

})();
