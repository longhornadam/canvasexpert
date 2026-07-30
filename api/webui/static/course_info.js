(function () {
  "use strict";

  const sel    = document.getElementById("ci-course");
  const status = document.getElementById("ci-status");
  if (!sel) return;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",
                                    '"':"&quot;","'":"&#39;" }[c]));
  }

  function currentName() {
    return sel.selectedOptions[0]?.dataset.name || "";
  }

  function setQuickLinks(id) {
    const base = window.QF_CANVAS_BASE || "";
    const links = {
      "ql-home":        `${base}/courses/${id}`,
      "ql-gradebook":   `${base}/courses/${id}/gradebook`,
      "ql-assignments": `${base}/courses/${id}/assignments`,
      "ql-modules":     `${base}/courses/${id}/modules`,
      "ql-quizzes":     `${base}/courses/${id}/quizzes`,
      "ql-people":      `${base}/courses/${id}/users?enrollment_type=student`,
    };
    for (const [elId, href] of Object.entries(links)) {
      const a = document.getElementById(elId);
      if (a) a.href = href;
    }
  }

  // ── Download folder row (same endpoints the dashboard uses) ────────────

  function loadFolder(courseName) {
    const row  = document.getElementById("folder-row");
    const path = document.getElementById("folder-path");
    const note = document.getElementById("folder-note");
    if (!row || !courseName) return;
    fetch(`/api/course-folder?course_name=${encodeURIComponent(courseName)}`)
      .then(r => r.json())
      .then(d => {
        row.hidden = false;
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
    const d = await fetch("/api/open-folder", {
      method: "POST", body: new URLSearchParams({ path: p }),
    }).then(r => r.json());
    if (!d.ok) alert("Could not open folder: " + d.error);
  });

  document.getElementById("btn-change-folder")?.addEventListener("click", async function () {
    const btn = this, orig = btn.textContent;
    btn.disabled = true; btn.textContent = "Choosing…";
    try {
      const d = await fetch("/api/pick-download-folder", { method: "POST" }).then(r => r.json());
      if (d.ok && d.root) loadFolder(currentName());
      else if (d.error) alert("Could not open the folder picker: " + d.error);
    } finally {
      btn.disabled = false; btn.textContent = orig;
    }
  });

  // ── Render helpers ──────────────────────────────────────────────────────

  function renderRoster(students) {
    const tbody = document.getElementById("ci-roster");
    tbody.innerHTML = "";
    if (!students.length) {
      tbody.innerHTML = '<tr><td colspan="1" class="muted">No students found.</td></tr>';
      return;
    }
    students.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(s.sortable_name || s.name)}</td>`;
      tbody.appendChild(tr);
    });
  }

  function renderGroups(groupSets) {
    const box = document.getElementById("ci-groups");
    if (!groupSets.length) {
      box.innerHTML = '<p class="hint" style="margin:0">No group sets in this course.</p>';
      return;
    }
    box.innerHTML = groupSets.map(gs => {
      const groups = gs.groups.map(g =>
        `<div class="ci-group">
           <div class="ci-group-name">${esc(g.name)} <span class="muted">(${g.members.length})</span></div>
           <div class="ci-group-members">${g.members.map(esc).join(", ") || "<span class='muted'>empty</span>"}</div>
         </div>`).join("");
      return `<div class="ci-groupset">
                <div class="ci-groupset-name">${esc(gs.name)}</div>${groups}
              </div>`;
    }).join("");
  }

  function renderModules(modules) {
    const box = document.getElementById("ci-module-list");
    if (!modules.length) {
      box.innerHTML = '<p class="hint" style="margin:0">No modules in this course.</p>';
      return;
    }
    box.innerHTML = modules.map(m =>
      `<div class="ci-module-row">
         <span class="ci-module-name">${esc(m.name)}</span>
         <span class="muted" style="white-space:nowrap">${m.items_count} item${m.items_count === 1 ? "" : "s"}${m.published ? "" : " · unpublished"}</span>
       </div>`).join("");
  }

  function renderAssignments(assignments) {
    const tbody = document.getElementById("ci-assign-tbody");
    const note  = document.getElementById("ci-assign-note");
    tbody.innerHTML = "";
    if (!assignments.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="muted">No assignments yet.</td></tr>';
      note.textContent = "";
      return;
    }
    // Newest due date first; undated at the end.
    const sorted = [...assignments].sort((a, b) =>
      (b.due_at || "0000-00-00").localeCompare(a.due_at || "0000-00-00"));
    const shown = sorted.slice(0, 15);
    note.textContent = shown.length < assignments.length
      ? `· showing ${shown.length} of ${assignments.length}` : "";
    shown.forEach(a => {
      const nm = a.html_url
        ? `<a href="${esc(a.html_url)}" target="_blank" rel="noopener">${esc(a.name)}</a>`
        : esc(a.name);
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${nm}</td>` +
        `<td class="muted">${esc(a.due_at || "—")}</td>` +
        `<td class="muted">${a.points ?? "—"}</td>` +
        `<td>${a.published
            ? '<span class="badge badge-upload">Published</span>'
            : '<span class="badge badge-none">Unpublished</span>'}</td>`;
      tbody.appendChild(tr);
    });
  }

  // ── Load ────────────────────────────────────────────────────────────────

  async function load() {
    const id = sel.value;
    if (!id) return;
    history.replaceState(null, "", "/course?course_id=" + encodeURIComponent(id));
    setQuickLinks(id);
    loadFolder(currentName());
    status.className = "status hint";
    status.textContent = "Loading course details from Canvas…";
    sel.disabled = true;
    try {
      const d = await fetch(`/api/course-detail?course_id=${encodeURIComponent(id)}`)
        .then(r => r.json());
      if (!d.ok) {
        status.className = "status error";
        status.textContent = "Error: " + d.error;
        return;
      }
      status.textContent = "";
      document.getElementById("ci-students").textContent    = d.students.length;
      document.getElementById("ci-groupsets").textContent   = d.group_sets.length;
      document.getElementById("ci-modules").textContent     = d.modules.length;
      document.getElementById("ci-assignments").textContent = d.assignments.length;
      renderRoster(d.students);
      renderGroups(d.group_sets);
      renderModules(d.modules);
      renderAssignments(d.assignments);
    } catch (e) {
      status.className = "status error";
      status.textContent = String(e);
    } finally {
      sel.disabled = false;
    }
  }

  sel.addEventListener("change", load);
  load();

})();
