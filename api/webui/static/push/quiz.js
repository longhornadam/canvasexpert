(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = [
    "postForm",
    "showLog",
    "hideBanner",
    "showBanner",
    "setBusy",
    "pushContent",
    "currentCourseId",
    "targetCourses",
    "collectSettings",
    "generatePhysical",
  ].every(function (name) { return typeof push[name] === "function"; });

  var fileSel = document.getElementById("quizfile");
  var result = document.getElementById("result");
  var variantRows = document.getElementById("variant-rows");
  var groupStatus = document.getElementById("groups-status");
  var canvasCategories = [];
  var fileOptions = window.QF_QUIZ_FILES || window.QF_FILES || [];

  function requireReady() {
    if (ready) return true;
    alert("Quiz push controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function resetCourseGroups() {
    canvasCategories = [];
    if (groupStatus) groupStatus.textContent = "";
  }

  function allGroupOptions() {
    return canvasCategories.flatMap(function (cat) {
      return cat.groups.map(function (g) {
        return {
          id: g.id,
          name: g.name,
          student_ids: g.student_ids,
          cat_name: cat.category_name,
        };
      });
    });
  }

  function addVariantRow(path, groupId) {
    var row = document.createElement("div");
    row.className = "variant-row";
    var groups = allGroupOptions();
    var gw = document.createElement("label");
    gw.textContent = "Canvas group";
    var gs = document.createElement("select");
    gs.className = "variant-group";
    if (!groups.length) {
      gs.appendChild(Object.assign(document.createElement("option"),
        { value: "", textContent: "— check a course to load groups —" }));
      gs.disabled = true;
    } else {
      groups.forEach(function (g) {
        var o = document.createElement("option");
        o.value = g.id;
        o.textContent = g.name + " (" + g.student_ids.length + ") — " + g.cat_name;
        o.dataset.studentIds = JSON.stringify(g.student_ids);
        o.dataset.groupName = g.name;
        if (g.id == groupId) o.selected = true;
        gs.appendChild(o);
      });
    }
    gw.appendChild(gs);
    var fileWrap = document.createElement("label");
    fileWrap.textContent = "Quiz file";
    var fileSl = document.createElement("select");
    fileSl.className = "variant-file";
    fileSl.appendChild(Object.assign(document.createElement("option"), { value: "", textContent: "— select —" }));
    fileOptions.forEach(function (f) {
      var o = document.createElement("option");
      o.value = f.path; o.textContent = f.label;
      if (f.path === path) o.selected = true;
      fileSl.appendChild(o);
    });
    fileWrap.appendChild(fileSl);
    row.appendChild(gw);
    row.appendChild(fileWrap);
    var rm = document.createElement("button");
    rm.type = "button"; rm.className = "small danger variant-remove";
    rm.textContent = "✕"; rm.title = "Remove this row";
    rm.addEventListener("click", function () { row.remove(); });
    row.appendChild(rm);
    variantRows?.appendChild(row);
  }

  function rebuildVariantRows() {
    var existing = Array.from(variantRows?.querySelectorAll(".variant-row") || []).map(function (r) {
      return {
        path: r.querySelector(".variant-file")?.value || "",
        groupId: r.querySelector(".variant-group")?.value || "",
      };
    });
    if (variantRows) variantRows.innerHTML = "";
    var groups = allGroupOptions();
    if (groups.length) {
      groups.forEach(function (g) {
        var prev = existing.find(function (e) { return e.groupId == g.id; });
        addVariantRow(prev?.path || "", g.id);
      });
    } else if (existing.length) {
      existing.forEach(function (e) { addVariantRow(e.path, e.groupId); });
    } else {
      addVariantRow("", "");
    }
  }

  // Focusing a different course, or re-clicking the differentiated-mode
  // segment, re-triggers this without cancelling a slower earlier request,
  // so a stale response could land last and fill the variant-row group
  // picker with the previous course's Canvas groups (and student counts)
  // while a different course is now focused. Stamp each request and let
  // only the newest one write, the same way inbox.js does.
  var loadGeneration = 0;

  async function loadGroupsForCurrentCourse() {
    if (!requireReady()) return;
    var id = push.currentCourseId();
    if (!id || !groupStatus) return;
    var generation = ++loadGeneration;
    groupStatus.className = "status hint";
    groupStatus.textContent = "Loading groups…";
    push.setBusy(true);
    try {
      var data = await fetch("/api/groups?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
      if (generation !== loadGeneration) return;
      if (!data.ok) {
        groupStatus.className = "status error";
        groupStatus.textContent = "Error: " + data.error;
        return;
      }
      canvasCategories = data.categories || [];
      if (!canvasCategories.length) {
        groupStatus.className = "status hint";
        groupStatus.textContent = data.message || "No group sets found in this course.";
        rebuildVariantRows();
        return;
      }
      var summary = canvasCategories.map(function (c) {
        return c.category_name + ": " + c.groups.map(function (g) {
          return g.name + " (" + g.student_ids.length + ")";
        }).join(", ");
      }).join(" · ");
      groupStatus.className = "status ok";
      groupStatus.textContent = "✓ Loaded: " + summary;
      rebuildVariantRows();
    } finally {
      push.setBusy(false);
    }
  }

  window.CE_QUIZ = { resetCourseGroups: resetCourseGroups };
  window.QF_loadGroups = loadGroupsForCurrentCourse;

  document.getElementById("btn-validate")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var path = fileSel?.value;
    if (!path) return alert("Pick a quiz file first.");
    var log = push.showLog(result);
    push.hideBanner(document.getElementById("push-banner"));
    log("Validating…");
    var data = await push.postForm("/api/validate", { path: path });
    if (data.error) { log("ERROR: " + data.error); return; }
    if (data.ok) {
      log("✓ No compliance issues found.");
      push.showBanner(document.getElementById("push-banner"), "ok", "✓ Validation passed — quiz is ready to push.");
    } else {
      log(data.problems.map(function (p) { return "  ✗ " + p; }).join("\n"));
      push.showBanner(document.getElementById("push-banner"), "fail",
        "✗ " + data.problems.length + " issue(s) found — see log above.");
    }
  });

  document.getElementById("btn-preview")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id = push.currentCourseId();
    var path = fileSel?.value;
    if (!id) return alert("Choose a course first.");
    if (!path) return alert("Pick a quiz file first.");
    var log = push.showLog(result);
    push.hideBanner(document.getElementById("push-banner"));
    log("Building dry-run preview (no live Canvas calls)…");
    push.setBusy(true);
    try {
      var settings = push.collectSettings();
      var data = await push.postForm("/api/push/preview", { course_id: id, path: path, settings: settings });
      log(data.error ? "ERROR: " + data.error : data.output);
    } finally {
      push.setBusy(false);
    }
  });

  document.getElementById("btn-push")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var targets = push.targetCourses();
    var path = fileSel?.value;
    if (!targets.length) return alert("Check at least one course on the right.");
    if (!path) return alert("Pick a quiz file first.");
    var settingsObj = {};
    try {
      settingsObj = JSON.parse(push.collectSettings() || "{}");
    } catch (e) {
      return alert("Quiz delivery settings could not be read. Refresh and try again.");
    }
    var wantPhysical = document.getElementById("physical-version")?.checked;
    push.setBusy(true);
    try {
      var applied = await push.pushContent(
        "qf",
        { mode: "whole", path: path, settings: settingsObj },
        result,
        document.getElementById("push-banner"),
        this,
        "Create this QuizForge quiz in Canvas."
      );
      if (applied && applied.status === "applied" && wantPhysical) {
        var physicalLog = function (line) {
          result.textContent += line + "\n";
          result.scrollTop = result.scrollHeight;
        };
        await push.generatePhysical(path, physicalLog, document.getElementById("push-banner"));
      }
    } finally {
      push.setBusy(false);
    }
  });

  document.getElementById("btn-add-variant")?.addEventListener("click", function () {
    addVariantRow("", "");
  });

  document.getElementById("btn-push-variants")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var targets = push.targetCourses();
    if (!targets.length) return alert("Check at least one course on the right.");
    var rows = variantRows ? Array.from(variantRows.querySelectorAll(".variant-row")) : [];
    var variants = rows.map(function (r) {
      return {
        path: r.querySelector(".variant-file")?.value || "",
        group_name: r.querySelector(".variant-group")?.selectedOptions[0]?.dataset.groupName || "",
      };
    }).filter(function (v) { return v.path; });
    if (variants.length < 2) return alert("Add at least 2 tier rows with files selected.");
    if (variants.some(function (variant) { return !variant.group_name.trim(); })) {
      return alert("Choose a Canvas group for every tier row with a quiz file.");
    }
    var settingsObj = {};
    try {
      settingsObj = JSON.parse(push.collectSettings() || "{}");
    } catch (e) {
      return alert("Quiz delivery settings could not be read. Refresh and try again.");
    }
    push.setBusy(true);
    try {
      await push.pushContent(
        "qf",
        { mode: "differentiated", variants: variants, settings: settingsObj },
        document.getElementById("variants-result"),
        document.getElementById("variants-banner"),
        this,
        "Create these differentiated QuizForge quizzes in Canvas."
      );
    } finally {
      push.setBusy(false);
    }
  });
})();
