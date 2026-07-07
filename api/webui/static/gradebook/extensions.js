(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "showBanner", "hideBanner", "esc", "gbCourseId",
               "gbCourseName", "_markLoaded", "_needsLoad", "_clearLoaded",
               "_clearStatus", "collectHolidays"]
    .every(function (name) { return typeof gb[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // ── Extensions (auto-loaded on tab activate) ───────────────────────────

  window.CE_GRADEBOOK.loadExtensions = async function _loadExtensions() {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return;
    gb._markLoaded("extensions");
    var st = document.getElementById("ext-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading assignments and students\u2026"; }
    try {
      var responses = await Promise.all([
        fetch("/api/assignments-full?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); }),
        fetch("/api/students/list?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); }),
        fetch("/api/extra-time?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); }),
      ]);
      var asg = responses[0], stu = responses[1], xt = responses[2];
      if (!asg.ok || !stu.ok) {
        if (st) { st.className = "status error"; st.textContent = "Error: " + (asg.error || stu.error); }
        return;
      }
      var sel = document.getElementById("ext-assignment");
      if (sel) {
        sel.innerHTML = "";
        sel.appendChild(new Option("\u2014 select an assignment \u2014", ""));
        asg.assignments.filter(function (a) { return a.due_at; }).forEach(function (a) {
          sel.appendChild(new Option(a.name + " (due " + a.due_at + ")", a.id));
        });
        sel.disabled = false;
      }
      var eh = document.getElementById("ext-hint");
      if (eh) eh.textContent = asg.assignments.filter(function (a) { return a.due_at; }).length + " assignments";
      var savedIds = new Set((xt.students || []).map(function (e) { return String(e.id); }));
      var box = document.getElementById("ext-students");
      if (box) {
        box.innerHTML = "";
        stu.students.forEach(function (s) {
          var row = document.createElement("div");
          row.className = "xt-row";
          row.innerHTML =
            '<label class="opt-check xt-name"><input type="checkbox" class="ext-cb"' +
            ' value="' + gb.esc(s.id) + '"' + (savedIds.has(s.id) ? " checked" : "") + '> ' + gb.esc(s.name) + '</label>';
          box.appendChild(row);
        });
      }
      var eb = document.getElementById("btn-ext-apply");
      if (eb) eb.hidden = false;
      if (st) {
        st.textContent = savedIds.size
          ? "Extra-time roster preselected \u2014 adjust as needed, pick an assignment, then grant."
          : "Pick an assignment and the students who get extra time.";
      }
    } catch (e) {
      if (st) { st.className = "status error"; st.textContent = String(e); }
    }
  };

  document.getElementById("btn-ext-reload")?.addEventListener("click", function () {
    gb._clearLoaded("extensions");
    window.CE_GRADEBOOK.loadExtensions();
  });

  document.getElementById("btn-ext-apply")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id   = gb.gbCourseId();
    var aSel = document.getElementById("ext-assignment");
    if (!aSel.value) return alert("Pick an assignment.");
    var sids = Array.from(document.querySelectorAll(".ext-cb:checked")).map(function (cb) { return cb.value; });
    if (!sids.length) return alert("Select at least one student.");
    var days = parseInt(document.getElementById("ext-days").value, 10) || 1;
    if (!confirm(
      "Give " + sids.length + " student(s) +" + days + " school day(s) on:\n" +
      '  "' + aSel.selectedOptions[0].text + '"\n\nCourse: ' + gb.gbCourseName() + "\n\n" +
      "This creates a Canvas assignment override \u2014 their due date actually moves.\n\nContinue?"
    )) return;
    var banner = document.getElementById("ext-banner");
    gb.hideBanner(banner);
    this.disabled = true;
    try {
      var d = await gb.postForm("/api/extend-due", {
        course_id:     id,
        assignment_id: aSel.value,
        student_ids:   JSON.stringify(sids),
        days:          String(days),
        skip_weekends: document.getElementById("sw-weekends")?.checked ? "true" : "false",
        holidays:      JSON.stringify(gb.collectHolidays()),
      });
      if (d.ok) {
        gb.showBanner(banner, "ok",
          "\u2713 " + gb.esc(d.assignment) + " \u2014 " + d.count + " student(s) now due " +
          gb.esc(new Date(d.new_due).toLocaleString()));
      } else {
        gb.showBanner(banner, "fail", "\u2717 " + gb.esc(d.error));
      }
    } finally { this.disabled = false; }
  });

})();