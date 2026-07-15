(function () {
  "use strict";

  var CE = window.CE_SETTINGS || {};

  var urlDisplay = document.getElementById("url-display");
  var urlInput = document.getElementById("base_url_input");
  var btnEditUrl = document.getElementById("btn-edit-url");
  var tokenInput = document.getElementById("token_input");
  var btnReplaceToken = document.getElementById("btn-replace-token");
  var form = document.getElementById("canvas-account-form");
  var statusEl = document.getElementById("account-status");
  var btnTest = document.getElementById("btn-test");

  function setStatus(msg, kind) {
    CE.setStatus(statusEl, msg, kind);
  }

  function getFormData() {
    return {
      base_url: CE.isHidden(urlInput)
        ? (urlDisplay ? (urlDisplay.textContent || "").trim() : "")
        : urlInput.value.trim(),
      token: CE.isHidden(tokenInput) ? "" : (tokenInput.value.trim() || ""),
    };
  }

  btnEditUrl && btnEditUrl.addEventListener("click", function () {
    var editing = urlInput.classList.contains("ce-settings-initially-hidden");
    urlInput.classList.toggle("ce-settings-initially-hidden", !editing);
    urlDisplay.classList.toggle("ce-settings-initially-hidden", editing);
    btnEditUrl.textContent = editing ? "Cancel" : "Edit";
    if (editing) urlInput.focus();
  });

  btnReplaceToken && btnReplaceToken.addEventListener("click", function () {
    var showing = !tokenInput.classList.contains("ce-settings-initially-hidden");
    tokenInput.classList.toggle("ce-settings-initially-hidden", showing);
    btnReplaceToken.textContent = showing ? "Replace" : "Cancel";
    if (!showing) tokenInput.focus();
  });

  btnTest && btnTest.addEventListener("click", async function () {
    var d = getFormData();
    if (!d.base_url) return setStatus("Enter the Canvas base URL first.", "error");
    setStatus(d.token ? "Testing connection…" : "Testing saved token…");
    var resp = await fetch("/settings/test-connection", {
      method: "POST",
      body: new URLSearchParams(d),
    });
    var data = await resp.json();
    if (data.ok) setStatus("✓ Connected — signed in as " + data.display_name, "ok");
    else setStatus("Connection failed: " + data.error, "error");
  });

  form && form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var d = getFormData();
    if (!d.base_url) return setStatus("Base URL is required.", "error");
    setStatus("Saving…");
    var resp = await fetch("/settings/canvas", {
      method: "POST",
      body: new URLSearchParams(d),
    });
    var data = await resp.json();
    if (!data.ok) {
      setStatus("Could not save.", "error");
      return;
    }
    if (d.token) {
      setStatus("Saved. Testing token…", "ok");
      var test = await fetch("/settings/test-connection", {
        method: "POST",
        body: new URLSearchParams(d),
      }).then(function (r) { return r.json(); });
      if (test.ok) {
        setStatus("Saved and connected as " + (test.display_name || "you") + " ✓", "ok");
      } else {
        setStatus("Saved, but the token test failed: " + (test.error || "unknown error"), "error");
      }
      setTimeout(function () { location.reload(); }, 900);
    } else {
      setStatus("Saved! Reloading…", "ok");
      setTimeout(function () { location.reload(); }, 600);
    }
  });
})();
