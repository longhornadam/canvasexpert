(function () {
  "use strict";

  var roster = window.CE_ROSTER || {};
  var required = ["getCurrentCourseId", "getGroupState", "onCourseLoaded", "postForm", "reloadCourse"];
  if (!required.every(function (name) { return typeof roster[name] === "function"; })) return;

  var snapshotSelect = document.getElementById("roster-assessment-snapshot");
  var methodSelect = document.getElementById("roster-assessment-method");
  var groupSetSelect = document.getElementById("roster-assessment-group-set");
  var noDataSelect = document.getElementById("roster-assessment-no-data-group");
  var previewButton = document.getElementById("roster-assessment-preview");
  var applyButton = document.getElementById("roster-assessment-apply");
  var statusEl = document.getElementById("roster-assessment-status");
  var proposalEl = document.getElementById("roster-assessment-proposal");
  var proposalSummary = document.getElementById("roster-assessment-proposal-summary");
  var tierSummary = document.getElementById("roster-assessment-tier-summary");
  var previewRows = document.getElementById("roster-assessment-preview-rows");
  var cutoffSupport = document.getElementById("roster-assessment-cutoff-support");
  var cutoffCore = document.getElementById("roster-assessment-cutoff-core");
  var cutoffAccelerate = document.getElementById("roster-assessment-cutoff-accelerate");
  var preview = null;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function setStatus(message, isError) {
    statusEl.textContent = message || "";
    statusEl.className = "hint" + (isError ? " error" : "");
  }

  function resetPreview() {
    preview = null;
    proposalEl.hidden = true;
    applyButton.disabled = true;
    tierSummary.innerHTML = "";
    previewRows.innerHTML = "";
  }

  function populateGroups(groups) {
    groupSetSelect.innerHTML = '<option value="">— select a group set —</option>';
    for (var i = 0; i < groups.length; i++) {
      var option = document.createElement("option");
      option.value = String(groups[i].category_id || "");
      option.textContent = groups[i].category_name || groups[i].category_id;
      groupSetSelect.appendChild(option);
    }
    var selected = (roster.getGroupState() || {}).selectedGroupCategoryId;
    if (selected != null) groupSetSelect.value = String(selected);
    groupSetSelect.disabled = groups.length === 0;
  }

  function loadSources() {
    resetPreview();
    snapshotSelect.innerHTML = '<option value="">— select an assessment —</option>';
    groupSetSelect.innerHTML = '<option value="">— select a group set —</option>';
    snapshotSelect.disabled = true;
    groupSetSelect.disabled = true;
    var courseId = roster.getCurrentCourseId();
    if (!courseId) return;
    fetch("/api/roster/assessment-groups/sources?course_id=" + encodeURIComponent(courseId))
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data.ok) { setStatus(data.error || "Assessment sources unavailable.", true); return; }
        for (var i = 0; i < (data.snapshots || []).length; i++) {
          var snapshot = data.snapshots[i];
          var option = document.createElement("option");
          option.value = snapshot.id;
          option.textContent = snapshot.label + (snapshot.date ? " — " + snapshot.date : "");
          snapshotSelect.appendChild(option);
        }
        snapshotSelect.disabled = (data.snapshots || []).length === 0;
        populateGroups(data.groups || []);
        if (!data.snapshots || !data.snapshots.length) setStatus("No offline assessment snapshots are available.", false);
      })
      .catch(function (error) { setStatus("Assessment sources unavailable: " + error.message, true); });
  }

  function renderProposal(value) {
    preview = value;
    proposalEl.hidden = false;
    applyButton.disabled = false;
    proposalSummary.textContent = value.snapshot_label + " · " + value.matched_count + " scored, " + value.no_data_count + " no-data, " + value.roster_count + " students total.";
    tierSummary.innerHTML = "";
    for (var i = 0; i < value.tiers.length; i++) {
      var tier = value.tiers[i];
      tierSummary.innerHTML += '<div class="roster-assessment-tier"><span>' + esc(tier.name) + '</span><strong>' + esc(tier.student_count) + '</strong></div>';
    }
    previewRows.innerHTML = "";
    for (var j = 0; j < value.placements.length; j++) {
      var row = value.placements[j];
      previewRows.innerHTML += '<tr><td>' + esc(row.display_name || row.pseudonym) + '</td><td>' + esc(row.score == null ? "—" : row.score) + '</td><td>' + esc(row.status) + '</td><td>' + esc(row.group) + '</td></tr>';
    }
    setStatus("Preview ready for review.", false);
  }

  function previewFields() {
    return {
      course_id: roster.getCurrentCourseId(),
      snapshot_id: snapshotSelect.value,
      method: methodSelect.value,
      no_data_group: noDataSelect.value,
      category_id: groupSetSelect.value,
      cutoffs: JSON.stringify({
        support: cutoffSupport.value,
        core: cutoffCore.value,
        accelerate: cutoffAccelerate.value
      })
    };
  }

  previewButton.addEventListener("click", function () {
    resetPreview();
    setStatus("Building preview...", false);
    roster.postForm("/api/roster/assessment-groups/preview", previewFields())
      .then(function (data) {
        if (!data.ok) { setStatus(data.error || "Preview failed.", true); return; }
        renderProposal(data.proposal);
      })
      .catch(function (error) { setStatus("Preview failed: " + error.message, true); });
  });

  function tierNames(tiers) {
    return tiers.map(function (tier) { return tier.name; }).join(", ");
  }

  function halt(tier, applied, remaining, reason) {
    // A group set that is part-way through no longer covers the roster exactly,
    // which is what differentiation prep checks. Say what landed and what did
    // not, rather than reporting one error and leaving the teacher to guess.
    var parts = [tier.name + " failed: " + (reason || "the group update was rejected") + "."];
    parts.push(applied.length ? "Already applied: " + applied.join(", ") + "." : "Nothing was applied.");
    if (remaining.length) parts.push("Not applied: " + tierNames(remaining) + ".");
    if (applied.length) {
      // Part of the set landed, so the reviewed placement no longer describes
      // Canvas. Force a fresh preview rather than leaving Apply live over it.
      parts.push("Preview again before using these groups for differentiation.");
      setStatus(parts.join(" "), true);
      resetPreview();
      roster.reloadCourse();
      return;
    }
    // Nothing was written, so the reviewed placement still stands and retrying
    // the same apply is safe.
    setStatus(parts.join(" "), true);
    applyButton.disabled = false;
  }

  function applyTier(tiers, index, applied) {
    if (index >= tiers.length) {
      setStatus("Applied " + preview.roster_count + " reviewed placements across " + tierNames(tiers) + ".", false);
      resetPreview();
      roster.reloadCourse();
      return;
    }
    var tier = tiers[index];
    roster.postForm("/api/roster/bulk", {
      course_id: roster.getCurrentCourseId(),
      user_ids: JSON.stringify(tier.student_ids),
      action: "set_canvas_group",
      value: JSON.stringify({ category_id: preview.category_id, group_id: tier.group_id })
    }).then(function (result) {
      if (!result.ok) { halt(tier, applied, tiers.slice(index + 1), result.error); return; }
      applied.push(tier.name);
      applyTier(tiers, index + 1, applied);
    }).catch(function (error) { halt(tier, applied, tiers.slice(index + 1), error.message); });
  }

  applyButton.addEventListener("click", function () {
    if (!preview) return;
    var reviewed = preview.proposal_digest;
    var tiers = preview.tiers;
    applyButton.disabled = true;
    // The digest is the only thing tying this write to what the teacher read.
    // Re-running the read-only preview catches a roster or snapshot that moved
    // underneath an open review, which nothing on the page can observe.
    setStatus("Re-checking the preview against the current roster...", false);
    roster.postForm("/api/roster/assessment-groups/preview", previewFields())
      .then(function (data) {
        if (!data.ok) {
          setStatus(data.error || "The preview could not be re-checked, so nothing was written.", true);
          applyButton.disabled = false;
          return;
        }
        if (!reviewed || data.proposal.proposal_digest !== reviewed) {
          renderProposal(data.proposal);
          setStatus("The roster or snapshot changed since you previewed. Nothing was written. This is the current placement: review it and apply again.", true);
          return;
        }
        setStatus("Applying reviewed placement...", false);
        applyTier(tiers, 0, []);
      })
      .catch(function (error) {
        setStatus("The preview could not be re-checked, so nothing was written: " + error.message, true);
        applyButton.disabled = false;
      });
  });

  methodSelect.addEventListener("change", function () {
    document.getElementById("roster-assessment-cutoffs").hidden = methodSelect.value !== "overall_pct";
    resetPreview();
  });
  [snapshotSelect, groupSetSelect, noDataSelect, cutoffSupport, cutoffCore, cutoffAccelerate].forEach(function (element) {
    element.addEventListener("change", resetPreview);
  });
  if (typeof roster.onGroupCategoryChanged === "function") roster.onGroupCategoryChanged(resetPreview);
  roster.onCourseLoaded(loadSources);
  document.getElementById("roster-assessment-cutoffs").hidden = false;
})();
