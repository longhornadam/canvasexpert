(function () {
  "use strict";

  function tabButtons() {
    return Array.prototype.slice.call(document.querySelectorAll(".ce-tab[role='tab']"));
  }

  function activateTab(tabName, options) {
    var shouldFocus = options && options.focus;
    var activated = false;
    document.querySelectorAll(".ce-tab").forEach(function (tab) {
      var isActive = tab.dataset.tab === tabName;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.tabIndex = isActive ? 0 : -1;
      if (isActive) {
        activated = true;
        if (shouldFocus) tab.focus();
      }
    });
    document.querySelectorAll(".ce-panel").forEach(function (panel) {
      var isActive = panel.id === "ce-tab-" + tabName;
      panel.classList.toggle("active", isActive);
      panel.hidden = !isActive;
      panel.inert = !isActive;
    });
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
    var known = Array.prototype.some.call(document.querySelectorAll(".ce-tab"), function (el) {
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

  bindTabButtons();
  bindDeepLink();
  bindDeliveryToggles();
  bindQuizModeToggle();
  bindFileSources();
  bindCopySkill();
  bindCoursePickerDismiss();
})();
