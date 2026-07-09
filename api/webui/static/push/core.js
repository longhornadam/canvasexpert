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

  function canvasWriteReview(options) {
    options = options || {};
    return new Promise(function (resolve) {
      var previousFocus = document.activeElement;
      var backdrop = document.createElement("div");
      backdrop.className = "ce-review-backdrop";
      var titleId = "ce-review-title-" + Math.random().toString(36).slice(2);
      var details = options.details || [];
      var targets = options.targets || [];
      var warnings = options.warnings || [];
      var targetHtml = targets.length
        ? '<ul class="ce-review-list">' + targets.map(function (t) {
          var label = t.name || t.label || "Course";
          var id = t.id ? " (#" + t.id + ")" : "";
          return "<li>" + esc(label) + esc(id) + "</li>";
        }).join("") + "</ul>"
        : '<p class="hint">No target selected.</p>';
      var detailsHtml = details.length
        ? '<ul class="ce-review-list">' + details.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") + "</ul>"
        : "";
      var warningsHtml = warnings.length
        ? '<div class="ce-review-warning"><strong>Canvas effects</strong><ul>' +
          warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul></div>"
        : "";
      backdrop.innerHTML =
        '<div class="ce-review-dialog" role="dialog" aria-modal="true" aria-labelledby="' + titleId + '">' +
          '<h3 id="' + titleId + '">' + esc(options.title || "Review Canvas write") + "</h3>" +
          '<p class="ce-review-action">' + esc(options.action || "Review this Canvas change before continuing.") + "</p>" +
          '<div class="ce-review-section"><strong>Target</strong>' + targetHtml + "</div>" +
          (detailsHtml ? '<div class="ce-review-section"><strong>Change</strong>' + detailsHtml + "</div>" : "") +
          warningsHtml +
          '<div class="ce-review-actions">' +
            '<button type="button" class="secondary ce-review-cancel">' + esc(options.cancelText || "Cancel") + "</button>" +
            '<button type="button" class="danger ce-review-confirm">' + esc(options.confirmText || "Write to Canvas") + "</button>" +
          "</div>" +
        "</div>";
      function close(ok) {
        document.removeEventListener("keydown", onKey);
        backdrop.remove();
        if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
        resolve(ok);
      }
      function onKey(event) {
        if (event.key === "Escape") close(false);
      }
      backdrop.addEventListener("click", function (event) {
        if (event.target === backdrop) close(false);
      });
      backdrop.querySelector(".ce-review-cancel").addEventListener("click", function () { close(false); });
      backdrop.querySelector(".ce-review-confirm").addEventListener("click", function () { close(true); });
      document.addEventListener("keydown", onKey);
      document.body.appendChild(backdrop);
      backdrop.querySelector(".ce-review-confirm").focus();
    });
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

  async function pushContent(kind, payload, logEl, bannerEl, btn, confirmLabel) {
    var push = window.CE_PUSH || {};
    var targets = typeof push.targetCourses === "function" ? push.targetCourses() : [];
    if (!targets.length) return alert("Check at least one course on the right.");
    var effects = describeContentEffects(payload);
    var ok = await canvasWriteReview({
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
    showLog: showLog,
    hideBanner: hideBanner,
    pushContent: pushContent,
    canvasWriteReview: canvasWriteReview,
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
})();
