/* Local-only, section-scoped seating relationship editor. */
(function () {
  "use strict";

  var sectionSelect = document.getElementById("roster-relationships-section");
  var studentA = document.getElementById("roster-relationship-student-a");
  var studentB = document.getElementById("roster-relationship-student-b");
  var typeSelect = document.getElementById("roster-relationship-type");
  var reasonInput = document.getElementById("roster-relationship-reason");
  var saveButton = document.getElementById("roster-relationship-save");
  var list = document.getElementById("roster-relationships-list");
  var status = document.getElementById("roster-relationships-status");
  var card = document.getElementById("roster-relationships");

  function ce() { return window.CE_ROSTER; }

  function setStatus(message, isError) {
    status.textContent = message || "";
    status.className = "hint" + (isError ? " error" : "");
  }

  function sections() {
    var seen = {};
    var result = [];
    (ce().getStudents() || []).forEach(function (student) {
      (student.sections || []).forEach(function (section) {
        var id = String(section.id || "");
        if (id && !seen[id]) {
          seen[id] = true;
          result.push({ id: id, name: section.name || "Section" });
        }
      });
    });
    return result.sort(function (a, b) { return a.name.localeCompare(b.name); });
  }

  function studentsInSection(sectionId) {
    return (ce().getStudents() || []).filter(function (student) {
      return (student.sections || []).some(function (section) {
        return String(section.id) === String(sectionId);
      });
    }).sort(function (a, b) {
      return String(a.name || a.display_name || "").localeCompare(String(b.name || b.display_name || ""));
    });
  }

  function studentName(student) {
    return student.display_name || student.name || student.id;
  }

  function populateSelect(select, students) {
    var selected = select.value;
    select.replaceChildren();
    students.forEach(function (student) {
      var option = document.createElement("option");
      option.value = String(student.id);
      option.textContent = studentName(student);
      select.appendChild(option);
    });
    if (selected && students.some(function (student) { return String(student.id) === selected; })) {
      select.value = selected;
    }
  }

  function currentItems() {
    var relationships = ce().getRelationships() || { by_section: {} };
    return ((relationships.by_section || {})[sectionSelect.value] || []).slice();
  }

  function renderList() {
    list.replaceChildren();
    var studentsById = {};
    studentsInSection(sectionSelect.value).forEach(function (student) {
      studentsById[String(student.id)] = student;
    });
    var items = currentItems();
    if (!sectionSelect.value) {
      list.textContent = "Choose a section to manage relationships.";
      return;
    }
    if (!items.length) {
      list.textContent = "No saved relationships for this section.";
      return;
    }
    items.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "roster-relationship-row";
      var description = document.createElement("div");
      var left = studentsById[item.student_a];
      var right = studentsById[item.student_b];
      description.textContent = studentName(left || { id: item.student_a }) + " — " + studentName(right || { id: item.student_b }) + " · " + (item.type === "keep_apart" ? "Keep apart" : "Preferred pair");
      row.appendChild(description);
      if (item.reason) {
        var reason = document.createElement("small");
        reason.textContent = "Private reason: " + item.reason;
        row.appendChild(reason);
      }
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "small";
      remove.textContent = "Remove";
      remove.addEventListener("click", function () {
        persist(items.filter(function (candidate) {
          return !(candidate.student_a === item.student_a && candidate.student_b === item.student_b);
        }), "Relationship removed.");
      });
      row.appendChild(remove);
      list.appendChild(row);
    });
  }

  function renderStudents() {
    var students = studentsInSection(sectionSelect.value);
    populateSelect(studentA, students);
    populateSelect(studentB, students);
    saveButton.disabled = !sectionSelect.value || students.length < 2;
    renderList();
  }

  function renderSections() {
    var selected = sectionSelect.value;
    sectionSelect.replaceChildren();
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— select a section —";
    sectionSelect.appendChild(placeholder);
    sections().forEach(function (section) {
      var option = document.createElement("option");
      option.value = section.id;
      option.textContent = section.name;
      sectionSelect.appendChild(option);
    });
    if (selected) sectionSelect.value = selected;
    renderStudents();
  }

  function persist(items, successMessage) {
    var courseId = ce().getCurrentCourseId();
    if (!courseId || !sectionSelect.value) return;
    setStatus("Saving…", false);
    ce().postForm("/api/roster/relationships", {
      course_id: courseId,
      section_id: sectionSelect.value,
      relationships: JSON.stringify(items)
    }).then(function (data) {
      if (!data.ok) {
        setStatus(data.error || "Could not save relationships.", true);
        return;
      }
      ce().setRelationships(data.relationships);
      reasonInput.value = "";
      setStatus(successMessage, false);
      renderList();
    }).catch(function (error) {
      setStatus("Network error: " + error.message, true);
    });
  }

  sectionSelect.addEventListener("change", function () {
    setStatus("", false);
    renderStudents();
  });

  saveButton.addEventListener("click", function () {
    var first = studentA.value;
    var second = studentB.value;
    if (!first || !second || first === second) {
      setStatus("Choose two different students.", true);
      return;
    }
    var ordered = [first, second].sort();
    var item = { student_a: ordered[0], student_b: ordered[1], type: typeSelect.value, reason: reasonInput.value };
    var items = currentItems().filter(function (candidate) {
      return candidate.student_a !== item.student_a || candidate.student_b !== item.student_b;
    });
    items.push(item);
    persist(items, "Relationship saved.");
  });

  ce().onCourseLoaded(function () {
    card.hidden = false;
    setStatus("", false);
    renderSections();
  });
})();
