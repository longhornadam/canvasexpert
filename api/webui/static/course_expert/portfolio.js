(function () {
  "use strict";

  function bindOpenFolder(link, folder) {
    link.hidden = false;
    link.onclick = function () {
      fetch("/api/open-folder", {
        method: "POST",
        body: new URLSearchParams({ path: folder }),
      });
    };
  }

  function bindNqPortfolio() {
    var fileInp = document.getElementById("nqp-file");
    if (!fileInp) return;

    var titleInp = document.getElementById("nqp-title");
    var genBtn = document.getElementById("nqp-generate");
    var openLink = document.getElementById("nqp-open");
    var status = document.getElementById("nqp-status");

    fileInp.addEventListener("change", function () {
      genBtn.disabled = !fileInp.files.length;
    });

    genBtn.addEventListener("click", function () {
      if (!fileInp.files.length) return;
      genBtn.disabled = true;
      openLink.hidden = true;
      status.textContent = "Generating…";

      var fd = new FormData();
      fd.append("file", fileInp.files[0]);
      fd.append("quiz_title", titleInp.value.trim());
      fetch("/api/portfolio/from-nq-csv", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) {
            status.textContent = "✓ " + d.count + " portfolio(s) created in " + d.folder;
            bindOpenFolder(openLink, d.folder);
          } else {
            status.textContent = "Error: " + (d.error || "failed");
          }
        })
        .catch(function (e) {
          status.textContent = "Error: " + e;
        })
        .finally(function () {
          genBtn.disabled = false;
        });
    });
  }

  function bindMergedPortfolio() {
    var courseSel = document.getElementById("mp-course");
    if (!courseSel) return;

    var cohortSel = document.getElementById("mp-cohort");
    var fileInp = document.getElementById("mp-file");
    var fromInp = document.getElementById("mp-from");
    var toInp = document.getElementById("mp-to");
    var genBtn = document.getElementById("mp-generate");
    var openLink = document.getElementById("mp-open");
    var status = document.getElementById("mp-status");
    var logEl = document.getElementById("mp-log");

    courseSel.addEventListener("change", function () {
      genBtn.disabled = !courseSel.value;
    });

    genBtn.addEventListener("click", function () {
      if (!courseSel.value) return;
      genBtn.disabled = true;
      openLink.hidden = true;
      logEl.hidden = true;
      status.textContent = "Generating… this can take a minute for a full class.";

      var fd = new FormData();
      fd.append("course_id", courseSel.value);
      fd.append("cohort", cohortSel.value);
      fd.append("date_from", fromInp.value);
      fd.append("date_to", toInp.value);
      if (fileInp.files.length) fd.append("file", fileInp.files[0]);
      fetch("/api/portfolio/merged", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.log && d.log.length) {
            logEl.textContent = d.log.join("\n");
            logEl.hidden = false;
          }
          if (d.ok) {
            status.textContent = "✓ " + d.count + " portfolio(s) created in " + d.folder;
            bindOpenFolder(openLink, d.folder);
          } else {
            status.textContent = "Error: " + (d.error || "failed");
          }
        })
        .catch(function (e) {
          status.textContent = "Error: " + e;
        })
        .finally(function () {
          genBtn.disabled = false;
        });
    });
  }

  bindNqPortfolio();
  bindMergedPortfolio();
})();
