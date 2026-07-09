(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "showLog", "showBanner", "hideBanner", "esc",
               "gbCourseId", "gbCourseName", "_markLoaded", "_clearLoaded",
               "_clearStatus", "gbTargets", "canvasWriteReview", "curveResults"]
    .every(function (name) {
      if (name === "curveResults") return typeof Object.getOwnPropertyDescriptor(gb, "curveResults") !== "undefined";
      return typeof gb[name] === "function";
    });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // ── Curves (auto-loaded on tab activate) ──────────────────────────────

  window.CE_GRADEBOOK.loadCurveAssignments = async function _loadCurveAssignments() {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return;
    gb._markLoaded("curves");
    var hint = document.getElementById("cv-assign-hint");
    if (hint) hint.textContent = "loading\u2026";
    var btn = document.getElementById("btn-curve-load");
    if (btn) btn.disabled = true;
    try {
      var d = await fetch("/api/curve/assignments?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
      var sel = document.getElementById("cv-assignment");
      if (sel) {
        sel.innerHTML = '<option value="">\u2014 select assignment \u2014</option>';
        (d.assignments || []).forEach(function (a) {
          var opt = document.createElement("option");
          opt.value = a.id;
          opt.textContent = a.name + (a.due_at ? "  (" + a.due_at + ")" : "") + "  [" + a.points + " pts]";
          sel.appendChild(opt);
        });
        sel.disabled = false;
      }
      if (hint) hint.textContent = (d.assignments || []).length + " assignments";
    } catch (e) {
      if (hint) hint.textContent = "error loading";
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  document.getElementById("btn-curve-load")?.addEventListener("click", function () {
    gb._clearLoaded("curves");
    window.CE_GRADEBOOK.loadCurveAssignments();
  });

  function syncCurveSettings() {
    var model = document.getElementById("cv-model")?.value || "flat_bump";
    ["flat_bump", "target_average", "proportional", "floor_cap"].forEach(function (m) {
      var el = document.getElementById("cv-settings-" + m);
      if (el) el.style.display = (m === model) ? "" : "none";
    });
  }
  document.getElementById("cv-model")?.addEventListener("change", syncCurveSettings);
  syncCurveSettings();

  function curveSettings() {
    var model = document.getElementById("cv-model")?.value || "flat_bump";
    if (model === "flat_bump") return {
      bump:       parseFloat(document.getElementById("cv-bump").value) || 0,
      cap:        document.getElementById("cv-bump-cap").value || null,
      do_no_harm: document.getElementById("cv-bump-donh").checked,
    };
    if (model === "target_average") return {
      target_avg_pct: parseFloat(document.getElementById("cv-target-avg-pct").value) || 75,
      cap:            document.getElementById("cv-target-cap").value || null,
      do_no_harm:     document.getElementById("cv-target-donh").checked,
    };
    if (model === "proportional") return {
      target_avg_pct: parseFloat(document.getElementById("cv-prop-avg-pct").value) || 75,
      cap:            document.getElementById("cv-prop-cap").value || null,
      do_no_harm:     document.getElementById("cv-prop-donh").checked,
    };
    if (model === "floor_cap") return {
      floor: parseFloat(document.getElementById("cv-floor").value) || 0,
      cap:   document.getElementById("cv-cap").value || null,
    };
    return {};
  }

  function updateCurveApplyBtn() {
    var n   = document.querySelectorAll(".cv-cb:checked").length;
    var btn = document.getElementById("btn-curve-apply");
    if (!btn) return;
    btn.hidden = n === 0;
    btn.textContent = "Apply curve to " + n + " student" + (n === 1 ? "" : "s") + "\u2026";
  }

  document.getElementById("btn-curve-preview")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id  = gb.gbCourseId();
    var aid = document.getElementById("cv-assignment")?.value;
    if (!id)  return alert("Pick a course first.");
    if (!aid) return alert("Select an assignment first.");
    var model = document.getElementById("cv-model")?.value || "flat_bump";
    var st = document.getElementById("cv-status");
    st.className = "status hint";
    st.textContent = "Loading submissions and computing curve\u2026";
    this.disabled = true;
    document.getElementById("cv-preview-wrap").hidden = true;
    gb.hideBanner(document.getElementById("cv-banner"));
    try {
      var d = await gb.postForm("/api/curve/preview", {
        course_id:     id,
        assignment_id: aid,
        curve_type:    model,
        settings:      JSON.stringify(curveSettings()),
      });
      if (!d.ok) { st.className = "status error"; st.textContent = "Error: " + d.error; return; }
      gb.curveResults = d.results || [];
      if (!gb.curveResults.length) {
        st.className = "status ok";
        st.textContent = "No graded submissions found for this assignment.";
        updateCurveApplyBtn();
        return;
      }
      var sm = d.summary || {};
      var ungraded = sm.ungraded ? " \u00B7 " + sm.ungraded + " submitted but not yet graded" : "";
      document.getElementById("cv-summary").innerHTML =
        "<strong>" + gb.esc(sm.assignment_name) + "</strong> \u00B7 " + sm.n + " graded \u00B7 " +
        "Avg: <strong>" + (sm.original_avg ?? "\u2014") + "</strong> \u2192 <strong>" + (sm.curved_avg ?? "\u2014") + "</strong> " +
        "(out of " + sm.points + ") \u00B7 " +
        '<span style="color:var(--forge-green)">' + sm.helped + " helped</span>" +
        (sm.lowered ? ' \u00B7 <span style="color:var(--danger)">' + sm.lowered + " lowered</span>" : "") +
        " \u00B7 " + sm.unchanged + " unchanged" + ungraded;
      var tbody = document.getElementById("cv-tbody");
      tbody.innerHTML = "";
      gb.curveResults.forEach(function (r, i) {
        var diff = r.curved_score - r.original_score;
        var sign = diff > 0 ? "+" : (diff < 0 ? "" : "\u00B1");
        var cls  = diff > 0 ? 'style="color:var(--forge-green)"'
                   : diff < 0 ? 'class="gb-bad"' : 'class="muted"';
        var tr = document.createElement("tr");
        tr.innerHTML =
          '<td><input type="checkbox" class="cv-cb" data-i="' + i + '" checked></td>' +
          '<td>' + gb.esc(r.student_name) + '</td>' +
          '<td class="muted">' + r.original_score + '</td>' +
          '<td><strong>' + r.curved_score + '</strong></td>' +
          '<td ' + cls + '>' + sign + Math.round(Math.abs(diff) * 100) / 100 + '</td>';
        tbody.appendChild(tr);
      });
      document.getElementById("cv-check-all").checked = true;
      document.getElementById("cv-preview-wrap").hidden = false;
      updateCurveApplyBtn();
      st.textContent = "Preview ready \u2014 uncheck students you want to skip. No changes yet.";
    } finally { this.disabled = false; }
  });

  document.getElementById("cv-check-all")?.addEventListener("change", function () {
    var checked = this.checked;
    document.querySelectorAll(".cv-cb").forEach(function (cb) { cb.checked = checked; });
    updateCurveApplyBtn();
  });
  document.getElementById("cv-tbody")?.addEventListener("change", function (e) {
    if (e.target.classList.contains("cv-cb")) updateCurveApplyBtn();
  });

  document.getElementById("btn-curve-apply")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id  = gb.gbCourseId();
    var aid = document.getElementById("cv-assignment")?.value;
    var rows = Array.from(document.querySelectorAll(".cv-cb:checked"))
      .map(function (cb) { return gb.curveResults[+cb.dataset.i]; }).filter(Boolean);
    if (!rows.length) return;
    var model   = document.getElementById("cv-model")?.value || "flat_bump";
    var helped  = rows.filter(function (r) { return r.curved_score > r.original_score; }).length;
    var lowered = rows.filter(function (r) { return r.curved_score < r.original_score; }).length;
    var aText = document.getElementById("cv-assignment")?.selectedOptions[0]?.text || "Selected assignment";
    var ok = await gb.canvasWriteReview({
      title: "Review curve score write",
      action: "Apply a " + model.replace(/_/g, " ") + " curve to selected submissions.",
      targets: typeof gb.gbTargets === "function" ? gb.gbTargets() : [{ id: id, name: gb.gbCourseName() }],
      details: [
        "Assignment: " + aText,
        rows.length + " selected student score(s)",
        helped + " score(s) will go up" + (lowered ? "; " + lowered + " will go down" : "; none will go down"),
      ],
      warnings: [
        "This writes real scores to Canvas.",
        "Canvas may notify students of grade changes depending on course settings.",
        "A local revert event is saved for this curve apply.",
      ],
      confirmText: "Apply curve scores",
    });
    if (!ok) return;
    var log = gb.showLog(document.getElementById("cv-log"));
    gb.hideBanner(document.getElementById("cv-banner"));
    this.disabled = true;
    log("Applying " + rows.length + " curved score(s)\u2026\n");
    try {
      var d = await gb.postForm("/api/curve/apply", {
        course_id:     id,
        assignment_id: aid,
        curve_type:    model,
        settings:      JSON.stringify(curveSettings()),
        results:       JSON.stringify(rows),
      });
      if (d.error && !d.results) {
        log("ERROR: " + d.error);
        gb.showBanner(document.getElementById("cv-banner"), "fail", "\u2717 " + gb.esc(d.error));
        return;
      }
      (d.results || []).forEach(function (r) {
        log((r.ok ? "\u2713" : "\u2717") + " " + r.student + ": " + r.original + " \u2192 " + r.curved +
        (r.ok ? "" : "  (" + r.error + ")"));
      });
      var okCount = (d.results || []).filter(function (r) { return r.ok; }).length;
      gb.showBanner(document.getElementById("cv-banner"), d.ok ? "ok" : "warn",
        (d.ok ? "\u2713" : "\u26A0") + " " + okCount + "/" + rows.length + " score(s) curved. " +
        "Event " + d.event_id + " saved \u2014 use \"Curve history\" below to revert.");
      document.getElementById("cv-preview-wrap").hidden = true;
      gb.curveResults = [];
      updateCurveApplyBtn();
    } finally { this.disabled = false; }
  });

  document.getElementById("btn-curve-events")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var id  = gb.gbCourseId();
    var aid = document.getElementById("cv-assignment")?.value;
    if (!id) return alert("Pick a course first.");
    var es   = document.getElementById("cv-events-status");
    var list = document.getElementById("cv-events-list");
    es.className = "status hint";
    es.textContent = "Loading\u2026";
    list.innerHTML = "";
    try {
      var url = "/api/curve/events?course_id=" + encodeURIComponent(id) +
        (aid ? "&assignment_id=" + encodeURIComponent(aid) : "");
      var d = await fetch(url).then(function (r) { return r.json(); });
      if (!d.ok) { es.className = "status error"; es.textContent = "Error: " + d.error; return; }
      var events = d.events || [];
      if (!events.length) {
        es.textContent = aid ? "No curve events for this assignment." : "No curve events for this course.";
        return;
      }
      es.textContent = "";
      events.forEach(function (ev) {
        var row = document.createElement("div");
        row.style.cssText = "display:flex; align-items:baseline; gap:12px; padding:8px 0; border-bottom:1px solid var(--line); font-size:13.5px";
        var applied    = ev.applied_at ? ev.applied_at.replace("T", " ") : "";
        var modelLabel = ev.curve_type ? ev.curve_type.replace(/_/g, " ") : "";
        row.innerHTML =
          '<span style="flex:1"><strong>' + gb.esc(ev.assignment_name) + '</strong> \u2014 ' + gb.esc(modelLabel) + '</span>' +
          '<span class="muted" style="font-size:12px">' + gb.esc(applied) + '</span>' +
          '<button class="small cv-revert-btn" data-event-id="' + gb.esc(ev.id) + '" data-course="' + gb.esc(id) + '">Revert\u2026</button>';
        list.appendChild(row);
      });
    } catch (e) { es.className = "status error"; es.textContent = String(e); }
  });

  document.getElementById("cv-events-list")?.addEventListener("click", async function (e) {
    if (!requireReady()) return;
    var btn = e.target.closest(".cv-revert-btn");
    if (!btn) return;
    var eventId  = btn.dataset.eventId;
    var courseId = btn.dataset.course;
    var label = btn.closest("div")?.querySelector("strong")?.textContent || "Selected curve event";
    var ok = await gb.canvasWriteReview({
      title: "Review curve revert",
      action: "Revert this curve event for all students included in the event.",
      targets: [{ id: courseId, name: gb.gbCourseName() || "Selected course" }],
      details: [
        "Assignment/event: " + label,
        "Event ID: " + eventId,
      ],
      warnings: [
        "This writes original scores back to Canvas.",
        "Scores changed since the curve may be flagged after the write and should be checked manually.",
        "Canvas may notify students of grade changes depending on course settings.",
      ],
      confirmText: "Revert Canvas scores",
    });
    if (!ok) return;
    btn.disabled = true;
    var es = document.getElementById("cv-events-status");
    es.className = "status hint";
    es.textContent = "Reverting\u2026";
    try {
      var d = await gb.postForm("/api/curve/revert", { event_id: eventId, course_id: courseId });
      if (d.error && !d.results) { es.className = "status error"; es.textContent = "Error: " + d.error; return; }
      var okCount = (d.results || []).filter(function (r) { return r.ok; }).length;
      var drifted = (d.results || []).filter(function (r) { return r.warned_drift; }).length;
      es.className   = d.ok ? "status ok" : "status error";
      es.textContent = (d.ok ? "\u2713" : "\u26A0") + " " + okCount + "/" + (d.results || []).length + " score(s) reverted" +
        (drifted ? " \u00B7 " + drifted + " had changed since the curve \u2014 check manually" : "");
      btn.closest("div").remove();
    } finally { btn.disabled = false; }
  });

})();
