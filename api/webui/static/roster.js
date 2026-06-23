/**
 * Roster Console V2 — compact inline editor.
 *
 * Inline editing: nicknames (input), pseudonym (input+regen), extra time
 * (checkbox+days), tier (select), monitor (checkbox), note (popover).
 * Autosaves per-cell on change/blur.
 */
(function () {
  "use strict";

  var courseSelect = document.getElementById("roster-course");
  var refreshBtn = document.getElementById("roster-refresh");
  var openCanvas = document.getElementById("roster-open-canvas");
  var statusEl = document.getElementById("roster-status");
  var tableCard = document.getElementById("roster-table-card");
  var tableBody = document.getElementById("roster-table-body");
  var searchInput = document.getElementById("roster-search");
  var filterBtns = document.querySelectorAll(".roster-filter-btn");
  var selectAll = document.getElementById("roster-select-all");
  var bulkBar = document.getElementById("roster-bulk-bar");
  var bulkCount = document.getElementById("roster-bulk-count");
  var bulkTier = document.getElementById("roster-bulk-tier");
  var bulkExtraDays = document.getElementById("roster-bulk-extra-days");
  var safetyCard = document.getElementById("roster-safety-card");
  var tierEditor = document.getElementById("roster-tier-editor");
  var tierRows = document.getElementById("roster-tier-rows");
  var tierAddBtn = document.getElementById("roster-tier-add");
  var tierSaveBtn = document.getElementById("roster-tier-save");
  var tierStatus = document.getElementById("roster-tier-status");

  // Protected names
  var protectedPacksEl = document.getElementById("roster-protected-packs");
  var customProtectedInput = document.getElementById("roster-custom-protected");
  var saveProtectedBtn = document.getElementById("roster-save-protected");
  var scrubText = document.getElementById("roster-scrub-text");
  var scrubRun = document.getElementById("roster-scrub-run");
  var scrubResult = document.getElementById("roster-scrub-result");
  var exportWhoBtn = document.getElementById("roster-export-who");
  var backupVaultBtn = document.getElementById("roster-backup-vault");

  // State
  var students = [];
  var tierScheme = [];
  var selectedStudentId = null;
  var filteredStudents = [];
  var currentCourseId = "";
  var protectedData = { packs: [], custom: [], active: [] };
  var saveTimeouts = {}; // row id -> timeout for debounced save

  // ── Helper ─────────────────────────────────────────────────────────

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function setStatus(msg, isOk) {
    statusEl.textContent = msg;
    statusEl.className = "hint" + (isOk ? " ok" : " error");
  }

  function toast(msg, isError) {
    var el = document.getElementById("ce-toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "ce-toast" + (isError ? " ce-toast--error" : " ce-toast--ok");
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, 3000);
  }

  function setRowStatus(rowId, msg, cls) {
    var row = tableBody.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) return;
    var el = row.querySelector(".roster-v2-status");
    if (!el) return;
    el.textContent = msg;
    el.className = "roster-v2-status " + (cls || "");
  }

  function findStudent(id) {
    for (var i = 0; i < students.length; i++) {
      if (students[i].id === id) return students[i];
    }
    return null;
  }

  // ── Course load ─────────────────────────────────────────────────────

  function loadCourse() {
    var cid = courseSelect.value;
    if (!cid) {
      tableCard.hidden = true;
      tierEditor.hidden = true;
      safetyCard.hidden = true;
      return;
    }
    currentCourseId = cid;
    setStatus("Loading...", true);
    openCanvas.href = window.CANVAS_BASE
      ? window.CANVAS_BASE + "/courses/" + cid + "/users"
      : "#";

    fetch("/api/roster?course_id=" + encodeURIComponent(cid))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          setStatus(data.error || "Failed to load roster.", false);
          return;
        }
        students = data.students || [];
        tierScheme = data.tier_scheme || [];
        renderSummary(data.counts);
        populateTierSelects();
        renderTable();
        tableCard.hidden = false;
        tierEditor.hidden = false;
        safetyCard.hidden = false;
        renderTierEditor();
        setStatus("Loaded " + students.length + " students" + (data.note ? " — " + data.note : ""), true);
        if (scrubText.value) scrubRun.click();
      })
      .catch(function (e) {
        setStatus("Network error: " + e.message, false);
      });
  }

  function renderSummary(counts) {
    if (!counts) return;
    document.getElementById("roster-summary-total").textContent = counts.total + " students";
    document.getElementById("roster-summary-extra").textContent = "Extra " + counts.extra_time;
    document.getElementById("roster-summary-monitored").textContent = "Monitored " + counts.monitored;
    document.getElementById("roster-summary-tier-unset").textContent = "Unset " + counts.tier_unset;
    document.getElementById("roster-summary-warnings").textContent = "!" + counts.warnings;
  }

  function populateTierSelects() {
    // Bulk tier select
    bulkTier.innerHTML = '<option value="">— unset —</option>';
    for (var i = 0; i < tierScheme.length; i++) {
      var t = tierScheme[i];
      if (!t.active) continue;
      var opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.teacher_label + " / " + t.alias;
      bulkTier.appendChild(opt);
    }
  }

  // ── Render table ───────────────────────────────────────────────────

  function renderTable() {
    var q = (searchInput.value || "").toLowerCase().trim();
    var activeFilter = document.querySelector(".roster-filter-btn.active");
    var filter = activeFilter ? activeFilter.dataset.filter : "all";

    filteredStudents = students.filter(function (s) {
      if (q) {
        var haystack = (s.name + " " + s.display_name + " " + s.short_name + " " +
          (s.nicknames || []).join(" ") + " " + (s.pseudonym || "")).toLowerCase();
        if (haystack.indexOf(q) === -1) return false;
      }
      if (filter === "extra_time" && !s.extra_time.enabled) return false;
      if (filter === "monitored" && !s.monitored.enabled) return false;
      if (filter === "tier_unset" && s.tier_id) return false;
      if (filter === "warnings" && (!s.warnings || s.warnings.length === 0)) return false;
      return true;
    });

    if (filteredStudents.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="9" class="roster-empty">No students.</td></tr>';
      return;
    }

    // Build tier select HTML (shared)
    function tierOptions(selected) {
      var h = '<option value="">— unset —</option>';
      for (var i = 0; i < tierScheme.length; i++) {
        var t = tierScheme[i];
        if (!t.active) continue;
        var sel = t.id === selected ? " selected" : "";
        h += '<option value="' + esc(t.id) + '"' + sel + '>' + esc(t.teacher_label) + " / " + esc(t.alias) + "</option>";
      }
      return h;
    }

    var html = "";
    for (var i = 0; i < filteredStudents.length; i++) {
      var s = filteredStudents[i];
      var sel = selectedStudentId === s.id ? ' class="roster-v2-row-selected"' : "";

      // Warn icons
      var warnHtml = "";
      for (var wi = 0; wi < (s.warnings || []).length; wi++) {
        warnHtml += '<span class="roster-warn-dot" title="' + esc(s.warnings[wi]) + '">!</span>';
      }

      var tierDisplay = s.tier_display || "";
      var nnVal = esc((s.nicknames || []).join(", "));
      var pseudoVal = esc(s.pseudonym || "");

      html += "<tr" + sel + ' data-id="' + esc(s.id) + '">' +
        '<td class="roster-col-check"><input type="checkbox" class="roster-row-check" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-name"><span class="roster-v2-name">' + esc(s.display_name || s.name) + "</span></td>" +
        '<td class="roster-col-nicknames"><input type="text" class="roster-v2-input roster-v2-nicknames" value="' + nnVal + '" placeholder="nicknames" data-id="' + esc(s.id) + '"></td>' +
        '<td class="roster-col-pseudo"><span class="roster-v2-pseudo-row"><input type="text" class="roster-v2-input roster-v2-pseudo" value="' + pseudoVal + '" placeholder="pseudonym" data-id="' + esc(s.id) + '" data-field="pseudo"><button type="button" class="roster-v2-regen" data-id="' + esc(s.id) + '" title="Regenerate">&#x21bb;</button></span></td>' +
        '<td class="roster-col-extratime"><label class="roster-v2-et"><input type="checkbox" class="roster-v2-et-cb" data-id="' + esc(s.id) + '"' + (s.extra_time.enabled ? " checked" : "") + ">" +
        (s.extra_time.enabled ? ('<input type="number" class="roster-v2-et-days" value="' + (s.extra_time.days || 0) + '" min="0" max="30" data-id="' + esc(s.id) + '">') : '<input type="number" class="roster-v2-et-days" value="0" min="0" max="30" data-id="' + esc(s.id) + '" hidden>') +
        "</label></td>" +
        '<td class="roster-col-tier"><select class="roster-v2-tier" data-id="' + esc(s.id) + '">' + tierOptions(s.tier_id) + "</select></td>" +
        '<td class="roster-col-monitor"><input type="checkbox" class="roster-v2-monitor" data-id="' + esc(s.id) + '"' + (s.monitored.enabled ? " checked" : "") + "></td>" +
        '<td class="roster-col-note"><button type="button" class="roster-v2-note-btn" data-id="' + esc(s.id) + '" title="Edit private note">&#9998;</button></td>" +
        '<td class="roster-col-status"><span class="roster-v2-status">' + warnHtml + "saved</span></td>" +
        "</tr>";
    }
    tableBody.innerHTML = html;
    attachInlineEvents();
    updateBulkBar();
  }

  // ── Inline editing with autosave ───────────────────────────────────

  function attachInlineEvents() {
    // Nicknames: save on Enter or blur
    tableBody.querySelectorAll(".roster-v2-nicknames").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var val = el.value.split(",").map(function (n) { return n.trim(); }).filter(Boolean);
        saveField(id, "nicknames", val);
      });
    });

    // Pseudonym: save on blur (full pseudo as first/last split)
    tableBody.querySelectorAll(".roster-v2-pseudo").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var parts = el.value.trim().split(/\s+/);
        var first = parts[0] || "";
        var last = parts.slice(1).join(" ") || "";
        saveField(id, "pseudonym", { first: first, last: last });
      });
    });

    // Regenerate
    tableBody.querySelectorAll(".roster-v2-regen").forEach(function (el) {
      el.addEventListener("click", function () {
        var id = el.dataset.id;
        setRowStatus(id, "saving...", "roster-v2-status-saving");
        saveField(id, "regenerate_pseudonym", true);
      });
    });

    // Extra time checkbox
    tableBody.querySelectorAll(".roster-v2-et-cb").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        var daysInput = el.closest("label").querySelector(".roster-v2-et-days");
        var enabled = el.checked;
        daysInput.hidden = !enabled;
        if (enabled) daysInput.value = daysInput.value || "2";
        saveField(id, "extra_time", {
          enabled: enabled,
          days: enabled ? parseInt(daysInput.value, 10) || 2 : 0,
          name: s ? (s.display_name || s.name) : ""
        });
      });
    });

    // Extra time days
    tableBody.querySelectorAll(".roster-v2-et-days").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        var cb = el.closest("label").querySelector(".roster-v2-et-cb");
        saveField(id, "extra_time", {
          enabled: cb.checked,
          days: parseInt(el.value, 10) || 0,
          name: s ? (s.display_name || s.name) : ""
        });
      });
    });

    // Tier select
    tableBody.querySelectorAll(".roster-v2-tier").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        saveField(id, "tier_id", el.value || "");
      });
    });

    // Monitor checkbox
    tableBody.querySelectorAll(".roster-v2-monitor").forEach(function (el) {
      el.addEventListener("change", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        saveField(id, "monitored", {
          enabled: el.checked,
          name: s ? (s.display_name || s.name) : "",
          note: s ? (s.monitored.note || "") : ""
        });
      });
    });

    // Note button — inline popover
    tableBody.querySelectorAll(".roster-v2-note-btn").forEach(function (el) {
      el.addEventListener("click", function () {
        var id = el.dataset.id;
        var s = findStudent(id);
        if (!s) return;
        var note = prompt("Private note for " + (s.display_name || s.name) + ":", s.monitored.note || "");
        if (note === null) return;
        saveField(id, "monitored", {
          enabled: s.monitored.enabled,
          name: s.display_name || s.name,
          note: note
        });
      });
    });
  }

  // ── Autosave ───────────────────────────────────────────────────────

  function saveField(userId, key, value) {
    setRowStatus(userId, "saving...", "roster-v2-status-saving");

    if (saveTimeouts[userId]) {
      clearTimeout(saveTimeouts[userId]);
    }

    // Debounce: wait 300ms then send
    saveTimeouts[userId] = setTimeout(function () {
      var patch = {};
      patch[key] = value;

      var body = new URLSearchParams();
      body.append("course_id", currentCourseId);
      body.append("user_id", userId);
      body.append("patch", JSON.stringify(patch));

      fetch("/api/roster/student", { method: "POST", body: body })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            setRowStatus(userId, "saved", "roster-v2-status-ok");
            // Update local student state without full refresh
            // (re-fetch patch response to get the updated state)
          } else {
            setRowStatus(userId, "error", "roster-v2-status-error");
            toast(data.error || "Save failed.", true);
          }
        })
        .catch(function (e) {
          setRowStatus(userId, "error", "roster-v2-status-error");
          toast("Network error: " + e.message, true);
        });
    }, 300);
  }

  // ── Filters ─────────────────────────────────────────────────────────

  searchInput.addEventListener("input", renderTable);

  for (var fi = 0; fi < filterBtns.length; fi++) {
    filterBtns[fi].addEventListener("click", function () {
      for (var fj = 0; fj < filterBtns.length; fj++) {
        filterBtns[fj].classList.remove("active");
      }
      this.classList.add("active");
      renderTable();
    });
  }

  // ── Select all / bulk ───────────────────────────────────────────────

  selectAll.addEventListener("change", function () {
    var checked = selectAll.checked;
    var checkboxes = tableBody.querySelectorAll(".roster-row-check");
    for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = checked;
    }
    updateBulkBar();
  });

  tableBody.addEventListener("change", function (e) {
    if (e.target.classList.contains("roster-row-check")) {
      updateBulkBar();
    }
  });

  function getSelectedIds() {
    var ids = [];
    var checks = tableBody.querySelectorAll(".roster-row-check:checked");
    for (var i = 0; i < checks.length; i++) {
      ids.push(checks[i].dataset.id);
    }
    return ids;
  }

  function updateBulkBar() {
    var ids = getSelectedIds();
    bulkBar.hidden = ids.length === 0;
    if (ids.length > 0) bulkCount.textContent = ids.length + " selected";
  }

  // ── Bulk actions ────────────────────────────────────────────────────

  document.querySelector(".roster-bulk-actions").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-bulk]");
    if (!btn) return;
    var action = btn.dataset.bulk;
    var ids = getSelectedIds();
    if (ids.length === 0) return;

    var value = {};
    if (action === "set_extra_time") {
      value = { days: parseInt(bulkExtraDays.value, 10) || 2, names: getSelectedNameMap() };
    } else if (action === "set_monitored") {
      value = { names: getSelectedNameMap() };
    } else if (action === "set_tier") {
      var tid = bulkTier.value;
      if (!tid) { toast("Select a tier first.", true); return; }
      value = { tier_id: tid };
      action = "set_tier";
    }

    doBulkAction(action, ids, value);
  });

  function getSelectedNameMap() {
    var names = {};
    var ids = getSelectedIds();
    for (var i = 0; i < ids.length; i++) {
      var s = findStudent(ids[i]);
      names[ids[i]] = s ? (s.display_name || s.name) : ids[i];
    }
    return names;
  }

  function doBulkAction(action, ids, value) {
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);
    body.append("user_ids", JSON.stringify(ids));
    body.append("action", action);
    body.append("value", JSON.stringify(value));

    fetch("/api/roster/bulk", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Updated " + data.updated + " students.", false);
          loadCourse();
        } else {
          toast(data.error || "Bulk action failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  }

  // ── Tier scheme editor ──────────────────────────────────────────────

  function renderTierEditor() {
    tierRows.innerHTML = "";
    for (var i = 0; i < tierScheme.length; i++) {
      var t = tierScheme[i];
      var row = document.createElement("div");
      row.className = "roster-v2-tier-row";
      row.dataset.tierId = t.id;

      var idInput = document.createElement("input");
      idInput.type = "hidden";
      idInput.className = "roster-v2-tier-id";
      idInput.value = t.id;

      var labelInput = document.createElement("input");
      labelInput.type = "text";
      labelInput.className = "roster-v2-tier-label";
      labelInput.value = t.teacher_label;
      labelInput.title = "Teacher label";
      labelInput.placeholder = "Label";

      var aliasInput = document.createElement("input");
      aliasInput.type = "text";
      aliasInput.className = "roster-v2-tier-alias";
      aliasInput.value = t.alias;
      aliasInput.title = "Canvas-safe alias";
      aliasInput.placeholder = "Alias";

      var meaningInput = document.createElement("input");
      meaningInput.type = "text";
      meaningInput.className = "roster-v2-tier-meaning";
      meaningInput.value = t.meaning || "";
      meaningInput.title = "Meaning";
      meaningInput.placeholder = "Meaning";

      var activeCb = document.createElement("input");
      activeCb.type = "checkbox";
      activeCb.className = "roster-v2-tier-active";
      activeCb.checked = t.active !== false;
      activeCb.title = "Active";

      var delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "small roster-v2-tier-del";
      delBtn.textContent = "X";
      delBtn.title = "Remove tier";
      delBtn.addEventListener("click", function () {
        this.closest(".roster-v2-tier-row").remove();
      });

      row.appendChild(idInput);
      row.appendChild(labelInput);
      row.appendChild(document.createTextNode(" → "));
      row.appendChild(aliasInput);
      row.appendChild(meaningInput);
      row.appendChild(activeCb);
      row.appendChild(document.createTextNode(" active"));
      row.appendChild(delBtn);
      tierRows.appendChild(row);
    }
  }

  tierAddBtn.addEventListener("click", function () {
    var row = document.createElement("div");
    row.className = "roster-v2-tier-row";

    var idInput = document.createElement("input");
    idInput.type = "hidden";
    idInput.className = "roster-v2-tier-id";
    idInput.value = "new_" + Date.now();

    var labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.className = "roster-v2-tier-label";
    labelInput.placeholder = "Label";
    labelInput.title = "Teacher label";

    var aliasInput = document.createElement("input");
    aliasInput.type = "text";
    aliasInput.className = "roster-v2-tier-alias";
    aliasInput.placeholder = "Alias";
    aliasInput.title = "Canvas-safe alias";

    var meaningInput = document.createElement("input");
    meaningInput.type = "text";
    meaningInput.className = "roster-v2-tier-meaning";
    meaningInput.placeholder = "Meaning";
    meaningInput.title = "Meaning";

    var activeCb = document.createElement("input");
    activeCb.type = "checkbox";
    activeCb.className = "roster-v2-tier-active";
    activeCb.checked = true;
    activeCb.title = "Active";

    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "small roster-v2-tier-del";
    delBtn.textContent = "X";
    delBtn.title = "Remove tier";
    delBtn.addEventListener("click", function () {
      this.closest(".roster-v2-tier-row").remove();
    });

    row.appendChild(idInput);
    row.appendChild(labelInput);
    row.appendChild(document.createTextNode(" → "));
    row.appendChild(aliasInput);
    row.appendChild(meaningInput);
    row.appendChild(activeCb);
    row.appendChild(document.createTextNode(" active"));
    row.appendChild(delBtn);
    tierRows.appendChild(row);
  });

  tierSaveBtn.addEventListener("click", function () {
    var rows = tierRows.querySelectorAll(".roster-v2-tier-row");
    var scheme = [];
    var order = 10;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var label = r.querySelector(".roster-v2-tier-label").value.trim();
      var alias = r.querySelector(".roster-v2-tier-alias").value.trim();
      var meaning = r.querySelector(".roster-v2-tier-meaning").value.trim();
      var active = r.querySelector(".roster-v2-tier-active").checked;
      var id = r.querySelector(".roster-v2-tier-id").value.trim();
      if (!label || !alias) continue;
      if (!id) id = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
      scheme.push({
        id: id,
        teacher_label: label,
        alias: alias,
        meaning: meaning,
        order: order,
        active: active,
      });
      order += 10;
    }

    tierStatus.textContent = "Saving...";
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);
    body.append("scheme", JSON.stringify(scheme));

    fetch("/api/roster/tier-scheme", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          tierStatus.textContent = "Saved.";
          tierScheme = data.tier_scheme || [];
          populateTierSelects();
          renderTierEditor();
          loadCourse(); // refresh roster with new tier options
        } else {
          tierStatus.textContent = data.error || "Save failed.";
        }
      })
      .catch(function (e) { tierStatus.textContent = "Error: " + e.message; });
  });

  // ── Protected names ─────────────────────────────────────────────────

  function loadProtected() {
    fetch("/api/names/protected")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        protectedData = data;
        renderProtectedPacks(data);
        customProtectedInput.value = (data.custom || []).join(", ");
      })
      .catch(function () {});
  }

  function renderProtectedPacks(data) {
    protectedPacksEl.innerHTML = "";
    var packs = data.packs || [];
    for (var i = 0; i < packs.length; i++) {
      var label = document.createElement("label");
      label.className = "roster-protected-pack";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = packs[i].enabled;
      cb.dataset.packId = packs[i].id;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + packs[i].title));
      protectedPacksEl.appendChild(label);
    }
  }

  saveProtectedBtn.addEventListener("click", function () {
    var packStates = {};
    var cbs = protectedPacksEl.querySelectorAll("input[type=checkbox]");
    for (var i = 0; i < cbs.length; i++) {
      packStates[cbs[i].dataset.packId] = cbs[i].checked;
    }
    var custom = customProtectedInput.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);

    var body = new URLSearchParams();
    body.append("data", JSON.stringify({ packs: packStates, custom: custom }));

    fetch("/api/names/protected", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Protected names saved.", false);
          loadProtected();
        } else {
          toast(data.error || "Save failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Scrub test ──────────────────────────────────────────────────────

  scrubRun.addEventListener("click", function () {
    var txt = scrubText.value;
    if (!txt) { scrubResult.hidden = true; return; }
    var body = new URLSearchParams();
    body.append("text", txt);
    body.append("course_id", currentCourseId);

    fetch("/api/names/scrub-test", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          scrubResult.textContent = data.scrubbed;
          scrubResult.hidden = false;
        } else {
          scrubResult.textContent = data.error || "Scrub test failed.";
          scrubResult.hidden = false;
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Export / backup ─────────────────────────────────────────────────

  exportWhoBtn.addEventListener("click", function () {
    if (!currentCourseId) return;
    var body = new URLSearchParams();
    body.append("course_id", currentCourseId);

    fetch("/api/names/who-is-who", { method: "POST", body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Exported to " + data.path, false);
        } else {
          toast(data.error || "Export failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  backupVaultBtn.addEventListener("click", function () {
    fetch("/api/names/backup-vault", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          toast("Backed up (" + data.entries + " entries).", false);
        } else {
          toast(data.error || "Backup failed.", true);
        }
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  });

  // ── Init ────────────────────────────────────────────────────────────

  window.CANVAS_BASE = document.querySelector('meta[name="canvas-base"]')
    ? document.querySelector('meta[name="canvas-base"]').content
    : "";

  var params = new URLSearchParams(window.location.search);
  var focus = params.get("focus");
  if (focus === "extra-time") {
    var etBtn = document.querySelector('.roster-filter-btn[data-filter="extra_time"]');
    if (etBtn) etBtn.click();
  }

  courseSelect.addEventListener("change", loadCourse);
  refreshBtn.addEventListener("click", loadCourse);

  loadProtected();

  if (courseSelect.value) {
    loadCourse();
  }
})();