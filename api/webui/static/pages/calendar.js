(function () {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message;
    el.className = "status ce-calendar-status" + (kind ? " " + kind : "");
  }

  /** Rejects when the copy did not actually happen, so a Copy control never
      claims success it cannot verify. The selected-text fallback reports
      execCommand's own result rather than assuming it worked. */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } finally {
      area.remove();
    }
    return copied ? Promise.resolve() : Promise.reject(new Error("copy refused"));
  }

  /** "2026-08-17" -> "Mon, Aug 17". Built from local Y/M/D components (not
      `new Date(dateStr)`, which parses as UTC midnight and can render the
      previous local day west of UTC). Falls back to the raw string if it
      cannot be parsed rather than showing a garbled date. */
  function friendlyDate(dateStr) {
    var parts = String(dateStr || "").split("-");
    if (parts.length !== 3) return esc(dateStr);
    var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (isNaN(d.getTime())) return esc(dateStr);
    return esc(d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }));
  }

  var state = { bellSchedules: [], teacherBlocks: [], courses: [], events: [] };

  /** The teacher-facing Bell Schedule name for a schedule_id, so a preview or
      upcoming row never shows only the raw id. */
  function scheduleLabel(scheduleId) {
    if (!scheduleId) return "";
    for (var i = 0; i < state.bellSchedules.length; i++) {
      if (state.bellSchedules[i].schedule_id === scheduleId) return state.bellSchedules[i].label;
    }
    return "";
  }

  // ── Readiness & upcoming ────────────────────────────────────────────────

  function renderReadiness(data) {
    var el = document.getElementById("calendar-readiness");
    var readiness = data.readiness || {};
    el.innerHTML = "";
    var notice = document.createElement("div");
    if (readiness.status === "unconfigured") {
      notice.className = "ce-notice";
      notice.textContent = "No school calendar yet. Create one below to get started.";
    } else if (readiness.status === "invalid_calendar") {
      notice.className = "ce-notice ce-notice--warn";
      notice.textContent = "The saved calendar could not be read. Create/replace it below.";
    } else if (readiness.status === "needs_attention") {
      notice.className = "ce-notice ce-notice--warn";
      var reasons = [];
      if (readiness.today && readiness.today.state === "outside_coverage" &&
          readiness.coverage_position === "after") {
        reasons.push("today is outside the configured coverage");
      }
      if ((readiness.unknown_schedule_dates || []).length) {
        reasons.push(readiness.unknown_schedule_dates.length + " date(s) name an unknown Bell Schedule");
      }
      if (readiness.coverage_position === "within" &&
          readiness.remaining_coverage_days != null && readiness.remaining_coverage_days < 30) {
        reasons.push(readiness.remaining_coverage_days + " day(s) of coverage remaining");
      }
      notice.textContent = "Needs attention: " + (reasons.join("; ") || "check coverage") + ".";
    } else {
      var today = readiness.today || {};
      notice.className = "ce-notice ce-notice--ok";
      if (readiness.coverage_position === "before") {
        notice.textContent = "Ready. The school year starts " +
          ((readiness.coverage || {}).start || "") + ".";
      } else if (today.state === "no_school" || today.state === "no_regular_classes") {
        notice.textContent = "No scheduled classes today" +
          (today.label ? ": " + today.label : "") + ".";
      } else {
        var todayDetail = today.state === "instructional" || today.state === "ready"
          ? (scheduleLabel(today.schedule_id) || today.schedule_id || "")
          : (today.label || "");
        notice.textContent = "Ready. School year " + (readiness.school_year || "") +
          ", coverage " + ((readiness.coverage || {}).start || "") + " through " +
          ((readiness.coverage || {}).end || "") +
          (todayDetail ? ". Today: " + todayDetail + "." : ".");
      }
    }
    el.appendChild(notice);
  }

  function renderUpcoming(data) {
    var el = document.getElementById("calendar-upcoming");
    var upcoming = data.upcoming || {};
    var days = upcoming.days || {};
    var keys = Object.keys(days).sort();
    if (!keys.length) {
      el.innerHTML = '<p class="ce-hint">No upcoming dates to show.</p>';
      return;
    }
    function rowHtml(dateKey) {
      var entry = days[dateKey] || {};
      var kindLabel = entry.kind === "instructional" ? "Instructional"
        : entry.kind === "no_regular_classes" ? "No regular classes"
        : entry.kind === "no_school" ? "No school" : esc(entry.kind);
      var detail;
      if (entry.kind === "instructional") {
        var label = scheduleLabel(entry.schedule_id);
        detail = label ? esc(label) : "Unknown Bell Schedule";
        if (entry.schedule_id) {
          detail += ' <span class="muted ce-calendar-id">(' + esc(entry.schedule_id) + ')</span>';
        }
      } else {
        detail = esc(entry.label || "");
      }
      return '<div class="ce-calendar-upcoming-row"><strong>' + friendlyDate(dateKey) + '</strong> — ' +
        kindLabel + (detail ? ": " + detail : "") + '</div>';
    }
    var visibleCount = 5;
    var visibleRows = keys.slice(0, visibleCount).map(rowHtml).join("");
    var remaining = keys.slice(visibleCount);
    if (!remaining.length) {
      el.innerHTML = visibleRows;
      return;
    }
    el.innerHTML = visibleRows +
      '<details id="calendar-upcoming-more" class="ce-calendar-upcoming-more"><summary>Show ' + remaining.length +
      ' more dates</summary>' + remaining.map(rowHtml).join("") + '</details>';
  }

  function openHashTarget() {
    if (!window.location.hash) return;
    var target = document.querySelector(window.location.hash);
    if (target && target.tagName === "DETAILS") target.open = true;
  }

  document.querySelectorAll('a[href^="#calendar-"]').forEach(function (link) {
    link.addEventListener("click", function () {
      var target = document.querySelector(link.getAttribute("href"));
      if (target && target.tagName === "DETAILS") target.open = true;
    });
  });
  openHashTarget();
  window.addEventListener("hashchange", openHashTarget);

  // ── Bell Schedules ───────────────────────────────────────────────────────

  function renderBellSchedules(data) {
    var bell = data.bell_schedules || {};
    var found = bell.found || [];
    state.bellSchedules = found;
    var list = document.getElementById("calendar-bell-list");
    if (!found.length) {
      list.innerHTML = '<p class="ce-empty">No Bell Schedule CSVs found in your Calendars folder.</p>';
    } else {
      list.innerHTML = found.map(function (entry) {
        var periods = Array.isArray(entry.periods) ? entry.periods : [];
        var periodRows = periods.map(function (p) {
          var segment = p.segment ? ' <span class="muted">' + esc(p.segment) + "</span>" : "";
          return '<div class="ce-calendar-period-row"><span class="ce-calendar-period-id">' +
            esc(p.period_id) + "</span><span>" + esc(p.start) + "&ndash;" + esc(p.end) + "</span>" +
            segment + "</div>";
        }).join("");
        return '<div class="ce-calendar-bell-row"><strong>' + esc(entry.label) + '</strong>' +
          ' <span class="muted ce-calendar-id">(' + esc(entry.schedule_id) + ')</span>' +
          '<div class="ce-calendar-period-list">' +
          (periodRows || '<p class="ce-empty">No periods parsed.</p>') + "</div></div>";
      }).join("");
    }
    if ((bell.problems || []).length) {
      list.innerHTML += '<div class="ce-notice ce-notice--warn">' +
        bell.problems.map(esc).join("<br>") + "</div>";
    }

    var options = found.map(function (entry) {
      return '<option value="' + esc(entry.schedule_id) + '">' + esc(entry.label) + '</option>';
    }).join("");
    var changeSelect = document.getElementById("cal-change-schedule");
    var createSelect = document.getElementById("cal-create-default-schedule");
    if (changeSelect) changeSelect.innerHTML = options;
    if (createSelect) createSelect.innerHTML = options;

    /* Per-weekday overrides are optional, so each one carries an empty "Default"
       choice that is omitted from the payload entirely. Re-selecting the prior
       value keeps a half-filled create form intact when loadState() re-renders. */
    document.querySelectorAll("#cal-create-weekday-schedules select").forEach(function (select) {
      var previous = select.value;
      select.innerHTML = '<option value="">Default</option>' + options;
      select.value = previous;
    });
  }

  var openFolderButton = document.getElementById("calendar-open-folder");
  if (openFolderButton) {
    openFolderButton.addEventListener("click", async function () {
      openFolderButton.disabled = true;
      try {
        var response = await fetch("/api/calendar/open-folder", { method: "POST" });
        var data = await response.json();
        if (!data.ok) {
          openFolderButton.title = data.error || "Could not open the Calendars folder.";
        }
      } finally {
        openFolderButton.disabled = false;
      }
    });
  }

  // ── Teacher Schedule (block editor) ──────────────────────────────────────

  function courseSelectHtml(block) {
    var courses = Array.isArray(state.courses) ? state.courses : [];
    var selected = block.course_id == null ? "" : String(block.course_id);
    var html = '<option value="">(none)</option>';
    courses.forEach(function (course) {
      var id = String(course.id == null ? "" : course.id);
      if (!id) return;
      html += '<option value="' + esc(id) + '"' +
        (id === selected ? " selected" : "") + ">" + esc(course.name || id) + "</option>";
    });
    // A block already naming a Previous/unknown course stays visible as a
    // concise repair warning, but is never offered as a valid choice: it
    // renders disabled, so the teacher must pick a Current course or clear it.
    if (selected && !courses.some(function (course) { return String(course.id) === selected; })) {
      html += '<option value="' + esc(selected) + '" selected disabled>' +
        esc(selected) + " — not a Current course; choose one or clear</option>";
    }
    return html;
  }

  function renderTeacherBlocks(blocks) {
    state.teacherBlocks = Array.isArray(blocks) ? blocks : [];
    var list = document.getElementById("calendar-teacher-block-list");
    if (!state.teacherBlocks.length) {
      list.innerHTML = '<p class="ce-empty">No blocks yet. Add a block to get started.</p>';
      return;
    }
    list.innerHTML = "";
    state.teacherBlocks.forEach(function (source) {
      var block = source && typeof source === "object" ? Object.assign({}, source) : {};
      var row = document.createElement("div");
      row.className = "ce-schedule-block-row";
      row.setAttribute("data-ce-hook", "block-row");
      row._sourceBlock = block;
      var periods = Array.isArray(block.raw_periods) ? block.raw_periods.join(", ") : "";
      row.innerHTML =
        '<label>Block<input type="text" data-field="name" value="' + esc(block.name || "") + '" placeholder="1st/2nd"></label>' +
        '<label>Periods<input type="text" data-field="periods" value="' + esc(periods) + '" placeholder="1, 2"></label>' +
        '<label>Class label<input type="text" data-field="label" value="' + esc(block.label || "") + '" placeholder="Intensive Reading"></label>' +
        '<label>Canvas course<select data-field="course_id"' + (state.courses.length ? "" : " disabled") + '>' +
        courseSelectHtml(block) + '</select>' +
        (state.courses.length ? "" : '<span class="ce-field-hint">Bookmark a course under Settings &rarr; Current courses.</span>') +
        '</label>' +
        '<button type="button" class="small danger" data-block-action="remove">Remove</button>';
      list.appendChild(row);
    });
  }

  function parsePeriods(value) {
    return value.split(",").map(function (part) {
      var trimmed = part.trim();
      return /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
    }).filter(function (part) { return part !== ""; });
  }

  function inputValue(row, field) {
    var input = row.querySelector('[data-field="' + field + '"]');
    return input ? input.value : "";
  }

  function readTeacherBlocks() {
    var list = document.getElementById("calendar-teacher-block-list");
    return Array.prototype.map.call(list.querySelectorAll('[data-ce-hook="block-row"]'), function (row) {
      var block = Object.assign({}, row._sourceBlock || {});
      block.name = inputValue(row, "name").trim();
      block.raw_periods = parsePeriods(inputValue(row, "periods"));
      var course = inputValue(row, "label").trim();
      if (course) block.label = course; else delete block.label;
      var courseId = inputValue(row, "course_id").trim();
      if (courseId) block.course_id = courseId; else delete block.course_id;
      delete block.weekdays;
      return block;
    });
  }

  document.getElementById("calendar-teacher-add-block").addEventListener("click", function () {
    state.teacherBlocks.push({ name: "", raw_periods: [] });
    renderTeacherBlocks(state.teacherBlocks);
  });

  document.getElementById("calendar-teacher-block-list").addEventListener("click", function (event) {
    var button = event.target.closest('[data-block-action="remove"]');
    if (!button) return;
    var row = button.closest('[data-ce-hook="block-row"]');
    if (row) row.remove();
  });

  document.getElementById("calendar-teacher-save-blocks").addEventListener("click", async function () {
    var status = document.getElementById("calendar-teacher-status");
    var response = await fetch("/api/schedule/teacher", {
      method: "POST",
      body: new URLSearchParams({ blocks: JSON.stringify(readTeacherBlocks()) }),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Nothing was saved. Fix these first: " + (data.problems || []).join(" "), "error");
      return;
    }
    setStatus(status, "Saved " + data.count + " block(s).", "ok");
    await loadState();
  });

  // ── Public events (structured preview/apply) ─────────────────────────────

  var lastEventPreview = null;

  function eventDateText(event) {
    if (!event) return "";
    if (event.shape === "date") return friendlyDate(event.date);
    if (event.shape === "span") return friendlyDate(event.start) + " to " + friendlyDate(event.end);
    var days = (event.weekdays || []).map(function (day) {
      return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day] || String(day);
    });
    var bounds = [event.effective_start, event.effective_end].filter(Boolean);
    return days.join(", ") + (bounds.length ? " (" + bounds.map(friendlyDate).join(" to ") + ")" : "");
  }

  function eventText(event) {
    if (!event) return "No event";
    var text = event.label + " — " + eventDateText(event);
    if (event.detail) text += " — " + event.detail;
    if (event.from || event.to) text += " (" + (event.from || "") + "–" + (event.to || "") + ")";
    if (event.result) text += " — Result: " + event.result;
    return text;
  }

  function renderEvents(events) {
    state.events = Array.isArray(events) ? events : [];
    var list = document.getElementById("calendar-event-list");
    if (!state.events.length) {
      list.innerHTML = '<p class="ce-empty">No public events in the canonical calendar.</p>';
      return;
    }
    list.innerHTML = state.events.map(function (event) {
      return '<div class="ce-calendar-event-row"><div><strong>' + esc(event.label) + '</strong>' +
        ' <span class="muted">(' + esc(event.kind) + ', ' + esc(event.shape) + ')</span><br>' +
        '<span>' + esc(eventDateText(event)) + '</span>' +
        (event.detail ? ' — ' + esc(event.detail) : "") +
        (event.result ? ' — <span>Result: ' + esc(event.result) + '</span>' : "") +
        '</div><div class="ce-calendar-event-actions"><button type="button" class="small" data-event-action="edit" data-event-id="' +
        esc(event.id) + '">Edit</button><button type="button" class="small danger" data-event-action="delete" data-event-id="' +
        esc(event.id) + '">Delete</button></div></div>';
    }).join("");
  }

  function eventField(id) { return document.getElementById(id); }

  function setEventEditor(event, action) {
    var editor = document.getElementById("calendar-event-editor");
    editor.hidden = false;
    event = event || {};
    eventField("cal-event-action").value = action || "upsert";
    eventField("cal-event-id").value = event.id || "";
    eventField("cal-event-kind").value = event.kind || "game";
    eventField("cal-event-label").value = event.label || "";
    eventField("cal-event-shape").value = event.shape || "date";
    eventField("cal-event-date").value = event.date || "";
    eventField("cal-event-start").value = event.start || "";
    eventField("cal-event-end").value = event.end || "";
    eventField("cal-event-effective-start").value = event.effective_start || "";
    eventField("cal-event-effective-end").value = event.effective_end || "";
    eventField("cal-event-detail").value = event.detail || "";
    eventField("cal-event-from").value = event.from || "";
    eventField("cal-event-to").value = event.to || "";
    eventField("cal-event-result").value = event.result || "";
    document.querySelectorAll("#cal-event-weekdays input").forEach(function (box) {
      box.checked = (event.weekdays || []).indexOf(Number(box.value)) !== -1;
    });
    updateEventEditorMode();
  }

  function updateEventEditorMode() {
    var action = eventField("cal-event-action").value;
    var kind = eventField("cal-event-kind").value;
    var shape = eventField("cal-event-shape").value;
    document.querySelectorAll("[data-event-shape]").forEach(function (section) {
      section.hidden = section.getAttribute("data-event-shape") !== shape;
    });
    document.querySelectorAll("[data-event-upsert-only]").forEach(function (section) {
      section.hidden = action === "delete";
    });
    ["cal-event-kind", "cal-event-label", "cal-event-shape", "cal-event-date", "cal-event-start",
      "cal-event-end", "cal-event-effective-start", "cal-event-effective-end", "cal-event-detail",
      "cal-event-from", "cal-event-to", "cal-event-result"].forEach(function (id) {
      var input = eventField(id);
      if (input) input.disabled = action === "delete";
    });
    document.querySelectorAll("#cal-event-weekdays input").forEach(function (box) {
      box.disabled = action === "delete";
    });
    document.getElementById("cal-event-result-field").hidden = kind !== "game" || action === "delete";
  }

  function readEventMutation() {
    var action = eventField("cal-event-action").value;
    var eventId = eventField("cal-event-id").value.trim();
    if (action === "delete") return { action: "delete", event_id: eventId };
    var shape = eventField("cal-event-shape").value;
    var event = {
      id: eventId,
      kind: eventField("cal-event-kind").value,
      label: eventField("cal-event-label").value.trim(),
      shape: shape,
    };
    if (shape === "date") event.date = eventField("cal-event-date").value;
    if (shape === "span") {
      event.start = eventField("cal-event-start").value;
      event.end = eventField("cal-event-end").value;
    }
    if (shape === "weekdays") {
      event.weekdays = Array.prototype.map.call(document.querySelectorAll("#cal-event-weekdays input:checked"), function (box) {
        return Number(box.value);
      });
      event.effective_start = eventField("cal-event-effective-start").value || null;
      event.effective_end = eventField("cal-event-effective-end").value || null;
    }
    [["detail", "cal-event-detail"], ["from", "cal-event-from"], ["to", "cal-event-to"]].forEach(function (pair) {
      var value = eventField(pair[1]).value.trim();
      if (value) event[pair[0]] = value;
    });
    if (event.kind === "game" && eventField("cal-event-result").value) {
      event.result = eventField("cal-event-result").value;
    }
    return { action: "upsert", event: event };
  }

  function renderEventPreview(data) {
    var result = document.getElementById("cal-event-preview-result");
    result.hidden = false;
    result.innerHTML = '<div><strong>Before:</strong> ' + esc(eventText(data.before)) + '</div>' +
      '<div><strong>After:</strong> ' + esc(eventText(data.after)) + '</div>';
  }

  function resetDeleteButtons() {
    document.querySelectorAll('[data-event-action="delete"][data-event-confirm="true"]').forEach(function (button) {
      button.removeAttribute("data-event-confirm");
      button.removeAttribute("aria-label");
      button.textContent = "Delete";
    });
  }

  function clearEventPreview() {
    lastEventPreview = null;
    resetDeleteButtons();
    document.getElementById("cal-event-preview-result").hidden = true;
    document.getElementById("cal-event-apply").hidden = true;
  }

  async function previewEventChange() {
    var status = document.getElementById("cal-event-status");
    var mutation = readEventMutation();
    var body = { action: mutation.action, event_id: mutation.event_id || "" };
    if (mutation.event) body.event = JSON.stringify(mutation.event);
    var response = await fetch("/api/calendar/event/preview", {
      method: "POST", body: new URLSearchParams(body),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Preview failed: " + (data.problems || []).join(" "), "error");
      clearEventPreview();
      return false;
    }
    lastEventPreview = data;
    renderEventPreview(data);
    document.getElementById("cal-event-apply").hidden = false;
    setStatus(status, data.is_noop ? "No change — this event already matches." :
      (mutation.action === "delete" ? "Review the deletion, then Apply." :
        "Review the before/after event, then Apply."), "");
    return true;
  }

  document.getElementById("cal-event-new").addEventListener("click", function () {
    setEventEditor(null, "upsert");
    clearEventPreview();
    document.getElementById("cal-event-status").textContent = "";
  });
  document.getElementById("calendar-event-list").addEventListener("click", async function (event) {
    var button = event.target.closest("[data-event-action]");
    if (!button) return;
    if (button.dataset.eventConfirm === "true") {
      await applyEventChange();
      return;
    }
    var selected = state.events.find(function (item) { return item.id === button.dataset.eventId; });
    var action = button.dataset.eventAction === "delete" ? "delete" : "upsert";
    setEventEditor(selected, action);
    clearEventPreview();
    document.getElementById("cal-event-status").textContent = "";
    if (action === "delete" && await previewEventChange()) {
      button.dataset.eventConfirm = "true";
      button.setAttribute("aria-label", "Confirm deletion of " + (selected.label || "this event"));
      button.textContent = "Confirm?";
    }
  });
  document.getElementById("calendar-event-editor").addEventListener("input", clearEventPreview);
  document.getElementById("calendar-event-editor").addEventListener("change", function () {
    clearEventPreview();
    updateEventEditorMode();
  });
  document.getElementById("cal-event-preview").addEventListener("click", previewEventChange);
  async function applyEventChange() {
    var status = document.getElementById("cal-event-status");
    if (!lastEventPreview) return false;
    var response = await fetch("/api/calendar/event/apply", {
      method: "POST", body: new URLSearchParams({
        expected_revision: String(lastEventPreview.base_revision),
        preview: JSON.stringify(lastEventPreview),
      }),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Apply failed: " + (data.problems || []).join(" "), "error");
      clearEventPreview();
      return false;
    }
    var wasDelete = lastEventPreview.mutation && lastEventPreview.mutation.action === "delete";
    setStatus(status, wasDelete ? "Deleted." : "Applied.", "ok");
    clearEventPreview();
    await loadState();
    return true;
  }

  document.getElementById("cal-event-apply").addEventListener("click", function () {
    applyEventChange();
  });

  // ── Change a date (preview/apply) ────────────────────────────────────────

  var lastPreview = null;

  /** Teacher-facing description of a day entry for a preview: the actual
      Bell Schedule name for an instructional day, never a bare "instructional". */
  function describeDayEntry(entry) {
    if (!entry) return "(unset)";
    if (entry.kind === "instructional") {
      var label = scheduleLabel(entry.schedule_id);
      return esc(label || entry.schedule_id || "unknown schedule");
    }
    return esc(entry.label || entry.kind || "");
  }

  function selectedWeekdays() {
    var boxes = document.querySelectorAll("#cal-change-weekdays input[type=checkbox]");
    var all = Array.prototype.map.call(boxes, function (box) { return box; });
    var checked = all.filter(function (box) { return box.checked; });
    if (checked.length === all.length) return null; // all selected == no filter
    return checked.map(function (box) { return Number(box.value); });
  }

  document.getElementById("cal-change-preview").addEventListener("click", async function () {
    var status = document.getElementById("cal-change-status");
    var resultEl = document.getElementById("cal-change-preview-result");
    var applyBtn = document.getElementById("cal-change-apply");
    var kind = document.getElementById("cal-change-kind").value;
    var scheduleId = document.getElementById("cal-change-schedule").value;
    var label = document.getElementById("cal-change-label").value.trim();
    var datesRaw = document.getElementById("cal-change-dates").value.trim();
    var from = document.getElementById("cal-change-from").value;
    var to = document.getElementById("cal-change-to").value;
    var weekdays = selectedWeekdays();

    var body = { kind: kind };
    if (datesRaw) {
      body.dates = JSON.stringify(datesRaw.split(",").map(function (s) { return s.trim(); }).filter(Boolean));
    } else {
      body.date_from = from;
      body.date_to = to;
      if (weekdays) body.weekdays = JSON.stringify(weekdays);
    }
    if (kind === "instructional") {
      body.schedule_id = scheduleId;
    } else {
      body.label = label;
    }

    var response = await fetch("/api/calendar/change/preview", {
      method: "POST",
      body: new URLSearchParams(body),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Preview failed: " + (data.problems || []).join(" "), "error");
      resultEl.hidden = true;
      applyBtn.hidden = true;
      return;
    }
    lastPreview = data;
    var affected = data.affected || [];
    var conflicts = data.conflicts || [];
    var conflictHtml = conflicts.length
      ? '<div><strong>Advisory:</strong> ' + conflicts.map(function (conflict) {
        var reason = conflict.reason === "weekend" ? "weekend" : "day kind changes";
        var label = conflict.from_label ? ' ("' + esc(conflict.from_label) + '")' : "";
        return '<div>' + friendlyDate(conflict.date) + ": " + esc(reason) +
          "; " + esc(conflict.from_kind || "(unset)") + label +
          " &rarr; " + esc(conflict.to_kind || "") + '</div>';
      }).join("") + '</div>'
      : "";
    resultEl.hidden = false;
    resultEl.innerHTML = conflictHtml + affected.map(function (entry) {
      return '<div>' + friendlyDate(entry.date) + ": " +
        describeDayEntry(entry.before) + " &rarr; " + describeDayEntry(entry.after) + '</div>';
    }).join("");
    setStatus(status, data.is_noop
      ? "No change — every date already matches."
      : affected.length + " date(s) will change. Review, then Apply.", "");
    applyBtn.hidden = false;
  });

  document.getElementById("cal-change-apply").addEventListener("click", async function () {
    var status = document.getElementById("cal-change-status");
    if (!lastPreview) return;
    var response = await fetch("/api/calendar/change/apply", {
      method: "POST",
      body: new URLSearchParams({
        expected_revision: String(lastPreview.base_revision),
        preview: JSON.stringify(lastPreview),
      }),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Apply failed: " + (data.problems || []).join(" "), "error");
      return;
    }
    setStatus(status, "Applied. Calendar is now at revision " + data.revision + ".", "ok");
    document.getElementById("cal-change-apply").hidden = true;
    document.getElementById("cal-change-preview-result").hidden = true;
    lastPreview = null;
    await loadState();
  });

  // ── Create / replace school year (staged preview/apply) ──────────────────

  var lastYearPreview = null;
  var importedDateLabels = null;

  /* The same bytes the Download link serves and the MCP get_authoring_contract
     tool returns, so a pasted assistant and a connected one read one text. */
  var GUIDE_URL = "/api/download-contract?name=AcademicCalendar";

  document.getElementById("cal-guide-copy").addEventListener("click", function () {
    var button = this;
    var result = document.getElementById("cal-guide-result");
    var original = button.textContent;
    button.disabled = true;
    setStatus(result, "");
    fetch(GUIDE_URL)
      .then(function (response) {
        if (!response.ok) throw new Error("http " + response.status);
        return response.text();
      })
      .then(function (text) {
        return copyText(text).then(function () {
          button.textContent = "Copied";
          setStatus(result, "The guide is on your clipboard. Paste it into your assistant, " +
            "then give it your district calendar.", "ok");
          setTimeout(function () { button.textContent = original; }, 1600);
        });
      })
      .catch(function () {
        setStatus(result, "That could not be copied. Use Download the guide instead, " +
          "then open the file and copy from there.", "error");
      })
      .then(function () { button.disabled = false; });
  });

  /** One editable grading-period row, appended rather than re-rendered from a
      state array, so adding a row never discards typing already in the others. */
  function appendPeriodRow(period) {
    var list = document.getElementById("cal-create-period-list");
    var empty = list.querySelector('[data-ce-hook="period-empty"]');
    if (empty) empty.remove();
    var source = period && typeof period === "object" ? period : {};
    var row = document.createElement("div");
    row.className = "ce-calendar-period-edit-row";
    row.setAttribute("data-ce-hook", "period-row");
    row.innerHTML =
      '<label>Code<input type="text" data-field="code" value="' + esc(source.code || "") + '" placeholder="T1"></label>' +
      '<label>Name<input type="text" data-field="name" value="' + esc(source.name || "") + '" placeholder="Term 1"></label>' +
      '<label>Start<input type="date" data-field="start" value="' + esc(source.start || "") + '"></label>' +
      '<label>End<input type="date" data-field="end" value="' + esc(source.end || "") + '"></label>' +
      '<label>Report issued <small class="lbl-hint">(optional)</small>' +
      '<input type="date" data-field="report_issue_date" value="' + esc(source.report_issue_date || "") + '"></label>' +
      '<button type="button" class="small danger" data-period-action="remove">Remove</button>';
    list.appendChild(row);
  }

  function renderGradingPeriods(periods) {
    var list = document.getElementById("cal-create-period-list");
    list.innerHTML = "";
    var rows = Array.isArray(periods) ? periods : [];
    if (!rows.length) {
      list.innerHTML = '<p class="ce-empty" data-ce-hook="period-empty">' +
        "No grading periods. Import a CSV or add them by hand.</p>";
      return;
    }
    rows.forEach(appendPeriodRow);
  }

  /** Rows back to canonical grading-period objects. A blank report_issue_date is
      omitted rather than sent as "": the validator accepts null or an exact ISO
      date and rejects the empty string. Entirely blank rows are dropped so a
      stray Add never fails the preview. */
  function readGradingPeriods() {
    var list = document.getElementById("cal-create-period-list");
    var rows = list.querySelectorAll('[data-ce-hook="period-row"]');
    return Array.prototype.map.call(rows, function (row) {
      var period = {
        code: inputValue(row, "code").trim(),
        name: inputValue(row, "name").trim(),
        start: inputValue(row, "start"),
        end: inputValue(row, "end"),
      };
      var report = inputValue(row, "report_issue_date");
      if (report) period.report_issue_date = report;
      return period;
    }).filter(function (period) {
      return period.code || period.name || period.start || period.end;
    });
  }

  document.getElementById("cal-create-add-period").addEventListener("click", function () {
    appendPeriodRow({});
  });

  document.getElementById("cal-create-period-list").addEventListener("click", function (event) {
    var button = event.target.closest('[data-period-action="remove"]');
    if (!button) return;
    var row = button.closest('[data-ce-hook="period-row"]');
    if (row) row.remove();
  });

  document.getElementById("cal-import-parse").addEventListener("click", async function () {
    var status = document.getElementById("cal-import-status");
    var notesEl = document.getElementById("cal-import-notes");
    var content = document.getElementById("cal-import-csv").value;
    notesEl.hidden = true;
    notesEl.innerHTML = "";
    if (!content.trim()) {
      setStatus(status, "Paste a CSV first.", "error");
      return;
    }
    var response = await fetch("/api/calendar/import", {
      method: "POST",
      body: new URLSearchParams({ content: content }),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Could not parse: " + (data.problems || []).join(" "), "error");
      return;
    }
    var dates = data.no_school_dates || [];
    var periods = data.grading_periods || [];
    document.getElementById("cal-create-no-school").value = dates.join("\n");
    renderGradingPeriods(periods);
    importedDateLabels = data.date_labels || {};
    setStatus(status, "Parsed " + dates.length + " no-school date(s) and " + periods.length +
      " grading period(s) into the form below.",
      dates.length || periods.length ? "ok" : "error");

    /* The parser's own account of rows it could not read. Showing it is the only
       way a teacher learns why a CSV that looked correct produced nothing. */
    var notes = data.notes || [];
    if (notes.length) {
      notesEl.innerHTML = "<div>Rows that were skipped:</div>" +
        notes.map(function (note) { return "<div>" + esc(note) + "</div>"; }).join("");
      notesEl.hidden = false;
    }
  });

  function yearMutationBody() {
    var noSchool = document.getElementById("cal-create-no-school").value
      .split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
    var weekdaySchedules = {};
    document.querySelectorAll("#cal-create-weekday-schedules select").forEach(function (select) {
      if (select.value) weekdaySchedules[select.getAttribute("data-weekday")] = select.value;
    });
    var body = {
      school_year: document.getElementById("cal-create-year").value.trim(),
      coverage_start: document.getElementById("cal-create-start").value,
      coverage_end: document.getElementById("cal-create-end").value,
      default_schedule_id: document.getElementById("cal-create-default-schedule").value,
      no_school_dates: JSON.stringify(noSchool),
      weekday_schedules: JSON.stringify(weekdaySchedules),
      grading_periods: JSON.stringify(readGradingPeriods()),
    };
    if (importedDateLabels) {
      body.date_labels = JSON.stringify(importedDateLabels);
    }
    return body;
  }

  document.getElementById("cal-create-preview").addEventListener("click", async function () {
    var status = document.getElementById("cal-create-status");
    var resultEl = document.getElementById("cal-create-preview-result");
    var applyBtn = document.getElementById("cal-create-apply");

    var response = await fetch("/api/calendar/year/preview", {
      method: "POST",
      body: new URLSearchParams(yearMutationBody()),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Preview failed: " + (data.problems || []).join(" "), "error");
      resultEl.hidden = true;
      applyBtn.hidden = true;
      return;
    }
    lastYearPreview = data;
    var isReplace = data.operation === "replace";
    var lines = [];
    if (isReplace) {
      lines.push('<div>Current: ' + esc(data.current_school_year) + " (" +
        esc((data.current_coverage || {}).start) + " through " +
        esc((data.current_coverage || {}).end) + ")</div>");
    }
    lines.push('<div>Proposed: ' + esc(data.proposed_school_year) + " (" +
      esc((data.proposed_coverage || {}).start) + " through " +
      esc((data.proposed_coverage || {}).end) + ")</div>");
    lines.push('<div>' + data.day_count + " day(s), " + data.grading_period_count +
      " grading period(s), " + data.event_count + " event(s)</div>");
    if (isReplace) {
      var changes = data.material_changes || {};
      lines.push('<div>Changes from the active calendar: ' + (changes.days_added || 0) +
        " added, " + (changes.days_removed || 0) + " removed, " + (changes.days_changed || 0) +
        " changed</div>");
    }
    resultEl.hidden = false;
    resultEl.innerHTML = lines.join("");
    applyBtn.textContent = isReplace ? "Replace calendar" : "Create calendar";
    applyBtn.hidden = false;
    setStatus(status, "Review the summary, then " + (isReplace ? "Replace" : "Create") + ".", "");
  });

  document.getElementById("cal-create-apply").addEventListener("click", async function () {
    var status = document.getElementById("cal-create-status");
    if (!lastYearPreview) return;
    var response = await fetch("/api/calendar/year/apply", {
      method: "POST",
      body: new URLSearchParams({
        expected_revision: String(lastYearPreview.base_revision),
        preview: JSON.stringify(lastYearPreview),
      }),
    });
    var data = await response.json();
    if (!data.ok) {
      setStatus(status, "Not applied: " + (data.problems || []).join(" "), "error");
      return;
    }
    setStatus(status, "Applied " + data.school_year + " (" + data.day_count +
      " days, revision " + data.revision + ").", "ok");
    document.getElementById("cal-create-apply").hidden = true;
    document.getElementById("cal-create-preview-result").hidden = true;
    lastYearPreview = null;
    await loadState();
  });

  // ── Load ──────────────────────────────────────────────────────────────

  async function loadState() {
    var response = await fetch("/api/calendar");
    var data = await response.json();
    state.courses = Array.isArray(data.courses) ? data.courses : [];
    renderBellSchedules(data);
    renderReadiness(data);
    renderUpcoming(data);
    renderEvents(data.events || []);
    renderTeacherBlocks((data.teacher_schedule || {}).blocks || []);
    /* Prefilled from the active calendar so a Create/Replace that does not touch
       this editor carries the existing periods forward instead of dropping them. */
    renderGradingPeriods(data.grading_periods || []);
  }

  loadState().catch(function (error) {
    setStatus(document.getElementById("cal-change-status"), "Could not load Calendar: " + error, "error");
  });
})();
