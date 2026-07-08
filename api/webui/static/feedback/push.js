(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};
  var esc = CE.esc || function (s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  };

  var pcCourse = document.getElementById("pc-course");
  var pcAssign = document.getElementById("pc-assignment");
  var pcJson = document.getElementById("pc-json");
  var pcPreview = document.getElementById("pc-preview");
  var pcStatus = document.getElementById("pc-status");
  var pcWrap = document.getElementById("pc-preview-wrap");
  var pcRows = document.getElementById("pc-rows");
  var pcVal = document.getElementById("pc-validation");

  function refreshBtn() {
    if (pcPreview) {
      pcPreview.disabled = !(pcCourse && pcAssign && pcCourse.value && pcAssign.value && pcJson && pcJson.value.trim());
    }
  }

  function loadAssignments(courseId) {
    if (!pcAssign) return;
    pcAssign.disabled = !courseId;
    pcAssign.innerHTML = courseId
      ? '<option value="">Loading…</option>'
      : '<option value="">— select course first —</option>';
    if (pcWrap) pcWrap.hidden = true;
    refreshBtn();
    if (!courseId) return;
    fetch("/api/assignments-full?course_id=" + encodeURIComponent(courseId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok || !d.assignments) {
          pcAssign.innerHTML = '<option value="">— failed —</option>';
          return;
        }
        pcAssign.innerHTML = '<option value="">— select an assignment —</option>' +
          d.assignments.filter(function (a) { return a.submission_types.indexOf("none") === -1; })
            .map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + "</option>"; }).join("");
      })
      .catch(function () {
        pcAssign.innerHTML = '<option value="">— error —</option>';
      });
  }

  function renderRows(rows) {
    pcRows._rows = rows;
    if (!rows.length) {
      pcRows.innerHTML = '<tr><td colspan="5" class="hint">No rows to post.</td></tr>';
      if (pcWrap) pcWrap.hidden = false;
      return;
    }
    pcRows.innerHTML = rows.map(function (r, i) {
      var disabled = !r.resolved;
      var checked = r.resolved && !r.already_graded;
      var cur = r.current_grade == null ? "—" : esc(String(r.current_grade));
      var sc = r.score == null ? "(comment only)" : esc(String(r.score));
      var nm = esc(r.real_name || "(unresolved)") +
        (r.already_graded ? ' <span class="muted" style="font-size:11px">already graded</span>' : "") +
        (!r.resolved ? ' <span style="color:#b3261e;font-size:11px">unresolved</span>' : "");
      var fb = r.feedback || "";
      return '<tr data-i="' + i + '">' +
        '<td><input type="checkbox" class="pc-pick"' + (checked ? " checked" : "") + (disabled ? " disabled" : "") + "></td>" +
        "<td>" + nm + "</td><td>" + cur + "</td><td>" + sc + "</td>" +
        '<td style="max-width:340px"><span title="' + esc(fb) + '">' + esc(fb.slice(0, 80)) + (fb.length > 80 ? "…" : "") + "</span></td>" +
        "</tr>";
    }).join("");
    if (pcWrap) pcWrap.hidden = false;
  }

  if (pcCourse && pcAssign && pcJson && pcPreview) {
    pcCourse.addEventListener("change", function () {
      loadAssignments(pcCourse.value);
    });
    pcAssign.addEventListener("change", function () {
      if (pcWrap) pcWrap.hidden = true;
      refreshBtn();
    });
    pcJson.addEventListener("input", refreshBtn);

    pcPreview.addEventListener("click", function () {
      if (pcStatus) pcStatus.textContent = "Validating…";
      if (pcVal) pcVal.hidden = true;
      if (pcWrap) pcWrap.hidden = true;
      fetch("/api/feedback/push/preview", {
        method: "POST",
        body: new URLSearchParams({
          course_id: pcCourse.value,
          assignment_id: pcAssign.value,
          results: pcJson.value,
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            if (pcStatus) pcStatus.textContent = d.error || "Failed.";
            var errs = (d.validation && d.validation.errors) || [];
            if (errs.length && pcVal) {
              pcVal.hidden = false;
              pcVal.innerHTML = '<strong style="color:#b3261e">Errors:</strong><br>' + errs.map(esc).join("<br>");
            }
            return;
          }
          if (pcStatus) pcStatus.textContent = "";
          var warns = (d.validation && d.validation.warnings) || [];
          if (warns.length && pcVal) {
            pcVal.hidden = false;
            pcVal.innerHTML = '<strong style="color:#9a6700">Warnings (not blocking):</strong><br>' + warns.map(esc).join("<br>");
          }
          renderRows(d.rows || []);
        })
        .catch(function (e) {
          if (pcStatus) pcStatus.textContent = "Error: " + e;
        });
    });
  }

  var allCheck = document.getElementById("pc-all");
  if (allCheck && pcRows) {
    allCheck.addEventListener("change", function () {
      var on = this.checked;
      pcRows.querySelectorAll(".pc-pick").forEach(function (cb) {
        if (!cb.disabled) cb.checked = on;
      });
    });
  }

  var applyBtn = document.getElementById("pc-apply");
  if (applyBtn && pcRows && pcCourse && pcAssign) {
    applyBtn.addEventListener("click", function () {
      var rows = pcRows._rows || [];
      var selected = [];
      pcRows.querySelectorAll("tr").forEach(function (tr) {
        var cb = tr.querySelector(".pc-pick");
        if (cb && cb.checked) {
          var r = rows[parseInt(tr.dataset.i, 10)];
          if (r) {
            selected.push({ canvas_id: r.canvas_id, score: r.score, feedback: r.feedback });
          }
        }
      });
      var st = document.getElementById("pc-apply-status");
      if (!selected.length) {
        if (st) st.textContent = "Nothing selected.";
        return;
      }
      if (!confirm("Post " + selected.length + " grade(s) + comment(s) to Canvas?\n\nThis changes real grades and notifies students.")) return;
      var btn = this;
      btn.disabled = true;
      if (st) st.textContent = "Posting…";
      fetch("/api/feedback/push/apply", {
        method: "POST",
        body: new URLSearchParams({
          course_id: pcCourse.value,
          assignment_id: pcAssign.value,
          rows: JSON.stringify(selected),
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (st) {
            st.textContent = d.ok
              ? ("Posted " + d.posted + " of " + d.total + (d.errors && d.errors.length ? (" · " + d.errors.length + " error(s)") : ""))
              : (d.error || "Failed.");
          }
        })
        .catch(function (e) {
          if (st) st.textContent = "Error: " + e;
        })
        .finally(function () {
          btn.disabled = false;
      });
    });
  }

  if (pcCourse.value) {
    loadAssignments(pcCourse.value);
  }
  refreshBtn();

  CE.renderPushRows = CE.renderPushRows || renderRows;
})();
