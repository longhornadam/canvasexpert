(function () {
  "use strict";

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    return Promise.resolve();
  }

  document.querySelectorAll(".ce-copy-button").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.getAttribute("data-copy-target"));
      if (!target) return;
      copyText(target.textContent || "")
        .then(function () { button.textContent = "Copied"; setTimeout(function () { button.textContent = "Copy"; }, 1400); })
        .catch(function () { button.textContent = "Copy failed"; });
    });
  });

  function pillFor(status) {
    if (status.error) return { cls: "off", text: "Status unavailable" };
    if (status.connected && status.current) return { cls: "on", text: "Connected" };
    if (status.connected) return { cls: "warn", text: "Update available" };
    if (!status.detected) return { cls: "warn", text: "App not found" };
    return { cls: "off", text: "Not connected" };
  }

  function actionButton(action, client, label, primary) {
    var cls = "button ce-ai-action" + (primary ? " primary" : "");
    return '<button type="button" class="' + cls + '" data-action="' + action +
      '" data-client="' + client + '">' + label + "</button>";
  }

  function actionsFor(status, client, connectLabel) {
    if (status.connected && status.current) {
      return actionButton("connect", client, "Reconnect", false) +
        actionButton("disconnect", client, "Disconnect", false);
    }
    if (status.connected) {
      return actionButton("connect", client, "Update connection", true) +
        actionButton("disconnect", client, "Disconnect", false);
    }
    return actionButton("connect", client, connectLabel, true);
  }

  function renderCard(card, status) {
    var client = card.getAttribute("data-client");
    var connectLabel = card.getAttribute("data-connect-label");
    var pill = card.querySelector("[data-pill]");
    if (pill) {
      var info = pillFor(status);
      pill.className = "ce-ai-pill ce-ai-pill--" + info.cls;
      pill.textContent = info.text;
    }
    var actions = card.querySelector("[data-actions]");
    if (actions) actions.innerHTML = actionsFor(status, client, connectLabel);
  }

  function setResult(card, message, isError) {
    var result = card.querySelector("[data-result]");
    if (!result) return;
    result.textContent = message || "";
    result.classList.toggle("ce-ai-result--error", !!isError);
  }

  function busy(card, on) {
    card.querySelectorAll(".ce-ai-action").forEach(function (b) { b.disabled = on; });
  }

  var cardsRoot = document.querySelector(".ce-ai-cards");
  if (cardsRoot) {
    cardsRoot.addEventListener("click", function (event) {
      var button = event.target.closest(".ce-ai-action");
      if (!button) return;
      var card = button.closest(".ce-ai-card");
      if (!card) return;
      var action = button.getAttribute("data-action");
      var client = button.getAttribute("data-client");

      busy(card, true);
      setResult(card, action === "disconnect" ? "Disconnecting..." : "Connecting...", false);

      fetch("/api/connections/" + client + "/" + action, {
        method: "POST",
        headers: { "Accept": "application/json" },
      })
        .then(function (response) {
          return response.json().then(function (body) { return { ok: response.ok, body: body }; });
        })
        .then(function (result) {
          var body = result.body || {};
          if (result.ok && body.ok && body.status) {
            renderCard(card, body.status);
            if (action === "disconnect") {
              setResult(card, "Disconnected.", false);
            } else {
              var note = card.getAttribute("data-restart-note") || "";
              var kept = body.status.other_server_count
                ? " Your other servers were kept." : "";
              setResult(card, "Connected. " + note + kept, false);
            }
          } else {
            setResult(card, body.detail || "That did not work. Try manual setup below.", true);
          }
        })
        .catch(function () {
          setResult(card, "Could not reach Canvas Expert. Is it still running?", true);
        })
        .finally(function () { busy(card, false); });
    });
  }
})();
