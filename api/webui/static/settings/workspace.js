(function () {
  "use strict";

  var CE = window.CE_SETTINGS || {};

  var dlRootForm = document.getElementById("download-root-form");
  var dlRootStatus = document.getElementById("download-root-status");
  var workspaceCard = document.getElementById("workspace-card");
  var accountStatus = document.getElementById("account-status");
  var aiTaCard = document.getElementById("ai-ta-card");
  var aiTaStatus = document.getElementById("ai-ta-status");
  var aiTaFileList = document.getElementById("ai-ta-file-list");
  var aiTaPath = aiTaCard ? (aiTaCard.dataset.path || "") : "";

  function setDlStatus(msg, kind) {
    CE.setStatus(dlRootStatus, msg, kind);
  }

  function setAiTaStatus(msg, kind) {
    CE.setStatus(aiTaStatus, msg, kind);
  }

  function renderAiTaFiles(files) {
    if (!aiTaFileList) return;
    aiTaFileList.innerHTML = "";
    (files || []).forEach(function (file) {
      var li = document.createElement("li");
      li.textContent = file.label;
      aiTaFileList.appendChild(li);
    });
    if (!files || !files.length) {
      var empty = document.createElement("li");
      empty.className = "hint";
      empty.textContent = "No files yet.";
      aiTaFileList.appendChild(empty);
    }
  }

  async function loadAiTaFiles() {
    if (!aiTaFileList) return;
    var data = await fetch("/api/ai-ta/files").then(function (r) { return r.json(); });
    renderAiTaFiles(data.files || []);
  }

  CE.loadAiTaFiles = loadAiTaFiles;

  dlRootForm && dlRootForm.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var path = document.getElementById("download-root-input")?.value.trim();
    if (!path) return setDlStatus("Enter a folder path.", "error");
    setDlStatus("Saving…");
    var r = await fetch("/settings/download-root", {
      method: "POST",
      body: new URLSearchParams({ path: path }),
    });
    var d = await r.json();
    if (d.ok) setDlStatus("✓ Saved", "ok");
    else setDlStatus("Could not save: " + (d.error || "unknown error"), "error");
  });

  document.getElementById("btn-ai-ta-open")?.addEventListener("click", async function () {
    if (!aiTaPath) return setAiTaStatus("Folder path unavailable.", "error");
    var r = await fetch("/api/open-folder", {
      method: "POST",
      body: new URLSearchParams({ path: aiTaPath }),
    });
    var d = await r.json();
    if (d.ok) setAiTaStatus("Opened in Explorer.", "ok");
    else setAiTaStatus(d.error || "Could not open folder.", "error");
  });

  document.getElementById("btn-workspace-open")?.addEventListener("click", async function () {
    var root = workspaceCard ? (workspaceCard.dataset.path || "") : "";
    if (!root) return CE.setStatus(accountStatus, "No OneDrive workspace is available on this machine.", "error");
    var r = await fetch("/api/open-folder", {
      method: "POST",
      body: new URLSearchParams({ path: root }),
    });
    var d = await r.json();
    if (d.ok) CE.setStatus(accountStatus, "Workspace opened in Explorer.", "ok");
    else CE.setStatus(accountStatus, d.error || "Could not open workspace folder.", "error");
  });

  document.getElementById("btn-ai-ta-rebuild")?.addEventListener("click", async function () {
    setAiTaStatus("Rebuilding…", "");
    var d = await fetch("/api/ai-ta/rebuild", { method: "POST" }).then(function (r) { return r.json(); });
    if (d.ok) {
      setAiTaStatus("Rebuilt " + (d.files?.length || 0) + " file(s).", "ok");
      await loadAiTaFiles();
    } else {
      setAiTaStatus(d.error || "Rebuild failed.", "error");
    }
  });
})();
