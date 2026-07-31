(function () {
  "use strict";

  var readiness = document.getElementById("class-schedule-readiness");
  if (!readiness) return;

  var CE = window.CE_SETTINGS || {};
  var blockList = document.getElementById("class-schedule-block-list");
  var blockStatus = document.getElementById("class-schedule-status");
  var state = { blocks: [], folders: {} };
  var weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"];

  function esc(value) {
    if (CE.esc) return CE.esc(value);
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function setStatus(message, kind) {
    if (CE.setStatus) return CE.setStatus(blockStatus, message, kind);
    if (!blockStatus) return;
    blockStatus.textContent = message;
    blockStatus.className = "status" + (kind ? " " + kind : "");
  }

  function notice(text, kind) {
    var el = document.createElement("div");
    el.className = "ce-notice" + (kind ? " ce-notice--" + kind : "");
    el.textContent = text;
    readiness.appendChild(el);
  }

  function detail(text) {
    var el = document.createElement("p");
    el.className = "ce-hint";
    el.textContent = text;
    el.setAttribute("data-ce-hook", "readiness-detail");
    readiness.appendChild(el);
  }

  function plural(count, word) {
    return count + " " + word + (count === 1 ? "" : "s");
  }

  function renderReadiness(data) {
    var pieces = data.pieces || {};
    var teacher = pieces.teacher_schedule || {};
    var bell = pieces.bell_schedules || {};
    var day = pieces.day_calendar || {};
    readiness.innerHTML = "";

    if (data.ready) {
      var span = day.first && day.last && day.first !== day.last
        ? ", " + day.first + " through " + day.last
        : "";
      notice("Ready. " + plural(teacher.count || 0, "block") + ", " +
        plural(bell.count || 0, "bell schedule") + ", " +
        plural(day.count || 0, "date") + " in your day calendar" + span + ".", "ok");
    } else {
      notice("SmartDeck cannot show a deck until all three parts are here.");
      if (!teacher.present) detail("No blocks yet. Add one below.");
      if (!bell.present) detail("No Bell Schedule CSV in your Calendars folder yet.");
      if (!day.present) detail("No day calendar yet. It says which bell schedule each date uses.");
    }

    if (day.present && !day.covers_today) {
      detail("Your day calendar does not cover today. It runs through " +
        (day.last || "its last date") +
        ", so SmartDeck has no times after that. Ask your assistant to extend it, or add the dates in your Calendars folder.");
    }

    var unknown = day.unknown_schedule_ids || [];
    if (unknown.length) {
      detail("Your day calendar points at a bell schedule that is not in your Calendars " +
        "folder: " + unknown.join(", ") + ". Dates using it will not resolve.");
    }

    var problems = []
      .concat(teacher.problems || [], bell.problems || [], day.problems || []);
    if (problems.length) detail(problems.join(" "));
  }

  function inputValue(row, field) {
    var input = row.querySelector('[data-field="' + field + '"]');
    return input ? input.value : "";
  }

  function blockDays(block) {
    return Array.isArray(block.weekdays) ? block.weekdays : [];
  }

  function renderBlocks(blocks) {
    state.blocks = Array.isArray(blocks) ? blocks : [];
    if (!state.blocks.length) {
      blockList.innerHTML = '<p class="ce-empty">No blocks yet. Add a block to get started.</p>';
      return;
    }
    blockList.innerHTML = "";
    state.blocks.forEach(function (source) {
      var block = source && typeof source === "object" ? Object.assign({}, source) : {};
      var row = document.createElement("div");
      row.className = "ce-schedule-block-row";
      row.setAttribute("data-ce-hook", "block-row");
      row._sourceBlock = block;
      var periods = Array.isArray(block.raw_periods) ? block.raw_periods.join(", ") : "";
      var days = blockDays(block);
      row.innerHTML =
        '<label>Block<input type="text" data-field="name" value="' +
        esc(block.name || "") + '" placeholder="1st/2nd"></label>' +
        '<label>Periods<input type="text" data-field="periods" value="' +
        esc(periods) + '" placeholder="1, 2"></label>' +
        '<label>Course<input type="text" data-field="label" value="' +
        esc(block.label || "") + '" placeholder="Intensive Reading"></label>' +
        '<div class="ce-schedule-weekdays"><span class="ce-schedule-field-label">Days</span><div class="ce-schedule-day-list">' +
        weekdays.map(function (day, index) {
          return '<label><input type="checkbox" data-weekday="' + index + '"' +
            (days.indexOf(index) >= 0 ? " checked" : "") + ">" + day + "</label>";
        }).join("") +
        '</div></div>' +
        '<button type="button" class="small danger" data-block-action="remove">Remove</button>';
      blockList.appendChild(row);
    });
  }

  function parsePeriods(value) {
    return value.split(",").map(function (part) {
      var trimmed = part.trim();
      if (/^-?\d+$/.test(trimmed)) return Number(trimmed);
      return trimmed;
    }).filter(function (part) { return part !== ""; });
  }

  function readBlocks() {
    return Array.prototype.map.call(blockList.querySelectorAll('[data-ce-hook="block-row"]'), function (row) {
      var block = Object.assign({}, row._sourceBlock || {});
      block.name = inputValue(row, "name").trim();
      block.raw_periods = parsePeriods(inputValue(row, "periods"));
      var course = inputValue(row, "label").trim();
      if (course) {
        block.label = course;
      } else {
        delete block.label;
      }
      var selected = Array.prototype.map.call(
        row.querySelectorAll('[data-weekday]:checked'),
        function (input) { return Number(input.getAttribute("data-weekday")); }
      );
      var originalDays = blockDays(row._sourceBlock || {});
      var weekend = originalDays.filter(function (day) { return day === 5 || day === 6; });
      if (Array.isArray((row._sourceBlock || {}).weekdays) || selected.length) {
        block.weekdays = selected.concat(weekend.filter(function (day) {
          return selected.indexOf(day) < 0;
        }));
      } else {
        delete block.weekdays;
      }
      return block;
    });
  }

  function setFolderButton(id, path) {
    var button = document.getElementById(id);
    if (!button || !path) return;
    button.setAttribute("data-open-path", path);
    button.disabled = false;
  }

  async function loadState() {
    var response = await fetch("/api/schedule");
    var data = await response.json();
    state.folders = data.folders || {};
    renderReadiness(data);
    renderBlocks(data.blocks || []);
    setFolderButton("class-schedule-open-calendars", state.folders.calendars);
  }

  document.getElementById("class-schedule-add-block").addEventListener("click", function () {
    state.blocks.push({ name: "", raw_periods: [] });
    renderBlocks(state.blocks);
  });

  document.getElementById("class-schedule-save-blocks").addEventListener("click", async function () {
    var response = await fetch("/api/schedule/teacher", {
      method: "POST",
      body: new URLSearchParams({ blocks: JSON.stringify(readBlocks()) })
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus("Nothing was saved. Fix these first: " + (data.problems || []).join(" "), "error");
      return;
    }
    setStatus("Saved " + plural(data.count, "block") + " to Teacher Schedule.json.", "ok");
    await loadState();
  });

  blockList.addEventListener("click", function (event) {
    var button = event.target.closest('[data-block-action="remove"]');
    if (!button) return;
    var row = button.closest('[data-ce-hook="block-row"]');
    if (row) row.remove();
  });

  loadState().catch(function (error) {
    setStatus("Could not load class schedule: " + error, "error");
  });
})();
