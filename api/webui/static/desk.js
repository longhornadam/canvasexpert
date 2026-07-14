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
  var localStatus = document.getElementById("desk-local-status");
  var scanButton = document.getElementById("desk-scan");
  var courseField = document.getElementById("desk-course-field");
  var scopeNote = document.getElementById("desk-scope-note");
  var csrfMeta = document.querySelector('meta[name="canvasexpert-csrf-token"]');
  var sharedContext = window.CE_CONTEXT;

  function currentCourseOptions() {
    return Array.from(courseField ? courseField.options : []).filter(function (option) {
      return option.value && option.value !== "__all__";
    }).map(function (option) {
      return { id: option.value, name: option.textContent };
    });
  }

  sharedContext?.reconcile(currentCourseOptions(), { source: "desk", authoritative: true });

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
      if (localStatus) localStatus.textContent = "Local state updated.";
    }).catch(function () {
      if (localStatus) localStatus.textContent = "Showing the last local view; refresh was unavailable.";
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
      if (localStatus) localStatus.textContent = "Local work updated.";
    }).catch(function () {
      if (localStatus) localStatus.textContent = "Action could not be completed; local work is unchanged.";
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
    mutate(job, action, until).then(function () { scanButton && scanButton.focus(); });
  });

  function applyExplicitScope() {
    var context = sharedContext;
    var selection = courseField ? courseField.value : "";
    if (!context || !selection) return;
    if (selection === "__all__") {
      var allCourses = currentCourseOptions();
      context.setFocus(null, "desk");
      context.setTargets(allCourses, "desk");
      if (scopeNote) scopeNote.textContent = "All Current courses will be used as targets.";
      return;
    }
    var option = courseField.options[courseField.selectedIndex];
    var course = { id: selection, name: option ? option.textContent : "" };
    context.setFocus(course, "desk");
    context.setTargets([course], "desk");
    if (scopeNote) scopeNote.textContent = "Focused and target course set for this workflow.";
  }

  document.querySelectorAll("[data-desk-start]").forEach(function (link) {
    link.addEventListener("click", function () {
      applyExplicitScope();
    });
  });

  if (scanButton) {
    scanButton.addEventListener("click", function () {
      scanButton.disabled = true;
      if (localStatus) localStatus.textContent = "Scanning Current courses…";
      fetch("/api/work/scan", {
        method: "POST",
        headers: mutationHeaders(),
      }).then(responseJson).then(function (result) {
        if (!result.response.ok || !result.body.ok) {
          throw new Error(result.body.error || "scan_unavailable");
        }
        if (localStatus) {
          localStatus.textContent = result.body.partial
            ? "Scan finished with stale course data; good local results were retained."
            : "Scan complete; local projections refreshed.";
        }
        return refreshLocal();
      }).catch(function () {
        if (localStatus) localStatus.textContent = "Scan unavailable; local work is unchanged.";
      }).finally(function () {
        scanButton.disabled = false;
        scanButton.focus();
      });
    });
  }

  render();
  refreshLocal();
})();
