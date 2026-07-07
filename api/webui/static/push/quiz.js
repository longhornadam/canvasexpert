(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = [
    "postForm",
    "showLog",
    "hideBanner",
    "showBanner",
    "setBusy",
    "streamSSE",
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

  async function loadGroupsForCurrentCourse() {
    if (!requireReady()) return;
    var id = push.currentCourseId();
    if (!id || !groupStatus) return;
    groupStatus.className = "status hint";
    groupStatus.textContent = "Loading groups…";
    push.setBusy(true);
    try {
      var data = await fetch("/api/groups?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
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

  document.getElementById("btn-push")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var targets = push.targetCourses();
    var path = fileSel?.value;
    if (!targets.length) return alert("Check at least one course on the right.");
    if (!path) return alert("Pick a quiz file first.");
    var fname = path.split(/[\\/]/).pop();
    var list = targets.map(function (t) { return "  • " + t.name + " (#" + t.id + ")"; }).join("\n");
    if (!confirm(
      'Create a LIVE, UNPUBLISHED quiz from:\n  "' + fname + '"\n\n' +
      "in " + targets.length + " course(s):\n" + list + "\n\n" +
      "Canvas: " + window.QF_CANVAS_BASE + "\n\nContinue?"
    )) return;
    var log = push.showLog(result);
    push.hideBanner(document.getElementById("push-banner"));
    push.setBusy(true);
    var settings = encodeURIComponent(push.collectSettings());
    var url;
    if (targets.length === 1) {
      log("Pushing live quiz…\n");
      url = "/api/push/stream?course_id=" + encodeURIComponent(targets[0].id) +
            "&path=" + encodeURIComponent(path) + "&settings=" + settings;
    } else {
      log("Pushing live quiz to " + targets.length + " courses…\n");
      var ids = targets.map(function (t) { return t.id; }).join(",");
      url = "/api/push-multi-whole/stream?course_ids=" + encodeURIComponent(ids) +
            "&path=" + encodeURIComponent(path) + "&settings=" + settings;
    }
    var wantPhysical = document.getElementById("physical-version")?.checked;
    push.streamSSE(url, log, document.getElementById("push-banner"), function (ok) {
      push.setBusy(false);
      if (ok && wantPhysical) push.generatePhysical(path, log, document.getElementById("push-banner"));
    });
  });

  document.getElementById("btn-add-variant")?.addEventListener("click", function () {
    addVariantRow("", "");
  });

  document.getElementById("btn-push-variants")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var targets = push.targetCourses();
    if (!targets.length) return alert("Check at least one course on the right.");
    var rows = variantRows ? Array.from(variantRows.querySelectorAll(".variant-row")) : [];
    var variants = rows.map(function (r) {
      return {
        path: r.querySelector(".variant-file")?.value || "",
        groupId: r.querySelector(".variant-group")?.value || "",
        groupName: r.querySelector(".variant-group")?.selectedOptions[0]?.dataset.groupName || "",
        studentIds: JSON.parse(r.querySelector(".variant-group")?.selectedOptions[0]?.dataset.studentIds || "[]"),
      };
    }).filter(function (v) { return v.path; });
    if (variants.length < 2) return alert("Add at least 2 tier rows with files selected.");

    var log = push.showLog(document.getElementById("variants-result"));
    push.hideBanner(document.getElementById("variants-banner"));
    push.setBusy(true);

    var list = targets.map(function (t) { return "  • " + t.name + " (#" + t.id + ")"; }).join("\n");
    var varList = variants.map(function (v) {
      return "  • " + v.groupName + ": " + v.path.split(/[\\/]/).pop();
    }).join("\n");
    if (!confirm(
      "Push " + variants.length + " tier variants to " + targets.length + " course(s):\n" +
      list + "\n\nVariants:\n" + varList + "\n\nContinue?"
    )) { push.setBusy(false); return; }

    if (targets.length === 1) {
      var t = targets[0];
      var entries = variants.map(function (v) {
        return {
          label: v.groupName,
          path: v.path,
          student_ids: v.studentIds,
          group_name: v.groupName,
        };
      });
      log("Pushing variants…\n");
      push.streamSSE(
        "/api/push-variants/stream?course_id=" + encodeURIComponent(t.id) +
        "&manifest=" + encodeURIComponent(JSON.stringify(entries)),
        log, document.getElementById("variants-banner"), function () { push.setBusy(false); });
    } else {
      var multiManifest = targets.map(function (t) {
        return {
          course_id: t.id,
          course_name: t.name,
          variants: variants.map(function (v) {
            return {
              label: v.groupName,
              path: v.path,
              student_ids: v.studentIds,
              group_name: v.groupName,
            };
          }),
        };
      });
      log("Pushing variants to " + targets.length + " courses…\n");
      push.streamSSE(
        "/api/push-multi/stream?multi_manifest=" + encodeURIComponent(JSON.stringify(multiManifest)),
        log, document.getElementById("variants-banner"), function () { push.setBusy(false); });
    }
  });
})();
