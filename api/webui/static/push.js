/**
 * push.js — push machinery for the Course Expert.
 *
 * Loaded by course_expert.html. Contains:
 *   - Course checklist / targets wiring
 *   - Assignment groups + modules loaders
 *   - Common helpers (esc, showLog, hideBanner, showBanner, setBusy, postForm)
 *   - localToISO, collectSettings
 *   - streamSSE, _renderBanner, pushContent
 *   - loadRubricFiles, syncRubricControls
 *   - Quiz validate/preview/push + variant rows
 *   - AF/PF/RF validate + push handlers
 *   - Download handlers
 *   - loadCourseFolder, open/change folder
 */
(function () {
  "use strict";

  // ── DOM refs ───────────────────────────────────────────────────────────
  const checklist   = document.getElementById("course-checklist");
  const fileSel     = document.getElementById("quizfile");
  const result      = document.getElementById("result");
  const variantRows = document.getElementById("variant-rows");
  const groupStatus = document.getElementById("groups-status");
  const afRubricSel = document.getElementById("af-rubric");
  const afRubricControls = document.getElementById("af-rubric-controls");
  const afRubricMode = document.getElementById("af-rubric-mode");
  const afRubricLink = document.getElementById("af-rubric-link");
  const afRubricStatus = document.getElementById("af-rubric-status");
  const rfFileSel = document.getElementById("rf-file");

  // ── State ──────────────────────────────────────────────────────────────
  let canvasCategories = [];

  // ── Helpers ────────────────────────────────────────────────────────────

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",
                                    '"':"&quot;","'":"&#39;" }[c]));
  }

  // expose for inline scripts
  window.esc = esc;

  function focusedRow() { return checklist?.querySelector(".cc-row.focused"); }
  function currentCourseId()   { return focusedRow()?.dataset.id   || ""; }
  function currentCourseName() { return focusedRow()?.dataset.name || ""; }

  function targetCourses() {
    return [...(checklist?.querySelectorAll(".cc-cb:checked") || [])]
      .map(cb => ({ id: cb.value, name: cb.dataset.name }));
  }

  function showLog(el) {
    el.hidden = false;
    el.textContent = "";
    return (line) => { el.textContent += line + "\n"; el.scrollTop = el.scrollHeight; };
  }

  function hideBanner(el) { if (el) { el.hidden = true; el.className = "push-banner"; el.innerHTML = ""; } }

  function showBanner(el, kind, html) {
    if (!el) return;
    el.hidden = false;
    el.className = "push-banner " + kind;
    el.innerHTML = html;
  }

  function setRubricStatus(msg, kind) {
    if (!afRubricStatus) return;
    afRubricStatus.textContent = msg || "";
    afRubricStatus.className = kind ? `hint ${kind}` : "hint";
  }

  function syncRubricControls() {
    const hasRubric = !!afRubricSel?.value;
    if (afRubricControls) afRubricControls.hidden = !hasRubric;
    if (hasRubric) {
      if (afRubricMode && !afRubricMode.value) afRubricMode.value = "grading";
      if (afRubricLink && afRubricLink.checked == null) afRubricLink.checked = true;
    }
  }

  const allBusyBtns = "#btn-validate,#btn-preview,#btn-push,#btn-push-variants,#btn-add-variant";

  function setBusy(v) {
    document.querySelectorAll(allBusyBtns).forEach(b => { b.disabled = v; });
  }

  async function postForm(url, fields) {
    return fetch(url, { method: "POST", body: new URLSearchParams(fields) })
      .then(r => r.json());
  }
  window.postForm = postForm;

  async function loadRubricFiles() {
    if (!afRubricSel && !rfFileSel) return;
    try {
      const data = await fetch("/api/rf/files").then(r => r.json());
      const files = data.files || [];
      if (afRubricSel) {
        const current = afRubricSel.value;
        afRubricSel.innerHTML = '<option value="">No rubric</option>';
        files.forEach(f => afRubricSel.appendChild(new Option(f.label, f.path)));
        if (current) afRubricSel.value = current;
      }
      if (rfFileSel) {
        const currentRf = rfFileSel.value;
        rfFileSel.innerHTML = '<option value="">— select —</option>';
        files.forEach(f => rfFileSel.appendChild(new Option(f.label, f.path)));
        if (currentRf) rfFileSel.value = currentRf;
      }
      syncRubricControls();
    } catch (e) {
      setRubricStatus("Could not load rubric files", "error");
    }
  }

  /** Convert datetime-local string to ISO 8601 with local offset. */
  function localToISO(val) {
    if (!val) return "";
    const d = new Date(val);
    if (isNaN(d)) return "";
    const off  = -d.getTimezoneOffset();
    const sign = off >= 0 ? "+" : "-";
    const ohh  = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0");
    const omm  = String(Math.abs(off) % 60).padStart(2, "0");
    const p    = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T` +
           `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}` +
           `${sign}${ohh}:${omm}`;
  }
  window.localToISO = localToISO;

  function collectSettings() {
    const s = {};
    const due    = localToISO(document.getElementById("due-at")?.value);
    const unlock = localToISO(document.getElementById("unlock-at")?.value);
    const lock   = localToISO(document.getElementById("lock-at")?.value);
    const agSel  = document.getElementById("assignment-group-select");
    const modSel = document.getElementById("module-select");
    const pub    = document.getElementById("publish-now")?.checked;
    const sis    = document.getElementById("post-to-sis")?.checked;
    const shufA  = document.getElementById("shuffle-answers");
    const shufQ  = document.getElementById("shuffle-questions");
    if (due)    s.due_at = due;
    if (unlock) s.unlock_at = unlock;
    if (lock)   s.lock_at = lock;
    if (agSel?.value) s.assignment_group_name = agSel.selectedOptions[0].text;
    if (modSel?.value === "__new__") {
      const name = document.getElementById("new-module-name")?.value.trim();
      if (name) s.module_name = name;
    } else if (modSel?.value) {
      s.module_name = modSel.selectedOptions[0].text;
    }
    if (sis)    s.post_to_sis = true;
    if (pub)    s.published = true;
    if (shufA) s.shuffle_answers   = shufA.checked;
    if (shufQ) s.shuffle_questions = shufQ.checked;
    if (document.getElementById("hide-results")?.checked) s.hide_results = true;
    if (document.getElementById("access-code-enable")?.checked) {
      const code = document.getElementById("access-code")?.value.trim();
      if (code) s.access_code = code;
    }
    if (document.getElementById("allow-attempts")?.checked) {
      s.allow_multiple_attempts = true;
      s.allowed_attempts        = document.getElementById("allowed-attempts")?.value ?? -1;
      s.score_to_keep           = document.getElementById("score-to-keep")?.value ?? "highest";
      const cd = parseInt(document.getElementById("attempt-cooldown")?.value || "0", 10);
      if (cd > 0) s.attempt_cooldown = cd;
      if (document.getElementById("build-on-last")?.checked) s.build_on_last_attempt = true;
    }
    if (document.getElementById("has-time-limit")?.checked) {
      const mins = parseInt(document.getElementById("time-limit-minutes")?.value || "0", 10);
      if (mins > 0) { s.has_time_limit = true; s.time_limit_minutes = mins; }
    }
    if (document.getElementById("one-at-a-time")?.checked) {
      s.one_at_a_time = true;
      s.allow_backtracking = document.getElementById("allow-backtracking")?.checked ?? true;
    }
    const calc = document.getElementById("calculator-type")?.value;
    if (calc && calc !== "none") s.calculator_type = calc;
    return Object.keys(s).length ? JSON.stringify(s) : "";
  }

  // ── SSE streaming ──────────────────────────────────────────────────────

  function streamSSE(url, logFn, bannerEl, onDone) {
    hideBanner(bannerEl);
    let canvasUrl = null;
    let resultLines = [];
    const es = new EventSource(url);
    es.onmessage = ev => {
      const line = JSON.parse(ev.data);
      if (line.startsWith("  CANVAS_URL: ")) {
        canvasUrl = line.slice("  CANVAS_URL: ".length).trim();
        return;
      }
      if (line.startsWith("  PUSH_OK: ")) {
        const title = line.slice("  PUSH_OK: ".length).trim();
        resultLines.push({ ok: true, title, url: canvasUrl });
        canvasUrl = null;
        logFn(line);
        return;
      }
      if (line.startsWith("  PUSH_WARN: ")) {
        const msg = line.slice("  PUSH_WARN: ".length).trim();
        resultLines.push({ ok: false, title: msg, url: canvasUrl });
        canvasUrl = null;
        logFn(line);
        return;
      }
      logFn(line);
      if (/^\[exit \d+\]$/.test(line)) {
        es.close();
        _renderBanner(bannerEl, resultLines, line === "[exit 0]");
        onDone?.(line === "[exit 0]");
      }
    };
    es.onerror = () => { es.close(); onDone?.(false); };
  }

  // ── Printable (PDF + DOCX) version: reuses the zero-auth engine via the backend ─
  async function generatePhysical(path, logFn, bannerEl) {
    logFn("\nGenerating printable version (PDF + DOCX)…");
    try {
      const d = await postForm("/api/physical/quiz", { path });
      if (!d.ok) { logFn("⚠ Printable version failed: " + (d.error || "unknown error")); return; }
      logFn("✓ Printable version saved to: " + d.folder);
      (d.files || []).forEach(f => logFn("    · " + f));
      (d.warnings || []).forEach(w => logFn("    ⚠ " + w));
      if (d.fallback) logFn("    (No OneDrive workspace found — saved to this PC's local Finished_Exports folder.)");
      if (bannerEl) {
        const prev = bannerEl.hidden ? "" : bannerEl.innerHTML;
        const note = d.fallback
          ? `<br><span class="hint">No OneDrive workspace found — saved to this PC at the path above.</span>`
          : "";
        showBanner(bannerEl, bannerEl.classList.contains("fail") ? "warn" : "ok",
          (prev ? prev + "<br>" : "") +
          `📄 Printable PDF + DOCX saved to <code>${esc(d.folder)}</code> — ` +
          `<a href="#" data-open-folder="${esc(d.folder)}">Open folder ↗</a>` + note);
        bannerEl.querySelector("[data-open-folder]")?.addEventListener("click", async e => {
          e.preventDefault();
          const r = await postForm("/api/open-path", { path: d.folder });
          if (r && r.ok === false) logFn("⚠ Could not open folder automatically — it's at: " + d.folder);
        });
      }
    } catch (e) {
      logFn("⚠ Printable version failed: " + e);
    }
  }

  function _renderBanner(el, results, exitOk) {
    if (!el) return;
    if (!results.length && !exitOk) {
      showBanner(el, "fail", "✗ Push failed — check the log above.");
      return;
    }
    if (!results.length) return;
    const allOk = results.every(r => r.ok);
    const kind = allOk && exitOk ? "ok" : "warn";
    const lines = results.map(r => {
      const link = r.url
        ? ` — <a href="${esc(r.url)}" target="_blank" rel="noopener">Open in Canvas ↗</a>`
        : "";
      const icon = r.ok ? "✓" : "⚠";
      return `${icon} <strong>${esc(r.title)}</strong>${link}`;
    }).join("<br>");
    showBanner(el, kind, lines);
  }

  // ── Module/aggroup helpers ─────────────────────────────────────────────

  function moduleChoice(selId) {
    const sel = document.getElementById(selId);
    if (!sel || !sel.value) return "";
    if (sel.value === "__new__") {
      return sel.closest("label")?.querySelector(".js-new-module")?.value.trim() || "";
    }
    return sel.selectedOptions[0].text;
  }

  function pushContent(kind, payload, logEl, bannerEl, btn, confirmLabel) {
    const targets = targetCourses();
    if (!targets.length) return alert("Check at least one course on the right.");
    const list = targets.map(t => `  • ${t.name} (#${t.id})`).join("\n");
    if (!confirm(
      `${confirmLabel}\n\nin ${targets.length} course(s):\n${list}\n\n` +
      `Canvas: ${window.QF_CANVAS_BASE}\n\nContinue?`
    )) return;
    const log = showLog(logEl);
    hideBanner(bannerEl);
    btn.disabled = true;
    log("Pushing…\n");
    postForm("/api/content/push", {
      kind,
      courses: JSON.stringify(targets),
      payload: JSON.stringify(payload),
    }).then(d => {
      if (d.error) {
        log("ERROR: " + d.error);
        showBanner(bannerEl, "fail", "✗ " + esc(d.error));
        return;
      }
      const results = d.results || [];
      results.forEach(r => {
        log(`${r.ok ? "✓" : "✗"} ${r.course_name}: ${r.ok ? r.title : (r.error || "failed")}`);
        (r.notes || []).forEach(n => log("    · " + n));
      });
      _renderBanner(bannerEl, results.map(r => ({
        ok:    r.ok,
        title: `${r.course_name} — ${r.ok ? r.title : (r.error || "failed")}`,
        url:   r.url,
      })), d.ok);
    }).catch(e => {
      log("ERROR: " + e);
      showBanner(bannerEl, "fail", "✗ " + esc(String(e)));
    }).finally(() => { btn.disabled = false; });
  }
  window.pushContent = pushContent;

  function loadAssignmentGroups(courseId) {
    const sels  = [...document.querySelectorAll(".js-aggroups")];
    const hints = [...document.querySelectorAll(".js-ag-hint")];
    if (!sels.length || !courseId) return;
    sels.forEach(sel => {
      sel.disabled = true;
      while (sel.options.length > 1) sel.remove(1);
    });
    hints.forEach(h => { h.textContent = "Loading…"; });
    fetch(`/api/assignment-groups?course_id=${encodeURIComponent(courseId)}`)
      .then(r => r.json())
      .then(d => {
        sels.forEach(sel => { sel.disabled = false; });
        if (!d.ok) { hints.forEach(h => { h.textContent = "Could not load categories"; }); return; }
        hints.forEach(h => { h.textContent = ""; });
        sels.forEach(sel => {
          (d.groups || []).forEach(g => sel.appendChild(new Option(g.name, g.id)));
          const daily = [...sel.options].find(o => o.text.trim().toLowerCase() === "daily");
          if (daily) sel.value = daily.value;
        });
      })
      .catch(() => sels.forEach(sel => { sel.disabled = false; }));
  }

  function fillModuleSelect(sel, mods) {
    const defNone = sel.dataset.default === "none";
    sel.innerHTML = "";
    if (defNone) sel.appendChild(new Option("— don't add to a module —", ""));
    mods.forEach(m => sel.appendChild(new Option(m.name, String(m.id))));
    sel.appendChild(new Option("＋ Create new module…", "__new__"));
    if (!defNone) sel.appendChild(new Option("— don't add to a module —", ""));
    sel.value = defNone ? "" : (mods.length ? String(mods[0].id) : "");
    sel.disabled = false;
    const nm = sel.closest("label")?.querySelector(".js-new-module");
    if (nm) nm.style.display = "none";
  }

  function loadModules(courseId) {
    const sels  = [...document.querySelectorAll(".js-modules")];
    const hints = [...document.querySelectorAll(".js-mod-hint")];
    if (!sels.length || !courseId) return;
    sels.forEach(s => { s.disabled = true; });
    hints.forEach(h => { h.textContent = "Loading…"; });
    fetch(`/api/modules?course_id=${encodeURIComponent(courseId)}`)
      .then(r => r.json())
      .then(d => {
        const mods = (d.ok && d.modules) ? d.modules : [];
        sels.forEach(s => fillModuleSelect(s, mods));
        hints.forEach(h => { h.textContent = d.ok ? "" : "Could not load modules"; });
      })
      .catch(() => sels.forEach(s => { s.disabled = false; }));
  }

  document.addEventListener("change", e => {
    const sel = e.target.closest(".js-modules");
    if (!sel) return;
    const nameInput = sel.closest("label")?.querySelector(".js-new-module");
    if (!nameInput) return;
    nameInput.style.display = sel.value === "__new__" ? "" : "none";
    if (sel.value === "__new__") nameInput.focus();
  });

  // ── Course checklist / targets ─────────────────────────────────────────

  function renderTargets() {
    const checked = [...(checklist?.querySelectorAll(".cc-cb:checked") || [])];
    const cnt = document.getElementById("target-count");
    if (cnt) cnt.textContent = checked.length ? `· ${checked.length} selected` : "";
    const sum = document.getElementById("ci-targets");
    if (sum) {
      if (checked.length > 1) {
        const names = checked.map(cb =>
          cb.closest(".cc-row").querySelector(".cc-focus").textContent);
        sum.hidden = false;
        sum.innerHTML = `<strong>Pushing to ${checked.length} courses:</strong> ` +
          names.map(esc).join(", ");
      } else {
        sum.hidden = true;
        sum.textContent = "";
      }
    }
    const _label = document.getElementById("ce-picker-label");
    if (_label) {
      const fn = focusedRow()?.querySelector(".cc-focus")?.textContent?.trim();
      if (!checked.length)            _label.textContent = "— pick courses —";
      else if (checked.length === 1)  _label.textContent = fn || "1 selected";
      else                            _label.textContent = (fn ? fn + " " : "") + "· " + checked.length + " selected";
    }
  }

  function setFocus(id) {
    if (!checklist || !id) return;
    checklist.querySelectorAll(".cc-row")
      .forEach(r => r.classList.toggle("focused", r.dataset.id === id));
    const name = currentCourseName();
    loadAssignmentGroups(id);
    loadModules(id);
    loadCourseFolder(name);
    const ciLink = document.getElementById("course-info-link");
    if (ciLink) ciLink.href = "/course?course_id=" + encodeURIComponent(id);
    canvasCategories = [];
    if (groupStatus) groupStatus.textContent = "";
    renderTargets();
  }

  async function renameCourse(btn) {
    const id = btn.dataset.id, name = btn.dataset.name;
    const next = prompt(`Nickname for "${name}":`, btn.dataset.nick || "");
    if (next == null) return;
    const nick = next.trim();
    if (!nick) return;
    const d = await postForm("/settings/courses/bookmark",
      { course_id: id, course_name: name, nickname: nick });
    if (d.ok) {
      btn.dataset.nick = nick;
      const focusBtn = btn.closest(".cc-row")?.querySelector(".cc-focus");
      if (focusBtn) focusBtn.textContent = nick;
    }
  }

  if (checklist) {
    checklist.addEventListener("click", e => {
      const fb = e.target.closest(".cc-focus");
      if (fb) {
        const row = fb.closest(".cc-row");
        const cb  = row.querySelector(".cc-cb");
        if (cb && !cb.checked) cb.checked = true;
        setFocus(row.dataset.id);
        return;
      }
      const rb = e.target.closest(".cc-rename");
      if (rb) { renameCourse(rb); return; }
    });
    checklist.addEventListener("change", e => {
      if (!e.target.classList.contains("cc-cb")) return;
      const focused = checklist.querySelector(".cc-row.focused");
      const focusedChecked = focused && focused.querySelector(".cc-cb").checked;
      if (!focusedChecked) {
        const first = checklist.querySelector(".cc-cb:checked");
        if (first) setFocus(first.value);
        else renderTargets();
      } else {
        renderTargets();
      }
    });
    const first = checklist.querySelector(".cc-row");
    if (first) {
      const cb = first.querySelector(".cc-cb");
      if (cb) cb.checked = true;
      setFocus(first.dataset.id);
    }

    // All courses load below the bookmarked (★) ones; same row structure,
    // so the delegated click/change handlers above just work.
    (async function loadAllCoursesIntoChecklist() {
      try {
        const d = await fetch("/api/courses").then(r => r.json());
        if (!d.ok || !d.courses?.length) return;   // offline/no token → bookmarks only
        const have = new Set([...checklist.querySelectorAll(".cc-row")].map(r => r.dataset.id));
        const extras = d.courses.filter(c => !have.has(c.id));
        if (!extras.length) return;
        const div = document.createElement("div");
        div.className = "cc-all-divider";
        div.textContent = "All courses";
        checklist.appendChild(div);
        extras.forEach(c => {
          const row = document.createElement("div");
          row.className = "cc-row";
          row.dataset.id = c.id;
          row.dataset.name = c.name;
          row.innerHTML =
            `<input type="checkbox" class="cc-cb" value="${esc(c.id)}" data-name="${esc(c.name)}">` +
            `<button type="button" class="cc-focus" title="Focus this course">${esc(c.name)}</button>`;
          checklist.appendChild(row);
        });
      } catch (e) { /* keep bookmarks only */ }
    })();
  }

  // ── Quiz push ──────────────────────────────────────────────────────────

  document.getElementById("btn-validate")?.addEventListener("click", async () => {
    const path = fileSel?.value;
    if (!path) return alert("Pick a quiz file first.");
    const log = showLog(result);
    hideBanner(document.getElementById("push-banner"));
    log("Validating…");
    const data = await postForm("/api/validate", { path });
    if (data.error) { log("ERROR: " + data.error); return; }
    if (data.ok) {
      log("✓ No compliance issues found.");
      showBanner(document.getElementById("push-banner"), "ok", "✓ Validation passed — quiz is ready to push.");
    } else {
      log(data.problems.map(p => "  ✗ " + p).join("\n"));
      showBanner(document.getElementById("push-banner"), "fail",
        `✗ ${data.problems.length} issue(s) found — see log above.`);
    }
  });

  document.getElementById("btn-preview")?.addEventListener("click", async () => {
    const id   = currentCourseId();
    const path = fileSel?.value;
    if (!id)   return alert("Choose a course first.");
    if (!path) return alert("Pick a quiz file first.");
    const log = showLog(result);
    hideBanner(document.getElementById("push-banner"));
    log("Building dry-run preview (no live Canvas calls)…");
    setBusy(true);
    try {
      const settings = collectSettings();
      const data = await postForm("/api/push/preview", { course_id: id, path, settings });
      log(data.error ? "ERROR: " + data.error : data.output);
    } finally { setBusy(false); }
  });

  document.getElementById("btn-push")?.addEventListener("click", () => {
    const targets = targetCourses();
    const path    = fileSel?.value;
    if (!targets.length) return alert("Check at least one course on the right.");
    if (!path)           return alert("Pick a quiz file first.");
    const fname = path.split(/[\\/]/).pop();
    const list  = targets.map(t => `  • ${t.name} (#${t.id})`).join("\n");
    if (!confirm(
      `Create a LIVE, UNPUBLISHED quiz from:\n  "${fname}"\n\n` +
      `in ${targets.length} course(s):\n${list}\n\n` +
      `Canvas: ${window.QF_CANVAS_BASE}\n\nContinue?`
    )) return;
    const log = showLog(result);
    hideBanner(document.getElementById("push-banner"));
    setBusy(true);
    const settings = encodeURIComponent(collectSettings());
    let url;
    if (targets.length === 1) {
      log("Pushing live quiz…\n");
      url = `/api/push/stream?course_id=${encodeURIComponent(targets[0].id)}` +
            `&path=${encodeURIComponent(path)}&settings=${settings}`;
    } else {
      log(`Pushing live quiz to ${targets.length} courses…\n`);
      const ids = targets.map(t => t.id).join(",");
      url = `/api/push-multi-whole/stream?course_ids=${encodeURIComponent(ids)}` +
            `&path=${encodeURIComponent(path)}&settings=${settings}`;
    }
    const wantPhysical = document.getElementById("physical-version")?.checked;
    streamSSE(url, log, document.getElementById("push-banner"), (ok) => {
      setBusy(false);
      if (ok && wantPhysical) generatePhysical(path, log, document.getElementById("push-banner"));
    });
  });

  // ── Variant rows ───────────────────────────────────────────────────────

  const fileOptions = window.QF_QUIZ_FILES || window.QF_FILES || [];

  function allGroupOptions() {
    return canvasCategories.flatMap(cat =>
      cat.groups.map(g => ({ ...g, cat_name: cat.category_name }))
    );
  }

  function addVariantRow(path, groupId) {
    const row = document.createElement("div");
    row.className = "variant-row";
    const groups = allGroupOptions();
    const gw = document.createElement("label");
    gw.textContent = "Canvas group";
    const gs = document.createElement("select");
    gs.className = "variant-group";
    if (!groups.length) {
      gs.appendChild(Object.assign(document.createElement("option"),
        { value: "", textContent: "— check a course to load groups —" }));
      gs.disabled = true;
    } else {
      groups.forEach(g => {
        const o = document.createElement("option");
        o.value = g.id;
        o.textContent = `${g.name} (${g.student_ids.length}) — ${g.cat_name}`;
        o.dataset.studentIds = JSON.stringify(g.student_ids);
        o.dataset.groupName  = g.name;
        if (g.id == groupId) o.selected = true;
        gs.appendChild(o);
      });
    }
    gw.appendChild(gs);
    const fileWrap = document.createElement("label");
    fileWrap.textContent = "Quiz file";
    const fileSl = document.createElement("select");
    fileSl.className = "variant-file";
    fileSl.appendChild(Object.assign(document.createElement("option"), { value: "", textContent: "— select —" }));
    fileOptions.forEach(f => {
      const o = document.createElement("option");
      o.value = f.path; o.textContent = f.label;
      if (f.path === path) o.selected = true;
      fileSl.appendChild(o);
    });
    fileWrap.appendChild(fileSl);
    row.appendChild(gw);
    row.appendChild(fileWrap);
    const rm = document.createElement("button");
    rm.type = "button"; rm.className = "small danger variant-remove";
    rm.textContent = "✕"; rm.title = "Remove this row";
    rm.addEventListener("click", () => row.remove());
    row.appendChild(rm);
    variantRows?.appendChild(row);
  }

  function rebuildVariantRows() {
    const existing = [...(variantRows?.querySelectorAll(".variant-row") || [])].map(r => ({
      path:    r.querySelector(".variant-file")?.value  || "",
      groupId: r.querySelector(".variant-group")?.value || "",
    }));
    if (variantRows) variantRows.innerHTML = "";
    const groups = allGroupOptions();
    if (groups.length) {
      groups.forEach(g => {
        const prev = existing.find(e => e.groupId == g.id);
        addVariantRow(prev?.path || "", g.id);
      });
    } else if (existing.length) {
      existing.forEach(e => addVariantRow(e.path, e.groupId));
    } else {
      addVariantRow("", "");
    }
  }

  async function loadGroupsForCurrentCourse() {
    const id = currentCourseId();
    if (!id || !groupStatus) return;
    groupStatus.className = "status hint";
    groupStatus.textContent = "Loading groups…";
    setBusy(true);
    try {
      const data = await fetch(`/api/groups?course_id=${encodeURIComponent(id)}`).then(r => r.json());
      if (!data.ok) {
        groupStatus.className = "status error";
        groupStatus.textContent = "Error: " + data.error;
        return;
      }
      canvasCategories = data.categories || [];
      if (!canvasCategories.length) {
        groupStatus.className = "status hint";
        groupStatus.textContent = data.message || "No group sets found in this course.";
        rebuildVariantRows();
        return;
      }
      const summary = canvasCategories.map(c =>
        `${c.category_name}: ` + c.groups.map(g => `${g.name} (${g.student_ids.length})`).join(", ")
      ).join(" · ");
      groupStatus.className = "status ok";
      groupStatus.textContent = "✓ Loaded: " + summary;
      rebuildVariantRows();
    } finally { setBusy(false); }
  }
  window.QF_loadGroups = loadGroupsForCurrentCourse;

  document.getElementById("btn-add-variant")?.addEventListener("click", () => addVariantRow("", ""));

  document.getElementById("btn-push-variants")?.addEventListener("click", () => {
    const targets = targetCourses();
    if (!targets.length) return alert("Check at least one course on the right.");
    const rows = variantRows ? [...variantRows.querySelectorAll(".variant-row")] : [];
    const variants = rows.map(r => ({
      path:        r.querySelector(".variant-file")?.value || "",
      groupId:     r.querySelector(".variant-group")?.value || "",
      groupName:   r.querySelector(".variant-group")?.selectedOptions[0]?.dataset.groupName || "",
      studentIds:  JSON.parse(r.querySelector(".variant-group")?.selectedOptions[0]?.dataset.studentIds || "[]"),
    })).filter(v => v.path);
    if (variants.length < 2) return alert("Add at least 2 tier rows with files selected.");

    const log = showLog(document.getElementById("variants-result"));
    hideBanner(document.getElementById("variants-banner"));
    setBusy(true);

    const list = targets.map(t => `  • ${t.name} (#${t.id})`).join("\n");
    const varList = variants.map(v => `  • ${v.groupName}: ${v.path.split(/[\\/]/).pop()}`).join("\n");
    if (!confirm(
      `Push ${variants.length} tier variants to ${targets.length} course(s):\n${list}\n\nVariants:\n${varList}\n\nContinue?`
    )) { setBusy(false); return; }

    if (targets.length === 1) {
      const t = targets[0];
      const entries = variants.map(v => ({
        label:       v.groupName,
        path:        v.path,
        student_ids: v.studentIds,
        group_name:  v.groupName,
      }));
      log("Pushing variants…\n");
      streamSSE(
        `/api/push-variants/stream?course_id=${encodeURIComponent(t.id)}` +
        `&manifest=${encodeURIComponent(JSON.stringify(entries))}`,
        log, document.getElementById("variants-banner"), () => setBusy(false));
    } else {
      const multiManifest = targets.map(t => ({
        course_id:   t.id,
        course_name: t.name,
        variants:    variants.map(v => ({
          label:       v.groupName,
          path:        v.path,
          student_ids: v.studentIds,
          group_name:  v.groupName,
        })),
      }));
      log(`Pushing variants to ${targets.length} courses…\n`);
      streamSSE(
        `/api/push-multi/stream?multi_manifest=${encodeURIComponent(JSON.stringify(multiManifest))}`,
        log, document.getElementById("variants-banner"), () => setBusy(false));
    }
  });

  // ── AF push ────────────────────────────────────────────────────────────

  afRubricSel?.addEventListener("change", syncRubricControls);

  document.getElementById("btn-af-validate")?.addEventListener("click", function () {
    const path = document.getElementById("af-file")?.value;
    if (!path) return alert("Pick an AssignmentForge file.");
    const log = showLog(document.getElementById("af-log"));
    hideBanner(document.getElementById("af-banner"));
    log("Validating…\n");
    postForm("/api/af/validate", { path }).then(d => {
      if (d.problems?.length) d.problems.forEach(p => log("✗ " + p));
      const s = d.summary;
      if (s) {
        log(`${d.ok ? "✓ VALID" : "✗ INVALID"} — ${s.type}: "${s.title}" (${s.points} pts)`);
        log(`  submission: ${s.submission_types.join(", ")}`);
        if (s.tiers.length) {
          s.tiers.forEach(t => log(`  tier ${t.label} → group "${t.group}"` +
                                   (t.scaffolded ? " (scaffolded)" : "")));
        } else {
          log("  whole-class (no tiers)");
        }
        (s.placeholders || []).forEach(p => log(`  placeholder {{${p}}} — resolved per course at push`));
      }
    }).catch(e => log("ERROR: " + e));
  });

  document.getElementById("btn-af-copy-prompt")?.addEventListener("click", async function () {
    const path = afRubricSel?.value;
    if (!path) return;
    setRubricStatus("Copying…", "");
    try {
      const resp = await fetch(`/api/rf/scoring-prompt?path=${encodeURIComponent(path)}`);
      const text = await resp.text();
      if (!resp.ok) throw new Error(text || "Could not load prompt");
      await navigator.clipboard.writeText(text);
      setRubricStatus("Copied — paste into MagicSchool or Copilot", "ok");
    } catch (e) {
      setRubricStatus(String(e), "error");
    }
  });

  document.getElementById("btn-af-push")?.addEventListener("click", function () {
    const path = document.getElementById("af-file")?.value;
    if (!path) return alert("Pick an AssignmentForge file.");
    const payload = {
      path,
      post_to_sis: document.getElementById("af-sis")?.checked,
      published:   document.getElementById("af-publish")?.checked,
    };
    if (afRubricSel?.value) {
      payload.rubric_path = afRubricSel.value;
      payload.rubric_mode = afRubricMode?.value || "grading";
      payload.rubric_link_page = afRubricLink?.checked !== false;
    }
    const due    = localToISO(document.getElementById("af-due")?.value);
    const unlock = localToISO(document.getElementById("af-unlock")?.value);
    const lock   = localToISO(document.getElementById("af-lock")?.value);
    if (due)    payload.due_at    = due;
    if (unlock) payload.unlock_at = unlock;
    if (lock)   payload.lock_at   = lock;
    const agSel = document.getElementById("af-aggroup");
    if (agSel?.value) payload.assignment_group_name = agSel.selectedOptions[0].text;
    const mod = moduleChoice("af-module");
    if (mod) payload.module_name = mod;
    pushContent("af", payload,
      document.getElementById("af-log"), document.getElementById("af-banner"), this,
      `Push AssignmentForge file "${path.split(/[\\/]/).pop()}"` +
      `${payload.published ? " (PUBLISHED)" : " (unpublished)"}`);
  });

  // ── PF push ────────────────────────────────────────────────────────────

  document.getElementById("btn-pf-validate")?.addEventListener("click", function () {
    const path = document.getElementById("pf-file")?.value;
    if (!path) return alert("Pick a PageForge file.");
    const log = showLog(document.getElementById("pf-log"));
    hideBanner(document.getElementById("pf-banner"));
    log("Validating…\n");
    postForm("/api/pf/validate", { path }).then(d => {
      (d.problems || []).forEach(p => log("✗ " + p));
      const s = d.summary;
      if (s) {
        log(`${d.ok ? "✓ VALID" : "✗ INVALID"} — ${s.type}: "${s.title}"`);
        (s.placeholders || []).forEach(p => log(`  placeholder {{${p}}} — resolved per course at push`));
      }
    }).catch(e => log("ERROR: " + e));
  });

  document.getElementById("btn-pf-push")?.addEventListener("click", function () {
    const path = document.getElementById("pf-file")?.value;
    if (!path) return alert("Pick a PageForge file.");
    const payload = {
      path,
      published: document.getElementById("pf-publish")?.checked,
    };
    const mod = moduleChoice("pf-module");
    if (mod) payload.module_name = mod;
    pushContent("pf", payload,
      document.getElementById("pf-log"), document.getElementById("pf-banner"), this,
      `Push PageForge file "${path.split(/[\\/]/).pop()}"` +
      `${payload.published ? " (PUBLISHED)" : " (unpublished)"}`);
  });

  // ── RF push ────────────────────────────────────────────────────────────

  document.getElementById("btn-rf-validate")?.addEventListener("click", function () {
    const path = document.getElementById("rf-file")?.value;
    if (!path) return alert("Pick a RubricForge file.");
    const log = showLog(document.getElementById("rf-log"));
    hideBanner(document.getElementById("rf-banner"));
    log("Validating…\n");
    postForm("/api/rf/validate", { path }).then(d => {
      (d.problems || []).forEach(p => log("✗ " + p));
      const s = d.summary;
      if (s) {
        log(`${d.ok ? "✓ VALID" : "✗ INVALID"} — ${s.type}: "${s.title}" (${s.total_points} pts)`);
        log(`  criteria: ${s.criteria_count}, rubric ratings: ${s.max_rating_count}`);
      }
    }).catch(e => log("ERROR: " + e));
  });

  document.getElementById("btn-rf-push")?.addEventListener("click", function () {
    const path = document.getElementById("rf-file")?.value;
    if (!path) return alert("Pick a RubricForge file.");
    pushContent("rf", { path },
      document.getElementById("rf-log"), document.getElementById("rf-banner"), this,
      `Push RubricForge file "${path.split(/[\\/]/).pop()}"`);
  });

  // ── Download ────────────────────────────────────────────────────────────

  function _assignmentBadge(types) {
    const t = (types || [])[0] || "";
    if (t === "online_text_entry") return `<span class="badge badge-text">Text</span>`;
    if (t === "online_upload")     return `<span class="badge badge-upload">Upload</span>`;
    if (t === "discussion_topic")  return `<span class="badge badge-disc">Discussion</span>`;
    if (t === "online_url")        return `<span class="badge badge-url">URL</span>`;
    if (t === "external_tool")     return `<span class="badge badge-ext">LTI</span>`;
    return `<span class="badge badge-none">${esc(t || "none")}</span>`;
  }

  let _dlAssignments = [];

  function _updateDlCount() {
    const sel  = [...document.querySelectorAll(".dl-cb:checked:not(:disabled)")];
    const cnt  = document.getElementById("dl-selected-count");
    const btn  = document.getElementById("btn-download-selected");
    const row  = document.getElementById("dl-action-row");
    if (cnt) cnt.textContent = sel.length ? `${sel.length} selected` : "";
    if (btn) btn.textContent = sel.length
      ? `⬇ Download ${sel.length} assignment${sel.length === 1 ? "" : "s"}…`
      : "⬇ Download selected";
    if (row) row.style.display = sel.length ? "" : "none";
  }

  function _applyDlFilter() {
    const typeFilter = document.getElementById("dl-type-filter")?.value || "";
    const fromVal    = document.getElementById("dl-date-from")?.value || "";
    const toVal      = document.getElementById("dl-date-to")?.value   || "";
    let vis = 0;
    document.querySelectorAll("#dl-tbody tr").forEach(tr => {
      const t = tr.dataset.type || "";
      const d = tr.dataset.due  || "";
      const showType = !typeFilter || t === typeFilter;
      const showFrom = !fromVal   || d >= fromVal;
      const showTo   = !toVal     || !d || d <= toVal;
      tr.hidden = !(showType && showFrom && showTo);
      if (!tr.hidden) vis++;
    });
    const vc = document.getElementById("dl-visible-count");
    if (vc) vc.textContent = `${vis} of ${_dlAssignments.length}`;
    _updateDlCount();
  }

  document.getElementById("btn-load-assignments")?.addEventListener("click", async function () {
    const id = currentCourseId();
    if (!id) return alert("Select a course first.");
    this.disabled = true; this.textContent = "Loading…";
    try {
      const data = await fetch(`/api/assignments?course_id=${encodeURIComponent(id)}`).then(r => r.json());
      if (!data.ok) { alert("Error: " + data.error); return; }
      _dlAssignments = data.assignments || [];
      const tbody = document.getElementById("dl-tbody");
      if (tbody) {
        tbody.innerHTML = "";
        _dlAssignments.forEach(a => {
          const canDl = (a.submission_types || []).some(
            t => ["online_text_entry","online_upload","discussion_topic","online_url"].includes(t));
          const tr = document.createElement("tr");
          tr.dataset.type = (a.submission_types || [])[0] || "";
          tr.dataset.due  = (a.due_at || "").slice(0, 10);
          if (!canDl) tr.classList.add("dl-row-dim");
          tr.innerHTML =
            `<td><input type="checkbox" class="dl-cb" value="${esc(a.id)}"` +
            ` data-name="${esc(a.name)}"${canDl ? "" : " disabled"}`+
            ` title="${canDl ? "" : "not downloadable — no text/file submissions"}"></td>` +
            `<td>${esc(a.name)}${a.html_url ? ` <a href="${esc(a.html_url)}" target="_blank" rel="noopener" class="small-link">↗</a>` : ""}</td>` +
            `<td>${_assignmentBadge(a.submission_types)}</td>` +
            `<td>${esc(a.due_at ? new Date(a.due_at).toLocaleDateString() : "—")}</td>` +
            `<td>${esc(a.points != null ? a.points : "—")}</td>`;
          tbody.appendChild(tr);
        });
      }
      const tbl  = document.getElementById("dl-assignment-table");
      const fwrap = document.getElementById("dl-filter-wrap");
      const dbar  = document.getElementById("dl-date-bar");
      if (tbl)   tbl.hidden   = false;
      if (fwrap) fwrap.hidden = false;
      if (dbar)  dbar.hidden  = false;
      _applyDlFilter();
    } finally {
      this.disabled = false;
      this.textContent = "Load assignments…";
    }
  });

  document.getElementById("dl-type-filter")?.addEventListener("change", _applyDlFilter);
  document.getElementById("dl-date-from")?.addEventListener("change",   _applyDlFilter);
  document.getElementById("dl-date-to")?.addEventListener("change",     _applyDlFilter);

  document.querySelectorAll(".dl-presets .chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const preset  = chip.dataset.preset;
      const year    = new Date().getFullYear();
      const fromEl  = document.getElementById("dl-date-from");
      const toEl    = document.getElementById("dl-date-to");
      const chips   = document.querySelectorAll(".dl-presets .chip");
      chips.forEach(c => c.classList.toggle("chip-active", c === chip));
      if (preset === "fall")   { if (fromEl) fromEl.value = `${year}-08-01`; if (toEl) toEl.value = `${year}-12-31`; }
      else if (preset === "spring") { if (fromEl) fromEl.value = `${year}-01-01`; if (toEl) toEl.value = `${year}-05-31`; }
      else if (preset === "30d")  {
        const d = new Date(); d.setDate(d.getDate() - 30);
        if (fromEl) fromEl.value = d.toISOString().slice(0,10);
        if (toEl)   toEl.value   = new Date().toISOString().slice(0,10);
      }
      else if (preset === "90d")  {
        const d = new Date(); d.setDate(d.getDate() - 90);
        if (fromEl) fromEl.value = d.toISOString().slice(0,10);
        if (toEl)   toEl.value   = new Date().toISOString().slice(0,10);
      }
      else { if (fromEl) fromEl.value = ""; if (toEl) toEl.value = ""; }
      _applyDlFilter();
    });
  });

  document.getElementById("dl-check-all")?.addEventListener("change", function () {
    document.querySelectorAll(".dl-cb:not(:disabled)").forEach(cb => {
      if (!cb.closest("tr")?.hidden) cb.checked = this.checked;
    });
    _updateDlCount();
  });

  document.getElementById("btn-dl-select-all")?.addEventListener("click", () => {
    document.querySelectorAll(".dl-cb:not(:disabled)").forEach(cb => {
      if (!cb.closest("tr")?.hidden) cb.checked = true;
    });
    _updateDlCount();
  });

  document.getElementById("btn-dl-clear")?.addEventListener("click", () => {
    document.querySelectorAll(".dl-cb").forEach(cb => cb.checked = false);
    const dca = document.getElementById("dl-check-all");
    if (dca) dca.checked = false;
    _updateDlCount();
  });

  document.getElementById("dl-assignment-table")?.addEventListener("change", e => {
    if (e.target.classList.contains("dl-cb")) _updateDlCount();
  });

  document.getElementById("btn-download-selected")?.addEventListener("click", () => {
    const id   = currentCourseId();
    const name = currentCourseName();
    if (!id) return alert("Choose a course first.");
    const checked = [...document.querySelectorAll(".dl-cb:checked:not(:disabled)")];
    if (!checked.length) return alert("Select at least one assignment.");
    const ids   = checked.map(cb => cb.value).join(",");
    const names = checked.map(cb => cb.dataset.name).join("\n  • ");
    if (!confirm(
      `Download submissions for ${checked.length} assignment(s):\n  • ${names}\n\n` +
      `Course: ${name}\n` +
      `Files will be saved to your configured download folder.\n\nContinue?`
    )) return;
    const log = showLog(document.getElementById("dl-log"));
    hideBanner(document.getElementById("dl-banner"));
    setBusy(true);
    let folderPath = null;
    streamSSE(
      `/api/submissions/download/stream` +
      `?course_id=${encodeURIComponent(id)}` +
      `&course_name=${encodeURIComponent(name)}` +
      `&assignment_ids=${encodeURIComponent(ids)}`,
      (line) => {
        if (line.startsWith("COURSE_FOLDER: ")) {
          folderPath = line.slice("COURSE_FOLDER: ".length).trim();
          return;
        }
        log(line);
      },
      null,
      () => {
        setBusy(false);
        loadCourseFolder(name);
        const banner = document.getElementById("dl-banner");
        if (folderPath) {
          showBanner(banner, "ok",
            `✓ Downloaded — ` +
            `<a href="#" data-open-folder="${esc(folderPath)}">Open folder ↗</a>`);
          banner.querySelector("[data-open-folder]")?.addEventListener("click", async e => {
            e.preventDefault();
            await fetch("/api/open-folder", { method: "POST",
                         body: new URLSearchParams({ path: folderPath }) });
          });
        } else {
          showBanner(banner, "warn", "⚠ Download finished — check log for errors.");
        }
      }
    );
  });

  // ── Folder controls ────────────────────────────────────────────────────

  function loadCourseFolder(courseName) {
    const row  = document.getElementById("folder-row");
    const path = document.getElementById("folder-path");
    const note = document.getElementById("folder-note");
    if (!row || !courseName) return;
    fetch(`/api/course-folder?course_name=${encodeURIComponent(courseName)}`)
      .then(r => r.json())
      .then(d => {
        row.hidden   = false;
        path.textContent = d.path;
        path.title       = d.path;
        note.textContent = d.exists ? "" : "(no downloads yet)";
        document.getElementById("btn-open-folder").dataset.path = d.path;
      })
      .catch(() => {});
  }

  document.getElementById("btn-open-folder")?.addEventListener("click", async function () {
    const p = this.dataset.path;
    if (!p) return;
    const r = await fetch("/api/open-folder", {
      method: "POST", body: new URLSearchParams({ path: p }),
    });
    const d = await r.json();
    if (!d.ok) alert("Could not open folder: " + d.error);
  });

  document.getElementById("btn-change-folder")?.addEventListener("click", async function () {
    const btn = this, orig = btn.textContent;
    btn.disabled = true; btn.textContent = "Choosing…";
    try {
      const d = await fetch("/api/pick-download-folder", { method: "POST" }).then(r => r.json());
      if (d.ok && d.root) {
        loadCourseFolder(currentCourseName());
      } else if (d.error) {
        alert("Could not open the folder picker: " + d.error);
      }
    } finally {
      btn.disabled = false; btn.textContent = orig;
    }
  });

  // ── Init ───────────────────────────────────────────────────────────────

  loadRubricFiles();

})();
