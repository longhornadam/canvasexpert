(function () {
  "use strict";

  function initFileSource(wrapper) {
    if (!wrapper) return;
    var sel = wrapper.querySelector("select");
    var pasteEl = wrapper.querySelector(".file-src-paste");
    var fileInp = wrapper.querySelector(".file-src-input");
    var hintEl = wrapper.querySelector(".file-src-hint");
    var srcBtns = Array.from(wrapper.querySelectorAll(".file-src-btn"));

    function setMode(mode) {
      srcBtns.forEach(function (b) {
        b.classList.toggle("active", b.dataset.src === mode);
      });
      if (sel) sel.style.display = mode === "select" ? "" : "none";
      if (pasteEl) pasteEl.style.display = mode === "paste" ? "" : "none";
      if (mode !== "paste" && hintEl) {
        hintEl.style.display = "none";
        hintEl.textContent = "";
        hintEl.className = "file-src-hint";
      }
    }

    function setTempOption(path, label) {
      if (!sel) return;
      var opt = sel.querySelector("option[data-temp]");
      if (!opt) {
        opt = document.createElement("option");
        opt.dataset.temp = "1";
        sel.appendChild(opt);
      }
      opt.value = path;
      opt.textContent = label;
      sel.value = path;
    }

    async function uploadContent(content) {
      try {
        var r = await fetch("/api/temp-upload", {
          method: "POST",
          body: new URLSearchParams({ content: content }),
        });
        var d = await r.json();
        return d.ok ? d.path : null;
      } catch (e) {
        return null;
      }
    }

    async function uploadFile(file) {
      try {
        var fd = new FormData();
        fd.append("file", file);
        var r = await fetch("/api/temp-upload", { method: "POST", body: fd });
        var d = await r.json();
        return d.ok ? d.path : null;
      } catch (e) {
        return null;
      }
    }

    srcBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.dataset.src === "upload") {
          if (fileInp) fileInp.click();
        } else {
          setMode(btn.dataset.src);
        }
      });
    });

    if (fileInp) {
      fileInp.addEventListener("change", async function () {
        var file = this.files[0];
        if (!file) return;
        if (hintEl) {
          hintEl.style.display = "";
          hintEl.className = "file-src-hint";
          hintEl.textContent = "Uploading...";
        }
        var path = await uploadFile(file);
        if (path) {
          setTempOption(path, "Uploaded: " + file.name);
          setMode("select");
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint ok";
            hintEl.textContent = "Ready: " + file.name;
          }
        } else {
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint err";
            hintEl.textContent = "Upload failed.";
          }
          setMode("select");
        }
        this.value = "";
      });
    }

    // Exposed so other push scripts (e.g. inbox.js, Slice D) can inject a
    // chosen Inbox draft's path into this exact select-and-validate seam
    // without duplicating setMode/setTempOption or touching the existing
    // paste/upload logic.
    wrapper.ceFileSource = { setMode: setMode, setTempOption: setTempOption };

    var timer;
    if (pasteEl) {
      pasteEl.addEventListener("input", function () {
        clearTimeout(timer);
        var val = pasteEl.value.trim();
        if (!val) {
          if (hintEl) hintEl.style.display = "none";
          return;
        }
        timer = setTimeout(async function () {
          if (hintEl) {
            hintEl.style.display = "";
            hintEl.className = "file-src-hint";
            hintEl.textContent = "Saving...";
          }
          var path = await uploadContent(val);
          if (path) {
            setTempOption(path, "Pasted JSON");
            if (hintEl) {
              hintEl.className = "file-src-hint ok";
              hintEl.textContent = "Ready - click Validate or Push";
            }
          } else if (hintEl) {
            hintEl.className = "file-src-hint err";
            hintEl.textContent = "Error saving content.";
          }
        }, 600);
      });
    }
  }

  async function copySkill(name, btn) {
    if (!name || !btn) return;
    var orig = btn.textContent;
    btn.textContent = "Copying...";
    btn.disabled = true;
    try {
      var r = await fetch("/api/ai-ta/file?name=" + encodeURIComponent(name));
      if (!r.ok) throw new Error("skill not found");
      await navigator.clipboard.writeText(await r.text());
      btn.textContent = "Copied";
    } catch (e) {
      btn.textContent = "Failed";
    }
    setTimeout(function () {
      btn.textContent = orig;
      btn.disabled = false;
    }, 1800);
  }

  window.CE_PUSH = Object.assign(window.CE_PUSH || {}, {
    initFileSource: initFileSource,
    copySkill: copySkill,
  });

  window.initFileSource = initFileSource;
  window.copySkill = copySkill;
})();
