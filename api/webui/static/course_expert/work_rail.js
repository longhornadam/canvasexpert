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
  // No freshness line lives on this page (unlike desk.js's Home cards), so a
  // failed check must say so rather than leave the server's default markup
  // ("None.") standing in for a real answer -- that silence is exactly what
  // makes a broken check look identical to nothing-in-progress.
  function fetchWork() {
    fetch("/api/work?section=all", {
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("work request failed");
        return r.json();
      })
      .then(function (body) {
        if (!body || body.ok !== true || !Array.isArray(body.jobs)) {
          throw new Error("invalid work response");
        }
        var jobs = body.jobs;
        renderList(continueEl, jobs.filter(function (j) {
          return ["draft", "ready", "in_progress"].indexOf(j.status) !== -1;
        }), "Continue");
        renderList(attentionEl, jobs.filter(function (j) {
          return j.status === "attention";
        }), "Review");
      })
      .catch(function () {
        renderDegraded(continueEl);
        renderDegraded(attentionEl);
      });
  }

  function renderDegraded(container) {
    if (!container) return;
    container.innerHTML = '<p class="ce-work-rail-empty">Work status couldn&rsquo;t be checked. Starting new work above still works.</p>';
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
  function syncActive(tab) {
    railItems.forEach(function (item) {
      item.classList.toggle(
        "ce-work-rail-item--active",
        item.getAttribute("data-rail-tab") === tab
      );
    });
  }

  function currentTab() {
    var active = document.querySelector('[data-ce-hook="course-tab"][aria-selected="true"]')
      || document.querySelector('[data-ce-hook="course-tab"].active');
    return active ? active.getAttribute("data-tab") : "";
  }

  document.addEventListener("click", function (e) {
    var tabBtn = e.target.closest('[data-ce-hook="course-tab"][data-tab]');
    if (!tabBtn) return;
    syncActive(tabBtn.getAttribute("data-tab"));
  });

  /* ── Initial load ──────────────────────────────────────────────────── */
  // Mark the tab the page opened on, including a ?tab= deep link, so the rail
  // never sits blank while the stage shows a tab.
  syncActive(currentTab());
  window.addEventListener("load", function () { syncActive(currentTab()); });
  fetchWork();
})();
