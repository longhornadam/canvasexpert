(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = ["postForm", "showLog", "hideBanner", "moduleChoice", "pushContent"]
    .every(function (name) { return typeof push[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("PageForge push controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function getLog() {
    return document.getElementById("pf-log");
  }

  function getBanner() {
    return document.getElementById("pf-banner");
  }

  document.getElementById("btn-pf-validate")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("pf-file")?.value;
    if (!path) return alert("Pick a PageForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    log("Validating…\n");
    push.postForm("/api/pf/validate", { path: path })
      .then(function (d) {
        (d.problems || []).forEach(function (p) { log("✗ " + p); });
        var s = d.summary;
        if (s) {
          log((d.ok ? "✓ VALID" : "✗ INVALID") + ' — ' + s.type + ': "' + s.title + '"');
          (s.placeholders || []).forEach(function (p) {
            log("  placeholder {{" + p + "}} — resolved per course at push");
          });
        }
      })
      .catch(function (e) { if (log) log("ERROR: " + e); });
  });

  document.getElementById("btn-pf-push")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("pf-file")?.value;
    if (!path) return alert("Pick a PageForge file.");
    var payload = {
      path: path,
      published: document.getElementById("pf-publish")?.checked,
    };
    var mod = push.moduleChoice("pf-module");
    if (mod) payload.module_name = mod;
    push.pushContent("pf", payload, getLog(), getBanner(), this,
      'Push PageForge file "' + path.split(/[\\/]/).pop() + '"' +
      (payload.published ? " (PUBLISHED)" : " (unpublished)"));
  });

  // ── Prepare publication (operation-ledger path) ──────────────────────
  function getCsrfToken() {
    var meta = document.querySelector('meta[name="canvasexpert-csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CanvasExpert-CSRF": getCsrfToken(),
      },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); });
  }

  function renderOperationsList() {
    var container = document.getElementById("ce-operations-list");
    if (!container) return;
    fetch("/api/operations")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var ops = data.operations || [];
        if (!ops.length) {
          container.innerHTML = '<p class="ce-operations-empty">Canvas unchanged.</p>';
          return;
        }
        container.innerHTML = ops.map(function (op) {
          var statusClass = "ce-op-status-" + op.status;
          var buttons = "";
          if (op.status === "reviewed") {
            buttons += '<button class="ce-op-review primary" data-op-id="' + op.operation_id + '">Review &amp; Apply</button> ';
          }
          if (op.status === "attention" || op.status === "partial" || op.status === "failed") {
            buttons += '<button class="ce-op-retry secondary" data-op-id="' + op.operation_id + '">Retry</button>';
          }
          return '<div class="ce-operation-item ' + statusClass + '">' +
            '<span class="ce-op-kind">' + op.kind + '</span> ' +
            '<span class="ce-op-status">' + op.status + '</span> ' +
            '<span class="ce-op-targets">' + op.target_count + ' target(s)</span> ' +
            buttons + '</div>';
        }).join("");

        // Wire buttons
        container.querySelectorAll(".ce-op-review").forEach(function (btn) {
          btn.addEventListener("click", function () { reviewAndApply(btn.dataset.opId); });
        });
        container.querySelectorAll(".ce-op-retry").forEach(function (btn) {
          btn.addEventListener("click", function () { retryOperation(btn.dataset.opId); });
        });
      })
      .catch(function () { /* silent — will retry on next render */ });
  }

  function reviewAndApply(operationId) {
    // Freeze a review batch for this operation
    postJson("/api/operation-batches/review", { operation_ids: [operationId] })
      .then(function (batchData) {
        if (!batchData.ok) return alert(batchData.error || "Review failed.");
        var frozen = batchData.frozen_reviews || [];
        var targets = frozen.map(function (f) {
          return { name: f.course_name };
        });
        var details = [];
        if (frozen.length) {
          var f0 = frozen[0];
          details.push("Page: " + (f0.page_title || "(untitled)"));
          details.push("Published: " + (f0.published ? "yes" : "no"));
          if (f0.module_name) details.push("Module: " + f0.module_name);
        }
        var ok = window.CE_WRITE_REVIEW.confirm({
          title: "Review page publication",
          action: "Publish " + (frozen.length ? frozen[0].page_title : "page") +
            " to " + frozen.length + " course(s)",
          targets: targets,
          details: details,
          warnings: ["This will create a new page in each target course."],
          confirmText: "Apply to Canvas",
          cancelText: "Cancel",
        });
        ok.then(function (confirmed) {
          if (!confirmed) return;
          postJson("/api/operation-batches/" + batchData.batch_id + "/apply", {
            review_digest: batchData.review_digest,
          }).then(function (applyData) {
            if (!applyData.ok) {
              alert(applyData.error || "Apply failed.");
            }
            renderOperationsList();
          }).catch(function (e) { alert("Apply error: " + e); });
        });
      })
      .catch(function (e) { alert("Review error: " + e); });
  }

  function retryOperation(operationId) {
    postJson("/api/operations/" + operationId + "/retry", {})
      .then(function (data) {
        if (!data.ok) alert(data.error || "Retry failed.");
        renderOperationsList();
      })
      .catch(function (e) { alert("Retry error: " + e); });
  }

  document.getElementById("btn-pf-prepare")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("pf-file")?.value;
    if (!path) return alert("Pick a PageForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    log("Preparing publication…\n");

    var payload = {
      path: path,
      published: document.getElementById("pf-publish")?.checked,
    };
    var mod = push.moduleChoice("pf-module");
    if (mod) payload.module_name = mod;

    postJson("/api/operations/content.page/prepare", payload)
      .then(function (d) {
        if (!d.ok) {
          log("✗ PREPARE FAILED: " + (d.error || "unknown error"));
          return;
        }
        log("✓ Prepared operation " + d.operation_id);
        var s = d.review_summary || {};
        log("  kind: " + s.kind + ", targets: " + s.target_count);
        (s.frozen_reviews || []).forEach(function (f) {
          log('  → ' + f.course_name + ': "' + f.page_title + '"' +
            (f.published ? " (published)" : " (unpublished)") +
            (f.module_name ? ' → module "' + f.module_name + '"' : ""));
        });
        renderOperationsList();
      })
      .catch(function (e) { if (log) log("ERROR: " + e); });
  });

  // Render the operations list on page load
  renderOperationsList();
})();
