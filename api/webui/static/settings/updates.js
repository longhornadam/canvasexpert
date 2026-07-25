(function () {
  "use strict";

  var CE = window.CE_SETTINGS || {};

  var checkBtn = document.getElementById("btn-update-check");
  var downloadBtn = document.getElementById("btn-update-download");
  var applyBtn = document.getElementById("btn-update-apply");
  var cancelBtn = document.getElementById("btn-update-cancel");
  var statusEl = document.getElementById("update-status");
  var availableBlock = document.getElementById("update-available");
  var readyBlock = document.getElementById("update-ready");
  var availableVersionEl = document.getElementById("update-available-version");
  var availableDateEl = document.getElementById("update-available-date");
  var notesLink = document.getElementById("update-notes-link");
  var readyVersionEl = document.getElementById("update-ready-version");

  function setStatus(msg, kind) {
    CE.setStatus(statusEl, msg, kind);
  }

  function showAvailable(version, publishedAt, notesUrl) {
    if (readyBlock) readyBlock.hidden = true;
    if (!availableBlock) return;
    availableBlock.hidden = false;
    if (availableVersionEl) availableVersionEl.textContent = "Version " + version;
    if (availableDateEl) {
      var when = publishedAt ? new Date(publishedAt) : null;
      availableDateEl.textContent = when && !isNaN(when) ? when.toLocaleDateString() : "date unknown";
    }
    if (notesLink) {
      if (notesUrl) {
        notesLink.href = notesUrl;
        notesLink.hidden = false;
      } else {
        notesLink.hidden = true;
      }
    }
  }

  function showReady(version) {
    if (availableBlock) availableBlock.hidden = true;
    if (!readyBlock) return;
    readyBlock.hidden = false;
    if (readyVersionEl) readyVersionEl.textContent = version;
  }

  function showNeither() {
    if (availableBlock) availableBlock.hidden = true;
    if (readyBlock) readyBlock.hidden = true;
  }

  checkBtn && checkBtn.addEventListener("click", async function () {
    checkBtn.disabled = true;
    setStatus("Checking…");
    showNeither();
    try {
      var r = await fetch("/api/update/status");
      var d = await r.json();
      if (d.staged) {
        showReady(d.staged.version);
        setStatus("A downloaded update is ready to install.", "ok");
      } else if (d.ok && d.available) {
        showAvailable(d.latest, d.published_at, d.notes_url);
        setStatus("");
      } else if (d.ok) {
        setStatus("You're already on the latest version.", "ok");
      } else {
        setStatus(d.error || "Could not check for updates.", "error");
      }
    } catch (e) {
      setStatus("Could not check for updates. Check your internet connection.", "error");
    } finally {
      checkBtn.disabled = false;
    }
  });

  downloadBtn && downloadBtn.addEventListener("click", async function () {
    downloadBtn.disabled = true;
    setStatus("Downloading…");
    try {
      var r = await fetch("/api/update/download", { method: "POST" });
      var d = await r.json();
      if (d.ok) {
        showReady(d.version);
        setStatus("Downloaded. Ready to install.", "ok");
      } else {
        setStatus(d.error || "The download failed.", "error");
      }
    } catch (e) {
      setStatus("The download failed. Check your internet connection.", "error");
    } finally {
      downloadBtn.disabled = false;
    }
  });

  applyBtn && applyBtn.addEventListener("click", async function () {
    applyBtn.disabled = true;
    if (cancelBtn) cancelBtn.disabled = true;
    setStatus("Restarting to install the update…");
    try {
      var r = await fetch("/api/update/apply", { method: "POST" });
      var d = await r.json();
      if (!d.ok) {
        setStatus(d.error || "Could not restart to apply the update.", "error");
        applyBtn.disabled = false;
        if (cancelBtn) cancelBtn.disabled = false;
      }
      // On success the server is about to shut down; there is no further
      // response to react to. The teacher watches the console window close
      // and reopen on its own.
    } catch (e) {
      setStatus("The app is restarting…");
    }
  });

  cancelBtn && cancelBtn.addEventListener("click", async function () {
    cancelBtn.disabled = true;
    try {
      await fetch("/api/update/cancel", { method: "POST" });
    } catch (e) {
      // Nothing to react to -- cancel is best-effort local cleanup.
    }
    showNeither();
    setStatus("Canceled.");
    cancelBtn.disabled = false;
  });
})();
