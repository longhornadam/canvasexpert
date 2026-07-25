(function () {
  "use strict";

  function localToISO(val) {
    if (!val) return "";
    var d = new Date(val);
    if (isNaN(d)) return "";
    var off = -d.getTimezoneOffset();
    var sign = off >= 0 ? "+" : "-";
    var ohh = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0");
    var omm = String(Math.abs(off) % 60).padStart(2, "0");
    var p = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" +
      p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()) + sign + ohh + ":" + omm;
  }

  function collectSettings() {
    var s = {};
    var due = localToISO(document.getElementById("due-at")?.value);
    var unlock = localToISO(document.getElementById("unlock-at")?.value);
    var lock = localToISO(document.getElementById("lock-at")?.value);
    var agSel = document.getElementById("assignment-group-select");
    var modSel = document.getElementById("module-select");
    var pub = document.getElementById("publish-now")?.checked;
    var sis = document.getElementById("post-to-sis")?.checked;
    var shufA = document.getElementById("shuffle-answers");
    var shufQ = document.getElementById("shuffle-questions");
    if (due) s.due_at = due;
    if (unlock) s.unlock_at = unlock;
    if (lock) s.lock_at = lock;
    if (agSel?.value) s.assignment_group_name = agSel.selectedOptions[0].text;
    if (modSel?.value === "__new__") {
      var name = document.getElementById("new-module-name")?.value.trim();
      if (name) s.module_name = name;
    } else if (modSel?.value) {
      s.module_name = modSel.selectedOptions[0].text;
    }
    if (sis) s.post_to_sis = true;
    if (pub) s.published = true;
    if (shufA) s.shuffle_answers = shufA.checked;
    if (shufQ) s.shuffle_questions = shufQ.checked;
    if (document.getElementById("hide-results")?.checked) s.hide_results = true;
    if (document.getElementById("access-code-enable")?.checked) {
      var code = document.getElementById("access-code")?.value.trim();
      if (code) s.access_code = code;
    }
    if (document.getElementById("allow-attempts")?.checked) {
      s.allow_multiple_attempts = true;
      s.allowed_attempts = document.getElementById("allowed-attempts")?.value ?? -1;
      s.score_to_keep = document.getElementById("score-to-keep")?.value ?? "highest";
      var cd = parseInt(document.getElementById("attempt-cooldown")?.value || "0", 10);
      if (cd > 0) s.attempt_cooldown = cd;
      if (document.getElementById("build-on-last")?.checked) s.build_on_last_attempt = true;
    }
    if (document.getElementById("has-time-limit")?.checked) {
      var mins = parseInt(document.getElementById("time-limit-minutes")?.value || "0", 10);
      if (mins > 0) {
        s.has_time_limit = true;
        s.time_limit_minutes = mins;
      }
    }
    if (document.getElementById("one-at-a-time")?.checked) {
      s.one_at_a_time = true;
      s.allow_backtracking = document.getElementById("allow-backtracking")?.checked ?? true;
    }
    var calc = document.getElementById("calculator-type")?.value;
    if (calc && calc !== "none") s.calculator_type = calc;
    return Object.keys(s).length ? JSON.stringify(s) : "";
  }

  function moduleChoice(selId) {
    var sel = document.getElementById(selId);
    if (!sel || !sel.value) return "";
    if (sel.value === "__new__") {
      return sel.closest("label")?.querySelector(".js-new-module")?.value.trim() || "";
    }
    return sel.selectedOptions[0].text;
  }

  // Focusing a different course (course_picker.js's setFocus) re-triggers
  // both loaders below without cancelling a slower earlier request, so a
  // stale response could land last and fill these pickers with the
  // previous course's categories/modules while a different course is now
  // focused. Stamp each request and let only the newest one write, the
  // same way inbox.js does.
  var aggroupsGeneration = 0;
  var modulesGeneration = 0;

  function loadAssignmentGroups(courseId) {
    var sels = Array.from(document.querySelectorAll(".js-aggroups"));
    var hints = Array.from(document.querySelectorAll(".js-ag-hint"));
    if (!sels.length || !courseId) return;
    var generation = ++aggroupsGeneration;
    sels.forEach(function (sel) {
      sel.disabled = true;
      while (sel.options.length > 1) sel.remove(1);
    });
    hints.forEach(function (h) { h.textContent = "Loading…"; });
    fetch("/api/assignment-groups?course_id=" + encodeURIComponent(courseId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (generation !== aggroupsGeneration) return;
        sels.forEach(function (sel) { sel.disabled = false; });
        if (!d.ok) {
          hints.forEach(function (h) { h.textContent = "Could not load categories"; });
          return;
        }
        hints.forEach(function (h) { h.textContent = ""; });
        sels.forEach(function (sel) {
          (d.groups || []).forEach(function (g) {
            sel.appendChild(new Option(g.name, g.id));
          });
          var daily = Array.from(sel.options).find(function (o) {
            return o.text.trim().toLowerCase() === "daily";
          });
          if (daily) sel.value = daily.value;
        });
      })
      .catch(function () {
        if (generation !== aggroupsGeneration) return;
        sels.forEach(function (sel) { sel.disabled = false; });
      });
  }

  function fillModuleSelect(sel, mods) {
    var defNone = sel.dataset.default === "none";
    sel.innerHTML = "";
    if (defNone) sel.appendChild(new Option("— don't add to a module —", ""));
    mods.forEach(function (m) { sel.appendChild(new Option(m.name, String(m.id))); });
    sel.appendChild(new Option("＋ Create new module…", "__new__"));
    if (!defNone) sel.appendChild(new Option("— don't add to a module —", ""));
    sel.value = defNone ? "" : (mods.length ? String(mods[0].id) : "");
    sel.disabled = false;
    var nm = sel.closest("label")?.querySelector(".js-new-module");
    if (nm) nm.style.display = "none";
  }

  function loadModules(courseId) {
    var sels = Array.from(document.querySelectorAll(".js-modules"));
    var hints = Array.from(document.querySelectorAll(".js-mod-hint"));
    if (!sels.length || !courseId) return;
    var generation = ++modulesGeneration;
    sels.forEach(function (s) { s.disabled = true; });
    hints.forEach(function (h) { h.textContent = "Loading…"; });
    fetch("/api/modules?course_id=" + encodeURIComponent(courseId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (generation !== modulesGeneration) return;
        var mods = (d.ok && d.modules) ? d.modules : [];
        sels.forEach(function (s) { fillModuleSelect(s, mods); });
        hints.forEach(function (h) { h.textContent = d.ok ? "" : "Could not load modules"; });
      })
      .catch(function () {
        if (generation !== modulesGeneration) return;
        sels.forEach(function (s) { s.disabled = false; });
      });
  }

  document.addEventListener("change", function (e) {
    var sel = e.target.closest(".js-modules");
    if (!sel) return;
    var nameInput = sel.closest("label")?.querySelector(".js-new-module");
    if (!nameInput) return;
    nameInput.style.display = sel.value === "__new__" ? "" : "none";
    if (sel.value === "__new__") nameInput.focus();
  });

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    moduleChoice: moduleChoice,
    collectSettings: collectSettings,
    loadAssignmentGroups: loadAssignmentGroups,
    loadModules: loadModules,
  });

  window.localToISO = localToISO;
})();
