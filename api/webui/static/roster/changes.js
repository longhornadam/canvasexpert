/* Roster-change detection: new/departed/section-changed students against the
   last acknowledged baseline, plus the one-click section-change migration. */
(function () {
  "use strict";

  var card = document.getElementById("roster-changes");
  var statusEl = document.getElementById("roster-changes-status");
  var listEl = document.getElementById("roster-changes-list");
  var acknowledgeBtn = document.getElementById("roster-changes-acknowledge");

  function ce() { return window.CE_ROSTER; }

  if (!card || !statusEl || !listEl || !acknowledgeBtn || !ce() || typeof ce().getRosterChanges !== "function") {
    return;
  }

  function setStatus(message, isError) {
    statusEl.textContent = message || "";
    statusEl.className = "hint" + (isError ? " error" : "");
  }

  function studentName(student, fallbackId) {
    return (student && (student.display_name || student.name)) || fallbackId;
  }

  function addHeading(text) {
    var heading = document.createElement("strong");
    heading.textContent = text;
    listEl.appendChild(heading);
  }

  function addRow(description, note, button) {
    var row = document.createElement("div");
    row.className = "roster-change-row";
    var text = document.createElement("div");
    var main = document.createElement("div");
    main.textContent = description;
    text.appendChild(main);
    if (note) {
      var small = document.createElement("small");
      small.textContent = note;
      text.appendChild(small);
    }
    row.appendChild(text);
    row.appendChild(button || document.createElement("span"));
    listEl.appendChild(row);
  }

  function strandedNote(detail) {
    var parts = [];
    var columns = [];
    (detail.score_values || []).forEach(function (holding) {
      columns = columns.concat(holding.columns || []);
    });
    if (columns.length) parts.push("score columns: " + columns.join(", "));
    if ((detail.relationship_pairs || []).length) {
      parts.push("relationship pairs with " + detail.relationship_pairs.map(function (pair) {
        return pair.partner_name;
      }).join(", "));
    }
    if ((detail.seats || []).length) {
      parts.push("seat" + (detail.seats.length > 1 ? "s" : "") + " in " + detail.seats.map(function (seat) {
        return seat.mode_name;
      }).join(", "));
    }
    if (!parts.length) return "Nothing local was stranded under the old section.";
    return "Stranded under the old section: " + parts.join("; ") + ".";
  }

  function departedNote(entry) {
    var parts = [];
    if (entry.settings) parts.push("classroom settings");
    if (entry.extra_time_days) parts.push("extra time (" + entry.extra_time_days + " days)");
    if (entry.monitored) parts.push("monitored status");
    if ((entry.score_values || []).length) parts.push("score values");
    if ((entry.relationship_pairs || []).length) parts.push("relationship pairs");
    if ((entry.seats || []).length) parts.push("a seat assignment");
    if (!parts.length) return "No local data is still held for this student.";
    return "Still held locally: " + parts.join(", ") + ".";
  }

  function migrateSection(studentId, button) {
    button.disabled = true;
    ce().postForm("/api/roster/changes/migrate-section", {
      course_id: ce().getCurrentCourseId(),
      user_id: studentId
    }).then(function (data) {
      if (!data.ok) {
        ce().toast(data.error || "Could not bring that data over.", true);
        button.disabled = false;
        return;
      }
      ce().toast("Brought local data to the new section.", false);
      ce().reloadCourse();
    }).catch(function (error) {
      ce().toast("Network error: " + error.message, true);
      button.disabled = false;
    });
  }

  function migrateButton(studentId) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "small";
    button.textContent = "Bring data to new section";
    button.addEventListener("click", function () {
      migrateSection(studentId, button);
    });
    return button;
  }

  function render() {
    var changes = ce().getRosterChanges() || {};
    listEl.replaceChildren();
    card.hidden = false;

    if (!changes.baseline_set) {
      setStatus("Not tracking roster changes for this course yet. Acknowledge the current roster to start.", false);
      return;
    }

    var students = ce().getStudents() || [];
    var added = students.filter(function (student) {
      return student.roster_change && student.roster_change.is_new;
    });
    var changedSection = students.filter(function (student) {
      return student.roster_change && student.roster_change.changed_section;
    });
    var departed = changes.departed || [];
    var total = added.length + changedSection.length + departed.length;

    setStatus(total === 0
      ? "No roster changes since you last acknowledged this class."
      : total + " roster change" + (total === 1 ? "" : "s") + " since you last acknowledged this class.", false);

    if (added.length) {
      addHeading("New since you last looked");
      added.forEach(function (student) {
        addRow(studentName(student, student.id) + " is new on this roster.");
      });
    }

    if (changedSection.length) {
      addHeading("Changed section");
      changedSection.forEach(function (student) {
        var detail = student.roster_change.changed_section;
        var oldNames = (detail.old_section_names || []).join(", ") || "an old section";
        var newNames = (detail.new_section_names || []).join(", ") || "a new section";
        var description = studentName(student, student.id) + ": " + oldNames + " to " + newNames;
        var button = detail.can_migrate ? migrateButton(student.id) : null;
        addRow(description, strandedNote(detail), button);
      });
    }

    if (departed.length) {
      addHeading("No longer on this roster");
      departed.forEach(function (entry) {
        addRow(entry.display_name + " left this course.", departedNote(entry));
      });
    }
  }

  acknowledgeBtn.addEventListener("click", function () {
    var courseId = ce().getCurrentCourseId();
    if (!courseId) return;
    acknowledgeBtn.disabled = true;
    setStatus("Acknowledging...", false);
    ce().postForm("/api/roster/changes/acknowledge", { course_id: courseId }).then(function (data) {
      acknowledgeBtn.disabled = false;
      if (!data.ok) {
        setStatus(data.error || "Could not acknowledge the roster.", true);
        return;
      }
      ce().toast("Roster acknowledged.", false);
      ce().reloadCourse();
    }).catch(function (error) {
      acknowledgeBtn.disabled = false;
      setStatus("Network error: " + error.message, true);
    });
  });

  ce().onCourseLoaded(render);
})();
