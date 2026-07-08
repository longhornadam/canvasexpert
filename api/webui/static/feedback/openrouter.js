(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};
  var esc = CE.esc || function (s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  };
  var greenTokens = 0;
  var hasKey = false;

  function badge(b) {
    return b.green
      ? '<span style="color:#2f8132;font-weight:600">🟢 Pseudonymized</span>'
      : '<span style="color:#b3261e;font-weight:600">🔴 Identifiable data — do not send</span>';
  }

  function softNote(b) {
    return b.soft ? ('<div class="hint" style="color:#9a6700">⚠ Mentions a roster name in the writing (' +
      esc((b.soft_names || []).join(", ")) + ') — review before sending.</div>') : "";
  }

  function renderCSV(d) {
    d = d || {};
    hasKey = !!d.has_key;
    var orList = document.getElementById("or-bundles");
    greenTokens = 0;
    if (orList) {
      if (!d.bundles || !d.bundles.length) {
        orList.innerHTML = '<p class="hint">No bundles yet — Process the Inbox above.</p>';
      } else {
        orList.innerHTML = d.bundles.map(function (b) {
          if (b.green) greenTokens += b.tokens || 0;
          return '<div class="cal-row" style="display:block"><div><strong>' + esc(b.name) + '</strong> ' +
            badge(b) + ' <span class="muted" style="font-size:12px">· ~' + (b.tokens || 0) + ' tokens</span></div>' +
            softNote(b) + "</div>";
        }).join("");
      }
    }
    var send = document.getElementById("or-send");
    if (send) {
      send.disabled = !(hasKey && greenTokens > 0);
      send.textContent = "Send 🟢 bundles to OpenRouter" + (greenTokens ? " (~" + greenTokens + " input tokens)" : "");
    }
  }

  function loadCSVStatus() {
    return CE.loadStatus().then(function (d) {
      renderCSV(d || CE.state.status || {});
      return d;
    });
  }

  var laneSub = document.getElementById("lane-sub");
  var laneManual = document.getElementById("lane-manual");
  var laneOpenRouter = document.getElementById("lane-openrouter");
  var laneButtons = document.querySelectorAll("#lane-chooser .lane-btn");
  var laneCopy = {
    manual: "Your work is pseudonymized here, then you score it in your own tool and bring results back.",
    openrouter: "Your work is pseudonymized here, then sent automatically to OpenRouter and brought back."
  };

  function setLane(lane) {
    if (laneManual) laneManual.hidden = (lane !== "manual");
    if (laneOpenRouter) laneOpenRouter.hidden = (lane !== "openrouter");
    laneButtons.forEach(function (b) {
      b.classList.toggle("primary", b.dataset.lane === lane);
    });
    if (laneSub) laneSub.textContent = laneCopy[lane] || "";
  }

  laneButtons.forEach(function (b) {
    b.addEventListener("click", function () {
      setLane(b.dataset.lane);
    });
  });
  setLane("manual");

  var orConfig = document.getElementById("or-config");
  if (orConfig) {
    orConfig.addEventListener("submit", function (e) {
      e.preventDefault();
      var st = document.getElementById("or-config-status");
      if (st) st.textContent = "Saving…";
      fetch("/api/feedback/openrouter-config", {
        method: "POST",
        body: new URLSearchParams({
          api_key: (document.getElementById("or-key") || {}).value ? document.getElementById("or-key").value.trim() : "",
          model: (document.getElementById("or-model") || {}).value ? document.getElementById("or-model").value.trim() : "",
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function () {
          if (st) st.textContent = "Saved.";
          var keyEl = document.getElementById("or-key");
          if (keyEl) keyEl.value = "";
          loadCSVStatus();
        })
        .catch(function (e) {
          if (st) st.textContent = "Error: " + e;
        });
    });
  }

  var orSend = document.getElementById("or-send");
  if (orSend) {
    orSend.addEventListener("click", function () {
      var model = (document.getElementById("or-model") || {}).value ? document.getElementById("or-model").value.trim() : "";
      if (!confirm("Send all 🟢 green (pseudonymized) bundles to OpenRouter?\n\nModel: " +
                   (model || "saved default") +
                   "\n~" + greenTokens +
                   " input tokens. This calls a paid API and costs money. Continue?")) return;
      var btn = this;
      var st = document.getElementById("or-send-status");
      var logEl = document.getElementById("or-log");
      btn.disabled = true;
      if (st) st.textContent = "Scoring via OpenRouter…";
      if (logEl) logEl.hidden = true;
      fetch("/api/feedback/score-openrouter", {
        method: "POST",
        body: new URLSearchParams({ rubric_name: (document.getElementById("or-rubric") || {}).value || "" }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (logEl && d.log && d.log.length) {
            logEl.textContent = d.log.join("\n");
            logEl.hidden = false;
          }
          if (st) st.textContent = d.ok ? "Done — review in ToEnter before posting." : ("Error: " + (d.error || "failed"));
          if (d.ok && d.folder) {
            var open = document.getElementById("or-open-toenter");
            if (open) {
              open.hidden = false;
              open.onclick = function () {
                CE.openPath("/api/open-folder", d.folder);
              };
            }
          }
          loadCSVStatus();
        })
        .catch(function (e) {
          if (st) st.textContent = "Error: " + e;
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  loadCSVStatus();

  CE.loadCSVStatus = CE.loadCSVStatus || loadCSVStatus;
  CE.renderCSV = CE.renderCSV || renderCSV;
  CE.setLane = CE.setLane || setLane;
})();
