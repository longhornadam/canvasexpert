(function () {
  "use strict";

  var push = window.CE_PUSH || {};
  var ready = ["postForm", "showLog", "hideBanner", "pushContent"]
    .every(function (name) { return typeof push[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("RubricForge push controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  function getLog() {
    return document.getElementById("rf-log");
  }

  function getBanner() {
    return document.getElementById("rf-banner");
  }

  document.getElementById("btn-rf-validate")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("rf-file")?.value;
    if (!path) return alert("Pick a RubricForge file.");
    var log = push.showLog(getLog());
    push.hideBanner(getBanner());
    log("Validating…\n");
    push.postForm("/api/rf/validate", { path: path }).then(function (d) {
      // A failed request comes back as {ok:false, error} with no problems and
      // no summary, so without this the log would just stop at "Validating…".
      if (d.error) { log("ERROR: " + d.error); return; }
      (d.problems || []).forEach(function (p) { log("✗ " + p); });
      var s = d.summary;
      if (s) {
        log((d.ok ? "✓ VALID" : "✗ INVALID") + ' — ' + s.type + ': "' + s.title + '" (' + s.total_points + ' pts)');
        log("  criteria: " + s.criteria_count + ", rubric ratings: " + s.max_rating_count);
      }
    }).catch(function (e) { log("ERROR: " + e); });
  });

  document.getElementById("btn-rf-push")?.addEventListener("click", function () {
    if (!requireReady()) return;
    var path = document.getElementById("rf-file")?.value;
    if (!path) return alert("Pick a RubricForge file.");
    push.pushContent("rf", { path: path },
      getLog(), getBanner(), this,
      "Create this rubric in Canvas.");
  });
})();
