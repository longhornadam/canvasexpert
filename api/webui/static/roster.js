/**
 * Roster Console V3 — Canvas groups are the source of truth.
 *
 * Canvas group column shows real Canvas groups from a selected group set.
 * Status: "synced to Canvas" or actual Canvas error.
 */
(function () {
  "use strict";

  var courseSelect = document.getElementById("roster-course");
  var refreshBtn = document.getElementById("roster-refresh");
  var openCanvas = document.getElementById("roster-open-canvas");
  var statusEl = document.getElementById("roster-status");
  var tableCard = document.getElementById("roster-table-card");
  var tableBody = document.getElementById("roster-table-body");
  var searchInput = document.getElementById("roster-search");
  var filterBtns = document.querySelectorAll(".roster-filter-btn");
  var selectAll = document.getElementById("roster-select-all");
  var bulkBar = document.getElementById("roster-bulk-bar");
  var bulkCount = document.getElementById("roster-bulk-count");
  var bulkGroup = document.getElementById("roster-bulk-group");
  var bulkExtraDays = document.getElementById("roster-bulk-extra-days");
  var safetyCard = document.getElementById("roster-safety-card");
  var groupLabelsEditor = document.getElementById("roster-group-labels-editor");
  var groupLabelsRows = document.getElementById("roster-group-labels-rows");
  var groupLabelsSaveBtn = document.getElementById("roster-group-labels-save");
  var groupLabelsStatus = document.getElementById("roster-group-labels-status");

  // Protected names
  var protectedPacksEl = document.getElementById("roster-protected-packs");
  var customProtectedInput = document.getElementById("roster-custom-protected");
  var saveProtectedBtn = document.getElementById("roster-save-protected");
  var scrubText = document.getElementById("roster-scrub-text");
  var scrubRun = document.getElementById("roster-scrub-run");
  var scrubResult = document.getElementById("roster-scrub-result");
  var exportWhoBtn = document.getElementById("roster-export-who");
  var backupVaultBtn = document.getElementById("roster-backup-vault");

  // Group set picker
  var groupSetPicker = document.getElementById("roster-group-set-picker");

  // State
  var students = [];
  var groups = [];
  var selectedGroupCategoryId = null;
  var groupLabelScheme = {};
  var selectedStudentId = null;
  var filteredStudents = [];
  var currentCourseId = "";
  var protectedData = { packs: [], custom: [], active: [] };
  var saveTimeouts = {}; // row id -> timeout for debounced save

  // ── Helper ─────────────────────────────────────────────────────────

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function setStatus(msg, isOk) {
    statusEl.textContent = msg;
    statusEl.className = "hint" + (isOk ? " ok" : " error");
  }

  function toast(msg, isError) {
    var el = document.getElementById("ce-toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "ce-toast" + (isError ? " ce-toast--error" : " ce-toast--ok");
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, 3000);
  }

  function setRowStatus(rowId, msg, cls) {
    var row = tableBody.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) return;
    var el = row.querySelector(".roster-v2-status");
    if (!el) return;
    el.textContent = msg;
    el.title = msg;
    el.className = "roster-v2-status " + (cls || "");
  }

  function warningLabel(code) {
    var labels = {
      missing_pseudonym: "Missing pseudonym",
      extra_time_without_days: "Extra time needs days",
      group_unset: "Group unset",
      multiple_groups_in_selected_set: "Multiple groups",
      protected_name_collision: "Protected name collision",
      nickname_collision: "Nickname collision"
    };
    return labels[code] || String(code || "Issue").replace(/_/g, " ");
  }

  function rowStatus(warnings, canvasGroup) {
    var issues = (warnings || []).map(warningLabel);
    if (canvasGroup && canvasGroup.group_id) {
      // Canvas-backed field
      if (issues.length > 0) {
        return {
          text: issues[0] + (issues.length > 1 ? " +" + (issues.length - 1) : ""),
          title: issues.join("; "),
          cls: "roster-v2-status-warning"
        };
      }
      return {
        text: "synced to Canvas",
        title: "Synced to Canvas",
        cls: "roster-v2-status-ok"
      };
    }
    // No group assigned
    if (issues.length > 0) {
      return {
        text: issues[0] + (issues.length > 1 ? " +" + (issues.length - 1) : ""),
        title: issues.join("; "),
        cls: "roster-v2-status-warning"
      };
    }
    return {
      text: "not in group",
      title: "Not assigned to a group in the selected set",
      cls: "roster-v2-status-none"
    };
  }

  function findStudent(id) {
    for (var i = 0; i < students.length; i++) {
      if (students[i].id === id) return students[i];
    }
    return null;
  }

  // ── Course load ─────────────────────────────────────────────────────

  function loadCourse() {
    var cid = courseSelect.value;
    if (!cid) {
      tableCard.hidden = true;
      groupLabelsEditor.hidden = true;
      safetyCard.hidden = true;
      return;
    }
    currentCourseId = cid;
    setStatus("Loading...", true);
    openCanvas.href = window.CANVAS_BASE
      ? window.CANVAS_BASE + "/courses/" + cid + "/users"
      : "#";

    fetch("/api/roster?course_id=" + encodeURIComponent(cid))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          setStatus(data.error || "Failed to load roster.", false);
          return;
        }
        students = data.students || [];
        groups = data.groups || [];
        selectedGroupCategoryId = data.selected_group_category_id;
        groupLabelScheme = data.group_label_scheme || {};
        renderSummary(data.counts);
        populateGroupSetPicker();
        populateCanvasGroupSelects();
        renderTable();
        tableCard.hidden = false;
        groupLabelsEditor.hidden = false;
        safetyCard.hidden = false;
        renderGroupLabelsEditor();
        setStatus("Loaded " + students.length + " students" + (data.note ? " — " + data.note : ""), true);
        if (data.legacy_tier_count) {
          toast("This course has old local tier assignments. Canvas groups are now the source of truth.", true);
        }
        if (scrubText.value) scrubRun.click();
      })
      .catch(function (e) {
        setStatus("Network error: " + e.message, false);
      });
  }

  function renderSummary(counts) {
    if (!counts) return;
    document.getElementById("roster-summary-total").textContent = counts.total + " students";
    document.getElementById("roster-summary-extra").textContent = "Extra " + counts.extra_time;
    document.getElementById("roster-summary-monitored").textContent = "Monitored " + counts.monitored;
    document.getElementById("roster-summary-group-unset").textContent = "Unset " + counts.group_unset;
    document.getElementById("roster-summary-warnings").textContent = "Issues " + counts.warnings;
  }

  function populateGroupSetPicker() {
    groupSetPicker.innerHTML = "";
    if (!groups.length) {
      groupSetPicker.innerHTML = '<option value="">— no group sets —</option>';
      return;
    }
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      var sel = g.category_id === selectedGroupCategoryId ? " selected" : "";
      groupSetPicker.innerHTML += '<option value="' + esc(g.category_id) + '"' + sel + '>' + esc(g.category_name) + '</option>';
    }
  }

  function populateCanvasGroupSelects() {
    // Build the list of groups in the selected category
    var category = groups.find(function(g) { return g.category_id === selectedGroupCategoryId; });
    var categoryGroups = category ? category.groups : [];

    // Store for use in row rendering
    window._currentCategoryGroups = categoryGroups;

    bulkGroup.innerHTML = '<option value="">Choose group...</option>';
    for (var i = 0; i < categoryGroups.length; i++) {
      var g = categoryGroups[i];
      var gid = groupId(g);
      var label = groupDisplay(g);
      bulkGroup.innerHTML += '<option value="' + esc(gid) + '">' + esc(label) + '</option>';
    }
  }

  function groupId(group) {
    return String((group && (group.id || group.group_id)) || "");
  }

  function groupLabel(group) {
    var gid = groupId(group);
    return (groupLabelScheme && groupLabelScheme[gid]) || {};
  }

  function groupDisplay(group) {
    var label = groupLabel(group).teacher_label || group.teacher_label || "";
    return label && label !== group.name ? label + " / " + group.name : group.name;
  }

  function findCurrentCategoryGroup(targetGroupId) {
    var categoryGroups = window._currentCategoryGroups || [];
    var target = String(targetGroupId || "");
    for (var i = 0; i < categoryGroups.length; i++) {
      if (groupId(categoryGroups[i]) === target) return categoryGroups[i];
    }
    return null;
  }

  // ── Render table ───────────────────────────────────────────────────

  function renderTable() {
    var q = (searchInput.value || "").toLowerCase().trim();
    var activeFilter = document.querySelector(".roster-filter-btn.active");
    var filter = activeFilter ? activeFilter.dataset.filter : "all";

    var categoryGroups = window._currentCategoryGroups || [];

    filteredStudents = students.filter(function (s) {
      if (q) {
        var haystack = (s.name + " " + s.display_name + " " + s.short_name + " " +
          (s.nicknames || []).join(" ") + " " + (s.pseudonym || "") + " " +
          ((s.monitored && s.monitored.note) || "")).toLowerCase();
        if (haystack.indexOf(q) === -1) return false;
      }
      if (filter === "extra_time" && !s.extra_time.enabled) return false;
      if (filter === "monitored" && !s.monitored.enabled) return false;
      if (filter === "group_unset" && s.canvas_group && s.canvas_group.group_id) return false;
      if (filter === "warnings" && (!s.warnings || s.warnings.length === 0)) return false;
      return true;
    });

    if (filteredStudents.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="9" class="roster-empty">No students.</td></tr>';
      return;
    }

    // Build canvas group select HTML
    function canvasGroupOptions(selected) {
      var h = '<option value="">— no group —</option>';
      for (var i = 0; i < categoryGroups.length; i++) {
        var g = categoryGroups[i];
        var gid = groupId(g);
        var label = groupDisplay(g);
        var sel = gid === String(selected || "") ? " selected" : "";
        h += '<option value="' + esc(gid) + '"' + sel + '>' + esc(label) + "</option>";
      }
      return h;
    }

    var html = "";
    for (var i = 0; i < filteredStudents.length; i++) {
      var s = filteredStudents[i];
      var sel = selectedStudentId === s.id ? ' class="roster-v2-row-selected"' : "";

      var canvasGroup = s.canvas_group || {};
      var nnVal = esc((s.nicknames || []).join(", "));
      var pseudoVal = esc(s.pseudonym || "");
      var noteVal = esc((s.monitored && s.monitored.note) || "");
      var status = rowStatus(s.warnings, canvasGroup);

      html += "<tr" + sel + ' data-id="' + esc(s.id) + '">' +
        '<td class="roster-col-check"><input type="checkbox" class="roster-row-check" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-name"><span class="roster-v2-name">' + esc(s.display_name || s.name) + "</span></td>" +
        '<td class="roster-col-nicknames"><input type="text" class="roster-v2-input roster-v2-nicknames" value="' + nnVal + '" placeholder="nicknames" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-pseudo"><span class="roster-v2-pseudo-row"><input type="text" class="roster-v2-input roster-v2-pseudo" value="' + pseudoVal + '" placeholder="pseudonym" data-id="' + esc(s.id) + '" data-field="pseudo"><button type="button" class="roster-v2-regen" data-id="' + esc(s.id) + '" title="Regenerate">&#x21bb;</button></span></td>' +
        '<td class="roster-col-extratime"><label class="roster-v2-et"><input type="checkbox" class="roster-v2-et-cb" data-id="' + esc(s.id) + '"' + (s.extra_time.enabled ? " checked" : "") + ">" +
        (s.extra_time.enabled ? ('<input type="number" class="roster-v2-et-days" value="' + (s.extra_time.days || 0) + '" min="0" max="30" data-id="' + esc(s.id) + '">') : '<input type="number" class="roster-v2-et-days" value="0" min="0" max="30" data-id="' + esc(s.id) + '" hidden>') +
        "</label></td>" +
        '<td class="roster-col-group"><select class="roster-v2-canvas-group" data-id="' + esc(s.id) + '" data-category="' + esc(selectedGroupCategoryId || "") + '">' + canvasGroupOptions(canvasGroup.group_id) + "</select></td>" +
        '<td class="roster-col-monitor"><input type="checkbox" class="roster-v2-monitor" data-id="' + esc(s.id) + '"' + (s.monitored.enabled ? " checked" : "") + "></td>" +
        '<td class="roster-col-note"><input type="text" class="roster-v2-input roster-v2-note" value="' + noteVal + '" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-status"><span class="roster-v2-status ' + status.cls + '" title="' + esc(status.title) + '">' + esc(status.text) + '</span></td>' +
        "</tr>";
    }
    tableBody.innerHTML = html;
    attachInlineEvents();
    updateBulkBar();
  }

  // ── Inline editing with autosave ───────────────────────────────────

  function attachInlineEvents() {
    // Nicknames: save on Enter or blur
    tableBody.querySelectorAll(".roster-v2-nicknames").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var val = el.value.split(",").map(function (n) { return n.trim(); }).filter(Boolean);
        saveField(id, "nicknames", val);
      });
    });

    // Pseudonym: save on blur (full pseudo as first/last split)
    tableBody.querySelectorAll(".roster-v2-pseudo").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var parts = el.value.trim().split(/\s+/);
        var first = parts[0] || "";
        var last = parts.slice(1).join(" ") || "";
        saveField(id, "pseudonym", { first: first, last: last });
      });
    });

    // Regenerate
    tableBody.querySelectorAll(".roster-v2-regen").forEach(function (el) {
      el.addEventListener("click", function () {
        var id = el.dataset.id;
        setRowStatus(id, "saving...", "roster-v2-status-saving");
        saveField(id, "regenerate_pseudonym", true);
      });
    });

    // Extra time checkbox
    tableBody.querySelectorAll(".roster-v2-et-cb").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        var daysInput = el.closest("label").querySelector(".roster-v2-et-days");
        var enabled = el.checked;
        daysInput.hidden = !enabled;
        if (enabled) daysInput.value = daysInput.value || "2";
        saveField(id, "extra_time", {
          enabled: enabled,
          days: enabled ? parseInt(daysInput.value, 10) || 2 : 0,
          name: s ? (s.display_name || s.name) : ""
        });
      });
    });

    // Extra time days
    tableBody.querySelectorAll(".roster-v2-et-days").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        var cb = el.closest("label").querySelector(".roster-v2-et-cb");
        saveField(id, "extra_time", {
          enabled: cb.checked,
          days: parseInt(el.value, 10) || 0,
          name: s ? (s.display_name || s.name) : ""
        });
      });
    });

    // Canvas group select: writes real Canvas group membership.
    tableBody.querySelectorAll(".roster-v2-canvas-group").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        saveField(id, "canvas_group", {
          category_id: el.dataset.category || selectedGroupCategoryId,
          group_id: el.value || null
        });
      });
    });

    // Monitor checkbox
    tableBody.querySelectorAll(".roster-v2-monitor").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        var noteInput = el.closest("tr").querySelector(".roster-v2-note");
        saveField(id, "monitored", {
          enabled: el.checked,
          name: s ? (s.display_name || s.name) : "",
          note: noteInput ? noteInput.value : (s ? (s.monitored.note || "") : "")
        });
      });
    });

    // Private note: stored with the monitored-student metadata.
    tableBody.querySelectorAll(".roster-v2-note").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        if (!s) return;
        var note = el.value.trim();
        saveField(id, "monitored", {
          enabled: s.monitored.enabled || !!note,
          name: s.display_name || s.name,
          note: note
        });
      });
    });
  }

  // ── Autosave ───────────────────────────────────────────────────────

  function saveField(userId, key, value) {
    var isCanvasGroup = key === "canvas_group";
    setRowStatus(userId, isCanvasGroup ? "syncing to Canvas..." : "saving locally...", "roster-v2-status-saving");

    if (saveTimeouts[userId]) {
      clearTimeout(saveTimeouts[userId]);
    }

    // Debounce: wait 300ms then send
    saveTimeouts[userId] = setTimeout(function () {
      var patch = {};
      patch[key] = value;

      var body = new URLSearchParams();
      body.append("course_id", currentCourseId);
      body.append("user_id", userId);
      body.append("patch", JSON.stringify(patch));

      fetch("/api/roster/student", { method: "POST", body: body })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            updateLocalStudent(userId, key, value);
            setRowStatus(userId, isCanvasGroup ? "synced to Canvas" : "saved locally", "roster-v2-status-ok");
          } else {
            var apiMsg = data.error || "Save failed.";
            setRowStatus(userId, "Error: " + apiMsg, "roster-v2-status-error");
            toast(apiMsg, true);
          }
        })
        .catch(function (e) {
          var netMsg = "Network error: " + e.message;
          setRowStatus(userId, netMsg, "roster-v2-status-error");
          toast(netMsg, true);
        });
    }, 300);
  }

  function updateLocalStudent(userId, key, value) {
    var s = findStudent(userId);
    if (!s) return;
    if (key === "nicknames") {
      s.nicknames = value;
    } else if (key === "pseudonym") {
      s.pseudonym = [value.first, value.last].filter(Boolean).join(" ");
    } else if (key === "extra_time") {
      s.extra_time = { enabled: !!value.enabled, days: value.days || 0 };
    } else if (key === "canvas_group") {
      var group = findCurrentCategoryGroup(value.group_id);
      if (group && value.group_id) {
        var label = groupLabel(group).teacher_label || group.teacher_label || "";
        s.canvas_group = {
          category_id: value.category_id,
          category_name: (groups.find(function (g) { return g.category_id === value.category_id; }) || {}).category_name || "",
          group_id: groupId(group),
          group_name: group.name,
          teacher_label: label || null,
          display: groupDisplay(group)
        };
      } else {
        s.canvas_group = null;
      }
    } else if (key === "monitored") {
      s.monitored = { enabled: !!value.enabled, note: value.note || "" };
    }
  }

  // ── Group set picker change ─────────────────────────────────────────

  groupSetPicker.addEventListener("change", function () {
    selectedGroupCategoryId = this.value;
    saveGroupSetPreference();
    populateCanvasGroupSelects();
    renderTable();
  });

  function saveGroupSetPreference() {
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);
    body.append("category_id", selectedGroupCategoryId || "");
    fetch("/api/roster/group-set-preference", { method: "POST", body: body })
      .catch(function (e) { /* silent fail */ });
  }

  // ── Filters ─────────────────────────────────────────────────────────

  searchInput.addEventListener("input", renderTable);

  for (var fi = 0; fi < filterBtns.length; fi++) {
    filterBtns[fi].addEventListener("click", function () {
      for (var fj = 0; fj < filterBtns.length; fj++) {
        filterBtns[fj].classList.remove("active");
      }
      this.classList.add("active");
      renderTable();
    });
  }

  // ── Select all / bulk ───────────────────────────────────────────────

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

  // ── Bulk actions ────────────────────────────────────────────────────

  document.querySelector(".roster-bulk-actions").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-bulk]");
    if (!btn) return;
    var action = btn.dataset.bulk;
    var ids = getSelectedIds();
    if (ids.length === 0) return;

    var value = {};
    if (action === "set_extra_time") {
      value = { days: parseInt(bulkExtraDays.value, 10) || 2, names: getSelectedNameMap() };
    } else if (action === "set_monitored") {
      value = { names: getSelectedNameMap() };
    } else if (action === "set_canvas_group") {
      var gid = bulkGroup.value;
      if (!gid) { toast("Select a group first.", true); return; }
      value = { category_id: selectedGroupCategoryId, group_id: gid };
      action = "set_canvas_group";
    } else if (action === "clear_canvas_group") {
      if (!selectedGroupCategoryId) { toast("Select a group set first.", true); return; }
      value = { category_id: selectedGroupCategoryId };
    }

    doBulkAction(action, ids, value);
  });

  function getSelectedNameMap() {
    var names = {};
    var ids = getSelectedIds();
    for (var i = 0; i < ids.length; i++) {
      var s = findStudent(ids[i]);
      names[ids[i]] = s ? (s.display_name || s.name) : ids[i];
    }
    return names;
  }

  function doBulkAction(action, ids, value) {
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);
    body.append("user_ids", JSON.stringify(ids));
    body.append("action", action);
    body.append("value", JSON.stringify(value));

    fetch("/api/roster/bulk", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          var msg = "Updated " + data.updated + " students.";
          if (data.failed && data.failed > 0) {
            msg = "Updated " + data.updated + "; failed " + data.failed + ": " + (data.errors || []).join("; ");
          }
          toast(msg, data.failed > 0);
          loadCourse();
        } else {
          toast(data.error || "Bulk action failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  }

  // ── Group labels editor ─────────────────────────────────────────────

  function renderGroupLabelsEditor() {
    groupLabelsRows.innerHTML = "";
    var categoryGroups = window._currentCategoryGroups || [];
    for (var i = 0; i < categoryGroups.length; i++) {
      var g = categoryGroups[i];
      var gid = groupId(g);
      var label = groupLabelScheme[gid] || {};
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

  groupLabelsSaveBtn.addEventListener("click", function () {
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
    body.append("course_id", currentCourseId);
    body.append("labels", JSON.stringify(labels));

    fetch("/api/roster/group-labels", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          groupLabelsStatus.textContent = "Saved.";
          groupLabelScheme = data.group_labels || {};
          renderGroupLabelsEditor();
          loadCourse(); // refresh roster with new labels
        } else {
          groupLabelsStatus.textContent = data.error || "Save failed.";
        }
      })
      .catch(function (e) { groupLabelsStatus.textContent = "Error: " + e.message; });
  });

  // ── Protected names ─────────────────────────────────────────────────

  function loadProtected() {
    fetch("/api/names/protected")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        protectedData = data;
        renderProtectedPacks(data);
        customProtectedInput.value = (data.custom || []).join(", ");
      })
      .catch(function () {});
  }

  function renderProtectedPacks(data) {
    protectedPacksEl.innerHTML = "";
    var packs = data.packs || [];
    for (var i = 0; i < packs.length; i++) {
      var label = document.createElement("label");
      label.className = "roster-protected-pack";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = packs[i].enabled;
      cb.dataset.packId = packs[i].id;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + packs[i].title));
      protectedPacksEl.appendChild(label);
    }
  }

  saveProtectedBtn.addEventListener("click", function () {
    var packStates = {};
    var cbs = protectedPacksEl.querySelectorAll("input[type=checkbox]");
    for (var i = 0; i < cbs.length; i++) {
      packStates[cbs[i].dataset.packId] = cbs[i].checked;
    }
    var custom = customProtectedInput.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);

    var body = new URLSearchParams();
    body.append("data", JSON.stringify({ packs: packStates, custom: custom }));

    fetch("/api/names/protected", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Protected names saved.", false);
          loadProtected();
        } else {
          toast(data.error || "Save failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Scrub test ──────────────────────────────────────────────────────

  scrubRun.addEventListener("click", function () {
    var txt = scrubText.value;
    if (!txt) { scrubResult.hidden = true; return; }
    var body = new URLSearchParams();
    body.append("text", txt);
    body.append("course_id", currentCourseId);

    fetch("/api/names/scrub-test", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          scrubResult.textContent = data.scrubbed;
          scrubResult.hidden = false;
        } else {
          scrubResult.textContent = data.error || "Scrub test failed.";
          scrubResult.hidden = false;
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Export / backup ─────────────────────────────────────────────────

  exportWhoBtn.addEventListener("click", function () {
    if (!currentCourseId) return;
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);

    fetch("/api/names/who-is-who", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Exported to " + data.path, false);
        } else {
          toast(data.error || "Export failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  backupVaultBtn.addEventListener("click", function () {
    fetch("/api/names/backup-vault", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Backed up (" + data.entries + " entries).", false);
        } else {
          toast(data.error || "Backup failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Init ────────────────────────────────────────────────────────────

  window.CANVAS_BASE = document.querySelector('meta[name="canvas-base"]')
    ? document.querySelector('meta[name="canvas-base"]').content
    : "";

  var params = new URLSearchParams(window.location.search);
  var focus = params.get("focus");
  if (focus === "extra-time") {
    var etBtn = document.querySelector('.roster-filter-btn[data-filter="extra_time"]');
    if (etBtn) etBtn.click();
  }

  courseSelect.addEventListener("change", loadCourse);
  refreshBtn.addEventListener("click", loadCourse);

  loadProtected();

  if (courseSelect.value) {
    loadCourse();
  }
})();
