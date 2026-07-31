(function () {
  "use strict";

  var CE = window.CE_SETTINGS || {};

  var calOpStatus = document.getElementById("cal-op-status");
  var calCustomStatus = document.getElementById("cal-custom-status");
  var aiTaLoad = CE.loadAiTaFiles;
  var parsedCalDates = null;
  var parsedCalPeriods = null;
  var parsedCalSource = null;
  var noSchoolTypes = new Set(["holiday", "no school for students", "holiday for students/teachers"]);

  function setCalStatus(el, msg, kind) {
    CE.setStatus(el, msg, kind);
  }

  function renderCalendars(calendars) {
    var list = document.getElementById("cal-list");
    if (!list) return;
    var entries = Object.entries(calendars || {});
    if (!entries.length) {
      list.innerHTML = '<div class="callout warn" id="cal-none-callout">No academic calendar configured - only weekends are skipped by default.</div>';
      return;
    }
    list.innerHTML = entries.map(function (_ref) {
      var key = _ref[0];
      var cal = _ref[1];
      var days = (cal.no_count_dates || []).length;
      var periods = (cal.grading_periods || []).length;
      return '<div class="cal-row" data-cal-key="' + CE.esc(key) + '">' +
        '<div><strong>' + CE.esc(cal.label) + '</strong>' +
        '<span class="muted" style="font-size:12.5px;margin-left:8px">' +
        days + ' day(s) off · ' + periods + ' grading period(s)</span></div>' +
        '<button class="danger small cal-remove-btn" data-cal-key="' + CE.esc(key) + '">Remove</button>' +
        '</div>';
    }).join("");
  }

  function parseDate(s) {
    if (aiTaLoad) aiTaLoad();
    s = (s || "").trim();
    var m1 = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m1) return m1[3] + "-" + m1[1].padStart(2, "0") + "-" + m1[2].padStart(2, "0");
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    return null;
  }

  function expandRange(start, end) {
    var dates = [];
    var s = new Date(start + "T12:00:00");
    var e = new Date(end + "T12:00:00");
    if (isNaN(s) || isNaN(e)) return dates;
    for (var d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) {
      dates.push(d.toISOString().slice(0, 10));
    }
    return dates;
  }

  async function loadCalendarFile(name, label, btn) {
    if (btn) btn.disabled = true;
    setCalStatus(calOpStatus, "Loading " + label + "…", "");
    try {
      var fd = new FormData();
      fd.append("name", name);
      var d = await fetch("/api/calendar/load-builtin", { method: "POST", body: fd }).then(function (r) { return r.json(); });
      if (d.ok) {
        var note = (d.grading_periods || []).length ? " · " + d.grading_periods.length + " grading period(s)" : "";
        setCalStatus(calOpStatus, "✓ Loaded " + d.count + " day(s) off" + note + " - " + d.label, "ok");
        var cd = await fetch("/api/calendar").then(function (r) { return r.json(); });
        if (cd.ok) renderCalendars(cd.calendars);
      } else {
        setCalStatus(calOpStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.getElementById("cal-builtin-actions")?.addEventListener("click", function (e) {
    var btn = e.target.closest(".cal-load-btn");
    if (!btn) return;
    loadCalendarFile(btn.dataset.calFile, btn.textContent.replace(/^Load\s+/, ""), btn);
  });

  document.getElementById("cal-list")?.addEventListener("click", async function (e) {
    var btn = e.target.closest(".cal-remove-btn");
    if (!btn) return;
    var key = btn.dataset.calKey;
    if (!confirm('Remove "' + key + '" from your active calendars?')) return;
    btn.disabled = true;
    try {
      var fd = new FormData();
      fd.append("source", key);
      var d = await fetch("/api/calendar/clear", { method: "POST", body: fd }).then(function (r) { return r.json(); });
      if (d.ok) {
        setCalStatus(calOpStatus, "Calendar removed.", "ok");
        var cd = await fetch("/api/calendar").then(function (r) { return r.json(); });
        if (cd.ok) renderCalendars(cd.calendars);
      } else {
        btn.disabled = false;
        setCalStatus(calOpStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } catch (err) {
      btn.disabled = false;
    }
  });

  document.getElementById("btn-cal-parse")?.addEventListener("click", function () {
    var raw = document.getElementById("cal-csv-input")?.value || "";
    var lines = raw.split(/\r?\n/).filter(Boolean);
    var preview = document.getElementById("cal-parse-preview");
    var saveBtn = document.getElementById("btn-cal-save");
    parsedCalDates = null;
    parsedCalPeriods = null;
    parsedCalSource = null;
    if (saveBtn) saveBtn.hidden = true;
    if (preview) preview.hidden = true;
    setCalStatus(calCustomStatus, "", "");

    if (!lines.length) {
      setCalStatus(calCustomStatus, "Paste some CSV content first.", "error");
      return;
    }

    var canonical = lines[0].toLowerCase().includes("row_type") && lines[0].toLowerCase().includes("start_date");
    var allDates = [];
    var dayOffRows = [];
    var periodRows = [];

    for (var i = 1; i < lines.length; i++) {
      var parts = lines[i].split(",").map(function (s) { return s.trim().replace(/^["']|["']$/g, ""); });
      if (canonical) {
        if (parts.length < 6) continue;
        var rowType = (parts[1] || "").toLowerCase();
        var code = parts[2] || "";
        var name = parts[3] || "";
        var s = parseDate(parts[4]);
        var e = parseDate(parts[5]);
        if (!s || !e) continue;
        if (noSchoolTypes.has(rowType)) {
          var expanded = expandRange(s, e);
          allDates.push.apply(allDates, expanded);
          dayOffRows.push({ name: name || parts[1], start: s, end: e, count: expanded.length });
        } else if (rowType === "academic period") {
          periodRows.push({ name: name, code: code, start: s, end: e });
        }
      } else {
        if (parts.length < 4) continue;
        var cat = parts[0];
        var _name = parts[1];
        var startDate = parts[2];
        var endDate = parts[3];
        var catLow = cat.toLowerCase();
        var _s = parseDate(startDate);
        var _e = parseDate(endDate);
        if (!_s || !_e) continue;
        if (catLow.includes("student day off") || catLow.includes("no school")) {
          var _expanded = expandRange(_s, _e);
          allDates.push.apply(allDates, _expanded);
          dayOffRows.push({ name: _name, start: _s, end: _e, count: _expanded.length });
        } else if (catLow.includes("academic period")) {
          periodRows.push({ name: _name, code: "", start: _s, end: _e });
        }
      }
    }

    if (!dayOffRows.length && !periodRows.length) {
      var hint = canonical
        ? 'No "Holiday", "No School for Students", or "Academic Period" rows found. Check row_type column spelling.'
        : 'No "Student Day Off" or "Academic Period" rows found. Check Category column spelling.';
      setCalStatus(calCustomStatus, hint, "error");
      return;
    }

    var uniq = Array.from(new Set(allDates)).sort();
    parsedCalDates = uniq;
    parsedCalPeriods = periodRows;
    parsedCalSource = "Custom CSV";

    var dayHtml = dayOffRows.map(function (r) {
      return '<div style="padding:3px 0; border-bottom:1px solid var(--ce-rule)">' +
        '<strong>' + CE.esc(r.name) + '</strong> - ' + CE.esc(r.start) + ' to ' + CE.esc(r.end) + ' ' +
        '<span class="muted">(' + r.count + ' day' + (r.count === 1 ? "" : "s") + ')</span></div>';
    }).join("");
    var perHtml = periodRows.length
      ? '<div style="margin-top:10px"><strong>' + periodRows.length + ' grading period(s):</strong>' +
        periodRows.map(function (r) {
          return '<div style="padding:3px 0; border-bottom:1px solid var(--ce-rule)">' +
            '<strong>' + CE.esc(r.name) + '</strong> - ' + CE.esc(r.start) + ' to ' + CE.esc(r.end) + '</div>';
        }).join("") + "</div>"
      : "";
    if (preview) {
      preview.innerHTML =
        '<strong>' + uniq.length + ' holiday date(s) across ' + dayOffRows.length + ' break(s):</strong>' +
        '<div style="margin-top:8px">' + dayHtml + "</div>" + perHtml;
      preview.hidden = false;
    }
    if (saveBtn) saveBtn.hidden = false;
    var pNote = periodRows.length ? " · " + periodRows.length + " grading period(s)" : "";
    setCalStatus(calCustomStatus, "Parsed: " + uniq.length + " no-count date(s)" + pNote + ". Save to activate.", "ok");
  });

  document.getElementById("btn-cal-save")?.addEventListener("click", async function () {
    if (!parsedCalDates || !parsedCalDates.length) return;
    var btn = this;
    btn.disabled = true;
    setCalStatus(calCustomStatus, "Saving…", "");
    try {
      var d = await fetch("/api/calendar/set", {
        method: "POST",
        body: new URLSearchParams({
          source: parsedCalSource || "Custom CSV",
          dates: JSON.stringify(parsedCalDates),
          grading_periods: JSON.stringify(parsedCalPeriods || []),
        }),
      }).then(function (r) { return r.json(); });
      if (d.ok) {
        var pNote = parsedCalPeriods && parsedCalPeriods.length ? " · " + parsedCalPeriods.length + " grading period(s)" : "";
        setCalStatus(calCustomStatus, "✓ Saved " + parsedCalDates.length + " date(s)" + pNote + ".", "ok");
        var cd = await fetch("/api/calendar").then(function (r) { return r.json(); });
        if (cd.ok) renderCalendars(cd.calendars);
        setCalStatus(calOpStatus, "", "");
      } else {
        setCalStatus(calCustomStatus, "Error: " + (d.error || "unknown"), "error");
      }
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("btn-copy-llm-prompt")?.addEventListener("click", async function () {
    var text = document.getElementById("llm-prompt-text")?.value || "";
    try {
      await navigator.clipboard.writeText(text);
      var orig = this.textContent;
      this.textContent = "Copied!";
      setTimeout(function () { this.textContent = orig; }.bind(this), 1800);
    } catch {
      document.getElementById("llm-prompt-text")?.select();
    }
  });
})();
