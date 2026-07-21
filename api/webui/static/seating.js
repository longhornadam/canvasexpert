/* Local-only Seating layouts and manual placement. */
(function () {
  "use strict";

  var courseSelect = document.getElementById("seating-course");
  var refreshButton = document.getElementById("seating-refresh");
  var status = document.getElementById("seating-status");
  var workspace = document.getElementById("seating-workspace");
  var layoutSelect = document.getElementById("seating-layout-select");
  var layoutEditor = document.getElementById("seating-layout-editor");
  var modeSelect = document.getElementById("seating-mode-select");
  var modeEditor = document.getElementById("seating-mode-editor");
  var chartCard = document.getElementById("seating-chart-card");
  var printChart = document.getElementById("seating-print-chart");
  var proposalCard = document.getElementById("seating-proposal-card");
  var proposalStatus = document.getElementById("seating-proposal-status");

  var state = emptyState();
  var students = [];
  var rosterRelationships = { by_section: {} };
  var currentCourseId = "";
  var selectedLayoutId = "";
  var selectedModeId = "";
  var proposal = null;
  var proposalLocks = {};
  var rerollSeatIds = {};
  var proposalResults = null;
  var undoAssignment = null;

  function emptyState() { return { layouts: [], modes: [] }; }
  function seatId(row, column) { return "seat-" + row + "-" + column; }
  function seatLabel(row, column) { return row + "-" + column; }

  function setStatus(message, isError) {
    status.textContent = message || "";
    status.className = "hint" + (isError ? " error" : "");
  }

  function setProposalStatus(message, isError) {
    proposalStatus.textContent = message || "";
    proposalStatus.className = "hint" + (isError ? " error" : "");
  }

  function clearTransient() {
    proposal = null;
    proposalLocks = {};
    rerollSeatIds = {};
    proposalResults = null;
    undoAssignment = null;
    proposalCard.hidden = true;
    document.getElementById("seating-proposal-chart").replaceChildren();
    document.getElementById("seating-proposal-results").replaceChildren();
    document.getElementById("seating-undo-apply").hidden = true;
    setProposalStatus("", false);
  }

  function newId(prefix) {
    var token = window.crypto && window.crypto.randomUUID
      ? window.crypto.randomUUID().replace(/-/g, "")
      : String(Date.now()) + String(Math.floor(Math.random() * 1000000));
    return prefix + "-" + token;
  }

  function postState(next, successMessage, onSaved) {
    if (!currentCourseId) return;
    var initiatingCourseId = currentCourseId;
    setStatus("Saving…", false);
    fetch("/api/seating/state", {
      method: "POST",
      body: new URLSearchParams({ course_id: initiatingCourseId, state: JSON.stringify(next) })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (initiatingCourseId !== currentCourseId) return;
      if (!data.ok) {
        setStatus(data.error || "Could not save Seating state.", true);
        return;
      }
      state = data.state || emptyState();
      if (typeof onSaved === "function") onSaved();
      setStatus(successMessage || "Saved.", false);
      renderAll();
    }).catch(function (error) {
      if (initiatingCourseId !== currentCourseId) return;
      setStatus("Network error: " + error.message, true);
    });
  }

  function option(select, value, label) {
    var item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    select.appendChild(item);
  }

  function selectedLayout() {
    return state.layouts.find(function (layout) { return layout.id === selectedLayoutId; }) || null;
  }

  function selectedMode() {
    return state.modes.find(function (mode) { return mode.id === selectedModeId; }) || null;
  }

  function allSections() {
    var result = [];
    var seen = {};
    students.forEach(function (student) {
      (student.sections || []).forEach(function (section) {
        var id = String(section.id || "");
        if (id && !seen[id]) {
          seen[id] = true;
          result.push({ id: id, name: section.name || "Section" });
        }
      });
    });
    return result.sort(function (left, right) { return left.name.localeCompare(right.name); });
  }

  function studentsInSection(sectionId) {
    return students.filter(function (student) {
      return (student.sections || []).some(function (section) {
        return String(section.id) === String(sectionId);
      });
    }).sort(function (left, right) {
      return String(left.display_name || left.name || "").localeCompare(
        String(right.display_name || right.name || ""));
    });
  }

  function displayName(student) {
    return student.display_name || student.name || "Student";
  }

  function renderLayoutSelect() {
    if (!state.layouts.some(function (layout) { return layout.id === selectedLayoutId; })) {
      selectedLayoutId = state.layouts.length ? state.layouts[0].id : "";
    }
    layoutSelect.replaceChildren();
    option(layoutSelect, "", "— select a layout —");
    state.layouts.forEach(function (layout) { option(layoutSelect, layout.id, layout.name); });
    layoutSelect.value = selectedLayoutId;
  }

  function renderLayoutEditor() {
    var layout = selectedLayout();
    layoutEditor.hidden = !layout;
    if (!layout) return;
    document.getElementById("seating-layout-name").value = layout.name;
    document.getElementById("seating-layout-rows").value = layout.rows;
    document.getElementById("seating-layout-columns").value = layout.columns;
    var grid = document.getElementById("seating-layout-grid");
    grid.replaceChildren();
    grid.style.gridTemplateColumns = "repeat(" + layout.columns + ", minmax(38px, 1fr))";
    var seats = {};
    layout.seats.forEach(function (seat) { seats[seat.id] = true; });
    for (var row = 1; row <= layout.rows; row++) {
      for (var column = 1; column <= layout.columns; column++) {
        var button = document.createElement("button");
        var id = seatId(row, column);
        button.type = "button";
        button.className = "seating-layout-seat" + (seats[id] ? " is-seat" : "");
        button.textContent = seatLabel(row, column);
        button.setAttribute("aria-pressed", seats[id] ? "true" : "false");
        button.addEventListener("click", (function (selectedRow, selectedColumn) {
          return function () { toggleSeat(selectedRow, selectedColumn); };
        })(row, column));
        grid.appendChild(button);
      }
    }
    var nearTeacherSeats = document.getElementById("seating-near-teacher-seats");
    nearTeacherSeats.replaceChildren();
    var marks = {};
    (layout.near_teacher_seat_ids || []).forEach(function (seatIdValue) { marks[seatIdValue] = true; });
    layout.seats.forEach(function (seat) {
      var label = document.createElement("label");
      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(marks[seat.id]);
      checkbox.setAttribute("aria-label", "Mark " + seat.label + " as near the teacher");
      checkbox.addEventListener("change", (function (seatIdValue) {
        return function () { toggleNearTeacherSeat(seatIdValue); };
      })(seat.id));
      label.append(checkbox, document.createTextNode(seat.label));
      nearTeacherSeats.appendChild(label);
    });
  }

  function fillSections(select, selectedId) {
    select.replaceChildren();
    option(select, "", "— select a section —");
    allSections().forEach(function (section) { option(select, section.id, section.name); });
    if (selectedId) select.value = selectedId;
  }

  function fillLayouts(select, selectedId) {
    select.replaceChildren();
    option(select, "", "— select a layout —");
    state.layouts.forEach(function (layout) { option(select, layout.id, layout.name); });
    if (selectedId) select.value = selectedId;
  }

  function renderModeSelect() {
    if (!state.modes.some(function (mode) { return mode.id === selectedModeId; })) {
      selectedModeId = state.modes.length ? state.modes[0].id : "";
    }
    modeSelect.replaceChildren();
    option(modeSelect, "", "— select a mode —");
    state.modes.forEach(function (mode) { option(modeSelect, mode.id, mode.name); });
    modeSelect.value = selectedModeId;
    fillSections(document.getElementById("seating-new-mode-section"), "");
    fillLayouts(document.getElementById("seating-new-mode-layout"), selectedLayoutId);
  }

  function renderModeEditor() {
    var mode = selectedMode();
    modeEditor.hidden = !mode;
    if (!mode) return;
    document.getElementById("seating-mode-name").value = mode.name;
    fillSections(document.getElementById("seating-mode-section"), mode.section_id);
    fillLayouts(document.getElementById("seating-mode-layout"), mode.layout_id);
  }

  function chartLayout(mode) {
    return state.layouts.find(function (layout) { return layout.id === mode.layout_id; }) || null;
  }

  function renderAssignmentControls(mode, layout) {
    var seatSelect = document.getElementById("seating-assignment-seat");
    var studentSelect = document.getElementById("seating-assignment-student");
    var previousSeat = seatSelect.value;
    seatSelect.replaceChildren();
    option(seatSelect, "", "— select a seat —");
    layout.seats.forEach(function (seat) { option(seatSelect, seat.id, seat.label); });
    if (previousSeat) seatSelect.value = previousSeat;

    var seatStudent = mode.assignment[seatSelect.value] || "";
    var assignedElsewhere = {};
    Object.keys(mode.assignment).forEach(function (seatIdValue) {
      if (seatIdValue !== seatSelect.value) assignedElsewhere[mode.assignment[seatIdValue]] = true;
    });
    studentSelect.replaceChildren();
    option(studentSelect, "", "— select a student —");
    studentsInSection(mode.section_id).forEach(function (student) {
      if (!assignedElsewhere[String(student.id)] || String(student.id) === seatStudent) {
        option(studentSelect, String(student.id), displayName(student));
      }
    });
    if (seatStudent) studentSelect.value = seatStudent;
  }

  function renderChart() {
    var mode = selectedMode();
    var layout = mode && chartLayout(mode);
    chartCard.hidden = !layout;
    if (!layout) {
      printChart.replaceChildren();
      return;
    }
    document.getElementById("seating-chart-subtitle").textContent = mode.name;
    var namesById = {};
    studentsInSection(mode.section_id).forEach(function (student) {
      namesById[String(student.id)] = displayName(student);
    });
    var chart = document.getElementById("seating-chart");
    chart.replaceChildren();
    chart.style.gridTemplateColumns = "repeat(" + layout.columns + ", minmax(92px, 1fr))";
    var seats = {};
    layout.seats.forEach(function (seat) { seats[seat.id] = seat; });
    for (var row = 1; row <= layout.rows; row++) {
      for (var column = 1; column <= layout.columns; column++) {
        var seat = seats[seatId(row, column)];
        if (!seat) {
          var spacer = document.createElement("div");
          spacer.setAttribute("aria-hidden", "true");
          chart.appendChild(spacer);
          continue;
        }
        var cell = document.createElement("div");
        cell.className = "seating-chart-seat";
        var label = document.createElement("strong");
        label.textContent = seat.label;
        cell.appendChild(label);
        var assigned = document.createElement("span");
        assigned.textContent = namesById[mode.assignment[seat.id]] || "";
        cell.appendChild(assigned);
        chart.appendChild(cell);
      }
    }
    renderAssignmentControls(mode, layout);
    renderPrintChart(mode, layout, namesById);
  }

  function renderPrintChart(mode, layout, namesById) {
    printChart.replaceChildren();
    var title = document.createElement("h1");
    title.className = "seating-print-title";
    title.textContent = mode.name;
    printChart.appendChild(title);
    var grid = document.createElement("div");
    grid.className = "seating-print-grid";
    grid.style.gridTemplateColumns = "repeat(" + layout.columns + ", minmax(0, 1fr))";
    layout.seats.forEach(function (seat) {
      var cell = document.createElement("div");
      cell.className = "seating-print-seat";
      var label = document.createElement("span");
      label.className = "seating-print-label";
      label.textContent = seat.label;
      cell.appendChild(label);
      var name = document.createElement("span");
      name.className = "seating-print-name";
      name.textContent = namesById[mode.assignment[seat.id]] || "";
      cell.appendChild(name);
      grid.appendChild(cell);
    });
    printChart.appendChild(grid);
  }

  function seatingContext(mode) {
    var selectedStudents = studentsInSection(mode.section_id);
    var allowed = { none: true, preferred: true, required: true };
    var studentIds = {};
    var projectedStudents = selectedStudents.map(function (student) {
      var seating = student.seating_context || {};
      var id = String(student.id);
      studentIds[id] = true;
      return {
        id: id,
        front_row: allowed[seating.front_row] ? seating.front_row : "none",
        near_teacher: allowed[seating.near_teacher] ? seating.near_teacher : "none"
      };
    });
    var relationships = ((rosterRelationships.by_section || {})[mode.section_id] || [])
      .filter(function (relationship) {
        return studentIds[relationship.student_a] && studentIds[relationship.student_b];
      }).map(function (relationship) {
        return {
          type: relationship.type,
          students: [relationship.student_a, relationship.student_b]
        };
      });
    return { section_id: mode.section_id, students: projectedStudents, relationships: relationships };
  }

  function proposalNames(mode) {
    var names = {};
    studentsInSection(mode.section_id).forEach(function (student) {
      names[String(student.id)] = displayName(student);
    });
    return names;
  }

  function requestProposal(operation, nextProposal) {
    var mode = selectedMode();
    var layout = mode && chartLayout(mode);
    if (!mode || !layout) return;
    var initiatingCourseId = currentCourseId;
    var initiatingModeId = mode.id;
    setProposalStatus("Working…", false);
    fetch("/api/seating/proposal", {
      method: "POST",
      body: new URLSearchParams({
        course_id: initiatingCourseId,
        mode_id: initiatingModeId,
        operation: operation,
        context: JSON.stringify(seatingContext(mode)),
        locks: JSON.stringify(proposalLocks),
        proposal: JSON.stringify(nextProposal || proposal || {}),
        reroll_seat_ids: JSON.stringify(Object.keys(rerollSeatIds))
      })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (initiatingCourseId !== currentCourseId || initiatingModeId !== selectedModeId) return;
      if (!data.ok) {
        setProposalStatus(data.error || "Could not build a proposal.", true);
        return;
      }
      proposal = data.proposal || {};
      proposalResults = data.results || null;
      rerollSeatIds = {};
      setProposalStatus("Proposal updated.", false);
      renderProposal();
    }).catch(function (error) {
      if (initiatingCourseId !== currentCourseId || initiatingModeId !== selectedModeId) return;
      setProposalStatus("Network error: " + error.message, true);
    });
  }

  function renderProposalResults() {
    var results = document.getElementById("seating-proposal-results");
    results.replaceChildren();
    if (!proposal) {
      results.textContent = "Generate a temporary proposal to review required conditions and preferences.";
      return;
    }
    if (!proposalResults) {
      results.textContent = "Proposal needs local evaluation.";
      return;
    }
    var summary = document.createElement("p");
    if (proposalResults.required_ok) {
      summary.textContent = "All required conditions pass.";
    } else {
      summary.textContent = proposalResults.required_violations.length + " required condition(s) need attention before apply.";
    }
    results.appendChild(summary);
    var preference = document.createElement("p");
    preference.textContent = proposalResults.unmet_preferences.length
      ? proposalResults.unmet_preferences.length + " preference(s) are unmet."
      : "All configured preferences are met.";
    results.appendChild(preference);
  }

  function renderSwapOptions() {
    var first = document.getElementById("seating-swap-a");
    var second = document.getElementById("seating-swap-b");
    var firstValue = first.value;
    var secondValue = second.value;
    first.replaceChildren();
    second.replaceChildren();
    option(first, "", "— choose seat —");
    option(second, "", "— choose seat —");
    Object.keys(proposal || {}).sort().forEach(function (seat) {
      if (!proposalLocks[seat]) {
        option(first, seat, seat);
        option(second, seat, seat);
      }
    });
    if (firstValue) first.value = firstValue;
    if (secondValue) second.value = secondValue;
  }

  function renderProposal() {
    var mode = selectedMode();
    var layout = mode && chartLayout(mode);
    proposalCard.hidden = !layout;
    if (!layout) return;
    renderProposalResults();
    renderSwapOptions();
    document.getElementById("seating-apply-proposal").disabled = !(
      proposal && proposalResults && proposalResults.required_ok
    );
    document.getElementById("seating-undo-apply").hidden = !undoAssignment;
    var chart = document.getElementById("seating-proposal-chart");
    chart.replaceChildren();
    if (!proposal) return;
    chart.style.gridTemplateColumns = "repeat(" + layout.columns + ", minmax(92px, 1fr))";
    var seats = {};
    layout.seats.forEach(function (seat) { seats[seat.id] = seat; });
    var names = proposalNames(mode);
    for (var row = 1; row <= layout.rows; row++) {
      for (var column = 1; column <= layout.columns; column++) {
        var seat = seats[seatId(row, column)];
        if (!seat) {
          var spacer = document.createElement("div");
          spacer.setAttribute("aria-hidden", "true");
          chart.appendChild(spacer);
          continue;
        }
        var cell = document.createElement("div");
        cell.className = "seating-chart-seat";
        var label = document.createElement("strong");
        label.textContent = seat.label;
        cell.appendChild(label);
        var assigned = document.createElement("span");
        assigned.textContent = names[proposal[seat.id]] || "";
        cell.appendChild(assigned);
        if (proposal[seat.id]) {
          var flags = document.createElement("div");
          flags.className = "seating-proposal-flags";
          var lockLabel = document.createElement("label");
          var lock = document.createElement("input");
          lock.type = "checkbox";
          lock.checked = proposalLocks[seat.id] === proposal[seat.id];
          lock.addEventListener("change", (function (seatIdValue, checkbox) {
            return function () {
              if (checkbox.checked) proposalLocks[seatIdValue] = proposal[seatIdValue];
              else delete proposalLocks[seatIdValue];
              delete rerollSeatIds[seatIdValue];
              renderProposal();
            };
          })(seat.id, lock));
          lockLabel.appendChild(lock);
          lockLabel.appendChild(document.createTextNode("Lock"));
          flags.appendChild(lockLabel);
          var rerollLabel = document.createElement("label");
          var reroll = document.createElement("input");
          reroll.type = "checkbox";
          reroll.disabled = !!proposalLocks[seat.id];
          reroll.checked = !!rerollSeatIds[seat.id];
          reroll.addEventListener("change", (function (seatIdValue, checkbox) {
            return function () {
              if (checkbox.checked) rerollSeatIds[seatIdValue] = true;
              else delete rerollSeatIds[seatIdValue];
            };
          })(seat.id, reroll));
          rerollLabel.appendChild(reroll);
          rerollLabel.appendChild(document.createTextNode("Reroll"));
          flags.appendChild(rerollLabel);
          cell.appendChild(flags);
        }
        chart.appendChild(cell);
      }
    }
  }

  function applyProposal() {
    var mode = selectedMode();
    if (!mode || !proposal || !proposalResults || !proposalResults.required_ok) return;
    var initiatingCourseId = currentCourseId;
    var initiatingModeId = mode.id;
    var previousAssignment = Object.assign({}, mode.assignment);
    setProposalStatus("Applying…", false);
    fetch("/api/seating/apply", {
      method: "POST",
      body: new URLSearchParams({
        course_id: initiatingCourseId,
        mode_id: initiatingModeId,
        context: JSON.stringify(seatingContext(mode)),
        proposal: JSON.stringify(proposal)
      })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (initiatingCourseId !== currentCourseId || initiatingModeId !== selectedModeId) return;
      if (!data.ok) {
        proposalResults = data.results || proposalResults;
        setProposalStatus(data.error || "Could not apply proposal.", true);
        renderProposal();
        return;
      }
      state = data.state || state;
      proposal = null;
      proposalLocks = {};
      rerollSeatIds = {};
      proposalResults = null;
      undoAssignment = previousAssignment;
      setProposalStatus("Proposal applied to the current chart.", false);
      renderAll();
    }).catch(function (error) {
      if (initiatingCourseId !== currentCourseId || initiatingModeId !== selectedModeId) return;
      setProposalStatus("Network error: " + error.message, true);
    });
  }

  function undoLastApply() {
    var mode = selectedMode();
    if (!mode || !undoAssignment) return;
    var restored = Object.assign({}, undoAssignment);
    var next = {
      layouts: state.layouts,
      modes: state.modes.map(function (item) {
        return item.id === mode.id ? Object.assign({}, item, { assignment: restored }) : item;
      })
    };
    postState(next, "Previous chart restored.", function () {
      undoAssignment = null;
      setProposalStatus("Undo applied.", false);
    });
  }

  function renderAll() {
    renderLayoutSelect();
    renderLayoutEditor();
    renderModeSelect();
    renderModeEditor();
    renderChart();
    renderProposal();
  }

  function updateLayout(nextLayout, message) {
    if (selectedMode() && selectedMode().layout_id === nextLayout.id) clearTransient();
    var layouts = state.layouts.map(function (layout) {
      return layout.id === nextLayout.id ? nextLayout : layout;
    });
    var validSeats = {};
    nextLayout.seats.forEach(function (seat) { validSeats[seat.id] = true; });
    var modes = state.modes.map(function (mode) {
      if (mode.layout_id !== nextLayout.id) return mode;
      var assignment = {};
      Object.keys(mode.assignment).forEach(function (seat) {
        if (validSeats[seat]) assignment[seat] = mode.assignment[seat];
      });
      return Object.assign({}, mode, { assignment: assignment });
    });
    postState({ layouts: layouts, modes: modes }, message);
  }

  function toggleSeat(row, column) {
    var layout = selectedLayout();
    if (!layout) return;
    var target = seatId(row, column);
    var seats = layout.seats.filter(function (seat) { return seat.id !== target; });
    if (seats.length === layout.seats.length) {
      seats.push({ id: target, row: row, column: column, label: seatLabel(row, column) });
    }
    seats.sort(function (left, right) { return left.row - right.row || left.column - right.column; });
    updateLayout(Object.assign({}, layout, { seats: seats }), "Seat positions saved.");
  }

  function toggleNearTeacherSeat(targetSeatId) {
    var layout = selectedLayout();
    if (!layout || !layout.seats.some(function (seat) { return seat.id === targetSeatId; })) return;
    var marks = {};
    (layout.near_teacher_seat_ids || []).forEach(function (seatIdValue) { marks[seatIdValue] = true; });
    if (marks[targetSeatId]) {
      delete marks[targetSeatId];
    } else {
      marks[targetSeatId] = true;
    }
    updateLayout(Object.assign({}, layout, {
      near_teacher_seat_ids: layout.seats.filter(function (seat) { return marks[seat.id]; })
        .map(function (seat) { return seat.id; })
    }), "Near-teacher seats saved.");
  }

  function loadCourse() {
    var courseId = courseSelect.value;
    currentCourseId = courseId;
    students = [];
    rosterRelationships = { by_section: {} };
    state = emptyState();
    selectedLayoutId = "";
    selectedModeId = "";
    workspace.hidden = true;
    chartCard.hidden = true;
    printChart.replaceChildren();
    clearTransient();
    if (!courseId) {
      setStatus("", false);
      return;
    }
    setStatus("Loading Roster…", false);
    fetch("/api/roster?course_id=" + encodeURIComponent(courseId))
      .then(function (response) { return response.json(); })
      .then(function (roster) {
        if (currentCourseId !== courseId) return null;
        if (!roster.ok) throw new Error(roster.error || "Could not load Roster.");
        students = roster.students || [];
        rosterRelationships = roster.relationships || { by_section: {} };
        return fetch("/api/seating?course_id=" + encodeURIComponent(courseId));
      })
      .then(function (response) { return response ? response.json() : null; })
      .then(function (data) {
        if (!data || currentCourseId !== courseId) return;
        if (!data.ok) throw new Error(data.error || "Could not load Seating state.");
        state = data.state || emptyState();
        workspace.hidden = false;
        renderAll();
        setStatus("Loaded local Seating for " + students.length + " students.", false);
      })
      .catch(function (error) {
        if (currentCourseId === courseId) setStatus(error.message, true);
      });
  }

  document.getElementById("seating-create-layout").addEventListener("click", function () {
    var name = document.getElementById("seating-new-layout-name").value.trim();
    var rows = Number(document.getElementById("seating-new-layout-rows").value);
    var columns = Number(document.getElementById("seating-new-layout-columns").value);
    if (!name || rows < 1 || rows > 12 || columns < 1 || columns > 12) {
      setStatus("Use a layout name and a grid from 1 to 12 rows and columns.", true);
      return;
    }
    var seats = [];
    for (var row = 1; row <= rows; row++) {
      for (var column = 1; column <= columns; column++) {
        seats.push({ id: seatId(row, column), row: row, column: column, label: seatLabel(row, column) });
      }
    }
    var layout = { id: newId("layout"), name: name, rows: rows, columns: columns,
                   seats: seats, near_teacher_seat_ids: [] };
    selectedLayoutId = layout.id;
    postState({ layouts: state.layouts.concat([layout]), modes: state.modes }, "Layout created.");
  });

  document.getElementById("seating-save-layout").addEventListener("click", function () {
    var layout = selectedLayout();
    if (!layout) return;
    var name = document.getElementById("seating-layout-name").value.trim();
    var rows = Number(document.getElementById("seating-layout-rows").value);
    var columns = Number(document.getElementById("seating-layout-columns").value);
    if (!name || rows < 1 || rows > 12 || columns < 1 || columns > 12) {
      setStatus("Use a layout name and a grid from 1 to 12 rows and columns.", true);
      return;
    }
    var seats = layout.seats.filter(function (seat) { return seat.row <= rows && seat.column <= columns; });
    var validSeats = {};
    seats.forEach(function (seat) { validSeats[seat.id] = true; });
    updateLayout(Object.assign({}, layout, {
      name: name, rows: rows, columns: columns, seats: seats,
      near_teacher_seat_ids: (layout.near_teacher_seat_ids || []).filter(function (seat) { return validSeats[seat]; })
    }), "Layout saved.");
  });

  document.getElementById("seating-delete-layout").addEventListener("click", function () {
    var layout = selectedLayout();
    if (!layout) return;
    selectedLayoutId = "";
    if (selectedMode() && selectedMode().layout_id === layout.id) selectedModeId = "";
    postState({
      layouts: state.layouts.filter(function (item) { return item.id !== layout.id; }),
      modes: state.modes.filter(function (mode) { return mode.layout_id !== layout.id; })
    }, "Layout and dependent modes removed.");
  });

  layoutSelect.addEventListener("change", function () {
    selectedLayoutId = layoutSelect.value;
    renderAll();
  });

  document.getElementById("seating-create-mode").addEventListener("click", function () {
    var name = document.getElementById("seating-new-mode-name").value.trim();
    var sectionId = document.getElementById("seating-new-mode-section").value;
    var layoutId = document.getElementById("seating-new-mode-layout").value;
    if (!name || !sectionId || !layoutId) {
      setStatus("Choose a name, loaded Roster section, and layout.", true);
      return;
    }
    var mode = { id: newId("mode"), name: name, section_id: sectionId,
                 layout_id: layoutId, strategy: "manual", assignment: {} };
    selectedModeId = mode.id;
    postState({ layouts: state.layouts, modes: state.modes.concat([mode]) }, "Mode created.");
  });

  document.getElementById("seating-save-mode").addEventListener("click", function () {
    var mode = selectedMode();
    if (!mode) return;
    var name = document.getElementById("seating-mode-name").value.trim();
    var sectionId = document.getElementById("seating-mode-section").value;
    var layoutId = document.getElementById("seating-mode-layout").value;
    if (!name || !sectionId || !layoutId) {
      setStatus("Choose a name, loaded Roster section, and layout.", true);
      return;
    }
    var nextAssignment = mode.assignment;
    if (sectionId !== mode.section_id) nextAssignment = {};
    var layout = state.layouts.find(function (item) { return item.id === layoutId; });
    var validSeats = {};
    (layout ? layout.seats : []).forEach(function (seat) { validSeats[seat.id] = true; });
    nextAssignment = Object.keys(nextAssignment).reduce(function (assignment, seat) {
      if (validSeats[seat]) assignment[seat] = nextAssignment[seat];
      return assignment;
    }, {});
    var replacement = Object.assign({}, mode, { name: name, section_id: sectionId,
                                                 layout_id: layoutId, assignment: nextAssignment });
    postState({
      layouts: state.layouts,
      modes: state.modes.map(function (item) { return item.id === mode.id ? replacement : item; })
    }, "Mode saved.");
  });

  document.getElementById("seating-delete-mode").addEventListener("click", function () {
    var mode = selectedMode();
    if (!mode) return;
    selectedModeId = "";
    postState({ layouts: state.layouts,
                modes: state.modes.filter(function (item) { return item.id !== mode.id; }) }, "Mode removed.");
  });

  modeSelect.addEventListener("change", function () {
    selectedModeId = modeSelect.value;
    clearTransient();
    renderAll();
  });

  document.getElementById("seating-assignment-seat").addEventListener("change", function () {
    renderChart();
  });

  document.getElementById("seating-assign").addEventListener("click", function () {
    var mode = selectedMode();
    var seat = document.getElementById("seating-assignment-seat").value;
    var student = document.getElementById("seating-assignment-student").value;
    if (!mode || !seat || !student) {
      setStatus("Choose a seat and a student from this mode's loaded Roster section.", true);
      return;
    }
    var assignment = {};
    Object.keys(mode.assignment).forEach(function (assignedSeat) {
      if (mode.assignment[assignedSeat] !== student || assignedSeat === seat) {
        assignment[assignedSeat] = mode.assignment[assignedSeat];
      }
    });
    assignment[seat] = student;
    var replacement = Object.assign({}, mode, { assignment: assignment });
    postState({ layouts: state.layouts,
                modes: state.modes.map(function (item) { return item.id === mode.id ? replacement : item; }) },
              "Student assigned.");
  });

  document.getElementById("seating-clear-seat").addEventListener("click", function () {
    var mode = selectedMode();
    var seat = document.getElementById("seating-assignment-seat").value;
    if (!mode || !seat) {
      setStatus("Choose a seat to clear.", true);
      return;
    }
    var assignment = Object.assign({}, mode.assignment);
    delete assignment[seat];
    var replacement = Object.assign({}, mode, { assignment: assignment });
    postState({ layouts: state.layouts,
                modes: state.modes.map(function (item) { return item.id === mode.id ? replacement : item; }) },
              "Seat cleared.");
  });

  document.getElementById("seating-generate").addEventListener("click", function () {
    var mode = selectedMode();
    if (!mode) {
      setProposalStatus("Choose a loaded mode first.", true);
      return;
    }
    requestProposal("generate", proposal || {});
  });

  document.getElementById("seating-reroll").addEventListener("click", function () {
    if (!proposal) {
      setProposalStatus("Generate a proposal before rerolling seats.", true);
      return;
    }
    if (!Object.keys(rerollSeatIds).length) {
      setProposalStatus("Select one or more unlocked proposed seats to reroll.", true);
      return;
    }
    requestProposal("reroll", proposal);
  });

  document.getElementById("seating-swap").addEventListener("click", function () {
    if (!proposal) {
      setProposalStatus("Generate a proposal before swapping seats.", true);
      return;
    }
    var first = document.getElementById("seating-swap-a").value;
    var second = document.getElementById("seating-swap-b").value;
    if (!first || !second || first === second) {
      setProposalStatus("Choose two different unlocked proposed seats.", true);
      return;
    }
    if (proposalLocks[first] || proposalLocks[second]) {
      setProposalStatus("Unlock both seats before swapping them.", true);
      return;
    }
    var swapped = Object.assign({}, proposal);
    var firstStudent = swapped[first];
    swapped[first] = swapped[second];
    swapped[second] = firstStudent;
    requestProposal("evaluate", swapped);
  });

  document.getElementById("seating-apply-proposal").addEventListener("click", applyProposal);
  document.getElementById("seating-undo-apply").addEventListener("click", undoLastApply);

  document.getElementById("seating-print").addEventListener("click", function () {
    if (selectedMode()) window.print();
  });
  courseSelect.addEventListener("change", loadCourse);
  refreshButton.addEventListener("click", loadCourse);
})();
