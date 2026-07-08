(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};

  var processBtn = document.getElementById("fx-process");
  if (processBtn) {
    processBtn.addEventListener("click", function () {
      CE.runStep("/api/feedback/process-inbox", this,
        document.getElementById("fx-process-status"),
        document.getElementById("fx-process-log"),
        CE.loadStatus);
    });
  }

  var reidentifyBtn = document.getElementById("fx-reidentify");
  if (reidentifyBtn) {
    reidentifyBtn.addEventListener("click", function () {
      CE.runStep("/api/feedback/reidentify", this,
        document.getElementById("fx-reid-status"),
        document.getElementById("fx-reid-log"));
    });
  }
})();
