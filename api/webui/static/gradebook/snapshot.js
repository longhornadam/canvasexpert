(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["esc", "gbCourseId", "gbCourseName"]
    .every(function (name) { return typeof gb[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // ── Snapshot ───────────────────────────────────────────────────────────

  document.getElementById("btn-load-gradebook")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id   = gb.gbCourseId();
    var name = gb.gbCourseName();
    if (!id) return alert("Pick a course first.");
    var status = document.getElementById("gb-status");
    status.className = "status hint";
    status.textContent = "Loading gradebook for " + name + "\u2026 (pulls every submission \u2014 give it a moment)";
    this.disabled = true;
    try {
      var d = await fetch("/api/gradebook?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
      if (!d.ok) { status.className = "status error"; status.textContent = "Error: " + d.error; return; }
      status.textContent = "";
      var link = document.getElementById("gb-canvas-link");
      link.hidden = false;
      link.href = window.GB_CANVAS_BASE + "/courses/" + id + "/gradebook";

      document.getElementById("gb-avg").textContent      = d.class_avg != null ? d.class_avg + "%" : "\u2014";
      document.getElementById("gb-missing").textContent  = d.total_missing;
      document.getElementById("gb-ungraded").textContent = d.total_ungraded;
      document.getElementById("gb-students").textContent = d.student_count;
      document.getElementById("gb-summary").hidden = false;

      var stb = document.getElementById("gb-student-tbody");
      stb.innerHTML = "";
      Array.from(d.students)
        .sort(function (a, b) { return b.missing - a.missing || a.name.localeCompare(b.name); })
        .forEach(function (s) {
          var tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" + gb.esc(s.name) + "</td>" +
            '<td class="' + (s.missing ? "gb-bad" : "muted") + '">' + (s.missing || "\u2014") + "</td>" +
            '<td class="muted">' + (s.late || "\u2014") + "</td>" +
            '<td class="muted">' + (s.ungraded || "\u2014") + "</td>" +
            "<td>" + (s.pct != null ? s.pct + "%" : "\u2014") + "</td>";
          stb.appendChild(tr);
        });

      var atb = document.getElementById("gb-assign-tbody");
      atb.innerHTML = "";
      d.assignments.forEach(function (a) {
        var nm = a.html_url
          ? '<a href="' + gb.esc(a.html_url) + '" target="_blank" rel="noopener">' + gb.esc(a.name) + "</a>"
          : gb.esc(a.name);
        var ungraded = a.submitted - a.graded;
        var tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" + nm + "</td>" +
          '<td class="muted">' + gb.esc(a.due_at || "\u2014") + "</td>" +
          '<td class="muted">' + (a.points ?? "\u2014") + "</td>" +
          "<td>" + a.submitted + "</td>" +
          "<td>" + a.graded + (ungraded > 0 ? ' <span class="gb-warn">+' + ungraded + " to grade</span>" : "") + "</td>" +
          '<td class="' + (a.missing ? "gb-bad" : "muted") + '">' + (a.missing || "\u2014") + "</td>" +
          "<td>" + (a.avg_pct != null ? a.avg_pct + "%" : "\u2014") + "</td>";
        atb.appendChild(tr);
      });
      document.getElementById("gb-tables").hidden = false;
      this.textContent = "\u21BB Reload gradebook";
    } catch (e) {
      status.className  = "status error";
      status.textContent = String(e);
    } finally { this.disabled = false; }
  });

})();