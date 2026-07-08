(function () {
  "use strict";

  var CE = window.CE_SETTINGS = window.CE_SETTINGS || {};

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, function (c) {
        return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
      });
  }

  function isHidden(el) {
    return !el || el.style.display === "none";
  }

  function setStatus(el, msg, kind) {
    if (!el) return;
    el.textContent = msg;
    el.className = "status" + (kind ? " " + kind : "");
  }

  CE.esc = CE.esc || esc;
  CE.isHidden = CE.isHidden || isHidden;
  CE.setStatus = CE.setStatus || setStatus;
})();
