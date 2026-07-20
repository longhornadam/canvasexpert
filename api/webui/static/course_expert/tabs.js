(function () {
  "use strict";

  function tabButtons() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-ce-hook="course-tab"][role="tab"]'));
  }

  function updateWorkspaceTitle(tabName) {
    var title = document.getElementById("ce-workspace-title");
    if (!title) return;
    var tab = document.querySelector('[data-ce-hook="course-tab"][data-tab="' + tabName + '"]');
    title.textContent = tab ? tab.textContent.trim() : "Workspace";
  }

  function activateTab(tabName, options) {
    var shouldFocus = options && options.focus;
    var activated = false;
    document.querySelectorAll('[data-ce-hook="course-tab"]').forEach(function (tab) {
      var isActive = tab.dataset.tab === tabName;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.tabIndex = isActive ? 0 : -1;
      if (isActive) {
        activated = true;
        if (shouldFocus) tab.focus();
      }
    });
    document.querySelectorAll('[data-ce-hook="course-tab-panel"]').forEach(function (panel) {
      var isActive = panel.id === "ce-tab-" + tabName;
      panel.classList.toggle("active", isActive);
      panel.hidden = !isActive;
      panel.inert = !isActive;
    });
    if (activated) updateWorkspaceTitle(tabName);
    return activated;
  }

  function bindTabButtons() {
    var tabs = tabButtons();
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab.dataset.tab);
      });
      tab.addEventListener("keydown", function (event) {
        var keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
        if (keys.indexOf(event.key) === -1) return;
        event.preventDefault();
        var currentIndex = tabs.indexOf(tab);
        var nextIndex = currentIndex;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = tabs.length - 1;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (currentIndex + 1) % tabs.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        activateTab(tabs[nextIndex].dataset.tab, { focus: true });
      });
    });
  }

  function bindDeepLink() {
    var params = new URLSearchParams(location.search);
    var tab = params.get("tab") || location.hash.replace("#", "");
    var known = Array.prototype.some.call(document.querySelectorAll('[data-ce-hook="course-tab"]'), function (el) {
      return el.dataset.tab === tab;
    });
    if (tab && known) {
      activateTab(tab);
    }
  }

  function bindDeliveryToggles() {
    var accessCodeEnable = document.getElementById("access-code-enable");
    if (accessCodeEnable) {
      accessCodeEnable.addEventListener("change", function () {
        document.getElementById("access-code-wrap").hidden = !this.checked;
        if (this.checked) document.getElementById("access-code").focus();
      });
    }

    var allowAttempts = document.getElementById("allow-attempts");
    if (allowAttempts) {
      allowAttempts.addEventListener("change", function () {
        document.getElementById("attempts-wrap").hidden = !this.checked;
      });
    }

    var hasTimeLimit = document.getElementById("has-time-limit");
    if (hasTimeLimit) {
      hasTimeLimit.addEventListener("change", function () {
        document.getElementById("time-limit-wrap").hidden = !this.checked;
        if (this.checked) document.getElementById("time-limit-minutes").focus();
      });
    }

    var oneAtATime = document.getElementById("one-at-a-time");
    if (oneAtATime) {
      oneAtATime.addEventListener("change", function () {
        document.getElementById("one-at-a-time-wrap").hidden = !this.checked;
      });
    }
  }

  function bindQuizModeToggle() {
    var segments = document.querySelectorAll(".mode-seg");
    var diffCard = document.getElementById("quiz-diff");
    if (!segments.length || !diffCard) return;

    segments.forEach(function (seg) {
      seg.addEventListener("click", function () {
        segments.forEach(function (s) {
          s.classList.toggle("active", s === seg);
        });
        diffCard.hidden = seg.dataset.mode !== "diff";
        if (seg.dataset.mode === "diff" && typeof window.QF_loadGroups === "function") {
          window.QF_loadGroups();
        }
      });
    });
  }

  function bindFileSources() {
    document.querySelectorAll(".file-source").forEach(function (wrapper) {
      if (typeof initFileSource === "function") initFileSource(wrapper);
    });
  }

  function bindCopySkill() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest(".btn-copy-skill");
      if (button && typeof copySkill === "function") copySkill(button.dataset.name, button);
    });
  }

  function bindCoursePickerDismiss() {
    var picker = document.getElementById("ce-course-picker");
    if (!picker) return;
    document.addEventListener("click", function (event) {
      if (picker.open && !event.target.closest("#ce-course-picker")) picker.open = false;
    });
  }

  window.CE_COURSE_EXPERT = Object.assign(window.CE_COURSE_EXPERT || {}, {
    activateTab: activateTab,
  });

  /* ── Instrument view (slice 09) ────────────────────────────────────── */

  function currentView() {
    var params = new URLSearchParams(location.search);
    var view = params.get("view");
    return view === "instrument" ? "instrument" : "workbench";
  }

  function setView(view, options) {
    var params = new URLSearchParams(location.search);
    var tab = params.get("tab") || "";
    var shell = document.querySelector('[data-ce-hook="course-shell"]');
    var rail = document.querySelector('[data-ce-hook="course-rail"]');
    var summary = document.querySelector('[data-ce-hook="course-summary"]');

    if (view === "instrument") {
      if (shell) shell.classList.add("ce-course-expert--instrument");
      if (rail) rail.hidden = true;
      if (summary) summary.hidden = true;
    } else {
      if (shell) shell.classList.remove("ce-course-expert--instrument");
      if (rail) rail.hidden = false;
      if (summary) summary.hidden = false;
    }

    if (options && options.replace) {
      var newParams = new URLSearchParams();
      if (tab) newParams.set("tab", tab);
      if (view !== "workbench") newParams.set("view", view);
      var qs = newParams.toString();
      var url = qs ? location.pathname + "?" + qs : location.pathname;
      history.replaceState({ view: view, tab: tab }, "", url);
    } else {
      var newParams2 = new URLSearchParams(location.search);
      if (view !== "workbench") newParams2.set("view", view);
      else newParams2.delete("view");
      var qs2 = newParams2.toString();
      var url2 = qs2 ? location.pathname + "?" + qs2 : location.pathname;
      history.pushState({ view: view, tab: tab }, "", url2);
    }
  }

  function toggleInstrument() {
    var view = currentView() === "instrument" ? "workbench" : "instrument";
    setView(view);
  }

  /* Expose for instrument.js */
  window.CE_COURSE_EXPERT.currentView = currentView;
  window.CE_COURSE_EXPERT.setView = setView;
  window.CE_COURSE_EXPERT.toggleInstrument = toggleInstrument;

  /* Bind instrument toggle to any [data-instrument-toggle] */
  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-instrument-toggle]");
    if (btn) {
      event.preventDefault();
      toggleInstrument();
    }
  });

  /* Apply view on load */
  (function applyInitialView() {
    var view = currentView();
    if (view === "instrument") {
      setView("instrument", { replace: true });
    }
  })();

  /* popstate: reapply tab + view without adding history */
  window.addEventListener("popstate", function (event) {
    if (event.state && event.state.tab) {
      activateTab(event.state.tab);
    }
    var view = event.state && event.state.view ? event.state.view : "workbench";
    setView(view, { replace: true });
  });

  bindTabButtons();
  bindDeepLink();
  bindDeliveryToggles();
  bindQuizModeToggle();
  bindFileSources();
  bindCopySkill();
  bindCoursePickerDismiss();
})();
