(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var context = window.CE_CONTEXT || null;
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

  function publishContext(source) {
    if (!context) return;
    var row = focusedRow();
    context.setFocus(row ? { id: row.dataset.id, name: row.dataset.name } : null, source);
    context.setTargets(targetCourses(), source);
  }

  function courseListSummary(courses) {
    var shown = courses.slice(0, 3).map(function (c) { return push.esc(c.name || "Untitled course"); });
    var more = courses.length > shown.length ? " <span class=\"course-scope-more\">+" + (courses.length - shown.length) + " more</span>" : "";
    return shown.join(", ") + more;
  }

  function selectedDownloadCount() {
    return document.querySelectorAll(".dl-cb:checked:not(:disabled)").length;
  }

  function renderCourseScopeSummaries() {
    var targets = targetCourses();
    var focusName = currentCourseName();
    document.querySelectorAll("[data-course-scope]").forEach(function (el) {
      var mode = el.dataset.courseScope || "push";
      if (mode === "download") {
        var count = selectedDownloadCount();
        var html = focusName
          ? "<strong>Downloads from focused course only:</strong> " + push.esc(focusName)
          : "<strong>Downloads from focused course only:</strong> choose a focused course.";
        if (count) {
          html += ' <span class="course-scope-detail">Selected assignments: ' + count + "</span>";
        }
        el.innerHTML = html;
        return;
      }

      var html;
      if (!targets.length) {
        html = "<strong>Choose one or more target courses to continue.</strong>";
      } else if (targets.length === 1) {
        html = "<strong>Ready to push to:</strong> " + push.esc(targets[0].name) + ".";
      } else {
        html = "<strong>Ready to push to " + targets.length + " courses:</strong> " + courseListSummary(targets) + ".";
      }
      if (focusName) {
        html += ' <span class="course-scope-detail">Focused course for modules and categories: ' +
          push.esc(focusName) + ".</span>";
      }
      el.innerHTML = html;
    });
  }

  function readSavedState() {
    if (context) {
      var saved = context.snapshot();
      return {
        selectedIds: saved.targetCourses.map(function (item) { return String(item.id); }),
        focusedId: saved.focusedCourse ? String(saved.focusedCourse.id) : "",
      };
    }
    return null;
  }

  function saveState() {
    publishContext("course_picker");
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
        sum.innerHTML = "<strong>Ready to push to " + checked.length + " courses:</strong> " +
          names.map(push.esc).join(", ") + ".";
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
    renderCourseScopeSummaries();
  }

  // Focusing a different course row re-triggers this without cancelling a
  // slower earlier request, so a stale response could land last and point
  // "Open folder" at the previous course's downloads while a different
  // course is now focused. Stamp each request and let only the newest one
  // write, the same way inbox.js does.
  var folderLoadGeneration = 0;

  function loadCourseFolder(courseName) {
    var row = document.getElementById("folder-row");
    var path = document.getElementById("folder-path");
    var note = document.getElementById("folder-note");
    if (!row || !courseName) return;
    var generation = ++folderLoadGeneration;
    fetch("/api/course-folder?course_name=" + encodeURIComponent(courseName))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (generation !== folderLoadGeneration) return;
        row.hidden = false;
        path.textContent = d.path;
        path.title = d.path;
        note.textContent = d.exists ? "" : "(no downloads yet)";
        document.getElementById("btn-open-folder").dataset.path = d.path;
      })
      .catch(function () {});
  }

  function setFocus(id, options) {
    if (!checklist || !id) return;
    options = options || {};
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
    if (!options.skipSave) publishContext("course_picker");
  }

  function clearFocus() {
    if (!checklist) return;
    checklist.querySelectorAll(".cc-row.focused").forEach(function (r) {
      r.classList.remove("focused");
    });
    renderTargets();
    publishContext("course_picker");
  }

  function applySavedState() {
    if (!checklist) return false;
    var state = readSavedState();
    if (!state) {
      renderTargets();
      return false;
    }
    var selected = new Set(state.selectedIds);
    checklist.querySelectorAll(".cc-cb").forEach(function (cb) {
      cb.checked = selected.has(String(cb.value));
    });
    var focusId = state.focusedId || state.selectedIds.find(function (id) { return selected.has(id); });
    var focusExists = Array.from(checklist.querySelectorAll(".cc-row")).some(function (r) {
      return String(r.dataset.id) === String(focusId);
    });
    if (focusId && focusExists) {
      setFocus(focusId, { skipSave: true });
    } else {
      checklist.querySelectorAll(".cc-row.focused").forEach(function (r) {
        r.classList.remove("focused");
      });
      renderTargets();
    }
    return true;
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
      return;
    }
    // This row has no status line to write to, and the rename already speaks
    // through prompt(), so say plainly that the nickname did not save rather
    // than leave the old one sitting there looking accepted.
    alert(d.error || "That nickname could not be saved. The course keeps its previous name.");
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
        else clearFocus();
      } else {
        renderTargets();
        publishContext("course_picker");
      }
    });
    var currentCourses = Array.from(checklist.querySelectorAll(".cc-row")).map(function (row) {
      return { id: row.dataset.id, name: row.dataset.name };
    });
    context?.reconcile(currentCourses, { source: "course_picker", authoritative: true });
    applySavedState();
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    currentCourseId: currentCourseId,
    currentCourseName: currentCourseName,
    targetCourses: targetCourses,
    loadCourseFolder: loadCourseFolder,
    setFocus: setFocus,
    renderCourseScopeSummaries: renderCourseScopeSummaries,
  });
  window.targetCourses = targetCourses;

  bindChecklist();
  renderCourseScopeSummaries();
})();
