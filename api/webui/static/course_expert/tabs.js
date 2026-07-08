(function () {
  "use strict";

  function activateTab(tabName) {
    document.querySelectorAll(".ce-tab").forEach(function (tab) {
      tab.classList.toggle("active", tab.dataset.tab === tabName);
    });
    document.querySelectorAll(".ce-panel").forEach(function (panel) {
      panel.classList.toggle("active", panel.id === "ce-tab-" + tabName);
    });
  }

  function bindTabButtons() {
    document.querySelectorAll(".ce-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab.dataset.tab);
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
