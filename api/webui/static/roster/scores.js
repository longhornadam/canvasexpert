(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var ready = [
    "getCurrentCourseId",
    "getScoreMatrix",
    "getStudents",
    "hasLoadedCourse",
    "onCourseLoaded",
    "postForm",
    "setScoreMatrix",
    "toast"
  ].every(function (name) { return typeof roster[name] === "function"; });
  if (!ready) return;

  var workspace = document.getElementById("roster-score-matrix");
  var courseSelect = document.getElementById("roster-course");
  var sectionSelect = document.getElementById("roster-score-section");
  var newColumnInput = document.getElementById("roster-score-new-column");
  var addColumnButton = document.getElementById("roster-score-add-column");
  var columnsEl = document.getElementById("roster-score-columns");
  var gridHead = document.getElementById("roster-score-grid-head");
  var gridBody = document.getElementById("roster-score-grid-body");
  var saveButton = document.getElementById("roster-score-save");
  var statusEl = document.getElementById("roster-score-matrix-status");
  var selectedSectionId = "";

  if (!workspace || !sectionSelect || !newColumnInput || !addColumnButton || !columnsEl || !gridHead || !gridBody || !saveButton || !statusEl) return;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function matrix() {
    var value = roster.getScoreMatrix() || {};
    return {
      columns: value.columns || [],
      values_by_section: value.values_by_section || {}
    };
  }

  function setStatus(message, isError) {
    statusEl.textContent = message || "";
    statusEl.className = "hint" + (message && isError ? " error" : (message ? " ok" : ""));
  }

  function sections() {
    var found = {};
    (roster.getStudents() || []).forEach(function (student) {
      (student.sections || []).forEach(function (section) {
        if (section && section.id != null) {
          found[String(section.id)] = section.name || ("Section " + section.id);
        }
      });
    });
    return Object.keys(found).sort(function (a, b) {
      return found[a].localeCompare(found[b]);
    }).map(function (id) { return { id: id, name: found[id] }; });
  }

  function studentsInSection() {
    if (!selectedSectionId) return [];
    return (roster.getStudents() || []).filter(function (student) {
      return (student.sections || []).some(function (section) {
        return String(section.id) === selectedSectionId;
      });
    });
  }

  function renderSectionPicker() {
    var options = '<option value="">— select a section —</option>';
    sections().forEach(function (section) {
      options += '<option value="' + esc(section.id) + '"' +
        (section.id === selectedSectionId ? " selected" : "") + ">" +
        esc(section.name) + "</option>";
    });
    sectionSelect.innerHTML = options;
  }

  function renderColumns() {
    var columns = matrix().columns;
    if (!columns.length) {
      columnsEl.innerHTML = '<span class="hint">Add a labeled numeric column to begin.</span>';
      return;
    }
    columnsEl.innerHTML = columns.map(function (column) {
      return '<div class="roster-score-column" data-id="' + esc(column.id) + '">' +
        '<label>Column label<input type="text" class="roster-score-column-label" maxlength="80" value="' + esc(column.label) + '" aria-label="Score column label"></label>' +
        '<button type="button" class="small roster-score-remove-column" aria-label="Remove score column">Remove</button>' +
        "</div>";
    }).join("");
    columnsEl.querySelectorAll(".roster-score-column-label").forEach(function (input) {
      input.addEventListener("change", function () {
        var row = input.closest(".roster-score-column");
        saveColumns(matrix().columns.map(function (column) {
          return {
            id: column.id,
            label: column.id === row.dataset.id ? input.value : column.label
          };
        }));
      });
    });
    columnsEl.querySelectorAll(".roster-score-remove-column").forEach(function (button) {
      button.addEventListener("click", function () {
        var row = button.closest(".roster-score-column");
        saveColumns(matrix().columns.filter(function (column) {
          return column.id !== row.dataset.id;
        }));
      });
    });
  }

  function renderGrid() {
    var current = matrix();
    var columns = current.columns;
    gridHead.innerHTML = "<tr><th>Student</th>" + columns.map(function (column) {
      return "<th>" + esc(column.label) + "</th>";
    }).join("") + "</tr>";
    if (!selectedSectionId) {
      gridBody.innerHTML = '<tr><td class="roster-score-empty" colspan="' + (columns.length + 1) + '">Select a section to edit current scores.</td></tr>';
      return;
    }
    var students = studentsInSection();
    if (!students.length) {
      gridBody.innerHTML = '<tr><td class="roster-score-empty" colspan="' + (columns.length + 1) + '">No students are enrolled in this section.</td></tr>';
      return;
    }
    var sectionValues = current.values_by_section[selectedSectionId] || {};
    gridBody.innerHTML = students.map(function (student) {
      var scores = sectionValues[student.id] || {};
      var cells = columns.map(function (column) {
        var value = scores[column.id];
        return '<td><input type="number" step="any" class="roster-score-cell" data-column-id="' + esc(column.id) + '" value="' + esc(value == null ? "" : value) + '" aria-label="' + esc(column.label) + '"></td>';
      }).join("");
      return '<tr data-student-id="' + esc(student.id) + '"><td>' + esc(student.display_name || student.name) + "</td>" + cells + "</tr>";
    }).join("");
  }

  function render() {
    workspace.hidden = !roster.hasLoadedCourse();
    if (workspace.hidden) return;
    renderSectionPicker();
    renderColumns();
    renderGrid();
  }

  function applyResponse(data, successMessage) {
    if (!data || !data.ok) {
      var error = (data && data.error) || "Score-matrix save failed.";
      setStatus(error, true);
      roster.toast(error, true);
      return;
    }
    roster.setScoreMatrix(data.score_matrix);
    setStatus(successMessage, false);
    render();
  }

  function saveColumns(columns) {
    setStatus("Saving columns...", false);
    roster.postForm("/api/roster/score-matrix", {
      course_id: roster.getCurrentCourseId(),
      patch: JSON.stringify({ columns: columns })
    }).then(function (data) {
      applyResponse(data, "Columns saved locally.");
    }).catch(function (error) {
      setStatus("Network error: " + error.message, true);
      roster.toast("Score-matrix save failed.", true);
    });
  }

  function newColumnId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return "score-" + window.crypto.randomUUID();
    }
    return "score-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function addColumn() {
    var label = newColumnInput.value.trim();
    if (!label) {
      setStatus("Enter a score-column label first.", true);
      return;
    }
    var columns = matrix().columns.map(function (column) {
      return { id: column.id, label: column.label };
    });
    columns.push({ id: newColumnId(), label: label });
    saveColumns(columns);
    newColumnInput.value = "";
  }

  function saveScores() {
    var columns = matrix().columns;
    if (!selectedSectionId) {
      setStatus("Select a section before saving scores.", true);
      return;
    }
    if (!columns.length) {
      setStatus("Add a score column before saving scores.", true);
      return;
    }
    var values = {};
    gridBody.querySelectorAll("tr[data-student-id]").forEach(function (row) {
      var scores = {};
      row.querySelectorAll(".roster-score-cell").forEach(function (input) {
        scores[input.dataset.columnId] = input.value.trim() === "" ? null : Number(input.value);
      });
      values[row.dataset.studentId] = scores;
    });
    setStatus("Saving scores...", false);
    roster.postForm("/api/roster/score-matrix", {
      course_id: roster.getCurrentCourseId(),
      patch: JSON.stringify({ section_id: selectedSectionId, values: values })
    }).then(function (data) {
      applyResponse(data, "Scores saved locally.");
    }).catch(function (error) {
      setStatus("Network error: " + error.message, true);
      roster.toast("Score-matrix save failed.", true);
    });
  }

  sectionSelect.addEventListener("change", function () {
    selectedSectionId = sectionSelect.value;
    renderGrid();
  });
  addColumnButton.addEventListener("click", addColumn);
  newColumnInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      addColumn();
    }
  });
  saveButton.addEventListener("click", saveScores);
  roster.onCourseLoaded(function () {
    selectedSectionId = "";
    render();
  });
  if (courseSelect) {
    courseSelect.addEventListener("change", function () {
      if (!courseSelect.value) workspace.hidden = true;
    });
  }
})();
