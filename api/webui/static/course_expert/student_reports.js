(function () {
  "use strict";

  var courseSel = document.getElementById("sr-course");
  if (!courseSel) return;

  var stuSel = document.getElementById("sr-student");
  var monBtn = document.getElementById("sr-monitor");
  var genBtn = document.getElementById("sr-generate");
  var openA = document.getElementById("sr-open");
  var status = document.getElementById("sr-status");
  var logEl = document.getElementById("sr-log");

  function selName() {
    var opt = stuSel.options[stuSel.selectedIndex];
    return opt ? opt.textContent : "";
  }

  function refreshMonBtn(monitored) {
    monBtn.hidden = !stuSel.value;
    monBtn.textContent = monitored ? "★ Monitored" : "☆ Monitor";
    monBtn.dataset.mon = monitored ? "1" : "0";
  }

  courseSel.addEventListener("change", function () {
    stuSel.innerHTML = '<option value="">Loading…</option>';
    genBtn.disabled = true;
    monBtn.hidden = true;
    if (!courseSel.value) {
      stuSel.innerHTML = '<option value="">— pick a course first —</option>';
      return;
    }
    fetch("/api/students?course_id=" + encodeURIComponent(courseSel.value))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        stuSel.innerHTML = '<option value="">— pick a student —</option>';
        (d.students || []).forEach(function (student) {
          var opt = document.createElement("option");
          opt.value = student.id;
          opt.textContent = student.name;
          opt.dataset.mon = student.monitored ? "1" : "0";
          stuSel.appendChild(opt);
        });
      });
  });

  stuSel.addEventListener("change", function () {
    genBtn.disabled = !stuSel.value;
    var opt = stuSel.options[stuSel.selectedIndex];
    refreshMonBtn(opt && opt.dataset.mon === "1");
  });

  monBtn.addEventListener("click", function () {
    var on = monBtn.dataset.mon !== "1";
    fetch("/api/students/monitor", {
      method: "POST",
      body: new URLSearchParams({
        user_id: stuSel.value,
        name: selName(),
        monitored: on ? "true" : "false",
      }),
    }).then(function () {
      stuSel.options[stuSel.selectedIndex].dataset.mon = on ? "1" : "0";
      refreshMonBtn(on);
    });
  });

  genBtn.addEventListener("click", function () {
    var secs = Array.prototype.map.call(document.querySelectorAll(".sr-sec:checked"), function (c) {
      return c.value;
    });
    genBtn.disabled = true;
    openA.hidden = true;
    logEl.hidden = false;
    logEl.textContent = "";
    status.textContent = "Generating…";

    var qs = new URLSearchParams({
      user_id: stuSel.value,
      student_name: selName(),
      sections: secs.join(","),
    });
    var es = new EventSource("/api/student-packet/stream?" + qs.toString());
    var done = false;

    es.onmessage = function (event) {
      var line = JSON.parse(event.data);
      if (line === "[exit 0]" || line === "[exit 1]") {
        done = true;
        es.close();
        genBtn.disabled = false;
        status.textContent = line === "[exit 0]" ? "Done." : "Finished with errors.";
        return;
      }
      if (line.indexOf("FOLDER: ") === 0) {
        openA.setAttribute("data-open-path", line.slice(8));
        openA.hidden = false;
        return;
      }
      logEl.textContent += line + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    };

    es.onerror = function () {
      if (done) return;
      es.close();
      genBtn.disabled = false;
      status.textContent = "Connection lost.";
    };
  });
})();
