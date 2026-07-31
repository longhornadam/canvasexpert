(function () {
  "use strict";

  var readiness = document.getElementById("class-schedule-readiness");
  if (!readiness) return;

  var CE = window.CE_SETTINGS || {};
  var blockList = document.getElementById("class-schedule-block-list");
  var blockStatus = document.getElementById("class-schedule-status");
  var examples = document.getElementById("class-schedule-examples");
  var state = { blocks: [], folders: {}, examples: [] };
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

  function renderReadiness(data) {
    var pieces = data.pieces || {};
    var teacher = pieces.teacher_schedule || {};
    var bell = pieces.bell_schedules || {};
    var day = pieces.day_calendar || {};
    var bellLabels = (bell.found || []).map(function (item) {
      return item.label || item.name;
    });
    var dayRange = day.first && day.last ? ", " + day.first + " through " + day.last : "";
    var rows = [
      {
        label: "Your blocks.",
        text: teacher.present
          ? "Found " + (teacher.count || 0) + " blocks in Teacher Schedule.json."
          : "No Teacher Schedule.json yet. Add your blocks below, or load an example set."
      },
      {
        label: "Bell schedules.",
        text: bell.present
          ? "Found " + (bell.count || 0) + ": " + bellLabels.join(", ") + "."
          : "No Bell Schedule files in your Calendars folder yet."
      },
      {
        label: "Day calendar.",
        text: day.present
          ? "Found " + (day.date_count || 0) + " dates" + dayRange + "."
          : "No day calendar in your Calendars folder yet. A day calendar says which bell schedule each date uses."
      }
    ];
    readiness.innerHTML = rows.map(function (row) {
      return '<div class="ce-schedule-readiness-row" data-ce-hook="readiness-row"><strong>' +
        esc(row.label) + "</strong><span>" + esc(row.text) + "</span></div>";
    }).join("");

    var notice = document.createElement("div");
    notice.className = data.ready ? "ce-notice ce-notice--ok" : "ce-notice";
    notice.textContent = data.ready
      ? "SmartDeck has everything it needs."
      : "SmartDeck needs all three parts before it can show a deck.";
    readiness.appendChild(notice);
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
      var course = block.label || block.name || "";
      var days = blockDays(block);
      row.innerHTML =
        '<label>Course<input type="text" data-field="course" value="' + esc(course) + '"></label>' +
        '<label>Periods<input type="text" data-field="periods" value="' + esc(periods) + '" placeholder="1, 2"></label>' +
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
      var course = inputValue(row, "course").trim();
      block.name = course;
      block.raw_periods = parsePeriods(inputValue(row, "periods"));
      block.label = course;
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

  function renderExamples(items) {
    state.examples = Array.isArray(items) ? items : [];
    examples.innerHTML = state.examples.map(function (item) {
      var action = item.loaded ? "Remove this example" : "Load this example";
      var kind = item.loaded ? "remove" : "load";
      return '<div class="ce-schedule-example" data-ce-hook="example-card">' +
        '<div><h3>' + esc(item.name || item.slug) + '</h3><p class="ce-hint">' +
        esc(item.summary || "") + '</p><p class="ce-schedule-example-detail">' +
        esc(item.demonstrates || "") + '</p></div>' +
        '<button type="button" class="small" data-example-action="' + kind + '" data-example-slug="' +
        esc(item.slug) + '">' + action + '</button></div>';
    }).join("");
  }

  async function loadState() {
    var response = await fetch("/api/schedule");
    var data = await response.json();
    state.folders = data.folders || {};
    renderReadiness(data);
    renderBlocks(data.blocks || []);
    renderExamples(data.examples || []);
    setFolderButton("class-schedule-open-calendars", state.folders.calendars);
    setFolderButton("class-schedule-open-smartdecks", state.folders.smartdecks);
  }

  document.getElementById("class-schedule-add-block").addEventListener("click", function () {
    state.blocks.push({ name: "", raw_periods: [], label: "" });
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
    setStatus("Saved " + data.count + " blocks to Teacher Schedule.json.", "ok");
    await loadState();
  });

  blockList.addEventListener("click", function (event) {
    var button = event.target.closest('[data-block-action="remove"]');
    if (!button) return;
    var row = button.closest('[data-ce-hook="block-row"]');
    if (row) row.remove();
  });

  examples.addEventListener("click", async function (event) {
    var button = event.target.closest("[data-example-action]");
    if (!button) return;
    var slug = button.getAttribute("data-example-slug");
    var action = button.getAttribute("data-example-action");
    if (action === "remove") {
      if (!window.confirm("Move this example's files out of your workspace? They go to _System/Archive/Class Schedule Examples, and nothing is deleted. Files you have edited stay where they are.")) return;
      var removeResponse = await fetch("/api/schedule/examples/remove", {
        method: "POST", body: new URLSearchParams({ slug: slug })
      });
      var removeData = await removeResponse.json();
      if (!removeData.ok) window.alert((removeData.problems || []).join(" "));
      await loadState();
      return;
    }

    var loadResponse = await fetch("/api/schedule/examples/load", {
      method: "POST", body: new URLSearchParams({ slug: slug })
    });
    var loadData = await loadResponse.json();
    if (loadData.conflict === "teacher_schedule") {
      var replacement = loadData.replacement_name || "Teacher Schedule (replaced timestamp).json";
      if (!window.confirm("You already have a Teacher Schedule.json. Loading this example moves your current one aside as \"" + replacement + "\" and writes the example in its place. Continue?")) return;
      loadResponse = await fetch("/api/schedule/examples/load", {
        method: "POST", body: new URLSearchParams({ slug: slug, overwrite: "true" })
      });
      loadData = await loadResponse.json();
    }
    if (!loadData.ok) {
      window.alert((loadData.problems || []).join(" "));
      return;
    }
    var skipped = loadData.skipped || [];
    var message = "Loaded. " + (loadData.written || []).length + " files written.";
    if (skipped.length) message += " " + skipped.length + " was already there and was left alone: " + skipped.join(", ") + ".";
    if (loadData.day_calendar_overlap) message += " This example's day calendar covers " + loadData.day_calendar_overlap + " dates that your own day calendar already covers. On those dates the example may win. Remove the example when you are done looking at it.";
    setStatus(message, "ok");
    await loadState();
  });

  loadState().catch(function (error) {
    setStatus("Could not load class schedule: " + error, "error");
  });
})();
