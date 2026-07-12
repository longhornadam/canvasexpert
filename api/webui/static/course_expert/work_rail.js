(function () {
  "use strict";

  /* Work rail — activates tabs and shows in-progress/review summaries. */

  var railItems = document.querySelectorAll("[data-rail-tab]");
  var continueEl = document.getElementById("ce-rail-continue");
  var attentionEl = document.getElementById("ce-rail-attention");

  /* ── Tab activation ────────────────────────────────────────────────── */
  railItems.forEach(function (item) {
    item.addEventListener("click", function () {
      var tab = item.getAttribute("data-rail-tab");
      var tabButton = document.getElementById("ce-tab-button-" + tab);
      if (tabButton) {
        tabButton.click();
        tabButton.focus();
      }
    });
  });

  /* ── In-progress / review summaries ────────────────────────────────── */
  function fetchWork() {
    fetch("/api/work?section=all", {
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        if (!body.ok || !Array.isArray(body.jobs)) return;
        var jobs = body.jobs;
        renderList(continueEl, jobs.filter(function (j) {
          return ["draft", "ready", "in_progress"].indexOf(j.status) !== -1;
        }), "Continue");
        renderList(attentionEl, jobs.filter(function (j) {
          return j.status === "attention";
        }), "Review");
      })
      .catch(function () { /* silent */ });
  }

  function renderList(container, jobs, label) {
    if (!container) return;
    if (!jobs.length) {
      container.innerHTML = '<p class="ce-work-rail-empty">None.</p>';
      return;
    }
    var html = "";
    jobs.forEach(function (job) {
      var title = job.title || "Work item";
      var kind = job.kind || "Work";
      var url = job.resumable_url || "/";
      html +=
        '<a class="ce-work-rail-item ce-work-rail-' +
        (label === "Review" ? "attention" : "continue") +
        '" href="' + url + '">' +
        escapeHtml(title) +
        '<span class="ce-work-rail-item-desc">' +
        escapeHtml(kind) +
        "</span></a>";
    });
    container.innerHTML = html;
  }

  function escapeHtml(s) {
    if (typeof s !== "string") return "";
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ── Active rail item tracking ─────────────────────────────────────── */
  document.addEventListener("click", function (e) {
    var tabBtn = e.target.closest(".ce-tab[data-tab]");
    if (!tabBtn) return;
    var tab = tabBtn.getAttribute("data-tab");
    railItems.forEach(function (item) {
      item.classList.toggle(
        "ce-work-rail-item--active",
        item.getAttribute("data-rail-tab") === tab
      );
    });
  });

  /* ── Initial load ──────────────────────────────────────────────────── */
  fetchWork();
})();
