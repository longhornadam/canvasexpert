(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = [
    "esc",
    "showLog",
    "hideBanner",
    "showBanner",
    "setBusy",
    "streamSSE",
    "currentCourseId",
    "currentCourseName",
    "loadCourseFolder",
  ].every(function (name) { return typeof push[name] === "function"; });

  var dlAssignments = [];

  function requireReady() {
    if (ready) return true;
    alert("Download Work controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function assignmentBadge(types) {
    var t = (types || [])[0] || "";
    if (t === "online_text_entry") return '<span class="badge badge-text">Text</span>';
    if (t === "online_upload") return '<span class="badge badge-upload">Upload</span>';
    if (t === "discussion_topic") return '<span class="badge badge-disc">Discussion</span>';
    if (t === "online_url") return '<span class="badge badge-url">URL</span>';
    if (t === "external_tool") return '<span class="badge badge-ext">LTI</span>';
    return '<span class="badge badge-none">' + push.esc(t || "none") + "</span>";
  }

  function updateDlCount() {
    var sel = Array.from(document.querySelectorAll(".dl-cb:checked:not(:disabled)"));
    var cnt = document.getElementById("dl-selected-count");
    var btn = document.getElementById("btn-download-selected");
    var row = document.getElementById("dl-action-row");
    if (cnt) cnt.textContent = sel.length ? sel.length + " selected" : "";
    if (btn) {
      btn.textContent = sel.length
        ? "⬇ Download " + sel.length + " assignment" + (sel.length === 1 ? "" : "s") + "…"
        : "⬇ Download selected";
    }
    if (row) row.style.display = sel.length ? "" : "none";
    push.renderCourseScopeSummaries?.();
  }

  function applyDlFilter() {
    var typeFilter = document.getElementById("dl-type-filter")?.value || "";
    var fromVal = document.getElementById("dl-date-from")?.value || "";
    var toVal = document.getElementById("dl-date-to")?.value || "";
    var vis = 0;
    document.querySelectorAll("#dl-tbody tr").forEach(function (tr) {
      var t = tr.dataset.type || "";
      var d = tr.dataset.due || "";
      var showType = !typeFilter || t === typeFilter;
      var showFrom = !fromVal || d >= fromVal;
      var showTo = !toVal || !d || d <= toVal;
      tr.hidden = !(showType && showFrom && showTo);
      if (!tr.hidden) vis++;
    });
    var vc = document.getElementById("dl-visible-count");
    if (vc) vc.textContent = vis + " of " + dlAssignments.length;
    updateDlCount();
  }

  document.getElementById("btn-load-assignments")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id = push.currentCourseId();
    if (!id) return alert("Select a course first.");
    this.disabled = true; this.textContent = "Loading…";
    try {
      var data = await fetch("/api/assignments-full?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
      if (!data.ok) { alert("Error: " + data.error); return; }
      dlAssignments = data.assignments || [];
      var tbody = document.getElementById("dl-tbody");
      if (tbody) {
        tbody.innerHTML = "";
        dlAssignments.forEach(function (a) {
          var canDl = (a.submission_types || []).some(function (t) {
            return ["online_text_entry", "online_upload", "discussion_topic", "online_url"].includes(t);
          });
          var tr = document.createElement("tr");
          tr.dataset.type = (a.submission_types || [])[0] || "";
          tr.dataset.due = (a.due_at || "").slice(0, 10);
          if (!canDl) tr.classList.add("dl-row-dim");
          tr.innerHTML =
            '<td><input type="checkbox" class="dl-cb" value="' + push.esc(a.id) + '"' +
            ' data-name="' + push.esc(a.name) + '"' + (canDl ? "" : " disabled") +
            ' title="' + (canDl ? "" : "not downloadable — no text/file submissions") + '"></td>' +
            "<td>" + push.esc(a.name) +
              (a.html_url ? ' <a href="' + push.esc(a.html_url) + '" target="_blank" rel="noopener" class="small-link">↗</a>' : "") +
            "</td>" +
            "<td>" + assignmentBadge(a.submission_types) + "</td>" +
            "<td>" + push.esc(a.due_at ? new Date(a.due_at).toLocaleDateString() : "—") + "</td>" +
            "<td>" + push.esc(a.points_possible != null ? a.points_possible : "—") + "</td>";
          tbody.appendChild(tr);
        });
      }
      var tbl = document.getElementById("dl-assignment-table");
      var fwrap = document.getElementById("dl-filter-wrap");
      var dbar = document.getElementById("dl-date-bar");
      if (tbl) tbl.hidden = false;
      if (fwrap) fwrap.hidden = false;
      if (dbar) dbar.hidden = false;
      applyDlFilter();
    } finally {
      this.disabled = false;
      this.textContent = "Load assignments…";
    }
  });

  document.getElementById("dl-type-filter")?.addEventListener("change", applyDlFilter);
  document.getElementById("dl-date-from")?.addEventListener("change", applyDlFilter);
  document.getElementById("dl-date-to")?.addEventListener("change", applyDlFilter);

  document.querySelectorAll(".dl-presets .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var preset = chip.dataset.preset;
      var year = new Date().getFullYear();
      var fromEl = document.getElementById("dl-date-from");
      var toEl = document.getElementById("dl-date-to");
      var chips = document.querySelectorAll(".dl-presets .chip");
      chips.forEach(function (c) { c.classList.toggle("chip-active", c === chip); });
      if (preset === "fall") { if (fromEl) fromEl.value = year + "-08-01"; if (toEl) toEl.value = year + "-12-31"; }
      else if (preset === "spring") { if (fromEl) fromEl.value = year + "-01-01"; if (toEl) toEl.value = year + "-05-31"; }
      else if (preset === "30d") {
        var d30 = new Date(); d30.setDate(d30.getDate() - 30);
        if (fromEl) fromEl.value = d30.toISOString().slice(0, 10);
        if (toEl) toEl.value = new Date().toISOString().slice(0, 10);
      }
      else if (preset === "90d") {
        var d90 = new Date(); d90.setDate(d90.getDate() - 90);
        if (fromEl) fromEl.value = d90.toISOString().slice(0, 10);
        if (toEl) toEl.value = new Date().toISOString().slice(0, 10);
      }
      else { if (fromEl) fromEl.value = ""; if (toEl) toEl.value = ""; }
      applyDlFilter();
    });
  });

  document.getElementById("dl-check-all")?.addEventListener("change", function () {
    document.querySelectorAll(".dl-cb:not(:disabled)").forEach(function (cb) {
      if (!cb.closest("tr")?.hidden) cb.checked = this.checked;
    }, this);
    updateDlCount();
  });

  document.getElementById("btn-dl-select-all")?.addEventListener("click", function () {
    document.querySelectorAll(".dl-cb:not(:disabled)").forEach(function (cb) {
      if (!cb.closest("tr")?.hidden) cb.checked = true;
    });
    updateDlCount();
  });

  document.getElementById("btn-dl-clear")?.addEventListener("click", function () {
    document.querySelectorAll(".dl-cb").forEach(function (cb) { cb.checked = false; });
    var dca = document.getElementById("dl-check-all");
    if (dca) dca.checked = false;
    updateDlCount();
  });

  document.getElementById("dl-assignment-table")?.addEventListener("change", function (e) {
    if (e.target.classList.contains("dl-cb")) updateDlCount();
  });

  document.getElementById("btn-download-selected")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var id = push.currentCourseId();
    var name = push.currentCourseName();
    if (!id) return alert("Choose a course first.");
    var checked = Array.from(document.querySelectorAll(".dl-cb:checked:not(:disabled)"));
    if (!checked.length) return alert("Select at least one assignment.");
    var ids = checked.map(function (cb) { return cb.value; }).join(",");
    var names = checked.map(function (cb) { return cb.dataset.name; }).join("\n  • ");
    if (!confirm(
      "Download submissions for " + checked.length + " assignment(s):\n  • " + names + "\n\n" +
      "Course: " + name + "\n" +
      "Files will be saved to your configured download folder.\n\nContinue?"
    )) return;
    var log = push.showLog(document.getElementById("dl-log"));
    push.hideBanner(document.getElementById("dl-banner"));
    push.setBusy(true);
    var folderPath = null;
    push.streamSSE(
      "/api/submissions/download/stream" +
      "?course_id=" + encodeURIComponent(id) +
      "&course_name=" + encodeURIComponent(name) +
      "&assignment_ids=" + encodeURIComponent(ids),
      function (line) {
        if (line.startsWith("COURSE_FOLDER: ")) {
          folderPath = line.slice("COURSE_FOLDER: ".length).trim();
          return;
        }
        log(line);
      },
      null,
      function () {
        push.setBusy(false);
        push.loadCourseFolder(name);
        var banner = document.getElementById("dl-banner");
        if (folderPath) {
          push.showBanner(banner, "ok",
            "✓ Downloaded — " +
            '<a href="#" data-open-folder="' + push.esc(folderPath) + '">Open folder ↗</a>');
          banner.querySelector("[data-open-folder]")?.addEventListener("click", async function (e) {
            e.preventDefault();
            await fetch("/api/open-folder", {
              method: "POST",
              body: new URLSearchParams({ path: folderPath }),
            });
          });
        } else {
          push.showBanner(banner, "warn", "⚠ Download finished — check log for errors.");
        }
      }
    );
  });

  document.getElementById("btn-open-folder")?.addEventListener("click", async function () {
    var p = this.dataset.path;
    if (!p) return;
    var r = await fetch("/api/open-folder", {
      method: "POST", body: new URLSearchParams({ path: p }),
    });
    var d = await r.json();
    if (!d.ok) alert("Could not open folder: " + d.error);
  });

  document.getElementById("btn-change-folder")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var btn = this, orig = btn.textContent;
    btn.disabled = true; btn.textContent = "Choosing…";
    try {
      var d = await fetch("/api/pick-download-folder", { method: "POST" }).then(function (r) { return r.json(); });
      if (d.ok && d.root) {
        push.loadCourseFolder(push.currentCourseName());
      } else if (d.error) {
        alert("Could not open the folder picker: " + d.error);
      }
    } finally {
      btn.disabled = false; btn.textContent = orig;
    }
  });
})();
