(function () {
  "use strict";

  var CE = window.CE_FEEDBACK || {};
  var esc = CE.esc || function (s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  };

  function loadPersonaSelect(selectedId) {
    fetch("/api/feedback/personas")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var sel = document.getElementById("ta-persona-select");
        if (!sel) return;
        sel.innerHTML = '<option value="">— custom —</option>' +
          (d.personas || []).map(function (p) {
            return '<option value="' + esc(p.id) + '"' + (p.id === selectedId ? ' selected' : '') + '>' +
              (p.builtin ? "" : "⭐ ") + esc(p.name) + (p.builtin ? "" : " (custom)") + "</option>";
          }).join("");
        sel.addEventListener("change", function () {
          var id = sel.value;
          if (!id) return;
          for (var i = 0; i < (d.personas || []).length; i++) {
            if (d.personas[i].id === id) {
              var nameEl = document.getElementById("ta-name");
              var toneEl = document.getElementById("ta-personality");
              if (nameEl) nameEl.value = d.personas[i].name;
              if (toneEl) toneEl.value = d.personas[i].personality;
              break;
            }
          }
        });
      })
      .catch(function () {});
  }

  var personaForm = document.getElementById("persona-form");
  if (personaForm) {
    personaForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var st = document.getElementById("persona-status");
      if (st) st.textContent = "Saving…";
      var nameEl = document.getElementById("ta-name");
      var toneEl = document.getElementById("ta-personality");
      fetch("/api/feedback/persona", {
        method: "POST",
        body: new URLSearchParams({
          name: nameEl ? nameEl.value.trim() : "",
          personality: toneEl ? toneEl.value.trim() : "",
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (st) st.textContent = d.ok ? "Saved." : "Error";
        })
        .catch(function (e) {
          if (st) st.textContent = "Error: " + e;
        });
    });
  }

  loadPersonaSelect("");

  CE.loadPersonaSelect = CE.loadPersonaSelect || loadPersonaSelect;
})();
