(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var checklist = document.getElementById("course-checklist");

  function focusedRow() {
    return checklist?.querySelector(".cc-row.focused");
  }

  function currentCourseId() {
    return focusedRow()?.dataset.id || "";
  }

  function currentCourseName() {
    return focusedRow()?.dataset.name || "";
  }

  function targetCourses() {
    return Array.from(checklist?.querySelectorAll(".cc-cb:checked") || [])
      .map(function (cb) {
        return { id: cb.value, name: cb.dataset.name };
      });
  }

  function renderTargets() {
    var checked = Array.from(checklist?.querySelectorAll(".cc-cb:checked") || []);
    var cnt = document.getElementById("target-count");
    if (cnt) cnt.textContent = checked.length ? "· " + checked.length + " selected" : "";
    var sum = document.getElementById("ci-targets");
    if (sum) {
      if (checked.length > 1) {
        var names = checked.map(function (cb) {
          return cb.closest(".cc-row").querySelector(".cc-focus").textContent;
        });
        sum.hidden = false;
        sum.innerHTML = "<strong>Pushing to " + checked.length + " courses:</strong> " +
          names.map(push.esc).join(", ");
      } else {
        sum.hidden = true;
        sum.textContent = "";
      }
    }
    var label = document.getElementById("ce-picker-label");
    if (label) {
      var fn = focusedRow()?.querySelector(".cc-focus")?.textContent?.trim();
      if (!checked.length) label.textContent = "— pick courses —";
      else if (checked.length === 1) label.textContent = fn || "1 selected";
      else label.textContent = (fn ? fn + " " : "") + "· " + checked.length + " selected";
    }
  }

  function loadCourseFolder(courseName) {
    var row = document.getElementById("folder-row");
    var path = document.getElementById("folder-path");
    var note = document.getElementById("folder-note");
    if (!row || !courseName) return;
    fetch("/api/course-folder?course_name=" + encodeURIComponent(courseName))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        row.hidden = false;
        path.textContent = d.path;
        path.title = d.path;
        note.textContent = d.exists ? "" : "(no downloads yet)";
        document.getElementById("btn-open-folder").dataset.path = d.path;
      })
      .catch(function () {});
  }

  function setFocus(id) {
    if (!checklist || !id) return;
    checklist.querySelectorAll(".cc-row").forEach(function (r) {
      r.classList.toggle("focused", r.dataset.id === id);
    });
    var name = currentCourseName();
    push.loadAssignmentGroups?.(id);
    push.loadModules?.(id);
    loadCourseFolder(name);
    window.CE_QUIZ?.resetCourseGroups?.();
    var ciLink = document.getElementById("course-info-link");
    if (ciLink) ciLink.href = "/course?course_id=" + encodeURIComponent(id);
    renderTargets();
  }

  async function renameCourse(btn) {
    var id = btn.dataset.id;
    var name = btn.dataset.name;
    var next = prompt('Nickname for "' + name + '":', btn.dataset.nick || "");
    if (next == null) return;
    var nick = next.trim();
    if (!nick) return;
    var d = await push.postForm("/settings/courses/bookmark", {
      course_id: id,
      course_name: name,
      nickname: nick,
    });
    if (d.ok) {
      btn.dataset.nick = nick;
      var focusBtn = btn.closest(".cc-row")?.querySelector(".cc-focus");
      if (focusBtn) focusBtn.textContent = nick;
    }
  }

  function bindChecklist() {
    if (!checklist) return;
    checklist.addEventListener("click", function (e) {
      var fb = e.target.closest(".cc-focus");
      if (fb) {
        var row = fb.closest(".cc-row");
        var cb = row.querySelector(".cc-cb");
        if (cb && !cb.checked) cb.checked = true;
        setFocus(row.dataset.id);
        return;
      }
      var rb = e.target.closest(".cc-rename");
      if (rb) renameCourse(rb);
    });
    checklist.addEventListener("change", function (e) {
      if (!e.target.classList.contains("cc-cb")) return;
      var focused = checklist.querySelector(".cc-row.focused");
      var focusedChecked = focused && focused.querySelector(".cc-cb").checked;
      if (!focusedChecked) {
        var firstChecked = checklist.querySelector(".cc-cb:checked");
        if (firstChecked) setFocus(firstChecked.value);
        else renderTargets();
      } else {
        renderTargets();
      }
    });
    var first = checklist.querySelector(".cc-row");
    if (first) {
      var cb = first.querySelector(".cc-cb");
      if (cb) cb.checked = true;
      setFocus(first.dataset.id);
    }
  }

  async function loadAllCoursesIntoChecklist() {
    if (!checklist) return;
    try {
      var d = await fetch("/api/courses").then(function (r) { return r.json(); });
      if (!d.ok || !d.courses?.length) return;
      var have = new Set(Array.from(checklist.querySelectorAll(".cc-row")).map(function (r) {
        return r.dataset.id;
      }));
      var extras = d.courses.filter(function (c) { return !have.has(c.id); });
      if (!extras.length) return;
      var div = document.createElement("div");
      div.className = "cc-all-divider";
      div.textContent = "All courses";
      checklist.appendChild(div);
      extras.forEach(function (c) {
        var row = document.createElement("div");
        row.className = "cc-row";
        row.dataset.id = c.id;
        row.dataset.name = c.name;
        row.innerHTML =
          '<input type="checkbox" class="cc-cb" value="' + push.esc(c.id) +
          '" data-name="' + push.esc(c.name) + '">' +
          '<button type="button" class="cc-focus" title="Focus this course">' +
          push.esc(c.name) + "</button>";
        checklist.appendChild(row);
      });
    } catch (e) {
      // Keep bookmarks only when offline or unauthenticated.
    }
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    currentCourseId: currentCourseId,
    currentCourseName: currentCourseName,
    targetCourses: targetCourses,
    loadCourseFolder: loadCourseFolder,
    setFocus: setFocus,
  });
  window.targetCourses = targetCourses;

  bindChecklist();
  loadAllCoursesIntoChecklist();
})();
