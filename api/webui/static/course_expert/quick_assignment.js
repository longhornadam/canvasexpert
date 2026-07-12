(function () {
  "use strict";

  var btn = document.getElementById("btn-qa-push");
  if (!btn) return;

  btn.addEventListener("click", function () {
    var name = document.getElementById("qa-name")?.value.trim();
    if (!name) return alert("Give the assignment a name.");

    var payload = {
      name: name,
      points: parseFloat(document.getElementById("qa-points")?.value) || 100,
      submission_type: document.getElementById("qa-subtype")?.value || "none",
      published: document.getElementById("qa-publish")?.checked || false,
    };
    var due = typeof localToISO === "function"
      ? localToISO(document.getElementById("qa-due")?.value || "")
      : "";
    if (due) payload.due_at = due;

    var agSel = document.getElementById("qa-aggroup");
    if (agSel && agSel.value) payload.assignment_group_name = agSel.selectedOptions[0].text;

    window.CE_PUSH.pushContent(
      "quick",
      payload,
      document.getElementById("qa-log"),
      document.getElementById("qa-banner"),
      btn,
      'Create quick assignment "' + name + '"'
    );
  });
})();
