/**
 * push.js — push machinery for the Course Expert.
 *
 * Loaded by course_expert.html. Contains:
 *   - Course checklist / targets wiring
 *   - Assignment groups + modules loaders
 *   - Common helpers (esc, showLog, hideBanner, showBanner, setBusy, postForm)
 *   - localToISO, collectSettings
 *   - streamSSE, _renderBanner, pushContent
 *   - loadRubricFiles, shared rubric controls
 *   - loadCourseFolder
 */
(function () {
  "use strict";

  // ── DOM refs ───────────────────────────────────────────────────────────
  const checklist   = document.getElementById("course-checklist");
  const afRubricSel = document.getElementById("af-rubric");
  const afRubricControls = document.getElementById("af-rubric-controls");
  const afRubricMode = document.getElementById("af-rubric-mode");
  const afRubricLink = document.getElementById("af-rubric-link");
  const afRubricStatus = document.getElementById("af-rubric-status");
  const rfFileSel = document.getElementById("rf-file");

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
  window.targetCourses = targetCourses;

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

  const allBusyBtns = "#btn-validate,#btn-preview,#btn-push,#btn-push-variants,#btn-add-variant,#btn-nf-validate,#btn-nf-generate,#btn-nf-attach";

  function setBusy(v) {
    document.querySelectorAll(allBusyBtns).forEach(b => { b.disabled = v; });
  }

  async function postForm(url, fields) {
    return fetch(url, { method: "POST", body: new URLSearchParams(fields) })
      .then(r => r.json());
  }
  window.postForm = postForm;

  function initFileSource(wrapper) {
    if (!wrapper) return;
    const sel      = wrapper.querySelector("select");
    const pasteEl  = wrapper.querySelector(".file-src-paste");
    const fileInp  = wrapper.querySelector(".file-src-input");
    const hintEl   = wrapper.querySelector(".file-src-hint");
    const srcBtns  = Array.from(wrapper.querySelectorAll(".file-src-btn"));

    function setMode(mode) {
      srcBtns.forEach(b => { b.classList.toggle("active", b.dataset.src === mode); });
      if (sel)     sel.style.display     = mode === "select" ? "" : "none";
      if (pasteEl) pasteEl.style.display = mode === "paste"  ? "" : "none";
      if (mode !== "paste" && hintEl) {
        hintEl.style.display = "none";
        hintEl.textContent = "";
        hintEl.className = "file-src-hint";
      }
    }

    function setTempOption(path, label) {
      if (!sel) return;
      let opt = sel.querySelector("option[data-temp]");
      if (!opt) {
        opt = document.createElement("option");
        opt.dataset.temp = "1";
        sel.appendChild(opt);
      }
      opt.value = path;
      opt.textContent = label;
      sel.value = path;
    }

    async function uploadContent(content) {
      try {
        const r = await fetch("/api/temp-upload", {
          method: "POST",
          body: new URLSearchParams({ content }),
        });
        const d = await r.json();
        return d.ok ? d.path : null;
      } catch (e) {
        return null;
      }
    }

    async function uploadFile(file) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch("/api/temp-upload", { method: "POST", body: fd });
        const d = await r.json();
        return d.ok ? d.path : null;
      } catch (e) {
        return null;
      }
    }

    srcBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.src === "upload") {
          if (fileInp) fileInp.click();
        } else {
          setMode(btn.dataset.src);
        }
      });
    });

    if (fileInp) {
      fileInp.addEventListener("change", async function () {
        const file = this.files[0];
        if (!file) return;
        if (hintEl) {
          hintEl.style.display = "";
          hintEl.className = "file-src-hint";
          hintEl.textContent = "Uploading...";
        }
        const path = await uploadFile(file);
        if (path) {
          setTempOption(path, "Uploaded: " + file.name);
          setMode("select");
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint ok";
            hintEl.textContent = "Ready: " + file.name;
          }
        } else {
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint err";
            hintEl.textContent = "Upload failed.";
          }
          setMode("select");
        }
        this.value = "";
      });
    }

    let timer;
    if (pasteEl) {
      pasteEl.addEventListener("input", () => {
        clearTimeout(timer);
        const val = pasteEl.value.trim();
        if (!val) {
          if (hintEl) hintEl.style.display = "none";
          return;
        }
        timer = setTimeout(async () => {
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint";
            hintEl.textContent = "Saving...";
          }
          const path = await uploadContent(val);
          if (path) {
            setTempOption(path, "Pasted JSON");
            if (hintEl) {
              hintEl.className = "file-src-hint ok";
              hintEl.textContent = "Ready - click Validate or Push";
            }
          } else if (hintEl) {
            hintEl.className = "file-src-hint err";
            hintEl.textContent = "Error saving content.";
          }
        }, 600);
      });
    }
  }
  window.initFileSource = initFileSource;

  async function copySkill(name, btn) {
    if (!name || !btn) return;
    const orig = btn.textContent;
    btn.textContent = "Copying...";
    btn.disabled = true;
    try {
      const r = await fetch("/api/ai-ta/file?name=" + encodeURIComponent(name));
      if (!r.ok) throw new Error("skill not found");
      await navigator.clipboard.writeText(await r.text());
      btn.textContent = "Copied";
    } catch (e) {
      btn.textContent = "Failed";
    }
    setTimeout(() => {
      btn.textContent = orig;
      btn.disabled = false;
    }, 1800);
  }
  window.copySkill = copySkill;

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
  async function generatePhysical(path, logFn, bannerEl, kind) {
    const isNote = kind === "note";
    const endpoint = isNote ? "/api/physical/note" : "/api/physical/quiz";
    logFn(isNote
      ? "\nGenerating printable notes (PDF + DOCX)..."
      : "\nGenerating printable version (PDF + DOCX)…");
    try {
      const d = await postForm(endpoint, { path });
      if (!d.ok) { logFn("⚠ Printable version failed: " + (d.error || "unknown error")); return; }
      logFn("✓ Printable version saved to: " + d.folder);
      (d.files || []).forEach(f => logFn("    · " + f));
      (d.warnings || []).forEach(w => logFn("    ⚠ " + w));
      if (d.fallback) logFn("    (No OneDrive workspace found — saved to this PC's local Finished_Exports folder.)");
      if (isNote) {
        window.CE_LAST_NOTE_PRINTABLE = {
          pdf_path: d.primary_pdf || "",
          folder: d.folder || "",
          title: d.title || "",
          artifacts: d.artifacts || {},
        };
      }
      if (bannerEl) {
        const prev = bannerEl.hidden ? "" : bannerEl.innerHTML;
        const note = d.fallback
          ? `<br><span class="hint">No OneDrive workspace found — saved to this PC at the path above.</span>`
          : "";
        showBanner(bannerEl, bannerEl.classList.contains("fail") ? "warn" : "ok",
          (prev ? prev + "<br>" : "") +
          `📄 ${isNote ? "Printable notes" : "Printable PDF + DOCX"} saved to <code>${esc(d.folder)}</code> — ` +
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
  window.CE_PUSH = {
    postForm,
    showLog,
    hideBanner,
    moduleChoice,
    pushContent,
    generatePhysical,
    setRubricStatus,
    syncRubricControls,
    esc,
    showBanner,
    setBusy,
    streamSSE,
    currentCourseId,
    currentCourseName,
    targetCourses,
    collectSettings,
    loadCourseFolder,
  };
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
    window.CE_QUIZ?.resetCourseGroups?.();
    const ciLink = document.getElementById("course-info-link");
    if (ciLink) ciLink.href = "/course?course_id=" + encodeURIComponent(id);
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

  // ── Init ───────────────────────────────────────────────────────────────

  loadRubricFiles();

})();
