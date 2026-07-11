(function () {
  "use strict";

  var root = document.getElementById("desk-root");
  if (!root) return;

  var dataScript = document.getElementById("desk-initial-data");
  var initial = { jobs: [], receipts: [] };
  try {
    initial = JSON.parse(dataScript ? dataScript.textContent : "{}") || initial;
  } catch (e) {
    initial = { jobs: [], receipts: [] };
  }

  var state = {
    jobs: Array.isArray(initial.jobs) ? initial.jobs : [],
    receipts: Array.isArray(initial.receipts) ? initial.receipts : [],
  };
  var continueList = document.getElementById("desk-continue-list");
  var attentionList = document.getElementById("desk-attention-list");
  var receiptsList = document.getElementById("desk-receipts-list");
  var localStatus = document.getElementById("desk-local-status");
  var scanButton = document.getElementById("desk-scan");
  var courseField = document.getElementById("desk-course-field");
  var scopeNote = document.getElementById("desk-scope-note");
  var csrfMeta = document.querySelector('meta[name="canvasexpert-csrf-token"]');

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
      emptyList(node, actionLabel === "Review" ? "No current attention items." : "No local work to continue.");
      return;
    }
    clear(node);
    jobs.forEach(function (job) {
      var article = element("article", "ce-desk-job");
      article.dataset.jobId = job.job_id;
      article.dataset.materialVersion = job.material_version;
      article.dataset.origin = job.origin;

      var detail = element("div");
      detail.appendChild(element("strong", "", job.title || "Work item"));
      var counts = job.counts || {};
      var summary = actionLabel === "Review"
        ? (job.attention_reason || "Work needs attention")
        : ((job.kind || "Work") + " · " + (counts.total || 0) + " items");
      detail.appendChild(element("span", "", summary));
      article.appendChild(detail);

      var link = element("a", "ce-desk-inline-link", actionLabel);
      link.href = job.resumable_url || "/";
      article.appendChild(link);
      article.appendChild(jobActions(job));
      node.appendChild(article);
    });
  }

  function renderReceipts() {
    if (!receiptsList) return;
    if (!state.receipts.length) {
      emptyList(receiptsList, "No receipts recorded yet.");
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

  function render() {
    renderJobList(continueList, state.jobs.filter(function (job) {
      return ["draft", "ready", "in_progress"].indexOf(job.status) !== -1;
    }), "Continue");
    renderJobList(attentionList, state.jobs.filter(function (job) {
      return job.status === "attention";
    }), "Review");
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
      fetch("/api/receipts", { headers: { "Accept": "application/json" } }).then(responseJson),
    ]).then(function (results) {
      var workResult = results[0];
      var receiptResult = results[1];
      if (!workResult.response.ok || !workResult.body.ok) throw new Error("work_unavailable");
      if (!receiptResult.response.ok || !receiptResult.body.ok) throw new Error("receipts_unavailable");
      state.jobs = Array.isArray(workResult.body.jobs) ? workResult.body.jobs : [];
      state.receipts = Array.isArray(receiptResult.body.receipts) ? receiptResult.body.receipts : [];
      render();
      if (localStatus) localStatus.textContent = "Using current local projections.";
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
    var context = window.CE_CONTEXT;
    var selection = courseField ? courseField.value : "";
    if (!context || !selection) return;
    if (selection === "__all__") {
      var allCourses = Array.from(courseField.options).filter(function (option) {
        return option.value && option.value !== "__all__";
      }).map(function (option) {
        return { id: option.value, name: option.textContent };
      });
      context.setFocus(null, "desk");
      context.setTargets(allCourses, "desk");
      if (scopeNote) scopeNote.textContent = "All active courses will be used as targets.";
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
      if (localStatus) localStatus.textContent = "Scanning active courses…";
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
