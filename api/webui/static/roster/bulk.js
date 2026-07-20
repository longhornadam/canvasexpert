(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "toast",
    "postForm",
    "getCurrentCourseId",
    "getGroupState",
    "getSelectedNameMap",
    "onTableRendered",
    "reloadCourse"
  ].every(function (name) { return typeof roster[name] === "function"; });

  if (!ready) {
    window.alert("Roster bulk tools need a page refresh.");
    return;
  }

  var selectAll = document.getElementById("roster-select-all");
  var bulkBar = document.getElementById("roster-bulk-bar");
  var bulkCount = document.getElementById("roster-bulk-count");
  var bulkGroup = document.getElementById("roster-bulk-group");
  var bulkExtraDays = document.getElementById("roster-bulk-extra-days");
  var bulkActions = document.querySelector(".roster-bulk-actions");
  var tableBody = document.getElementById("roster-table-body");

  if (!selectAll || !bulkBar || !bulkCount || !bulkGroup || !bulkExtraDays || !bulkActions || !tableBody) {
    return;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function groupId(group) {
    return String((group && (group.id || group.group_id)) || "");
  }

  function groupDisplay(group, labelScheme) {
    var gid = groupId(group);
    var label = (labelScheme && labelScheme[gid] && labelScheme[gid].teacher_label) || group.teacher_label || "";
    return label && label !== group.name ? label + " / " + group.name : group.name;
  }

  function getSelectedIds() {
    var ids = [];
    var checks = tableBody.querySelectorAll(".roster-row-check:checked");
    for (var i = 0; i < checks.length; i++) {
      ids.push(checks[i].dataset.id);
    }
    return ids;
  }

  function updateBulkBar() {
    var ids = getSelectedIds();
    bulkBar.hidden = ids.length === 0;
    if (ids.length > 0) bulkCount.textContent = "Bulk edit: " + ids.length + " selected";
  }

  function refreshBulkGroupOptions() {
    var state = roster.getGroupState() || {};
    var groups = state.currentCategoryGroups || [];
    var labelScheme = state.groupLabelScheme || {};
    var selected = bulkGroup.value;

    bulkGroup.innerHTML = '<option value="">Choose group...</option>';
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      var gid = groupId(g);
      var label = groupDisplay(g, labelScheme);
      bulkGroup.innerHTML += '<option value="' + esc(gid) + '">' + esc(label) + "</option>";
    }
    bulkGroup.value = selected;
  }

  function refreshBulkUi() {
    refreshBulkGroupOptions();
    updateBulkBar();
  }

  function doBulkAction(action, ids, value) {
    roster.postForm("/api/roster/bulk", {
      course_id: roster.getCurrentCourseId(),
      user_ids: JSON.stringify(ids),
      action: action,
      value: JSON.stringify(value)
    })
      .then(function (data) {
        if (data.ok) {
          var msg = "Updated " + data.updated + " students.";
          if (data.failed && data.failed > 0) {
            msg = "Updated " + data.updated + "; failed " + data.failed + ": " + (data.errors || []).join("; ");
          }
          roster.toast(msg, data.failed > 0);
          roster.reloadCourse();
        } else {
          roster.toast(data.error || "Bulk action failed.", true);
        }
      })
      .catch(function (e) { roster.toast("Error: " + e.message, true); });
  }

  selectAll.addEventListener("change", function () {
    var checked = selectAll.checked;
    var checkboxes = tableBody.querySelectorAll(".roster-row-check");
    for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = checked;
    }
    updateBulkBar();
  });

  tableBody.addEventListener("change", function (e) {
    if (e.target.classList.contains("roster-row-check")) {
      updateBulkBar();
    }
  });

  bulkActions.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-bulk]");
    if (!btn) return;
    var action = btn.dataset.bulk;
    var ids = getSelectedIds();
    if (ids.length === 0) return;

    var value = {};
    if (action === "set_extra_time") {
      value = { days: parseInt(bulkExtraDays.value, 10) || 2, names: roster.getSelectedNameMap() };
    } else if (action === "set_monitored") {
      value = { names: roster.getSelectedNameMap() };
    } else if (action === "set_canvas_group") {
      var gid = bulkGroup.value;
      if (!gid) {
        roster.toast("Select a group first.", true);
        return;
      }
      var state = roster.getGroupState() || {};
      value = { category_id: state.selectedGroupCategoryId, group_id: gid };
    } else if (action === "clear_canvas_group") {
      var stateForClear = roster.getGroupState() || {};
      if (!stateForClear.selectedGroupCategoryId) {
        roster.toast("Select a group set first.", true);
        return;
      }
      value = { category_id: stateForClear.selectedGroupCategoryId };
    }

    doBulkAction(action, ids, value);
  });

  roster.onTableRendered(refreshBulkUi);
  refreshBulkUi();
})();
