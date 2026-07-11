(function () {
  "use strict";

  var strip = document.getElementById("ce-readiness-strip");
  if (!strip) return;
  var refresh = strip.querySelector("[data-readiness-refresh]");
  var details = strip.querySelector("[data-readiness-details]");
  var detailText = strip.querySelector("[data-readiness-detail]");

  function label(component) {
    if (!component) return "Unknown";
    if (component.status === "ready") return "Ready";
    if (component.status === "unconfigured") return "Not configured";
    if (component.status === "degraded") return "Needs attention";
    return "Unknown";
  }

  function render(data) {
    var components = data.components || {};
    strip.dataset.status = data.status || "unknown";
    ["canvas", "openrouter", "privacy"].forEach(function (name) {
      var item = components[name] || { status: "unknown" };
      var value = strip.querySelector('[data-readiness-value="' + name + '"]');
      var dot = strip.querySelector('[data-readiness-dot="' + name + '"]');
      if (value) value.textContent = label(item);
      if (dot) dot.dataset.state = item.status === "ready" ? "ready" : item.status === "degraded" ? "attention" : "";
    });
    var degraded = data.status === "degraded";
    if (refresh) refresh.hidden = !degraded;
    if (details) details.hidden = !degraded;
    if (detailText) {
      detailText.textContent = Object.keys(components).map(function (name) {
        var item = components[name] || {};
        return name + ": " + (item.code || label(item));
      }).join(" · ");
    }
  }

  function load(force) {
    var url = "/api/readiness/probe" + (force ? "?force=1" : "");
    return fetch(force ? url : "/api/readiness")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!force && data.status === "unknown") return fetch(url, { method: "POST" }).then(function (r) { return r.json(); });
        return data;
      })
      .then(render)
      .catch(function () { render({ status: "degraded", components: { canvas: { status: "degraded", code: "network" }, openrouter: { status: "unknown" }, privacy: { status: "unknown" } } }); });
  }

  if (refresh) refresh.addEventListener("click", function () { load(true); });
  load(false);
})();
