(function () {
  "use strict";

  var root = document.getElementById("desk-root");
  if (!root) return;

  var dataScript = document.getElementById("desk-initial-data");
  var initial = { jobs: [], presentations: {}, operations: [], receipts: [] };
  try {
    initial = JSON.parse(dataScript ? dataScript.textContent : "{}") || initial;
  } catch (e) {
    initial = { jobs: [], presentations: {}, operations: [], receipts: [] };
  }

  var state = {
    jobs: Array.isArray(initial.jobs) ? initial.jobs : [],
    presentations: initial.presentations && typeof initial.presentations === "object"
      ? initial.presentations : {},
    operations: Array.isArray(initial.operations) ? initial.operations : [],
    receipts: Array.isArray(initial.receipts) ? initial.receipts : [],
  };
  var continueList = document.getElementById("desk-continue-list");
  var attentionList = document.getElementById("desk-attention-list");
  var preparedList = document.getElementById("desk-prepared-list");
  var receiptsList = document.getElementById("desk-receipts-list");
  var csrfMeta = document.querySelector('meta[name="canvasexpert-csrf-token"]');
  var syncButton = document.getElementById("desk-sync");
  var mirrorRoot = document.getElementById("desk-mirror");
  var mirrorLabel = document.getElementById("desk-mirror-label");
  var mirrorDot = mirrorRoot ? mirrorRoot.querySelector("[data-mirror-dot]") : null;
  var syncing = false;
  var mirrorCanSync = true;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function emptyList(node, text) {
    clear(node);
    node.appendChild(element("p", "ce-desk-empty", text));
  }

  function jobActions(job) {
    var actions = element("div", "ce-desk-job-actions");
    [
      ["ignore", "Ignore"],
      ["snooze", "Snooze"],
    ].forEach(function (item) {
      var button = element("button", "", item[1]);
      button.type = "button";
      button.dataset.jobAction = item[0];
      button.dataset.jobId = job.job_id;
      actions.appendChild(button);
    });
    if (job.origin === "intentional") {
      var complete = element("button", "", "Complete");
      complete.type = "button";
      complete.dataset.jobAction = "complete";
      complete.dataset.jobId = job.job_id;
      actions.appendChild(complete);
    }
    return actions;
  }

  function renderJobList(node, jobs, actionLabel) {
    if (!node) return;
    if (!jobs.length) {
      emptyList(node, actionLabel === "Review" ? "No items need review." : "No open work.");
      return;
    }
    clear(node);
    jobs.forEach(function (job) {
      var presentation = state.presentations[job.job_id] || {};
      var article = element("article", "ce-desk-job");
      article.dataset.jobId = job.job_id;
      article.dataset.materialVersion = job.material_version;
      article.dataset.origin = job.origin;

      var detail = element("div", "ce-desk-job-detail");
      if (presentation.course_label) {
        detail.appendChild(element("span", "ce-desk-course-label", presentation.course_label));
      }
      detail.appendChild(element("strong", "", presentation.title || job.title || "Work item"));
      var fallbackSummary = actionLabel === "Review"
        ? (job.attention_reason || "Work needs attention")
        : "Work in progress";
      detail.appendChild(element("span", "ce-desk-job-summary", presentation.summary || fallbackSummary));
      article.appendChild(detail);

      var link = element("a", "ce-desk-inline-link", presentation.action_label || actionLabel);
      link.href = job.resumable_url || "/";
      article.appendChild(link);
      article.appendChild(jobActions(job));
      node.appendChild(article);
    });
  }

  function renderReceipts() {
    if (!receiptsList) return;
    if (!state.receipts.length) {
      emptyList(receiptsList, "No receipts.");
      return;
    }
    clear(receiptsList);
    state.receipts.forEach(function (receipt) {
      var article = element("article", "ce-desk-receipt");
      var detail = element("div");
      detail.appendChild(element("strong", "", receipt.kind || "Receipt"));
      var count = Number(receipt.target_count) === 1 ? "target" : "targets";
      detail.appendChild(element("span", "", (receipt.status || "recorded") + " · " + (receipt.target_count || 0) + " " + count));
      article.appendChild(detail);
      var link = element("a", "ce-desk-inline-link", "Receipt");
      link.href = receipt.detail_url || "/api/receipts";
      article.appendChild(link);
      receiptsList.appendChild(article);
    });
  }

  function renderPrepared() {
    if (!preparedList) return;
    var prepared = state.operations.filter(function (operation) {
      return ["prepared", "reviewed"].indexOf(operation.status) !== -1;
    });
    if (!prepared.length) {
      clear(preparedList);
      var empty = element("p", "ce-desk-empty", "No prepared operations.");
      empty.id = "desk-prepared-empty";
      preparedList.appendChild(empty);
      return;
    }
    clear(preparedList);
    prepared.forEach(function (operation) {
      var article = element("article", "ce-desk-prepared");
      var detail = element("div");
      detail.appendChild(element("strong", "", operation.kind || "Operation"));
      var count = Number(operation.target_count) === 1 ? "target" : "targets";
      detail.appendChild(element("span", "", (operation.status || "prepared") + " · " + (operation.target_count || 0) + " " + count));
      article.appendChild(detail);
      preparedList.appendChild(article);
    });
  }

  function render() {
    renderJobList(continueList, state.jobs.filter(function (job) {
      return ["draft", "ready", "in_progress"].indexOf(job.status) !== -1;
    }), "Continue");
    renderJobList(attentionList, state.jobs.filter(function (job) {
      return job.status === "attention";
    }), "Review");
    renderPrepared();
    renderReceipts();
  }

  function responseJson(response) {
    return response.json().catch(function () { return {}; }).then(function (body) {
      return { response: response, body: body };
    });
  }

  // Transient message shown in the freshness line, then restored to real state.
  function note(message) {
    if (!mirrorLabel) return;
    mirrorLabel.textContent = message;
    setTimeout(loadMirror, 3000);
  }

  function refreshLocal() {
    return Promise.all([
      fetch("/api/work?section=all", { headers: { "Accept": "application/json" } }).then(responseJson),
      fetch("/api/operations", { headers: { "Accept": "application/json" } }).then(responseJson),
      fetch("/api/receipts", { headers: { "Accept": "application/json" } }).then(responseJson),
    ]).then(function (results) {
      var workResult = results[0];
      var operationResult = results[1];
      var receiptResult = results[2];
      if (!workResult.response.ok || !workResult.body.ok) throw new Error("work_unavailable");
      if (!operationResult.response.ok || !operationResult.body.ok) throw new Error("operations_unavailable");
      if (!receiptResult.response.ok || !receiptResult.body.ok) throw new Error("receipts_unavailable");
      state.jobs = Array.isArray(workResult.body.jobs) ? workResult.body.jobs : [];
      state.presentations = workResult.body.presentations && typeof workResult.body.presentations === "object"
        ? workResult.body.presentations : {};
      state.operations = Array.isArray(operationResult.body.operations) ? operationResult.body.operations : [];
      state.receipts = Array.isArray(receiptResult.body.receipts) ? receiptResult.body.receipts : [];
      render();
    }).catch(function () {
      // Keep the last rendered cards in place; the freshness line reports sync state.
    });
  }

  function mutationHeaders() {
    return {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-CanvasExpert-CSRF": csrfMeta ? csrfMeta.content : "",
    };
  }

  function mutate(job, action, until) {
    var body = { material_version: job.material_version };
    if (action === "snooze") body.until = until;
    return fetch("/api/work/" + encodeURIComponent(job.job_id) + "/" + action, {
      method: "POST",
      headers: mutationHeaders(),
      body: JSON.stringify(body),
    }).then(responseJson).then(function (result) {
      if (!result.response.ok || !result.body.ok) throw new Error("mutation_rejected");
      state.jobs = state.jobs.filter(function (item) { return item.job_id !== job.job_id; });
      render();
    }).catch(function () {
      note("That action could not be completed; work is unchanged.");
    });
  }

  function snoozeUntil() {
    var suggested = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    return window.prompt("Snooze until (ISO-8601):", suggested);
  }

  function findJob(jobId) {
    return state.jobs.find(function (job) { return job.job_id === jobId; });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-job-action]") : null;
    if (!button) return;
    var job = findJob(button.dataset.jobId);
    if (!job) return;
    var action = button.dataset.jobAction;
    if (action === "complete" && !window.confirm("Mark this intentional work complete?")) return;
    var until = action === "snooze" ? snoozeUntil() : null;
    if (action === "snooze" && !until) return;
    button.disabled = true;
    mutate(job, action, until).then(function () { if (syncButton) syncButton.focus(); });
  });

  function relativeTime(ms) {
    var minutes = Math.floor(ms / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return minutes + (minutes === 1 ? " minute ago" : " minutes ago");
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + (hours === 1 ? " hour ago" : " hours ago");
    var days = Math.floor(hours / 24);
    return days + (days === 1 ? " day ago" : " days ago");
  }

  function mirrorSummary(data) {
    if (!data || data.ok === false) return { state: "", label: "Canvas sync status unavailable", sync: false };
    if (!data.enabled) return { state: "", label: "Background Canvas sync is off", sync: false };
    if (!data.workspace_configured) return { state: "", label: "No workspace — Canvas sync unavailable", sync: false };
    var courses = Array.isArray(data.courses) ? data.courses : [];
    if (!courses.length) return { state: "", label: "No active courses to sync", sync: false };
    var oldest = null;
    var neverCount = 0;
    courses.forEach(function (course) {
      var passes = course.passes || {};
      var full = (passes.full || {}).last_success_at || "";
      var delta = (passes.delta || {}).last_success_at || "";
      var newest = full > delta ? full : delta; // ISO-Z strings compare lexically
      if (!newest) { neverCount += 1; return; }
      if (oldest === null || newest < oldest) oldest = newest;
    });
    if (neverCount === courses.length) {
      return { state: "attention", label: "Canvas data not synced yet", sync: true };
    }
    if (neverCount > 0) {
      return { state: "attention", label: neverCount + " of " + courses.length + " courses not synced yet", sync: true };
    }
    var ageMs = Date.now() - new Date(oldest).getTime();
    var maxAgeMs = (Number(data.serve_max_age_hours) || 6) * 3600 * 1000;
    return {
      state: ageMs <= maxAgeMs ? "ready" : "attention",
      label: "Canvas data synced " + relativeTime(ageMs),
      sync: true,
    };
  }

  var SYNC_ERROR_MESSAGES = {
    auth_failed: "Canvas sync failed: your Canvas token may need to be updated in Settings.",
    auth_unavailable: "Canvas sync failed: your Canvas token may need to be updated in Settings.",
    forbidden: "Canvas sync failed: this Canvas account may not have access to a course.",
    not_found: "Canvas sync failed: a course or item may have been moved or removed.",
  };

  function syncFailureMessage(plan) {
    var jobs = Array.isArray(plan.jobs) ? plan.jobs : [];
    var failed = jobs.filter(function (job) { return job.state === "failed"; });
    var code = failed.length ? failed[0].error_code : "";
    return SYNC_ERROR_MESSAGES[code] || "Canvas sync failed. Try again in a few minutes.";
  }

  function renderMirror(summary) {
    if (!mirrorRoot) return;
    mirrorRoot.dataset.state = summary.state || "unknown";
    if (mirrorLabel) mirrorLabel.textContent = summary.label;
    if (mirrorDot) {
      mirrorDot.dataset.state = summary.state === "ready" ? "ready"
        : summary.state === "attention" ? "attention" : "";
    }
    mirrorCanSync = !!summary.sync;
    if (syncButton && !syncing) syncButton.disabled = !summary.sync;
  }

  function loadMirror() {
    if (!mirrorRoot) return Promise.resolve();
    return fetch("/api/mirror/status", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (data) { renderMirror(mirrorSummary(data)); })
      .catch(function () { renderMirror({ state: "", label: "Canvas sync status unavailable", sync: false }); });
  }

  function pollMirrorPlan(planId, remaining) {
    return fetch("/api/mirror/status?plan_id=" + encodeURIComponent(planId), {
      headers: { "Accept": "application/json" }
    }).then(responseJson).then(function (result) {
      var plans = result.body && result.body.plan && result.body.plan.plans;
      var plan = Array.isArray(plans) ? plans[0] : null;
      if (!result.response.ok || !plan) throw new Error("sync_status_unavailable");
      if (["succeeded", "failed", "cancelled"].indexOf(plan.state) !== -1) return plan;
      if (remaining <= 0) throw new Error("sync_status_timeout");
      var jobs = Array.isArray(plan.jobs) ? plan.jobs : [];
      var completed = jobs.filter(function (job) {
        return ["succeeded", "failed", "cancelled"].indexOf(job.state) !== -1;
      }).length;
      renderMirror({ state: "", label: "Syncing Canvas data… " + completed + "/" + jobs.length + " scopes complete", sync: true });
      return new Promise(function (resolve) { setTimeout(resolve, 750); })
        .then(function () { return pollMirrorPlan(planId, remaining - 1); });
    });
  }

  // One honest action: pull fresh Canvas data into the mirror, then recompute
  // the work lists from it, then repaint the cards and freshness line.
  if (syncButton) {
    syncButton.addEventListener("click", function () {
      if (syncing) return;
      syncing = true;
      syncButton.disabled = true;
      renderMirror({ state: "", label: "Syncing Canvas data… you can keep working", sync: mirrorCanSync });
      // keepalive lets both requests finish server-side even if the teacher
      // navigates away (e.g. clicks a Start link) mid-sync.
      fetch("/api/mirror/sync-now", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "",
        keepalive: true,
      }).then(responseJson).then(function (syncResult) {
        if (!syncResult.response.ok || !syncResult.body.plan_id) throw new Error("sync_not_queued");
        return pollMirrorPlan(syncResult.body.plan_id, 160);
      }).then(function (plan) {
        if (plan.state === "failed") {
          // A failed plan produced no new data: skip the work-list recompute
          // and stop before loadMirror() can overwrite this message with the
          // stale "synced N days ago" summary.
          renderMirror({ state: "attention", label: syncFailureMessage(plan), sync: true });
          return;
        }
        return fetch("/api/work/scan", { method: "POST", headers: mutationHeaders(), keepalive: true }).then(responseJson)
          .then(function () { return Promise.all([loadMirror(), refreshLocal()]); });
      }).catch(function () {
        renderMirror({ state: "attention", label: "Canvas sync could not finish", sync: true });
      }).finally(function () {
        syncing = false;
        if (syncButton) syncButton.disabled = !mirrorCanSync;
      });
    });
  }

  render();
  refreshLocal();
  loadMirror();
})();
