(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, function (c) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[c];
      });
  }

  function showLog(el) {
    el.hidden = false;
    el.textContent = "";
    return function (line) {
      el.textContent += line + "\n";
      el.scrollTop = el.scrollHeight;
    };
  }

  function hideBanner(el) {
    if (!el) return;
    el.hidden = true;
    el.className = "push-banner";
    el.innerHTML = "";
  }

  function showBanner(el, kind, html) {
    if (!el) return;
    el.hidden = false;
    el.className = "push-banner " + kind;
    el.innerHTML = html;
  }

  function describeContentEffects(payload) {
    payload = payload || {};
    var details = [];
    var warnings = [];
    if (payload.path) details.push("Source file: " + payload.path.split(/[\\/]/).pop());
    if (payload.module_name) details.push("Add to module: " + payload.module_name);
    if (payload.assignment_group_name) details.push("Assignment group: " + payload.assignment_group_name);
    if (payload.due_at) details.push("Due: " + payload.due_at);
    if (payload.unlock_at) details.push("Unlock: " + payload.unlock_at);
    if (payload.lock_at) details.push("Lock: " + payload.lock_at);
    if (payload.rubric_path) details.push("Rubric: " + payload.rubric_path.split(/[\\/]/).pop() + " (" + (payload.rubric_mode || "grading") + ")");
    warnings.push(payload.published ? "Item will be published for students." : "Item will be created unpublished.");
    if (payload.post_to_sis) warnings.push("Post to SIS is enabled where Canvas supports it.");
    if (payload.autoscore_schedule) {
      warnings.push("Scheduled Auto-Score is enabled for this assignment and creates draft AI suggestions after the due date.");
    }
    if (payload.autoscore_auto_push) {
      warnings.push("Scheduled auto-push is enabled only for eligible reviewed cases for this assignment.");
    }
    return { details: details, warnings: warnings };
  }

  var allBusyBtns = "#btn-validate,#btn-preview,#btn-push,#btn-push-variants,#btn-add-variant";

  function setBusy(v) {
    document.querySelectorAll(allBusyBtns).forEach(function (b) {
      b.disabled = v;
    });
  }

  async function postForm(url, fields) {
    return fetch(url, { method: "POST", body: new URLSearchParams(fields) })
      .then(function (r) { return r.json(); });
  }

  function renderBanner(el, results, exitOk) {
    if (!el) return;
    if (!results.length && !exitOk) {
      showBanner(el, "fail", "✗ Push failed — check the log above.");
      return;
    }
    if (!results.length) return;
    var allOk = results.every(function (r) { return r.ok; });
    var kind = allOk && exitOk ? "ok" : "warn";
    var lines = results.map(function (r) {
      var link = r.url
        ? ' — <a href="' + esc(r.url) + '" target="_blank" rel="noopener">Open in Canvas ↗</a>'
        : "";
      var icon = r.ok ? "✓" : "⚠";
      return icon + " <strong>" + esc(r.title) + "</strong>" + link;
    }).join("<br>");
    showBanner(el, kind, lines);
  }

  function streamSSE(url, logFn, bannerEl, onDone) {
    hideBanner(bannerEl);
    var canvasUrl = null;
    var resultLines = [];
    var es = new EventSource(url);
    es.onmessage = function (ev) {
      var line = JSON.parse(ev.data);
      if (line.startsWith("  CANVAS_URL: ")) {
        canvasUrl = line.slice("  CANVAS_URL: ".length).trim();
        return;
      }
      if (line.startsWith("  PUSH_OK: ")) {
        var title = line.slice("  PUSH_OK: ".length).trim();
        resultLines.push({ ok: true, title: title, url: canvasUrl });
        canvasUrl = null;
        logFn(line);
        return;
      }
      if (line.startsWith("  PUSH_WARN: ")) {
        var msg = line.slice("  PUSH_WARN: ".length).trim();
        resultLines.push({ ok: false, title: msg, url: canvasUrl });
        canvasUrl = null;
        logFn(line);
        return;
      }
      logFn(line);
      if (/^\[exit \d+\]$/.test(line)) {
        es.close();
        renderBanner(bannerEl, resultLines, line === "[exit 0]");
        if (onDone) onDone(line === "[exit 0]");
      }
    };
    es.onerror = function () {
      es.close();
      if (onDone) onDone(false);
    };
  }

  async function generatePhysical(path, logFn, bannerEl) {
    logFn("\nGenerating printable version (PDF + DOCX)…");
    try {
      var d = await postForm("/api/physical/quiz", { path: path });
      if (!d.ok) {
        logFn("⚠ Printable version failed: " + (d.error || "unknown error"));
        return;
      }
      logFn("✓ Printable version saved to: " + d.folder);
      (d.files || []).forEach(function (f) { logFn("    · " + f); });
      (d.warnings || []).forEach(function (w) { logFn("    ⚠ " + w); });
      if (d.fallback) {
        logFn("    (No OneDrive workspace found — saved to this PC's local Finished_Exports folder.)");
      }
      if (bannerEl) {
        var prev = bannerEl.hidden ? "" : bannerEl.innerHTML;
        var note = d.fallback
          ? '<br><span class="hint">No OneDrive workspace found — saved to this PC at the path above.</span>'
          : "";
        showBanner(
          bannerEl,
          bannerEl.classList.contains("fail") ? "warn" : "ok",
          (prev ? prev + "<br>" : "") +
          "📄 Printable PDF + DOCX saved to <code>" + esc(d.folder) + "</code> — " +
          '<a href="#" data-open-folder="' + esc(d.folder) + '">Open folder ↗</a>' + note
        );
        bannerEl.querySelector("[data-open-folder]")?.addEventListener("click", async function (e) {
          e.preventDefault();
          var r = await postForm("/api/open-path", { path: d.folder });
          if (r && r.ok === false) logFn("⚠ Could not open folder automatically — it's at: " + d.folder);
        });
      }
    } catch (e) {
      logFn("⚠ Printable version failed: " + e);
    }
  }

  var operationKinds = {
    quick: "content.quick_assignment",
    af: "content.assignment",
    pf: "content.page",
    rf: "content.rubric",
  };

  function csrfToken() {
    var meta = document.querySelector('meta[name="canvasexpert-csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  async function postJson(url, body) {
    var response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CanvasExpert-CSRF": csrfToken(),
      },
      body: JSON.stringify(body),
    });
    var data;
    try {
      data = await response.json();
    } catch (e) {
      data = { ok: false, error: "Server returned an unreadable response." };
    }
    if (!response.ok) {
      throw new Error(data.error || data.detail || ("Request failed (HTTP " + response.status + ")"));
    }
    return data;
  }

  function operationTargets() {
    var push = window.CE_PUSH || {};
    var selected = typeof push.targetCourses === "function" ? push.targetCourses() : [];
    return selected.map(function (target) {
      return { course_id: String(target.id) };
    });
  }

  function frozenReviewOptions(frozen, confirmLabel) {
    var first = frozen[0] || {};
    var details = [];
    var warnings = [];
    if (first.assignment_name) details.push("Assignment: " + first.assignment_name);
    if (first.page_title) details.push("Page: " + first.page_title);
    if (first.rubric_title) details.push("Rubric: " + first.rubric_title);
    if (first.points != null) details.push("Points: " + first.points);
    if (first.total_points != null) details.push("Rubric points: " + first.total_points);
    if (first.criteria_count != null) details.push("Criteria: " + first.criteria_count);
    if (first.due_at) details.push("Due: " + first.due_at);
    if (first.module_name) details.push("Module: " + first.module_name);
    if (first.student_page_title) details.push("Student page: " + first.student_page_title);
    if (first.post_to_sis) details.push("Sync to SIS: yes");
    if (first.published === true) warnings.push("The item will be published for students.");
    if (first.published === false) warnings.push("The item will be created unpublished.");
    if (first.autoscore && first.autoscore.scheduled) {
      warnings.push("Scheduled Auto-Score will create draft AI suggestions after the due date.");
      if (first.autoscore.auto_push) {
        warnings.push("Per-assignment auto-push is enabled only for policy-eligible cases.");
      }
    }
    if (first.tiered) {
      frozen.forEach(function (review) {
        (review.tiers || []).forEach(function (tier) {
          details.push((review.course_name || "Course") + " — " + tier.label +
            ": " + tier.group + " (" + tier.student_count + " students)");
        });
      });
      warnings.push("Canvas will create one assignment/gradebook column per tier.");
      warnings.push("Only that group's students can see each assignment (only_visible_to_overrides=true).");
    }
    return {
      title: "Review Canvas content push",
      action: confirmLabel || "Review this Canvas change before continuing.",
      targets: frozen.map(function (review) { return { name: review.course_name }; }),
      details: details,
      warnings: warnings,
      confirmText: "Apply to Canvas",
      cancelText: "Cancel",
    };
  }

  async function reviewAndApply(operationId, logFn, bannerEl, confirmLabel) {
    var batch = await postJson("/api/operation-batches/review", {
      operation_ids: [operationId],
    });
    var confirmed = await window.CE_WRITE_REVIEW.confirm(
      frozenReviewOptions(batch.frozen_reviews || [], confirmLabel)
    );
    if (!confirmed) {
      if (logFn) logFn("Canvas unchanged. The prepared operation remains available for later review.");
      renderOperationsList();
      return { cancelled: true };
    }
    var applied = await postJson(
      "/api/operation-batches/" + encodeURIComponent(batch.batch_id) + "/apply",
      { review_digest: batch.review_digest }
    );
    if (logFn) {
      (applied.target_results || []).forEach(function (result, index) {
        var review = (batch.frozen_reviews || [])[index] || {};
        logFn((result.state === "applied" ? "✓ " : "⚠ ") +
          (review.course_name || "Target") + ": " + result.state);
      });
    }
    showBanner(
      bannerEl,
      applied.status === "applied" ? "ok" : "warn",
      applied.status === "applied" ? "✓ Canvas changes applied." : "⚠ Operation needs attention."
    );
    renderOperationsList();
    return applied;
  }

  async function prepareOperation(kind, payload, logFn) {
    var targets = operationTargets();
    if (!targets.length) throw new Error("Check at least one course on the right.");
    var prepared = await postJson(
      "/api/operations/" + encodeURIComponent(kind) + "/prepare",
      { payload: payload, targets: targets }
    );
    if (logFn) logFn("✓ Prepared operation " + prepared.operation_id);
    renderOperationsList();
    return prepared;
  }

  async function prepareOnly(kind, payload, logEl, bannerEl, btn) {
    var log = showLog(logEl);
    hideBanner(bannerEl);
    if (btn) btn.disabled = true;
    try {
      return await prepareOperation(kind, payload, log);
    } catch (e) {
      log("ERROR: " + e.message);
      showBanner(bannerEl, "fail", "✗ " + esc(e.message));
      return null;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function renderOperationsList() {
    var container = document.getElementById("ce-operations-list");
    if (!container) return;
    fetch("/api/operations")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var ops = data.operations || [];
        if (!ops.length) {
          container.innerHTML = '<p class="ce-operations-empty">Canvas unchanged.</p>';
          return;
        }
        container.innerHTML = ops.map(function (op) {
          var buttons = "";
          if (op.status === "prepared" || op.status === "reviewed") {
            buttons += '<button class="ce-op-review primary" data-op-id="' + esc(op.operation_id) + '">Review &amp; Apply</button> ';
          }
          if (["attention", "partial", "failed"].indexOf(op.status) >= 0) {
            buttons += '<button class="ce-op-retry secondary" data-op-id="' + esc(op.operation_id) + '">Retry</button>';
          }
          return '<div class="ce-operation-item ce-op-status-' + esc(op.status) + '">' +
            '<span class="ce-op-kind">' + esc(op.kind) + '</span> ' +
            '<span class="ce-op-status">' + esc(op.status) + '</span> ' +
            '<span class="ce-op-targets">' + Number(op.target_count || 0) + ' target(s)</span> ' +
            buttons + '</div>';
        }).join("");
      })
      .catch(function () {});
  }

  document.addEventListener("click", function (event) {
    var reviewBtn = event.target.closest(".ce-op-review");
    if (reviewBtn) {
      reviewBtn.disabled = true;
      reviewAndApply(reviewBtn.dataset.opId, null, null)
        .catch(function (e) { alert(e.message); })
        .finally(function () { reviewBtn.disabled = false; });
      return;
    }
    var retryBtn = event.target.closest(".ce-op-retry");
    if (retryBtn) {
      retryBtn.disabled = true;
      postJson("/api/operations/" + encodeURIComponent(retryBtn.dataset.opId) + "/retry", {})
        .catch(function (e) { alert(e.message); })
        .finally(function () { retryBtn.disabled = false; renderOperationsList(); });
    }
  });

  async function pushContent(kind, payload, logEl, bannerEl, btn, confirmLabel) {
    var push = window.CE_PUSH || {};
    var targets = typeof push.targetCourses === "function" ? push.targetCourses() : [];
    if (!targets.length) return alert("Check at least one course on the right.");
    var operationKind = operationKinds[kind];
    if (operationKind) {
      var log = showLog(logEl);
      hideBanner(bannerEl);
      btn.disabled = true;
      try {
        var prepared = await prepareOperation(operationKind, payload, log);
        await reviewAndApply(prepared.operation_id, log, bannerEl, confirmLabel);
      } catch (e) {
        log("ERROR: " + e.message);
        showBanner(bannerEl, "fail", "✗ " + esc(e.message));
      } finally {
        btn.disabled = false;
      }
      return;
    }
    var effects = describeContentEffects(payload);
    var ok = await window.CE_WRITE_REVIEW.confirm({
      title: "Review Canvas content push",
      action: confirmLabel,
      targets: targets,
      details: effects.details.concat(["Canvas instance: " + (window.QF_CANVAS_BASE || "(configured Canvas)")]),
      warnings: effects.warnings,
      confirmText: "Push to Canvas",
    });
    if (!ok) return;
    var log = showLog(logEl);
    hideBanner(bannerEl);
    btn.disabled = true;
    log("Pushing…\n");
    postForm("/api/content/push", {
      kind: kind,
      courses: JSON.stringify(targets),
      payload: JSON.stringify(payload),
    }).then(function (d) {
      if (d.error) {
        log("ERROR: " + d.error);
        showBanner(bannerEl, "fail", "✗ " + esc(d.error));
        return;
      }
      var results = d.results || [];
      results.forEach(function (r) {
        log((r.ok ? "✓" : "✗") + " " + r.course_name + ": " + (r.ok ? r.title : (r.error || "failed")));
        (r.notes || []).forEach(function (n) { log("    · " + n); });
      });
      renderBanner(bannerEl, results.map(function (r) {
        return {
          ok: r.ok,
          title: r.course_name + " — " + (r.ok ? r.title : (r.error || "failed")),
          url: r.url,
        };
      }), d.ok);
    }).catch(function (e) {
      log("ERROR: " + e);
      showBanner(bannerEl, "fail", "✗ " + esc(String(e)));
    }).finally(function () {
      btn.disabled = false;
    });
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    postForm: postForm,
    postJson: postJson,
    showLog: showLog,
    hideBanner: hideBanner,
    pushContent: pushContent,
    prepareOnly: prepareOnly,
    reviewAndApply: reviewAndApply,
    renderOperationsList: renderOperationsList,
    operationKinds: operationKinds,
    canvasWriteReview: window.CE_WRITE_REVIEW.confirm,
    describeContentEffects: describeContentEffects,
    generatePhysical: generatePhysical,
    esc: esc,
    showBanner: showBanner,
    setBusy: setBusy,
    streamSSE: streamSSE,
  });

  window.esc = esc;
  window.postForm = postForm;
  window.pushContent = pushContent;
  renderOperationsList();
})();
