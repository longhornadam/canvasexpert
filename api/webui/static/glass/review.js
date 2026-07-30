(function () {
  "use strict";
  function token() { var node = document.querySelector('meta[name="canvasexpert-csrf-token"]'); return node ? node.content : ""; }
  function mutate(id, action, digest) { return fetch("/api/glass/drafts/" + encodeURIComponent(id) + "/" + action, {method: "POST", headers: {"Content-Type": "application/json", "X-CanvasExpert-CSRF": token()}, body: JSON.stringify({digest: digest || ""})}).then(function () { window.location.reload(); }); }
  document.querySelectorAll("[data-glass-approve]").forEach(function (button) { button.addEventListener("click", function () { mutate(button.dataset.glassApprove, "approve", button.dataset.glassDigest); }); });
  document.querySelectorAll("[data-glass-discard]").forEach(function (button) { button.addEventListener("click", function () { mutate(button.dataset.glassDiscard, "discard"); }); });
  document.querySelectorAll("[data-glass-aspect]").forEach(function (button) { button.addEventListener("click", function () { var frame = button.parentElement.querySelector("iframe"); if (frame) frame.style.aspectRatio = button.dataset.glassAspect.replace(":", " / "); button.parentElement.querySelectorAll("[data-glass-aspect]").forEach(function (item) { item.setAttribute("aria-pressed", String(item === button)); }); }); });
  document.querySelectorAll("[data-glass-layout]").forEach(function (select) { select.addEventListener("change", function () { var frame = select.parentElement.parentElement.querySelector(".glass-scene-preview"); if (frame) frame.src = frame.src.split("?")[0] + "?layout=" + encodeURIComponent(select.value); }); });
}());
