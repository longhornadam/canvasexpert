(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};

  function wireFolderButton(btn, fallbackKey) {
    if (!btn) return;
    btn.addEventListener("click", function () {
      CE.openFolder(btn.dataset.folder || fallbackKey);
    });
  }

  document.querySelectorAll(".fx-open").forEach(wireFolderButton);
  wireFolderButton(document.getElementById("gf-open-safe"), "safe");
  wireFolderButton(document.getElementById("gf-open-private"), "private");
})();
