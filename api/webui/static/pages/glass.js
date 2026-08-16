(function () {
  "use strict";

  var initial = window.GLASS_INITIAL || {};
  var initialContext = initial.context || {};
  var state = {
    payload: initial,
    clockMs: Date.parse(initialContext.at || ""),
    mode: initialContext.mode || "board",
    courseId: "",
    columns: [],
    expanded: {},
    rotationColumns: [],
    rotationIndex: 0,
    rotationCursors: {},
    manualUntil: 0,
    tool: "",
    note: "",
    noteVisible: false,
    randomSelected: "",
    reducedMotion: !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches),
    timer: {durationMs: 5 * 60 * 1000, remainingMs: 5 * 60 * 1000, running: false, startedAt: 0}
  };
  var timers = {tick: null, boundary: null, poll: null, rotation: null};
  var timeZone = "America/Chicago";
  var MAX_ROWS = 6;

  function byId(id) { return document.getElementById(id); }
  function text(value) { return value == null ? "" : String(value); }
  function nowMs() { return window.performance ? performance.now() : 0; }
  function dateLabel(value, options) {
    var parsed = new Date(text(value).length === 10 ? text(value) + "T12:00:00Z" : value);
    if (isNaN(parsed.getTime())) return text(value);
    return new Intl.DateTimeFormat("en-US", Object.assign({timeZone: timeZone}, options || {})).format(parsed);
  }
  function clockLabel(ms) {
    if (isNaN(ms)) return "—";
    return new Intl.DateTimeFormat("en-US", {timeZone: timeZone, hour: "numeric", minute: "2-digit"}).format(new Date(ms));
  }
  function dateTimeLabel(value) {
    var parsed = new Date(value || "");
    if (isNaN(parsed.getTime())) return text(value);
    return new Intl.DateTimeFormat("en-US", {timeZone: timeZone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit"}).format(parsed);
  }
  function remainingLabel(seconds) {
    if (seconds == null || isNaN(seconds)) return "—";
    seconds = Math.max(0, Math.round(seconds));
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }
  function asOfLabel(value) { return value ? "AS OF " + dateTimeLabel(value) : ""; }
  function stateLabel(value) { return text(value).replaceAll("_", " ").toUpperCase(); }
  function isRepair(region) {
    return !!region && ["unavailable", "attention", "mirror_needs_attention", "catalog_needs_attention", "changed_source", "expired", "no_course"].indexOf(region.state) >= 0;
  }
  function capItems(items) {
    items = Array.isArray(items) ? items.filter(function (item) { return item && typeof item === "object"; }) : [];
    return {items: items.slice(0, MAX_ROWS), extra: Math.max(0, items.length - MAX_ROWS)};
  }
  function row(main, detail, meta) { return {main: text(main), detail: text(detail), meta: text(meta)}; }
  function appendText(parent, className, value) {
    if (!value) return null;
    var node = document.createElement("div"); node.className = className; node.textContent = value; parent.appendChild(node); return node;
  }
  function repairCard(id, column, title, message, asOf) {
    return {id: id, column: column, title: title, message: message || "SYNC REQUIRED", asOf: asOf, repair: true, eligible: false};
  }
  function listCard(id, column, title, icon, rows, options) {
    options = options || {};
    var capped = capItems(rows);
    var allRows = capped.items.slice();
    if (capped.extra) allRows.push(row("+ " + capped.extra, "more", ""));
    var eligible = options.eligible !== false && allRows.length > 1;
    return {id: id, column: column, title: title || "", icon: icon || "", rows: allRows,
      compact: options.compact || (allRows[0] || row("", "", "")), asOf: options.asOf || "",
      eligible: eligible, forceExpanded: !!options.forceExpanded};
  }
  function itemDetail(item) {
    var parts = [];
    if (item && item.from && item.to) parts.push(item.from + "–" + item.to);
    else if (item && item.date) parts.push(dateLabel(item.date, {month: "short", day: "numeric"}));
    if (item && item.detail) parts.push(item.detail);
    if (item && item.result) parts.push(item.result);
    if (item && item.slot) parts.push(item.slot);
    return parts.join(" · ");
  }
  function calendarRows(items, kind) {
    return (items || []).map(function (item) {
      var name = item.label || item.name || "";
      var detail = itemDetail(item);
      if (kind === "academic") detail = "ACADEMIC · " + detail;
      return row(name, detail, item.from && item.to ? item.from : dateLabel(item.date, {month: "short", day: "numeric"}));
    });
  }
  function assignmentRows(assignments) {
    return (assignments || []).map(function (item) {
      return row(item.title, dateTimeLabel(item.due_at), item.due_at ? dateLabel(item.due_at, {month: "short", day: "numeric"}) : "");
    });
  }
  function missingRows(students) {
    return (students || []).map(function (student) {
      var count = Number(student.missing_count || 0);
      return row(student.student_name, (student.assignment_titles || []).join(" · "), count + (count === 1 ? " item" : " items"));
    });
  }
  function celebrationRows(items) {
    return (items || []).map(function (item) {
      return row(item.student_name, item.label, item.date ? dateLabel(item.date, {month: "short", day: "numeric"}) : "");
    });
  }
  function renderCard(descriptor) {
    var expanded = descriptor.forceExpanded || state.expanded[descriptor.column] === descriptor.id;
    var card = document.createElement("article");
    card.className = "glass-card " + (expanded ? "glass-card--expanded" : "glass-card--compact");
    if (state.manualUntil > nowMs() && expanded) card.classList.add("glass-card--manual");
    card.dataset.cardId = descriptor.id; card.dataset.column = descriptor.column;
    card.dataset.eligible = descriptor.eligible ? "true" : "false";
    card.dataset.state = descriptor.repair ? "repair" : "ready";
    card.tabIndex = descriptor.eligible ? 0 : -1;
    card.setAttribute("role", descriptor.eligible ? "button" : "region");
    card.setAttribute("aria-expanded", expanded ? "true" : "false");

    var head = document.createElement("div"); head.className = "glass-card__head";
    if (descriptor.icon) appendText(head, "glass-card__icon", descriptor.icon);
    appendText(head, "glass-card__title", descriptor.title);
    if (!expanded && !descriptor.repair && descriptor.id !== "objective") {
      appendText(head, "glass-card__head-summary", descriptor.compact.main + (descriptor.compact.meta ? " · " + descriptor.compact.meta : ""));
    }
    appendText(head, "glass-card__meta", asOfLabel(descriptor.asOf));
    card.appendChild(head);
    var body = document.createElement("div"); body.className = "glass-card__body";
    if (descriptor.repair) {
      appendText(body, "glass-card__repair", descriptor.message);
    } else if (descriptor.id === "objective") {
      appendText(body, "glass-card__detail", descriptor.message);
    } else {
      var compact = document.createElement("div"); compact.className = "glass-card__compact";
      appendText(compact, "glass-card__compact-main", descriptor.compact.main);
      appendText(compact, "glass-card__compact-sub", descriptor.compact.meta || descriptor.compact.detail);
      body.appendChild(compact);
      var detail = document.createElement("div"); detail.className = "glass-card__detail";
      descriptor.rows.forEach(function (item) {
        var line = document.createElement("div"); line.className = "glass-card__row";
        var main = document.createElement("div"); main.className = "glass-card__row-main"; main.textContent = item.main;
        var sub = document.createElement("div"); sub.className = "glass-card__row-detail"; sub.textContent = item.detail;
        var meta = document.createElement("div"); meta.className = "glass-card__row-meta"; meta.textContent = item.meta;
        var stack = document.createElement("div"); stack.appendChild(main); if (item.detail) stack.appendChild(sub);
        line.appendChild(stack); if (item.meta) line.appendChild(meta); detail.appendChild(line);
      });
      body.appendChild(detail);
    }
    card.appendChild(body); return card;
  }
  function renderColumns() {
    var targets = {left: byId("glass-left"), middle: byId("glass-middle"), right: byId("glass-right")};
    reconcileExpansion();
    Object.keys(targets).forEach(function (key) { targets[key].replaceChildren(); });
    state.columns.forEach(function (descriptors) {
      var column = descriptors[0] ? descriptors[0].column : null;
      if (!column) return;
      descriptors.forEach(function (descriptor) { targets[column].appendChild(renderCard(descriptor)); });
    });
    reconcileMotion();
    installTickers();
  }
  function reconcileExpansion() {
    var active = {};
    state.columns.forEach(function (descriptors) {
      if (!descriptors.length) return;
      var column = descriptors[0].column; active[column] = true;
      var eligible = descriptors.filter(function (item) { return item.eligible; });
      if (!eligible.length) { delete state.expanded[column]; return; }
      var current = eligible.some(function (item) { return item.id === state.expanded[column]; });
      if (!current) state.expanded[column] = eligible[0].id;
    });
    Object.keys(state.expanded).forEach(function (column) { if (!active[column]) delete state.expanded[column]; });
  }
  function setColumn(descriptors, column) { if (descriptors.length) state.columns.push(descriptors.map(function (item) { item.column = column; return item; })); }
  function classColumns(payload) {
    var classroom = payload.classroom || {}, due = classroom.due || {}, missing = classroom.missing || {}, celebrations = classroom.celebrations || {};
    var left = [], middle = [], right = [];
    if (Array.isArray(due.assignments) && due.assignments.length) left.push(listCard("due", "left", "", "", assignmentRows(due.assignments), {compact: assignmentRows(due.assignments)[0]}));
    else if (due.state && due.state !== "nothing_due" && due.message) left.push(repairCard("due-repair", "left", "", due.message, due.as_of));
    if (Array.isArray(missing.students) && missing.students.length) left.push(listCard("missing", "left", "MISSING WORK", "", missingRows(missing.students), {asOf: missing.as_of}));
    else if (isRepair(missing) && missing.message) left.push(repairCard("missing-repair", "left", "MISSING WORK", missing.message, missing.as_of));
    if (Array.isArray(celebrations.items) && celebrations.items.length) left.push(listCard("celebrations", "left", "CELEBRATIONS", "", celebrationRows(celebrations.items), {asOf: celebrations.as_of}));
    else if (isRepair(celebrations) && celebrations.message) left.push(repairCard("celebrations-repair", "left", "CELEBRATIONS", celebrations.message, celebrations.as_of));

    var objective = classroom.objective || {};
    if (objective.objective) middle.push({id: "objective", column: "middle", title: "", icon: "◎", message: objective.objective, eligible: false, forceExpanded: true});
    else if (objective.state && objective.state !== "no_objective" && objective.message) middle.push(repairCard("objective-repair", "middle", "", objective.message, ""));

    var board = payload.board || {};
    var events = [].concat(board.today_events || [], board.forward_events || [], board.academic_dates || []);
    if (events.length) right.push(listCard("calendar", "right", "", "▦", calendarRows(events), {eligible: events.length > 1}));
    var schoolRows = calendarRows(board.sports_results || [], "sports");
    if (schoolRows.length) right.push(listCard("sports", "right", "SPORTS", "", schoolRows));
    var bobcat = board.bobcat || {};
    if ((bobcat.activities || []).length) right.push(listCard("bobcat", "right", "BOBCAT HOUR", "", calendarRows(bobcat.activities, "bobcat")));
    var grading = board.grading_period || {};
    if (grading.state === "ready") right.push(listCard("grading", "right", "", "▣", [row(grading.name, grading.start + "–" + grading.end, grading.days_remaining + " DAYS")], {eligible: false}));
    setColumn(left, "left"); setColumn(middle, "middle"); setColumn(right, "right");
  }
  function boardColumns(payload) {
    var board = payload.board || {}, left = [], middle = [], right = [];
    var events = [].concat(board.today_events || [], board.forward_events || []);
    var academic = board.academic_dates || [];
    if (events.length) left.push(listCard("calendar", "left", "", "▦", calendarRows(events), {eligible: events.length > 1}));
    if (academic.length) middle.push(listCard("academic", "middle", "", "▦", calendarRows(academic, "academic"), {eligible: academic.length > 1}));
    var sports = calendarRows(board.sports_results || [], "sports");
    if (sports.length) right.push(listCard("sports", "right", "SPORTS", "", sports));
    var bobcat = board.bobcat || {};
    if ((bobcat.activities || []).length) right.push(listCard("bobcat", "right", "BOBCAT HOUR", "", calendarRows(bobcat.activities, "bobcat")));
    var grading = board.grading_period || {};
    if (grading.state === "ready") middle.push(listCard("grading", "middle", "", "▣", [row(grading.name, grading.start + "–" + grading.end, grading.days_remaining + " DAYS")], {eligible: false}));
    if (!left.length && board.message) left.push(repairCard("board-status", "left", "", board.message, ""));
    setColumn(left, "left"); setColumn(middle, "middle"); setColumn(right, "right");
  }
  function renderHeader(payload) {
    var context = payload.context || {}, board = payload.board || {}, classroom = payload.classroom || {}, period = classroom.period || {};
    byId("glass-date").textContent = dateLabel(context.date || "", {weekday: "long", month: "long", day: "numeric"});
    byId("glass-clock").textContent = clockLabel(state.clockMs);
    var isClass = context.mode === "class" && payload.classroom;
    var periodText = isClass ? (period.name || period.label || stateLabel(context.state)) : stateLabel(context.state);
    var courseText = isClass ? (period.label && period.label !== period.name ? period.label : "") : (board.schedule_label || "");
    byId("glass-period").textContent = periodText;
    byId("glass-course").textContent = courseText;
    var boundaryAt = isClass ? period.boundary_at : context.valid_until;
    var boundaryLabel = isClass ? (period.state === "up_next" ? "STARTS " : "ENDS ") : (context.state === "free" ? "NEXT ": "RESUMES ");
    byId("glass-boundary").textContent = boundaryAt ? boundaryLabel + clockLabel(Date.parse(boundaryAt)) : "";
    byId("glass-simulated").hidden = !context.simulated;
    var status = byId("glass-status"); status.textContent = board.message || ""; status.hidden = !board.message;
    byId("glass-footer-status").textContent = isClass ? stateLabel(classroom.state) : stateLabel(board.state || context.state);
  }
  function renderClassTime() {
    var period = ((state.payload || {}).classroom || {}).period || {};
    var boundary = Date.parse(period.boundary_at || "");
    var seconds = isNaN(boundary) ? period.remaining_seconds : Math.max(0, Math.round((boundary - state.clockMs) / 1000));
    var classCard = document.querySelector('[data-card-id="period"]');
    if (classCard) { var time = classCard.querySelector(".glass-card__row-meta"); if (time) time.textContent = remainingLabel(seconds); }
  }
  function renderTimer() {
    var remaining = timerRemaining();
    var value = remainingLabel(remaining / 1000);
    byId("glass-timer-value").textContent = value;
    byId("glass-timer-footer").textContent = state.timer.running || remaining !== state.timer.durationMs ? value : "";
  }
  function render(payload) {
    var oldMode = state.mode, oldCourse = state.courseId;
    state.payload = payload || {}; var context = state.payload.context || {};
    state.clockMs = Date.parse(context.at || ""); if (isNaN(state.clockMs)) state.clockMs = 0;
    state.mode = context.mode || "board";
    state.courseId = ((state.payload.classroom || {}).course_id || "");
    if (oldMode !== state.mode || oldCourse !== state.courseId) {
      state.expanded = {}; state.manualUntil = 0; state.randomSelected = ""; closeTool();
    }
    renderHeader(state.payload);
    state.columns = [];
    if (state.mode === "class" && state.payload.classroom) classColumns(state.payload); else boardColumns(state.payload);
    renderColumns();
    var names = ((state.payload.classroom || {}).random_name || {}).names || [];
    var randomButton = byId("glass-random-button"); randomButton.disabled = state.mode !== "class" || !names.length;
    renderRandom(); renderTimer(); scheduleDataRefresh();
  }
  function timerRemaining() {
    if (!state.timer.running) return state.timer.remainingMs;
    var remaining = Math.max(0, state.timer.remainingMs - (nowMs() - state.timer.startedAt));
    if (!remaining) { state.timer.remainingMs = 0; state.timer.running = false; }
    return remaining;
  }
  function setTimerMinutes(minutes) {
    state.timer.durationMs = Number(minutes) * 60 * 1000; state.timer.remainingMs = state.timer.durationMs; state.timer.running = false; renderTimer();
  }
  function startTimer() {
    if (timerRemaining() <= 0) state.timer.remainingMs = state.timer.durationMs;
    state.timer.startedAt = nowMs(); state.timer.running = true; renderTimer(); reconcileMotion();
  }
  function pauseTimer() { state.timer.remainingMs = timerRemaining(); state.timer.running = false; renderTimer(); }
  function resetTimer() { state.timer.running = false; state.timer.remainingMs = state.timer.durationMs; renderTimer(); }
  function renderRandom() {
    var target = byId("glass-random-result"); target.textContent = state.randomSelected || "—";
  }
  function chooseRandom() {
    var names = ((state.payload.classroom || {}).random_name || {}).names || [];
    if (!names.length) return;
    state.randomSelected = names[Math.floor(Math.random() * names.length)]; renderRandom(); openTool("random");
  }
  function openTool(tool) {
    if (tool === "blank") { closeTool(); byId("glass-blank-overlay").hidden = false; state.tool = "blank"; reconcileMotion(); return; }
    state.noteVisible = false;
    byId("glass-note-overlay").hidden = true;
    state.tool = tool; var overlay = byId("glass-tool-overlay"); overlay.hidden = false;
    Array.prototype.forEach.call(overlay.querySelectorAll("[data-panel]"), function (panel) { panel.hidden = panel.dataset.panel !== tool; });
    if (tool === "random") renderRandom(); if (tool === "timer") renderTimer(); if (tool === "note") byId("glass-note-input").value = state.note;
    var first = overlay.querySelector('[data-panel="' + tool + '"] button, [data-panel="' + tool + '"] textarea'); if (first) first.focus();
    reconcileMotion();
  }
  function closeTool() { state.tool = ""; state.noteVisible = false; byId("glass-tool-overlay").hidden = true; byId("glass-blank-overlay").hidden = true; byId("glass-note-overlay").hidden = true; reconcileMotion(); }
  function showNote() { state.note = byId("glass-note-input").value; if (!state.note.trim()) return; closeTool(); state.noteVisible = true; byId("glass-note-overlay-text").textContent = state.note; byId("glass-note-overlay").hidden = false; state.tool = "note-visible"; reconcileMotion(); }
  function hideNote() { state.noteVisible = false; byId("glass-note-overlay").hidden = true; if (state.tool === "note-visible") state.tool = ""; reconcileMotion(); }
  function isPaused() { return !!state.tool || document.hidden; }
  function reconcileMotion() {
    clearInterval(timers.rotation); timers.rotation = null;
    state.rotationColumns = state.columns.map(function (descriptors) { return descriptors.filter(function (item) { return item.eligible; }); }).filter(function (items) { return items.length > 1; });
    if (state.reducedMotion || isPaused() || !state.rotationColumns.length) return;
    timers.rotation = setInterval(autoAdvance, 8000);
  }
  function autoAdvance() {
    if (state.reducedMotion || isPaused() || nowMs() < state.manualUntil || !state.rotationColumns.length) return;
    var choices = state.rotationColumns; var group = choices[state.rotationIndex % choices.length]; state.rotationIndex += 1;
    var column = group[0].column; var current = state.expanded[column]; var index = group.findIndex(function (item) { return item.id === current; });
    index = (index + 1) % group.length; state.expanded[column] = group[index].id; renderColumns();
  }
  function selectCard(card) {
    if (card.dataset.eligible !== "true") return;
    state.expanded[card.dataset.column] = card.dataset.cardId; state.manualUntil = nowMs() + 20000; renderColumns();
  }
  function installTickers() {
    Array.prototype.forEach.call(document.querySelectorAll(".glass-ticker"), function (node) { node.classList.toggle("is-ticker", node.scrollWidth > node.clientWidth); });
  }
  function scheduleDataRefresh() {
    clearTimeout(timers.boundary); clearTimeout(timers.poll);
    var validUntil = Date.parse(((state.payload.context || {}).valid_until || ""));
    timers.boundary = setTimeout(reload, Math.max(250, validUntil - state.clockMs + 250));
    timers.poll = setTimeout(reload, 15 * 60 * 1000);
  }
  function reload() {
    var at = isNaN(state.clockMs) ? "" : new Date(state.clockMs).toISOString();
    fetch("/glass/data" + (at ? "?at=" + encodeURIComponent(at) : ""), {cache: "no-store"})
      .then(function (response) { if (!response.ok) throw new Error("Glass data unavailable"); return response.json(); })
      .then(render)
      .catch(function () { byId("glass-status").textContent = "SYNC REQUIRED · LOCAL SERVER UNAVAILABLE"; byId("glass-status").hidden = false; });
  }
  function tick() {
    if (!isNaN(state.clockMs)) { state.clockMs += 1000; byId("glass-clock").textContent = clockLabel(state.clockMs); renderClassTime(); }
    renderTimer();
  }
  function bindEvents() {
    byId("glass-content").addEventListener("click", function (event) { var card = event.target.closest(".glass-card"); if (card) selectCard(card); });
    byId("glass-content").addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { var card = event.target.closest(".glass-card"); if (card) { event.preventDefault(); selectCard(card); } } });
    document.querySelectorAll("[data-tool]").forEach(function (button) { button.addEventListener("click", function () { openTool(button.dataset.tool); }); });
    byId("glass-random-again").addEventListener("click", chooseRandom);
    document.querySelectorAll("[data-close-tool]").forEach(function (button) { button.addEventListener("click", closeTool); });
    document.querySelectorAll("[data-timer-minutes]").forEach(function (button) { button.addEventListener("click", function () { setTimerMinutes(button.dataset.timerMinutes); }); });
    byId("glass-timer-start").addEventListener("click", startTimer); byId("glass-timer-pause").addEventListener("click", pauseTimer); byId("glass-timer-reset").addEventListener("click", resetTimer);
    byId("glass-note-input").addEventListener("input", function () { state.note = byId("glass-note-input").value; });
    byId("glass-note-show").addEventListener("click", showNote); byId("glass-note-hide").addEventListener("click", hideNote);
    document.querySelector("[data-hide-note]").addEventListener("click", hideNote); document.querySelector("[data-close-blank]").addEventListener("click", closeTool);
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") { if (state.noteVisible) hideNote(); else closeTool(); } });
    document.addEventListener("visibilitychange", reconcileMotion);
    if (window.matchMedia) window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", function (event) { state.reducedMotion = event.matches; reconcileMotion(); });
  }
  bindEvents(); timers.tick = setInterval(tick, 1000); render(initial);
}());
