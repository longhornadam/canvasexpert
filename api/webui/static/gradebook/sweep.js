(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "showLog", "showBanner", "hideBanner", "esc",
               "gbCourseId", "gbCourseName", "gbTargets", "collectHolidays", "sweepEntries",
               "canvasWriteReview"]
    .every(function (name) {
      if (name === "sweepEntries") return typeof Object.getOwnPropertyDescriptor(gb, "sweepEntries") !== "undefined";
      return typeof gb[name] === "function";
    });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // ── Sweep helpers ─────────────────────────────────────────────────────

  function sweepSettings() {
    return {
      skip_weekends:    document.getElementById("sw-weekends").checked,
      holidays:         gb.collectHolidays(),
      honor_extra_time: document.getElementById("sw-extra").checked,
      date_from:        document.getElementById("sw-from")?.value || null,
      date_to:          document.getElementById("sw-to")?.value   || null,
    };
  }

  function updateSweepApplyBtn() {
    var n   = document.querySelectorAll(".sw-cb:checked").length;
    var btn = document.getElementById("btn-sweep-apply");
    if (!btn) return;
    btn.hidden = n === 0;
    btn.textContent = "Set lateness for " + n + " submission" + (n === 1 ? "" : "s") + "\u2026";
  }

  // ── Sweep handlers ────────────────────────────────────────────────────

  document.getElementById("btn-sweep-preview")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return alert("Pick a course first.");
    var st = document.getElementById("sw-status");
    var from = document.getElementById("sw-from")?.value;
    var to   = document.getElementById("sw-to")?.value;
    if (!from && !to) {
      if (!confirm("No date range set \u2014 this will scan the entire course history and may be very slow. Continue?")) return;
    }
    st.className = "status hint";
    st.textContent = from
      ? "Scanning late work from " + from + " to " + (to || "now") + "\u2026"
      : "Scanning all late work\u2026 (give it a moment)";
    this.disabled = true;
    document.getElementById("sw-table-wrap").hidden = true;
    gb.hideBanner(document.getElementById("sw-banner"));
    try {
      var d = await gb.postForm("/api/sweep/preview",
        { course_id: id, settings: JSON.stringify(sweepSettings()) });
      if (!d.ok) { st.className = "status error"; st.textContent = "Error: " + d.error; return; }
      gb.sweepEntries = d.entries || [];
      if (!gb.sweepEntries.length) {
        st.className = "status ok";
        st.textContent = "\u2713 No late submissions found in this date range \u2014 nothing to correct.";
        updateSweepApplyBtn();
        return;
      }
      st.textContent = gb.sweepEntries.length + " late submission(s) found" +
        " \u2014 uncheck rows you want to skip. No changes yet.";
      var tbody = document.getElementById("sw-tbody");
      tbody.innerHTML = "";
      gb.sweepEntries.forEach(function (e, i) {
        var tr = document.createElement("tr");
        var excl = e.excluded || [];
        tr.title = excl.length
          ? "Excluded: " + excl.join(", ") + (e.extra_days ? " + " + e.extra_days + " extra-time day(s)" : "")
          : (e.extra_days ? "Extra-time: " + e.extra_days + " day(s) excused" : "");
        tr.innerHTML =
          '<td><input type="checkbox" class="sw-cb" data-i="' + i + '" checked></td>' +
          '<td>' + gb.esc(e.student_name) + '</td>' +
          '<td>' + gb.esc(e.assignment_name) + '</td>' +
          '<td class="muted">' + gb.esc(e.due) + ' \u2192 ' + gb.esc(e.submitted) + '</td>' +
          '<td class="muted">' + e.canvas_days + '</td>' +
          '<td><strong>' + e.school_days + '</strong></td>' +
          '<td class="muted" style="font-size:12px">' + (excl.length ? excl.join(", ") : "\u2014") + '</td>';
        tbody.appendChild(tr);
      });
      var all = document.getElementById("sw-check-all");
      if (all) all.checked = true;
      document.getElementById("sw-table-wrap").hidden = false;
      updateSweepApplyBtn();
    } finally { this.disabled = false; }
  });

  document.getElementById("sw-check-all")?.addEventListener("change", function () {
    var checked = this.checked;
    document.querySelectorAll(".sw-cb").forEach(function (cb) { cb.checked = checked; });
    updateSweepApplyBtn();
  });
  document.getElementById("sw-tbody")?.addEventListener("change", function (e) {
    if (e.target.classList.contains("sw-cb")) updateSweepApplyBtn();
  });

  document.getElementById("btn-sweep-apply")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id   = gb.gbCourseId();
    var rows = Array.from(document.querySelectorAll(".sw-cb:checked"))
      .map(function (cb) { return gb.sweepEntries[+cb.dataset.i]; })
      .filter(Boolean);
    if (!rows.length) return;
    var ok = await gb.canvasWriteReview({
      title: "Review lateness override write",
      action: "Set lateness overrides for " + rows.length + " selected submission(s).",
      targets: typeof gb.gbTargets === "function" ? gb.gbTargets() : [{ id: id, name: gb.gbCourseName() }],
      details: [
        rows.length + " selected submission(s)",
        "Date range: " + (document.getElementById("sw-from")?.value || "course start") + " to " +
          (document.getElementById("sw-to")?.value || "now"),
      ],
      warnings: [
        "This writes lateness overrides to Canvas.",
        "Canvas recalculates each student's late penalty using the course late policy.",
        "No direct score values are written by this action.",
      ],
      confirmText: "Set lateness overrides",
    });
    if (!ok) return;
    var log = gb.showLog(document.getElementById("sw-log"));
    gb.hideBanner(document.getElementById("sw-banner"));
    this.disabled = true;
    log("Setting lateness override for " + rows.length + " submission(s)\u2026\n");
    try {
      var d = await gb.postForm("/api/sweep/apply", { course_id: id, entries: JSON.stringify(rows) });
      if (d.error && !d.results) {
        log("ERROR: " + d.error);
        gb.showBanner(document.getElementById("sw-banner"), "fail", "\u2717 " + gb.esc(d.error));
        return;
      }
      (d.results || []).forEach(function (r) {
        log((r.ok ? "\u2713" : "\u2717") + " " + r.student + " \u2014 " + r.assignment + " \u2192 " + r.school_days + " school day(s) late" +
        (r.ok ? "" : "  (" + r.error + ")"));
      });
      var okCount = (d.results || []).filter(function (r) { return r.ok; }).length;
      gb.showBanner(document.getElementById("sw-banner"), d.ok ? "ok" : "warn",
        (d.ok ? "\u2713" : "\u26A0") + " " + okCount + "/" + rows.length + " lateness override(s) set \u2014 Canvas will apply its late policy.");
      document.getElementById("sw-table-wrap").hidden = true;
      gb.sweepEntries = [];
      updateSweepApplyBtn();
    } finally { this.disabled = false; }
  });

})();
