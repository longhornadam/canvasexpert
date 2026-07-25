(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "esc", "gbCourseId", "gbCourseName", "_markLoaded",
               "_needsLoad", "_clearLoaded", "_clearStatus"]
    .every(function (name) { return typeof gb[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // Switching courses re-triggers this loader (see gradebook.js's
  // _autoloadTab) without cancelling a slower earlier request, so a stale
  // response could land last and fill the roster with the previous course's
  // students while the new course sits selected. Stamp each request and let
  // only the newest one write, the same way inbox.js does.
  var loadGeneration = 0;

  // ── Extra-time roster (auto-loaded) ───────────────────────────────────

  window.CE_GRADEBOOK.loadRoster = async function _loadRoster() {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return;
    var generation = ++loadGeneration;
    gb._markLoaded("extra-time");
    var st = document.getElementById("xt-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading\u2026"; }
    var reloadBtn = document.getElementById("btn-reload-roster");
    if (reloadBtn) reloadBtn.disabled = true;
    try {
      var response = await Promise.all([
        fetch("/api/students/list?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); }),
        fetch("/api/extra-time?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); }),
      ]);
      if (generation !== loadGeneration) return;
      var stu = response[0], saved = response[1];
      if (!stu.ok) {
        if (st) { st.className = "status error"; st.textContent = "Error: " + stu.error; }
        return;
      }
      var savedMap = new Map((saved.students || []).map(function (e) { return [String(e.id), e.days || 1]; }));
      var list = document.getElementById("xt-list");
      if (list) {
        list.innerHTML = "";
        stu.students.forEach(function (s) {
          var has = savedMap.has(s.id);
          var row = document.createElement("div");
          row.className = "xt-row";
          row.innerHTML =
            '<label class="opt-check xt-name"><input type="checkbox" class="xt-cb" value="' + gb.esc(s.id) + '"' +
            ' data-name="' + gb.esc(s.name) + '"' + (has ? " checked" : "") + '> ' + gb.esc(s.name) + '</label>' +
            '<span class="xt-days">+<input type="number" class="xt-days-input"' +
            ' value="' + (has ? savedMap.get(s.id) : 1) + '" min="1" max="10"> day(s)</span>';
          list.appendChild(row);
        });
      }
      if (st) {
        st.textContent = savedMap.size
          ? savedMap.size + " student(s) currently on the roster \u2014 check/uncheck and save."
          : "Check the students who get extra time, set their days, then save.";
      }
      var sb = document.getElementById("btn-save-roster");
      if (sb) sb.hidden = false;
    } catch (e) {
      if (generation !== loadGeneration) return;
      if (st) { st.className = "status error"; st.textContent = "Could not load the roster. Try Reload."; }
    } finally {
      if (reloadBtn) reloadBtn.disabled = false;
    }
  };

  document.getElementById("btn-reload-roster")?.addEventListener("click", function () {
    gb._clearLoaded("extra-time");
    window.CE_GRADEBOOK.loadRoster();
  });

  document.getElementById("btn-save-roster")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return;
    var students = Array.from(document.querySelectorAll("#xt-list .xt-row"))
      .filter(function (r) { return r.querySelector(".xt-cb").checked; })
      .map(function (r) {
        return {
          id:   r.querySelector(".xt-cb").value,
          name: r.querySelector(".xt-cb").dataset.name,
          days: parseInt(r.querySelector(".xt-days-input").value, 10) || 1,
        };
      });
    var d  = await gb.postForm("/api/extra-time", { course_id: id, students: JSON.stringify(students) });
    var st = document.getElementById("xt-status");
    if (d.ok) {
      st.className = "status ok";
      st.textContent = "\u2713 Saved " + students.length + " extra-time student(s) for " + gb.gbCourseName();
    } else {
      st.className = "status error";
      st.textContent = "Error: " + d.error;
    }
  });

})();