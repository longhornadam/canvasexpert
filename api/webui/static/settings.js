(function () {
  "use strict";

  // ── URL editing ────────────────────────────────────────────────────────

  const urlDisplay  = document.getElementById("url-display");
  const urlInput    = document.getElementById("base_url_input");
  const btnEditUrl  = document.getElementById("btn-edit-url");

  btnEditUrl?.addEventListener("click", () => {
    const editing = urlInput.style.display === "none";
    urlInput.style.display  = editing ? "" : "none";
    urlDisplay.style.display = editing ? "none" : "";
    btnEditUrl.textContent  = editing ? "Cancel" : "Edit";
    if (editing) urlInput.focus();
  });

  // ── Token replace ──────────────────────────────────────────────────────

  const tokenInput     = document.getElementById("token_input");
  const btnReplaceToken = document.getElementById("btn-replace-token");

  btnReplaceToken?.addEventListener("click", () => {
    const showing = tokenInput.style.display !== "none";
    tokenInput.style.display = showing ? "none" : "";
    btnReplaceToken.textContent = showing ? "Replace" : "Cancel";
    if (!showing) tokenInput.focus();
  });

  // ── Canvas account form ────────────────────────────────────────────────

  const form          = document.getElementById("canvas-account-form");
  const statusEl      = document.getElementById("account-status");
  const btnTest       = document.getElementById("btn-test");

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  function isHidden(el) { return !el || el.style.display === "none"; }

  function getFormData() {
    return {
      base_url: isHidden(urlInput)
        ? (urlDisplay?.textContent || "").trim()
        : urlInput.value.trim(),
      // Empty string when the input is hidden = use the already-saved token on the server
      token: isHidden(tokenInput) ? "" : (tokenInput?.value.trim() || ""),
    };
  }

  btnTest?.addEventListener("click", async () => {
    const d = getFormData();
    if (!d.base_url) return setStatus("Enter the Canvas base URL first.", "error");
    // d.token may be empty when testing the already-stored credential — that's fine,
    // the server will fall back to the keyring token.
    setStatus(d.token ? "Testing connection…" : "Testing saved token…");
    const resp = await fetch("/settings/test-connection", {
      method: "POST",
      body: new URLSearchParams(d),
    });
    const data = await resp.json();
    if (data.ok) setStatus(`✓ Connected — signed in as ${data.display_name}`, "ok");
    else         setStatus("Connection failed: " + data.error, "error");
  });

  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const d = getFormData();
    if (!d.base_url) return setStatus("Base URL is required.", "error");
    setStatus("Saving…");
    const resp = await fetch("/settings/canvas", {
      method: "POST",
      body: new URLSearchParams(d),
    });
    const data = await resp.json();
    if (!data.ok) {
      setStatus("Could not save.", "error");
      return;
    }
    if (d.token) {
      setStatus("Saved. Testing token…", "ok");
      const test = await fetch("/settings/test-connection", {
        method: "POST",
        body: new URLSearchParams(d),
      }).then(r => r.json());
      if (test.ok) {
        setStatus(`Saved and connected as ${test.display_name || "you"} ✓`, "ok");
      } else {
        setStatus("Saved, but the token test failed: " + (test.error || "unknown error"), "error");
      }
      setTimeout(() => location.reload(), 900);
    } else {
      setStatus("Saved! Reloading…", "ok");
      setTimeout(() => location.reload(), 600);
    }
  });

  // ── OpenRouter account ────────────────────────────────────────────────

  const openrouterForm     = document.getElementById("openrouter-form");
  const openrouterKeyInput = document.getElementById("openrouter-key-input");
  const openrouterModel    = document.getElementById("openrouter-model-input");
  const openrouterStatus   = document.getElementById("openrouter-status");
  const btnReplaceOrKey    = document.getElementById("btn-replace-openrouter-key");
  const btnOpenrouterHelp  = document.getElementById("btn-openrouter-help");
  const openrouterHelp     = document.getElementById("openrouter-help");
  const btnOpenrouterAuto  = document.getElementById("btn-openrouter-auto");
  const btnLoadOrModels    = document.getElementById("btn-openrouter-load-models");
  const btnTestOpenrouter  = document.getElementById("btn-openrouter-test");
  const openrouterModels   = document.getElementById("openrouter-model-list");
  const openrouterMajorBox = document.getElementById("openrouter-major-models");
  const openrouterMajorList = document.getElementById("openrouter-major-list");

  function setOpenrouterStatus(msg, kind) {
    if (!openrouterStatus) return;
    openrouterStatus.textContent = msg;
    openrouterStatus.className = "status" + (kind ? " " + kind : "");
  }

  btnReplaceOrKey?.addEventListener("click", () => {
    const showing = openrouterKeyInput.style.display !== "none";
    openrouterKeyInput.style.display = showing ? "none" : "";
    btnReplaceOrKey.textContent = showing ? "Replace" : "Cancel";
    if (!showing) openrouterKeyInput.focus();
  });

  btnOpenrouterHelp?.addEventListener("click", () => {
    if (!openrouterHelp) return;
    openrouterHelp.hidden = !openrouterHelp.hidden;
    btnOpenrouterHelp.textContent = openrouterHelp.hidden ? "What is this?" : "Hide instructions";
  });

  btnOpenrouterAuto?.addEventListener("click", () => {
    if (openrouterModel) openrouterModel.value = "openrouter/auto";
    setOpenrouterStatus("Auto Router selected. Save to keep it.", "ok");
  });

  function formatPrice(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
    const n = Number(v);
    if (n === 0) return "$0";
    if (n < 0.01) return "$" + n.toFixed(4);
    if (n < 1) return "$" + n.toFixed(3);
    return "$" + n.toFixed(2);
  }

  function formatScenarioCost(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
    const n = Number(v);
    if (n === 0) return "$0";
    if (n < 0.01) return "<$0.01";
    if (n < 1) return "$" + n.toFixed(2);
    return "$" + n.toFixed(2);
  }

  function estimateText(m) {
    if (m.scenario_cost_low !== undefined && m.scenario_cost_high !== undefined &&
        m.scenario_cost_low !== null && m.scenario_cost_high !== null) {
      return `${formatScenarioCost(m.scenario_cost_low)}-${formatScenarioCost(m.scenario_cost_high)}`;
    }
    return formatScenarioCost(m.scenario_cost);
  }

  function renderMajorModels(models, scenario) {
    if (!openrouterMajorBox || !openrouterMajorList) return;
    const rows = models || [];
    if (!rows.length) {
      openrouterMajorBox.hidden = true;
      return;
    }
    const scenarioLabel = scenario?.label || "30 1000-word essays";
    openrouterMajorList.innerHTML =
      '<table class="profiles" style="margin-top:6px">' +
      `<thead><tr><th>Family</th><th>Model</th><th>Estimate</th><th>Reference pricing</th><th></th></tr></thead>` +
      '<tbody>' + rows.map(m =>
        `<tr>` +
        `<td>${esc(m.family || "")}</td>` +
        `<td><strong>${esc(m.name || m.id)}</strong><br><span class="muted">${esc(m.id)}</span><br><span class="muted">${esc(m.strategy || "")}</span></td>` +
        `<td><strong>${estimateText(m)}</strong><br><span class="muted">${esc(scenarioLabel)}</span></td>` +
        `<td><span class="muted">Input ${formatPrice(m.input_per_mtok)} / 1M<br>Output ${formatPrice(m.output_per_mtok)} / 1M</span></td>` +
        `<td><button type="button" class="small" data-openrouter-model="${esc(m.id)}">Use</button></td>` +
        `</tr>`
      ).join("") + '</tbody></table>';
    openrouterMajorBox.hidden = false;
  }

  openrouterMajorList?.addEventListener("click", e => {
    const btn = e.target.closest("[data-openrouter-model]");
    if (!btn) return;
    if (openrouterModel) openrouterModel.value = btn.dataset.openrouterModel || "";
    setOpenrouterStatus("Model selected. Save to keep it.", "ok");
  });

  btnLoadOrModels?.addEventListener("click", async () => {
    if (!openrouterModels) return;
    btnLoadOrModels.disabled = true;
    btnLoadOrModels.textContent = "Loading…";
    setOpenrouterStatus("Loading current OpenRouter model IDs and prices…");
    try {
      const d = await fetch("/settings/openrouter/models").then(r => r.json());
      if (!d.ok) {
        setOpenrouterStatus("Could not load models: " + (d.error || "unknown error"), "error");
        return;
      }
      const options = ['<option value="openrouter/auto" label="Auto Router (recommended)"></option>'];
      (d.models || []).forEach(m => {
        const label = m.name && m.name !== m.id ? `${m.name}` : "";
        options.push(`<option value="${esc(m.id)}" label="${esc(label)}"></option>`);
      });
      openrouterModels.innerHTML = options.join("");
      renderMajorModels(d.majors || [], d.scenario || null);
      setOpenrouterStatus(`Loaded ${d.models?.length || 0} current model ID(s) and ${d.majors?.length || 0} major model price row(s).`, "ok");
      openrouterModel?.focus();
    } catch (e) {
      setOpenrouterStatus("Could not load models: " + e, "error");
    } finally {
      btnLoadOrModels.disabled = false;
      btnLoadOrModels.textContent = "Load current model IDs & prices";
    }
  });

  btnTestOpenrouter?.addEventListener("click", async () => {
    const apiKey = isHidden(openrouterKeyInput) ? "" : (openrouterKeyInput?.value.trim() || "");
    setOpenrouterStatus(apiKey ? "Testing pasted OpenRouter key…" : "Testing saved OpenRouter key…");
    const d = await fetch("/settings/openrouter/test", {
      method: "POST",
      body: new URLSearchParams({ api_key: apiKey }),
    }).then(r => r.json());
    if (d.ok) {
      const label = d.label ? ` (${d.label})` : "";
      setOpenrouterStatus(`OpenRouter key works${label}.`, "ok");
    } else {
      setOpenrouterStatus("OpenRouter key failed: " + (d.error || "unknown error"), "error");
    }
  });

  openrouterForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const apiKey = isHidden(openrouterKeyInput) ? "" : (openrouterKeyInput?.value.trim() || "");
    const model = openrouterModel?.value.trim() || "";
    if (!apiKey && !model) return setOpenrouterStatus("Enter a key or model first.", "error");
    setOpenrouterStatus("Saving…");
    const r = await fetch("/settings/openrouter", {
      method: "POST",
      body: new URLSearchParams({ api_key: apiKey, model }),
    });
    const d = await r.json();
    if (!d.ok) {
      setOpenrouterStatus(d.error || "Could not save OpenRouter settings.", "error");
      return;
    }
    if (openrouterKeyInput) openrouterKeyInput.value = "";
    if (d.key_valid) {
      const label = d.key_label ? ` (${d.key_label})` : "";
      setOpenrouterStatus(`Saved and validated OpenRouter key${label}.`, "ok");
      setTimeout(() => location.reload(), 900);
    } else {
      setOpenrouterStatus("Saved, but OpenRouter validation failed: " + (d.key_error || "unknown error"), "error");
    }
  });

  // ── Course browser ─────────────────────────────────────────────────────

  const btnFetch     = document.getElementById("btn-fetch-courses");
  const browser      = document.getElementById("course-browser");
  const searchInput  = document.getElementById("course-search");
  const courseList   = document.getElementById("course-list");

  let allCourses = [];

  btnFetch?.addEventListener("click", async () => {
    btnFetch.disabled = true;
    btnFetch.textContent = "Loading…";
    const resp = await fetch("/api/courses");
    const data = await resp.json();
    btnFetch.disabled = false;
    btnFetch.textContent = "Browse all my courses…";
    if (!data.ok) { alert("Could not fetch courses: " + data.error); return; }
    allCourses = data.courses;
    browser.hidden = false;
    renderCourseList(allCourses);
    searchInput.focus();
  });

  searchInput?.addEventListener("input", () => {
    const q = searchInput.value.toLowerCase();
    renderCourseList(allCourses.filter(c =>
      c.name.toLowerCase().includes(q) || c.id.includes(q)
    ));
  });

  function renderCourseList(courses) {
    courseList.innerHTML = "";
    courses.forEach(c => {
      const row = document.createElement("div");
      row.className = "course-row";
      row.innerHTML =
        `<span>${esc(c.name)} <span class="muted">#${esc(c.id)}</span></span>` +
        `<button type="button" class="small" data-id="${esc(c.id)}" data-name="${esc(c.name)}">Bookmark</button>`;
      row.querySelector("button").addEventListener("click", async (ev) => {
        const btn = ev.currentTarget;
        const nickname = prompt(`Bookmark nickname for:\n${c.name} (#${c.id})`, c.name);
        if (nickname === null) return;                   // cancelled
        btn.disabled = true; btn.textContent = "Saving…";
        const r = await fetch("/settings/courses/bookmark", {
          method: "POST",
          body: new URLSearchParams({ course_id: c.id, course_name: c.name,
                                       nickname: nickname || c.name }),
        });
        const d = await r.json();
        if (d.ok) { btn.textContent = "✓ Saved"; }
        else      { btn.disabled = false; btn.textContent = "Bookmark"; alert("Failed: " + d.error); }
      });
      courseList.appendChild(row);
    });
    if (!courses.length) {
      courseList.innerHTML = "<p class='hint'>No courses match.</p>";
    }
  }

  // ── Active / inactive toggles ──────────────────────────────────────────

  document.querySelectorAll(".active-toggle").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id      = btn.dataset.courseId;
      const current = btn.dataset.current === "true";
      const newVal  = !current;
      btn.disabled  = true;
      const r = await fetch(`/settings/courses/${encodeURIComponent(id)}/set-active`, {
        method: "POST",
        body: new URLSearchParams({ active: newVal }),
      });
      const d = await r.json();
      if (!d.ok) { btn.disabled = false; alert("Failed to update."); return; }
      btn.dataset.current = String(newVal);
      if (newVal) {
        btn.textContent = "✓ Active";
        btn.style.color = "#2f8132";
        btn.style.borderColor = "#a8d5b5";
      } else {
        btn.textContent = "Inactive";
        btn.style.color = "var(--muted)";
        btn.style.borderColor = "var(--line)";
      }
      btn.disabled = false;
    });
  });

  // ── Remove bookmarks ───────────────────────────────────────────────────

  document.querySelectorAll("[data-remove-course]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id   = btn.dataset.removeCourse;
      const name = btn.dataset.removeName;
      if (!confirm(`Remove bookmark for "${name}"?`)) return;
      await fetch(`/settings/courses/${encodeURIComponent(id)}/remove`, { method: "POST" });
      location.reload();
    });
  });

  // ── Download root ──────────────────────────────────────────────────────

  const dlRootForm   = document.getElementById("download-root-form");
  const dlRootStatus = document.getElementById("download-root-status");
  const workspaceCard = document.getElementById("workspace-card");

  function setDlStatus(msg, kind) {
    if (!dlRootStatus) return;
    dlRootStatus.textContent = msg;
    dlRootStatus.className = "status" + (kind ? " " + kind : "");
  }

  dlRootForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const path = document.getElementById("download-root-input")?.value.trim();
    if (!path) return setDlStatus("Enter a folder path.", "error");
    setDlStatus("Saving…");
    const r = await fetch("/settings/download-root", {
      method: "POST",
      body: new URLSearchParams({ path }),
    });
    const d = await r.json();
    if (d.ok) setDlStatus("✓ Saved", "ok");
    else      setDlStatus("Could not save: " + (d.error || "unknown error"), "error");
  });

  document.getElementById("btn-ai-ta-open")?.addEventListener("click", async () => {
    if (!aiTaPath) return setAiTaStatus("Folder path unavailable.", "error");
    const r = await fetch("/api/open-folder", {
      method: "POST",
      body: new URLSearchParams({ path: aiTaPath }),
    });
    const d = await r.json();
    if (d.ok) setAiTaStatus("Opened in Explorer.", "ok");
    else      setAiTaStatus(d.error || "Could not open folder.", "error");
  });

  document.getElementById("btn-workspace-open")?.addEventListener("click", async () => {
    const root = workspaceCard?.dataset.path || "";
    if (!root) return setStatus("No OneDrive workspace is available on this machine.", "error");
    const r = await fetch("/api/open-folder", {
      method: "POST",
      body: new URLSearchParams({ path: root }),
    });
    const d = await r.json();
    if (d.ok) setStatus("Workspace opened in Explorer.", "ok");
    else      setStatus(d.error || "Could not open workspace folder.", "error");
  });

  document.getElementById("btn-ai-ta-rebuild")?.addEventListener("click", async () => {
    setAiTaStatus("Rebuilding…", "");
    const d = await fetch("/api/ai-ta/rebuild", { method: "POST" }).then(r => r.json());
    if (d.ok) {
      setAiTaStatus(`Rebuilt ${d.files?.length || 0} file(s).`, "ok");
      await loadAiTaFiles();
    } else {
      setAiTaStatus(d.error || "Rebuild failed.", "error");
    }
  });

  // ── Academic calendar ──────────────────────────────────────────────────

  const calOpStatus     = document.getElementById("cal-op-status");
  const calCustomStatus = document.getElementById("cal-custom-status");
  const aiTaCard        = document.getElementById("ai-ta-card");
  const aiTaStatus      = document.getElementById("ai-ta-status");
  const aiTaFileList    = document.getElementById("ai-ta-file-list");
  const aiTaPath        = aiTaCard?.dataset.path || "";

  function setCalStatus(el, msg, kind) {
    if (!el) return;
    el.textContent = msg;
    el.className = "status" + (kind ? " " + kind : "");
  }

  function setAiTaStatus(msg, kind) {
    if (!aiTaStatus) return;
    aiTaStatus.textContent = msg;
    aiTaStatus.className = "status" + (kind ? " " + kind : "");
  }

  function renderAiTaFiles(files) {
    if (!aiTaFileList) return;
    aiTaFileList.innerHTML = "";
    (files || []).forEach(file => {
      const li = document.createElement("li");
      li.textContent = file.label;
      aiTaFileList.appendChild(li);
    });
    if (!files || !files.length) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = "No files yet.";
      aiTaFileList.appendChild(li);
    }
  }

  async function loadAiTaFiles() {
    if (!aiTaFileList) return;
    const data = await fetch("/api/ai-ta/files").then(r => r.json());
    renderAiTaFiles(data.files || []);
  }

  function _renderCalendars(calendars) {
    const list = document.getElementById("cal-list");
    if (!list) return;
    const entries = Object.entries(calendars || {});
    if (!entries.length) {
      list.innerHTML = '<div class="callout warn" id="cal-none-callout">No academic calendar configured — only weekends are skipped by default.</div>';
      return;
    }
    list.innerHTML = entries.map(([key, cal]) => {
      const days    = (cal.no_count_dates    || []).length;
      const periods = (cal.grading_periods   || []).length;
      return `<div class="cal-row" data-cal-key="${esc(key)}">` +
        `<div><strong>${esc(cal.label)}</strong>` +
        `<span class="muted" style="font-size:12.5px;margin-left:8px">` +
        `${days} day(s) off · ${periods} grading period(s)</span></div>` +
        `<button class="danger small cal-remove-btn" data-cal-key="${esc(key)}">Remove</button>` +
        `</div>`;
    }).join("");
  }

  async function _loadCalendarFile(name, label, btn) {
    if (btn) btn.disabled = true;
    setCalStatus(calOpStatus, `Loading ${label}…`, "");
    try {
      const fd = new FormData();
      fd.append("name", name);
      const d = await fetch("/api/calendar/load-builtin", { method: "POST", body: fd }).then(r => r.json());
      if (d.ok) {
        const note = (d.grading_periods || []).length
          ? ` · ${d.grading_periods.length} grading period(s)` : "";
        setCalStatus(calOpStatus, `✓ Loaded ${d.count} day(s) off${note} — ${d.label}`, "ok");
        const cd = await fetch("/api/calendar").then(r => r.json());
        if (cd.ok) _renderCalendars(cd.calendars);
      } else {
        setCalStatus(calOpStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } finally { if (btn) btn.disabled = false; }
  }

  document.getElementById("cal-builtin-actions")?.addEventListener("click", e => {
    const btn = e.target.closest(".cal-load-btn");
    if (!btn) return;
    _loadCalendarFile(btn.dataset.calFile, btn.textContent.replace(/^Load\s+/, ""), btn);
  });

  document.getElementById("cal-list")?.addEventListener("click", async e => {
    const btn = e.target.closest(".cal-remove-btn");
    if (!btn) return;
    const key = btn.dataset.calKey;
    if (!confirm(`Remove "${key}" from your active calendars?`)) return;
    btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("source", key);
      const d = await fetch("/api/calendar/clear", { method: "POST", body: fd }).then(r => r.json());
      if (d.ok) {
        setCalStatus(calOpStatus, "Calendar removed.", "ok");
        const cd = await fetch("/api/calendar").then(r => r.json());
        if (cd.ok) _renderCalendars(cd.calendars);
      } else {
        btn.disabled = false;
        setCalStatus(calOpStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } catch { btn.disabled = false; }
  });

  // Client-side CSV parse (mirrors the server-side logic for preview)
  function _parseDate(s) {

  loadAiTaFiles();
    s = (s || "").trim();
    // MM/DD/YYYY
    const m1 = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m1) return `${m1[3]}-${m1[1].padStart(2,"0")}-${m1[2].padStart(2,"0")}`;
    // YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    return null;
  }

  function _expandRange(start, end) {
    const dates = [];
    const s = new Date(start + "T12:00:00");
    const e = new Date(end   + "T12:00:00");
    if (isNaN(s) || isNaN(e)) return dates;
    for (let d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) {
      dates.push(d.toISOString().slice(0, 10));
    }
    return dates;
  }

  let _parsedCalDates   = null;
  let _parsedCalPeriods = null;
  let _parsedCalSource  = null;

  document.getElementById("btn-cal-parse")?.addEventListener("click", function () {
    const raw = document.getElementById("cal-csv-input")?.value || "";
    const lines = raw.split(/\r?\n/).filter(Boolean);
    const preview = document.getElementById("cal-parse-preview");
    const saveBtn = document.getElementById("btn-cal-save");
    _parsedCalDates   = null;
    _parsedCalPeriods = null;
    _parsedCalSource  = null;
    if (saveBtn) saveBtn.hidden = true;
    if (preview) preview.hidden = true;
    setCalStatus(calCustomStatus, "", "");

    if (!lines.length) {
      setCalStatus(calCustomStatus, "Paste some CSV content first.", "error");
      return;
    }

    const _NO_SCHOOL_TYPES = new Set(["holiday", "no school for students",
                                      "holiday for students/teachers"]);

    // Detect canonical 7-col (school_year,row_type,...) vs simple 4-col (Category,...)
    const headerLow = lines[0].toLowerCase();
    const canonical = headerLow.includes("row_type") && headerLow.includes("start_date");

    const allDates    = [];
    const dayOffRows  = [];
    const periodRows  = [];
    for (let i = 1; i < lines.length; i++) {
      const parts = lines[i].split(",").map(s => s.trim().replace(/^["']|["']$/g, ""));
      if (canonical) {
        // school_year[0], row_type[1], code[2], name[3], start_date[4], end_date[5]
        if (parts.length < 6) continue;
        const rowType = (parts[1] || "").toLowerCase();
        const code    = parts[2] || "";
        const name    = parts[3] || "";
        const s = _parseDate(parts[4]);
        const e = _parseDate(parts[5]);
        if (!s || !e) continue;
        if (_NO_SCHOOL_TYPES.has(rowType)) {
          const expanded = _expandRange(s, e);
          allDates.push(...expanded);
          dayOffRows.push({ name: name || parts[1], start: s, end: e, count: expanded.length });
        } else if (rowType === "academic period") {
          periodRows.push({ name, code, start: s, end: e });
        }
      } else {
        if (parts.length < 4) continue;
        const [cat, name, startDate, endDate] = parts;
        const catLow = cat.toLowerCase();
        const s = _parseDate(startDate);
        const e = _parseDate(endDate);
        if (!s || !e) continue;
        if (catLow.includes("student day off") || catLow.includes("no school")) {
          const expanded = _expandRange(s, e);
          allDates.push(...expanded);
          dayOffRows.push({ name, start: s, end: e, count: expanded.length });
        } else if (catLow.includes("academic period")) {
          periodRows.push({ name, code: "", start: s, end: e });
        }
      }
    }

    if (!dayOffRows.length && !periodRows.length) {
      const hint = canonical
        ? 'No "Holiday", "No School for Students", or "Academic Period" rows found. Check row_type column spelling.'
        : 'No "Student Day Off" or "Academic Period" rows found. Check Category column spelling.';
      setCalStatus(calCustomStatus, hint, "error");
      return;
    }

    const uniq = [...new Set(allDates)].sort();
    _parsedCalDates   = uniq;
    _parsedCalPeriods = periodRows;
    _parsedCalSource  = "Custom CSV";

    const dayHtml = dayOffRows.map(r =>
      `<div style="padding:3px 0; border-bottom:1px solid var(--line)">` +
      `<strong>${esc(r.name)}</strong> — ${esc(r.start)} to ${esc(r.end)} ` +
      `<span class="muted">(${r.count} day${r.count === 1 ? "" : "s"})</span></div>`
    ).join("");
    const perHtml = periodRows.length
      ? `<div style="margin-top:10px"><strong>${periodRows.length} grading period(s):</strong>` +
        periodRows.map(r =>
          `<div style="padding:3px 0; border-bottom:1px solid var(--line)">` +
          `<strong>${esc(r.name)}</strong> — ${esc(r.start)} to ${esc(r.end)}</div>`
        ).join("") + "</div>"
      : "";
    if (preview) {
      preview.innerHTML =
        `<strong>${uniq.length} holiday date(s) across ${dayOffRows.length} break(s):</strong>` +
        `<div style="margin-top:8px">${dayHtml}</div>${perHtml}`;
      preview.hidden = false;
    }
    if (saveBtn) saveBtn.hidden = false;
    const pNote = periodRows.length ? ` · ${periodRows.length} grading period(s)` : "";
    setCalStatus(calCustomStatus,
      `Parsed: ${uniq.length} no-count date(s)${pNote}. Save to activate.`, "ok");
  });

  document.getElementById("btn-cal-save")?.addEventListener("click", async function () {
    if (!_parsedCalDates || !_parsedCalDates.length) return;
    const btn = this;
    btn.disabled = true;
    setCalStatus(calCustomStatus, "Saving…", "");
    try {
      const d = await fetch("/api/calendar/set", {
        method: "POST",
        body: new URLSearchParams({
          source:          _parsedCalSource || "Custom CSV",
          dates:           JSON.stringify(_parsedCalDates),
          grading_periods: JSON.stringify(_parsedCalPeriods || []),
        }),
      }).then(r => r.json());
      if (d.ok) {
        const pNote = (_parsedCalPeriods || []).length
          ? ` · ${_parsedCalPeriods.length} grading period(s)` : "";
        setCalStatus(calCustomStatus, `✓ Saved ${_parsedCalDates.length} date(s)${pNote}.`, "ok");
        const cd = await fetch("/api/calendar").then(r => r.json());
        if (cd.ok) _renderCalendars(cd.calendars);
        setCalStatus(calOpStatus, "", "");
      } else {
        setCalStatus(calCustomStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } finally { btn.disabled = false; }
  });

  // ── LLM prompt copy ────────────────────────────────────────────────────

  document.getElementById("btn-copy-llm-prompt")?.addEventListener("click", async function () {
    const text = document.getElementById("llm-prompt-text")?.value || "";
    try {
      await navigator.clipboard.writeText(text);
      const orig = this.textContent;
      this.textContent = "Copied!";
      setTimeout(() => { this.textContent = orig; }, 1800);
    } catch {
      document.getElementById("llm-prompt-text")?.select();
    }
  });

  // ── Helpers ────────────────────────────────────────────────────────────

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
                                    '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
