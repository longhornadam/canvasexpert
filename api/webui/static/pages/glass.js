(function () {
  "use strict";

  var initial = window.GLASS_INITIAL || {};
  var frame = { payload: initial, clockMs: Date.parse((initial.context || {}).at || "") };
  var timers = { tick: null, boundary: null, poll: null };
  var timeZone = "America/Chicago";

  function byId(id) { return document.getElementById(id); }
  function text(value) { return value == null ? "" : String(value); }
  function dateLabel(value, options) {
    var parsed = new Date(value + "T12:00:00Z");
    if (isNaN(parsed.getTime())) return text(value);
    return new Intl.DateTimeFormat("en-US", Object.assign({timeZone: timeZone}, options || {})).format(parsed);
  }
  function clockLabel(ms) {
    return new Intl.DateTimeFormat("en-US", {timeZone: timeZone, hour: "numeric", minute: "2-digit"}).format(new Date(ms));
  }
  function itemNode(item, kind) {
    var row = document.createElement("div"); row.className = "glass-item";
    var marker = document.createElement("span"); marker.className = "glass-item__" + (kind || "date");
    marker.textContent = text(item.date || item.slot || item.kind).replaceAll("_", " ");
    var stack = document.createElement("div");
    var title = document.createElement("div"); title.className = "glass-item__title"; title.textContent = text(item.label || item.name || "Calendar item");
    var detail = document.createElement("div"); detail.className = "glass-item__detail";
    var detailParts = [];
    if (item.from && item.to) detailParts.push(item.from + "–" + item.to);
    if (item.detail) detailParts.push(item.detail);
    if (item.result) detailParts.push(item.result);
    if (item.slot && kind !== "slot") detailParts.push(item.slot);
    detail.textContent = detailParts.join(" · ");
    stack.appendChild(title); if (detail.textContent) stack.appendChild(detail);
    row.appendChild(marker); row.appendChild(stack); return row;
  }
  function list(id, items, kind, empty) {
    var target = byId(id); target.replaceChildren();
    if (!items || !items.length) { var blank = document.createElement("div"); blank.className = "glass-empty"; blank.textContent = empty; target.appendChild(blank); return; }
    items.forEach(function (item) { target.appendChild(itemNode(item, kind)); });
  }
  function renderGrading(period) {
    var target = byId("glass-grading"); target.replaceChildren();
    if (!period || period.state !== "ready") { var blank = document.createElement("div"); blank.className = "glass-empty"; blank.textContent = "No active grading period."; target.appendChild(blank); return; }
    var card = document.createElement("div"); card.className = "glass-grading-card";
    var name = document.createElement("div"); name.className = "glass-grading-card__name"; name.textContent = period.name;
    var days = document.createElement("div"); days.className = "glass-grading-card__days"; days.textContent = period.days_remaining + " days remaining";
    var range = document.createElement("div"); range.className = "glass-grading-card__range"; range.textContent = period.start + " – " + period.end;
    card.appendChild(name); card.appendChild(days); card.appendChild(range); target.appendChild(card);
  }
  function render(payload) {
    frame.payload = payload || {}; var context = frame.payload.context || {}; var board = frame.payload.board || {};
    frame.clockMs = Date.parse(context.at || "");
    if (isNaN(frame.clockMs)) frame.clockMs = 0;
    byId("glass-date").textContent = dateLabel(context.date || "", {weekday: "long", month: "long", day: "numeric"});
    byId("glass-schedule").textContent = board.schedule_label || (context.state === "no_school" ? "No school" : "");
    byId("glass-clock").textContent = clockLabel(frame.clockMs);
    byId("glass-simulated").hidden = !context.simulated;
    var status = byId("glass-status"); status.textContent = board.message || ""; status.hidden = !board.message;
    var today = board.today_events || []; byId("glass-today-count").textContent = today.length ? today.length + " items" : "";
    list("glass-today", today, "date", "Nothing scheduled today.");
    list("glass-upcoming", board.forward_events || [], "date", "No upcoming events.");
    list("glass-academic", board.academic_dates || [], "date", "No academic dates in the window.");
    list("glass-sports", board.sports_results || [], "date", "No recent results.");
    var bobcat = board.bobcat || {}; byId("glass-bobcat-state").textContent = bobcat.current_block || "";
    list("glass-bobcat", bobcat.activities || [], "slot", bobcat.state === "not_bobcat_hour" ? "Not a Bobcat Hour day." : "No clubs or tutorials.");
    renderGrading(board.grading_period);
    scheduleTimers();
  }
  function tick() { if (!isNaN(frame.clockMs)) byId("glass-clock").textContent = clockLabel(frame.clockMs += 1000); }
  function reload() {
    var at = isNaN(frame.clockMs) ? "" : new Date(frame.clockMs).toISOString();
    fetch("/glass/data" + (at ? "?at=" + encodeURIComponent(at) : ""), {cache: "no-store"})
      .then(function (response) { return response.json(); }).then(render).catch(function () { byId("glass-status").textContent = "Glass is waiting for the local server."; byId("glass-status").hidden = false; });
  }
  function scheduleTimers() {
    clearTimeout(timers.boundary); clearTimeout(timers.poll);
    var validUntil = Date.parse(((frame.payload.context || {}).valid_until || ""));
    timers.boundary = setTimeout(reload, Math.max(250, validUntil - frame.clockMs + 250));
    timers.poll = setTimeout(reload, 15 * 60 * 1000);
  }
  timers.tick = setInterval(tick, 1000);
  render(initial);
}());
