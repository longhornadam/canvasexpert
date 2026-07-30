(function () {
  "use strict";
  function token() { var node = document.querySelector('meta[name="canvasexpert-csrf-token"]'); return node ? node.content : ""; }
  function note(button, message) { var line = button.parentElement.querySelector("[data-glass-note]"); if (!line) { line = document.createElement("p"); line.setAttribute("data-glass-note", ""); line.setAttribute("role", "alert"); button.parentElement.appendChild(line); } line.textContent = message; }
  function reason(body) { var detail = (body.errors || []).map(function (item) { return item.field + ": " + item.message; }).join("; "); return [body.error || body.detail || "That did not go through.", detail].filter(Boolean).join(" "); }
  function mutate(button, id, action, digest) {
    button.disabled = true;
    return fetch("/api/glass/drafts/" + encodeURIComponent(id) + "/" + action, {method: "POST", headers: {"Content-Type": "application/json", "X-CanvasExpert-CSRF": token()}, body: JSON.stringify({digest: digest || ""})})
      .then(function (response) { return response.json().then(function (body) { return body; }, function () { return {}; }).then(function (body) { return {ok: response.ok && body.ok !== false, body: body}; }); })
      .then(function (result) { if (result.ok) { window.location.reload(); return; } button.disabled = false; note(button, reason(result.body)); })
      .catch(function () { button.disabled = false; note(button, "That did not go through."); });
  }
  document.querySelectorAll("[data-glass-approve]").forEach(function (button) { button.addEventListener("click", function () { mutate(button, button.dataset.glassApprove, "approve", button.dataset.glassDigest); }); });
  document.querySelectorAll("[data-glass-discard]").forEach(function (button) { button.addEventListener("click", function () { mutate(button, button.dataset.glassDiscard, "discard"); }); });
  document.querySelectorAll("[data-glass-aspect]").forEach(function (button) { button.addEventListener("click", function () { var frame = button.parentElement.querySelector("iframe"); if (frame) frame.style.aspectRatio = button.dataset.glassAspect.replace(":", " / "); button.parentElement.querySelectorAll("[data-glass-aspect]").forEach(function (item) { item.setAttribute("aria-pressed", String(item === button)); }); }); });
  document.querySelectorAll("[data-glass-layout]").forEach(function (select) { select.addEventListener("change", function () { var frame = select.parentElement.parentElement.querySelector(".glass-scene-preview"); if (frame) frame.src = frame.src.split("?")[0] + "?layout=" + encodeURIComponent(select.value); }); });
}());
