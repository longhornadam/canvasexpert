(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "getCurrentCourseId",
    "hasLoadedCourse",
    "onCourseLoaded",
    "getGroupState",
    "setSelectedGroupCategoryId",
    "reloadCourse"
  ].every(function (name) { return typeof roster[name] === "function"; });

  if (!ready) {
    window.alert("Roster group tools need a page refresh.");
    return;
  }

  var groupSetPicker = document.getElementById("roster-group-set-picker");
  var newGroupSetName = document.getElementById("roster-new-group-set-name");
  var newGroupNames = document.getElementById("roster-new-group-names");
  var createGroupSetBtn = document.getElementById("roster-create-group-set");
  var addGroupsBtn = document.getElementById("roster-add-groups");
  var groupBuilderStatus = document.getElementById("roster-group-builder-status");
  var groupLabelsEditor = document.getElementById("roster-group-labels-editor");
  var groupLabelsRows = document.getElementById("roster-group-labels-rows");
  var groupLabelsSaveBtn = document.getElementById("roster-group-labels-save");
  var groupLabelsStatus = document.getElementById("roster-group-labels-status");

  if (!groupSetPicker || !newGroupSetName || !newGroupNames || !createGroupSetBtn || !addGroupsBtn ||
      !groupBuilderStatus || !groupLabelsEditor || !groupLabelsRows || !groupLabelsSaveBtn || !groupLabelsStatus) {
    return;
  }

  var groupState = {
    groups: [],
    selectedGroupCategoryId: null,
    groupLabelScheme: {},
    currentCategoryGroups: []
  };

  function groupId(group) {
    return String((group && (group.id || group.group_id)) || "");
  }

  function setGroupBuilderStatus(msg, isOk) {
    groupBuilderStatus.textContent = msg;
    groupBuilderStatus.className = "hint" + (isOk ? " ok" : " error");
  }

  function parseGroupNameText() {
    return (newGroupNames.value || "")
      .split(/\r?\n|,/)
      .map(function (name) { return name.trim(); })
      .filter(Boolean);
  }

  function syncGroupState() {
    var state = roster.getGroupState() || {};
    groupState.groups = state.groups || [];
    groupState.selectedGroupCategoryId = state.selectedGroupCategoryId == null ? null : String(state.selectedGroupCategoryId);
    groupState.groupLabelScheme = state.groupLabelScheme || {};
    groupState.currentCategoryGroups = state.currentCategoryGroups || [];
  }

  function populateGroupSetPicker() {
    groupSetPicker.innerHTML = "";
    if (!groupState.groups.length) {
      groupSetPicker.innerHTML = '<option value="">— no group sets —</option>';
      return;
    }
    for (var i = 0; i < groupState.groups.length; i++) {
      var g = groupState.groups[i];
      var option = document.createElement("option");
      option.value = String(g.category_id);
      option.textContent = g.category_name;
      if (String(g.category_id) === String(groupState.selectedGroupCategoryId || "")) {
        option.selected = true;
      }
      groupSetPicker.appendChild(option);
    }
  }

  function renderGroupLabelsEditor() {
    groupLabelsRows.innerHTML = "";
    var categoryGroups = groupState.currentCategoryGroups || [];
    for (var i = 0; i < categoryGroups.length; i++) {
      var g = categoryGroups[i];
      var gid = groupId(g);
      var label = groupState.groupLabelScheme[gid] || {};
      var teacherLabel = label.teacher_label || "";
      var meaning = label.meaning || "";

      var row = document.createElement("div");
      row.className = "roster-v2-tier-row";
      row.dataset.groupId = gid;

      var nameSpan = document.createElement("span");
      nameSpan.className = "roster-v2-group-name";
      nameSpan.textContent = g.name;

      var teacherLabelInput = document.createElement("input");
      teacherLabelInput.type = "text";
      teacherLabelInput.className = "roster-v2-tier-label";
      teacherLabelInput.value = teacherLabel;
      teacherLabelInput.title = "Teacher label";
      teacherLabelInput.placeholder = "Label";

      var meaningInput = document.createElement("input");
      meaningInput.type = "text";
      meaningInput.className = "roster-v2-tier-meaning";
      meaningInput.value = meaning;
      meaningInput.title = "Meaning";
      meaningInput.placeholder = "Meaning";

      row.appendChild(nameSpan);
      row.appendChild(document.createTextNode(" → "));
      row.appendChild(teacherLabelInput);
      row.appendChild(meaningInput);
      groupLabelsRows.appendChild(row);
    }
  }

  function saveGroupSetPreference() {
    var body = new URLSearchParams();
    body.append("course_id", roster.getCurrentCourseId());
    body.append("category_id", groupState.selectedGroupCategoryId || "");
    fetch("/api/roster/group-set-preference", { method: "POST", body: body })
      .catch(function () { /* silent fail */ });
  }

  function createGroupSet() {
    var cid = roster.getCurrentCourseId();
    var setName = newGroupSetName.value.trim();
    var names = parseGroupNameText();
    if (!cid) { setGroupBuilderStatus("Select a course first.", false); return; }
    if (!setName) { setGroupBuilderStatus("Name the group set first.", false); return; }

    createGroupSetBtn.disabled = true;
    addGroupsBtn.disabled = true;
    setGroupBuilderStatus("Creating in Canvas...", true);

    var body = new URLSearchParams();
    body.append("course_id", cid);
    body.append("name", setName);
    body.append("group_names", JSON.stringify(names));

    fetch("/api/roster/group-set", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          setGroupBuilderStatus(data.error || "Create failed.", false);
          return;
        }
        newGroupSetName.value = "";
        newGroupNames.value = "";
        setGroupBuilderStatus("Created group set" + (data.created_groups && data.created_groups.length ? " and " + data.created_groups.length + " group(s)." : "."), true);
        roster.reloadCourse();
      })
      .catch(function (e) { setGroupBuilderStatus("Error: " + e.message, false); })
      .finally(function () {
        createGroupSetBtn.disabled = false;
        addGroupsBtn.disabled = false;
      });
  }

  function addGroups() {
    var cid = roster.getCurrentCourseId();
    var categoryId = groupSetPicker.value;
    var names = parseGroupNameText();
    if (!cid) { setGroupBuilderStatus("Select a course first.", false); return; }
    if (!categoryId) { setGroupBuilderStatus("Select a group set first.", false); return; }
    if (!names.length) { setGroupBuilderStatus("Enter at least one group name.", false); return; }

    createGroupSetBtn.disabled = true;
    addGroupsBtn.disabled = true;
    setGroupBuilderStatus("Creating groups in Canvas...", true);

    var body = new URLSearchParams();
    body.append("course_id", cid);
    body.append("category_id", categoryId);
    body.append("group_names", JSON.stringify(names));

    fetch("/api/roster/groups", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          setGroupBuilderStatus(data.error || "Create failed.", false);
          return;
        }
        newGroupNames.value = "";
        setGroupBuilderStatus("Created " + (data.created_groups || []).length + " group(s).", true);
        roster.reloadCourse();
      })
      .catch(function (e) { setGroupBuilderStatus("Error: " + e.message, false); })
      .finally(function () {
        createGroupSetBtn.disabled = false;
        addGroupsBtn.disabled = false;
      });
  }

  function saveGroupLabels() {
    var rows = groupLabelsRows.querySelectorAll(".roster-v2-tier-row");
    var labels = {};
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var gid = r.dataset.groupId;
      var label = r.querySelector(".roster-v2-tier-label").value.trim();
      var meaning = r.querySelector(".roster-v2-tier-meaning").value.trim();
      if (label) {
        labels[gid] = { teacher_label: label, meaning: meaning };
      }
    }

    groupLabelsStatus.textContent = "Saving...";
    var body = new URLSearchParams();
    body.append("course_id", roster.getCurrentCourseId());
    body.append("labels", JSON.stringify(labels));

    fetch("/api/roster/group-labels", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          groupLabelsStatus.textContent = "Saved.";
          groupState.groupLabelScheme = data.group_labels || {};
          renderGroupLabelsEditor();
          roster.reloadCourse();
        } else {
          groupLabelsStatus.textContent = data.error || "Save failed.";
        }
      })
      .catch(function (e) { groupLabelsStatus.textContent = "Error: " + e.message; });
  }

  function refreshGroupUi() {
    syncGroupState();
    populateGroupSetPicker();
    renderGroupLabelsEditor();
  }

  groupSetPicker.addEventListener("change", function () {
    roster.setSelectedGroupCategoryId(this.value);
    syncGroupState();
    saveGroupSetPreference();
  });

  createGroupSetBtn.addEventListener("click", createGroupSet);
  addGroupsBtn.addEventListener("click", addGroups);
  groupLabelsSaveBtn.addEventListener("click", saveGroupLabels);

  roster.onCourseLoaded(refreshGroupUi);
  syncGroupState();
  if (roster.hasLoadedCourse()) {
    refreshGroupUi();
  }
})();
