(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "getStudents",
    "getGroupState",
    "getFilteredStudents",
    "getSelectedNameMap",
    "setSelectedNameMap",
    "onTableRendered"
  ].every(function (name) { return typeof roster[name] === "function"; });

  if (!ready) {
    window.alert("Roster table tools need a page refresh.");
    return;
  }

  var tableBody = document.getElementById("roster-table-body");
  if (!tableBody) {
    return;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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

  function groupId(group) {
    return String((group && (group.id || group.group_id)) || "");
  }

  function groupLabel(group) {
    var state = roster.getGroupState() || {};
    var gid = groupId(group);
    return (state.groupLabelScheme && state.groupLabelScheme[gid]) || {};
  }

  function groupDisplay(group) {
    var label = groupLabel(group).teacher_label || group.teacher_label || "";
    return label && label !== group.name ? label + " / " + group.name : group.name;
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

  function updateSelectedNameMap() {
    var names = {};
    var checks = tableBody.querySelectorAll(".roster-row-check:checked");
    var students = roster.getStudents() || [];
    for (var i = 0; i < checks.length; i++) {
      var id = checks[i].dataset.id;
      var found = null;
      for (var j = 0; j < students.length; j++) {
        if (students[j].id === id) {
          found = students[j];
          break;
        }
      }
      names[id] = found ? (found.display_name || found.name) : id;
    }
    roster.setSelectedNameMap(names);
    return names;
  }

  function canvasGroupOptions(categoryGroups, selected) {
    var h = '<option value="">- no group -</option>';
    for (var i = 0; i < categoryGroups.length; i++) {
      var g = categoryGroups[i];
      var gid = groupId(g);
      var label = groupDisplay(g);
      var sel = gid === String(selected || "") ? " selected" : "";
      h += '<option value="' + esc(gid) + '"' + sel + '>' + esc(label) + "</option>";
    }
    return h;
  }

  function seatingSupportOptions(selected) {
    var options = [
      ["none", "None"],
      ["preferred", "Preferred"],
      ["required", "Required"]
    ];
    var html = "";
    for (var i = 0; i < options.length; i++) {
      var value = options[i][0];
      html += '<option value="' + value + '"' + (value === selected ? " selected" : "") + ">" + options[i][1] + "</option>";
    }
    return html;
  }

  function renderTable() {
    var filteredStudents = roster.getFilteredStudents() || [];
    var state = roster.getGroupState() || {};
    var categoryGroups = state.currentCategoryGroups || [];

    if (filteredStudents.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="13" class="roster-empty">No students.</td></tr>';
      updateSelectedNameMap();
      if (typeof roster.notifyTableRendered === "function") {
        roster.notifyTableRendered();
      }
      return;
    }

    var html = "";
    for (var i = 0; i < filteredStudents.length; i++) {
      var s = filteredStudents[i];
      var canvasGroup = s.canvas_group || {};
      var nnVal = esc((s.nicknames || []).join(", "));
      var pseudoVal = esc(s.pseudonym || "");
      var noteVal = esc((s.monitored && s.monitored.note) || "");
      var seatingContext = s.seating_context || {};
      var frontRow = seatingContext.front_row || "none";
      var nearTeacher = seatingContext.near_teacher || "none";
      var privateNote = esc(seatingContext.private_note || "");
      var aiContextNote = esc(seatingContext.ai_context_note || "");
      var status = rowStatus(s.warnings, canvasGroup);

      html += "<tr data-id=\"" + esc(s.id) + "\">" +
        '<td class="roster-col-check"><input type="checkbox" class="roster-row-check" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-name"><span class="roster-v2-name">' + esc(s.display_name || s.name) + "</span></td>" +
        '<td class="roster-col-nicknames"><input type="text" class="roster-v2-input roster-v2-nicknames" value="' + nnVal + '" placeholder="nicknames" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-pseudo"><span class="roster-v2-pseudo-row"><input type="text" class="roster-v2-input roster-v2-pseudo" value="' + pseudoVal + '" placeholder="pseudonym" data-id="' + esc(s.id) + '" data-field="pseudo"><button type="button" class="roster-v2-regen" data-id="' + esc(s.id) + '" title="Regenerate">&#x21bb;</button></span></td>' +
        '<td class="roster-col-extratime"><label class="roster-v2-et"><input type="checkbox" class="roster-v2-et-cb" data-id="' + esc(s.id) + '"' + (s.extra_time.enabled ? " checked" : "") + ">" +
        (s.extra_time.enabled ? ('<input type="number" class="roster-v2-et-days" value="' + (s.extra_time.days || 0) + '" min="0" max="30" data-id="' + esc(s.id) + '">') : '<input type="number" class="roster-v2-et-days" value="0" min="0" max="30" data-id="' + esc(s.id) + '" hidden>') +
        "</label></td>" +
        '<td class="roster-col-group"><select class="roster-v2-canvas-group" data-id="' + esc(s.id) + '" data-category="' + esc(state.selectedGroupCategoryId || "") + '">' + canvasGroupOptions(categoryGroups, canvasGroup.group_id) + "</select></td>" +
        '<td class="roster-col-monitor"><input type="checkbox" class="roster-v2-monitor" data-id="' + esc(s.id) + '"' + (s.monitored.enabled ? " checked" : "") + "></td>" +
        '<td class="roster-col-note"><input type="text" class="roster-v2-input roster-v2-note" value="' + noteVal + '" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-front-row"><select class="roster-v2-seating-front-row" data-id="' + esc(s.id) + '" aria-label="Front row">' + seatingSupportOptions(frontRow) + "</select></td>" +
        '<td class="roster-col-near-teacher"><select class="roster-v2-seating-near-teacher" data-id="' + esc(s.id) + '" aria-label="Near teacher">' + seatingSupportOptions(nearTeacher) + "</select></td>" +
        '<td class="roster-col-private-note"><input type="text" class="roster-v2-input roster-v2-seating-private-note" value="' + privateNote + '" data-id="' + esc(s.id) + '" aria-label="Private teacher note" placeholder="Private note"></td>' +
        '<td class="roster-col-ai-context-note"><input type="text" class="roster-v2-input roster-v2-seating-ai-context-note" value="' + aiContextNote + '" data-id="' + esc(s.id) + '" aria-label="AI-context note" placeholder="AI-context note"></td>' +
        '<td class="roster-col-status"><span class="roster-v2-status ' + status.cls + '" title="' + esc(status.title) + '">' + esc(status.text) + "</span></td>" +
        "</tr>";
    }

    tableBody.innerHTML = html;
    updateSelectedNameMap();
    if (typeof roster.notifyTableRendered === "function") {
      roster.notifyTableRendered();
    }
  }

  function bindSelectionSync() {
    tableBody.addEventListener("change", function (e) {
      if (e.target && e.target.classList && e.target.classList.contains("roster-row-check")) {
        updateSelectedNameMap();
      }
    });
  }

  roster.renderTable = renderTable;
  roster.setRowStatus = setRowStatus;
  roster.getSelectedNameMap = function () {
    return updateSelectedNameMap();
  };

  bindSelectionSync();
  updateSelectedNameMap();
})();
