(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  if (typeof push.loadRubricFiles === "function") {
    push.loadRubricFiles();
  }
})();
