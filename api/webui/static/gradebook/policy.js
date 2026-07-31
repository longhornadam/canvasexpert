(function () {
  "use strict";

  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "_renderBanner", "esc", "gbCourseId", "gbCourseName",
               "gbTargets", "_markLoaded", "_needsLoad", "hideBanner", "showBanner",
               "_clearStatus", "canvasWriteReview"]
    .every(function (name) { return typeof gb[name] === "function"; });

  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }

  // Switching courses re-triggers this loader (see gradebook.js's
  // _autoloadTab) without cancelling a slower earlier request, so a stale
  // response could land last and fill the policy form with the previous
  // course's settings while the new course sits selected. Stamp each
  // request and let only the newest one write, the same way inbox.js does.
  var loadGeneration = 0;

  // ── Late policy (auto-loaded) ──────────────────────────────────────────

  window.CE_GRADEBOOK.loadPolicy = async function _loadPolicy() {
    if (!requireReady()) return;
    var id = gb.gbCourseId();
    if (!id) return;
    var generation = ++loadGeneration;
    gb._markLoaded("policy");
    var st = document.getElementById("lp-status");
    if (st) { st.className = "status hint"; st.textContent = "Loading current policy…"; }
    try {
      var d = await fetch("/api/late-policy?course_id=" + encodeURIComponent(id)).then(function (r) { return r.json(); });
      if (generation !== loadGeneration) return;
      if (!d.ok) {
        if (st) { st.className = "status error"; st.textContent = "Could not load policy: " + d.error; }
        return;
      }
      if (!d.policy) {
        if (st) st.textContent = gb.gbCourseName() + " has no late policy yet — configure one below.";
        return;
      }
      var p = d.policy;
      document.getElementById("lp-late-enabled").checked     = !!p.late_submission_deduction_enabled;
      document.getElementById("lp-deduction").value          = p.late_submission_deduction ?? 10;
      document.getElementById("lp-interval").value           = p.late_submission_interval || "day";
      document.getElementById("lp-floor").value              = p.late_submission_minimum_percent ?? 50;
      document.getElementById("lp-missing-enabled").checked  = !!p.missing_submission_deduction_enabled;
      document.getElementById("lp-missing-pct").value        =
        p.missing_submission_deduction != null ? 100 - p.missing_submission_deduction : 0;
      if (st) { st.className = "status ok"; st.textContent = "✓ Loaded current policy for " + gb.gbCourseName(); }
    } catch (e) {
      if (generation !== loadGeneration) return;
      if (st) { st.className = "status error"; st.textContent = String(e); }
    }
  };

  document.getElementById("btn-apply-policy")?.addEventListener("click", async function () {
    if (!requireReady()) return;
    var targets = gb.gbTargets();
    if (!targets.length) return alert("Pick a course first.");
    var lateOn = document.getElementById("lp-late-enabled").checked;
    var missOn = document.getElementById("lp-missing-enabled").checked;
    var pct    = parseFloat(document.getElementById("lp-deduction").value) || 0;
    var intv   = document.getElementById("lp-interval").value;
    var floor  = parseFloat(document.getElementById("lp-floor").value) || 0;
    var missAt = parseFloat(document.getElementById("lp-missing-pct").value) || 0;
    var policy = {
      late_submission_deduction_enabled:       lateOn,
      late_submission_deduction:               pct,
      late_submission_interval:                intv,
      late_submission_minimum_percent_enabled: lateOn,
      late_submission_minimum_percent:         floor,
      missing_submission_deduction_enabled:    missOn,
      missing_submission_deduction:            100 - missAt,
    };
    var desc = [
      lateOn ? "late work: \u2212" + pct + "% per " + intv + ", floor " + floor + "%" : "late deduction: OFF",
      missOn ? "missing work scored at " + missAt + "%" : "missing deduction: OFF",
    ].join("\n  ");
    var ok = await gb.canvasWriteReview({
      title: "Review Canvas late policy",
      action: "Apply this Canvas late policy to the selected course.",
      targets: targets,
      details: desc.split("\n  "),
      warnings: [
        "Future submissions and grades are affected by Canvas late policy.",
        "Canvas may recalculate late and missing penalties automatically.",
      ],
      confirmText: "Apply late policy",
    });
    if (!ok) return;
    var banner = document.getElementById("lp-banner");
    gb.hideBanner(banner);
    this.disabled = true;
    try {
      var d = await gb.postForm("/api/late-policy/apply", {
        courses: JSON.stringify(targets), policy: JSON.stringify(policy),
      });
      if (d.error && !d.results) { gb.showBanner(banner, "fail", "\u2717 " + gb.esc(d.error)); return; }
      gb._renderBanner(banner, (d.results || []).map(function (r) {
        return {
          ok:    r.ok,
          title: r.course_name + " \u2014 " + (r.ok ? r.title : (r.error || "failed")),
          url:   null,
        };
      }), d.ok);
      gb._clearLoaded("policy");
      window.CE_GRADEBOOK.loadPolicy();
    } finally { this.disabled = false; }
  });

})();
