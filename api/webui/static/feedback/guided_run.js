(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};
  var esc = CE.esc || function (s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  };
  var courseSel = document.getElementById("gf-course");
  var assignSel = document.getElementById("gf-assignment");
  var gfGo = document.getElementById("gf-go");

  function loadAssignments(courseId) {
    if (!assignSel) return;
    assignSel.disabled = !courseId;
    assignSel.innerHTML = courseId
      ? '<option value="">Loading assignments…</option>'
      : '<option value="">— select course first —</option>';
    if (gfGo) gfGo.disabled = true;
    if (!courseId) return;
    fetch("/api/assignments-full?course_id=" + encodeURIComponent(courseId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok || !d.assignments) {
          assignSel.innerHTML = '<option value="">— failed to load —</option>';
          return;
        }
        assignSel.innerHTML = '<option value="">— select an assignment —</option>' +
          d.assignments
            .filter(function (a) { return a.submission_types.indexOf("none") === -1; })
            .map(function (a) {
              var label = a.name + (a.due_at ? " (due " + a.due_at + ")" : "");
              return '<option value="' + a.id + '">' + esc(label) + "</option>";
            }).join("");
      })
      .catch(function () {
        assignSel.innerHTML = '<option value="">— error loading —</option>';
      });
  }

  function loadPatterns() {
    fetch("/api/feedback/patterns")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var sel = document.getElementById("gf-pattern");
        if (!sel) return;
        sel.innerHTML = (d.patterns || []).map(function (p) {
          return '<option value="' + esc(p.id) + '">' + esc(p.name) + "</option>";
        }).join("");
      })
      .catch(function () {});
  }

  if (courseSel && assignSel) {
    courseSel.addEventListener("change", function () {
      loadAssignments(courseSel.value);
    });
    assignSel.addEventListener("change", function () {
      if (gfGo) gfGo.disabled = !(courseSel.value && assignSel.value);
    });
  }

  function showGuidedError(status, message) {
    if (status) status.textContent = message || "Error — see log above.";
  }

  if (gfGo) {
    gfGo.addEventListener("click", function () {
      var btn = this;
      var logEl = document.getElementById("gf-log");
      var wrap = document.getElementById("gf-progress-wrap");
      var fill = document.getElementById("gf-progress-fill");
      var resultActions = document.getElementById("gf-result-actions");
      var status = document.getElementById("gf-status");
      var rubricEl = document.getElementById("gf-rubric");
      var patternEl = document.getElementById("gf-pattern");
      var personaEl = document.getElementById("gf-persona");

      btn.disabled = true;
      if (status) status.textContent = "";
      if (wrap) wrap.hidden = false;
      if (resultActions) resultActions.hidden = true;
      if (logEl) {
        logEl.textContent = "Preparing — fetching submissions, pseudonymizing, safety-checking…";
        logEl.hidden = false;
      }
      if (fill) fill.style.width = "10%";

      function fail(msg) {
        showGuidedError(status, msg);
        btn.disabled = false;
      }

      var prep = new URLSearchParams({
        course_id: courseSel ? courseSel.value : "",
        assignment_id: assignSel ? assignSel.value : "",
        rubric_name: rubricEl ? rubricEl.value : "",
      });

      fetch("/api/feedback/run/prepare?" + prep.toString())
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            var extra = (d.hard && d.hard.length) ? ("\n⛔ " + d.hard.join("\n⛔ ")) : "";
            if (logEl) logEl.textContent = (d.error || "Prepare failed.") + extra;
            if (fill) fill.style.width = "100%";
            return fail(d.green === false ? "Blocked by PII safety gate." : "Couldn't prepare.");
          }
          if (fill) fill.style.width = "30%";
          var soft = (d.soft && d.soft.length)
            ? "\n⚠ " + d.soft.length + " possible name(s) in student text — review the output."
            : "";
          var att = (d.attachment_only && d.attachment_only.length)
            ? "\n📎 " + d.attachment_only.length + " student(s) uploaded non-text files (images/PDF) — score those manually."
            : "";
          if (logEl) {
            logEl.textContent = "SAFE bundle ready: " + d.students + " student(s) for '" +
              d.assignment_name + "'." + soft + att;
          }

          if (!d.has_key) {
            if (fill) fill.style.width = "100%";
            if (status) {
              status.textContent = "✓ SAFE bundle ready — open the SAFE folder, score it in your LLM, then paste results into Push to Canvas below.";
            }
            if (resultActions) resultActions.hidden = false;
            btn.disabled = false;
            return;
          }

          if (d.budget && d.budget.ok === false) {
            var reasons = (d.budget.reasons || []).join("; ");
            if (status) {
              status.textContent = "SAFE bundle ready, but paid scoring is blocked by the cost guard: " + reasons;
            }
            if (resultActions) resultActions.hidden = false;
            btn.disabled = false;
            return;
          }

          var estimate = d.budget && d.budget.estimated_cost != null
            ? ("\nEstimated total cost: $" + Number(d.budget.estimated_cost).toFixed(2))
            : "\nEstimated total cost: unavailable";
          if (!confirm("Model: " + (d.model || "unknown") +
                       "\n~" + d.tokens + " input tokens estimated for " + d.students +
                       " student(s)." + estimate +
                       "\n\nThis will call the paid OpenRouter API. Continue?")) {
            if (status) {
              status.textContent = "Cancelled — SAFE bundle is still saved; open the SAFE folder to use it manually.";
            }
            if (resultActions) resultActions.hidden = false;
            btn.disabled = false;
            return;
          }

          var params = new URLSearchParams({
            bundle_name: d.bundle_name,
            persona_id: personaEl ? personaEl.value : "sage",
            rubric_name: rubricEl ? rubricEl.value : "",
            pattern_id: patternEl ? patternEl.value : "basic",
          });
          var evtSource = new EventSource("/api/feedback/run/stream?" + params.toString());
          var lines = [];
          evtSource.onmessage = function (ev) {
            var line;
            try { line = JSON.parse(ev.data); } catch (e) { return; }
            if (typeof line !== "string") return;
            lines.push(line);
            if (logEl) {
              logEl.textContent = lines.join("\n");
              logEl.scrollTop = logEl.scrollHeight;
            }
            if (line.indexOf("[exit 0]") !== -1 || line.indexOf("[exit 1]") !== -1) {
              if (fill) fill.style.width = "100%";
              evtSource.close();
              if (line.indexOf("[exit 0]") !== -1) {
                if (status) status.textContent = "✓ Done — review in ToEnter before posting.";
                if (resultActions) resultActions.hidden = false;
              } else if (status) {
                status.textContent = "Error — see log above.";
              }
              btn.disabled = false;
              CE.loadStatus();
            } else if (line.indexOf("Scoring") !== -1) {
              if (fill) fill.style.width = "60%";
            } else if (line.indexOf("Re-identifying") !== -1) {
              if (fill) fill.style.width = "85%";
            }
          };
          evtSource.onerror = function () {
            evtSource.close();
            if (status) status.textContent = "Connection lost.";
            btn.disabled = false;
          };
        })
        .catch(function () {
          if (fill) fill.style.width = "100%";
          fail("Network error during prepare.");
        });
    });
  }

  var openSafe = document.getElementById("gf-open-safe");
  if (openSafe) {
    openSafe.addEventListener("click", function () {
      CE.openFolder("safe");
    });
  }

  var openPrivate = document.getElementById("gf-open-private");
  if (openPrivate) {
    openPrivate.addEventListener("click", function () {
      CE.openFolder("private");
    });
  }

  var pushBtn = document.getElementById("gf-push");
  if (pushBtn) {
    pushBtn.addEventListener("click", function () {
      document.getElementById("push-section").scrollIntoView({ behavior: "smooth" });
    });
  }

  loadPatterns();
  CE.loadStatus();
})();
