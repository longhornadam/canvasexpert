(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  async function load() {
    try {
      // Check readiness first
      const readinessResponse = await fetch("/smartdeck/api/readiness");
      const readiness = await readinessResponse.json();

      const unconfiguredDiv = document.getElementById("smartdeck-unconfigured");
      if (!readiness.ok || !readiness.ready) {
        unconfiguredDiv.hidden = false;
        const detailEl = document.getElementById("smartdeck-unconfigured-detail");
        if (readiness.missing && readiness.missing.length > 0) {
          detailEl.textContent = readiness.missing.join("; ");
        } else {
          detailEl.textContent = "Please configure your schedules in Settings.";
        }
      } else {
        unconfiguredDiv.hidden = true;
      }

      // Load decks and templates
      const decksResponse = await fetch("/smartdeck/api/decks");
      const decks = await decksResponse.json();

      if (!decks.ok) {
        document.getElementById("smartdeck-active-list").innerHTML =
          '<p class="ce-empty">Could not load decks.</p>';
        return;
      }

      // Render active decks
      renderDeckList("smartdeck-active-list", decks.active || [], false);

      // Render archived decks
      renderDeckList("smartdeck-archived-list", decks.archived || [], true);

      // Render templates
      renderTemplateList(
        "smartdeck-deck-templates-list",
        decks.deck_templates || []
      );
      renderTemplateList(
        "smartdeck-slide-templates-list",
        decks.slide_templates || []
      );
    } catch (e) {
      console.error("Error loading SmartDeck:", e);
      document.getElementById("smartdeck-active-list").innerHTML =
        '<p class="ce-empty">Error loading decks.</p>';
    }
  }

  function renderDeckList(elementId, decks, isArchived) {
    const container = document.getElementById(elementId);
    if (!decks || decks.length === 0) {
      container.innerHTML = isArchived
        ? '<p class="ce-empty">No archived decks.</p>'
        : '<p class="ce-empty">No active decks yet.</p>';
      return;
    }

    const rows = decks.map(function (deck) {
      const displayDate = deck.date || deck.deck_id;
      const title = esc(deck.title || "(Untitled)");
      const revision = "r" + (deck.revision || 0);

      let html = '<div class="smartdeck-deck-row">';
      html += '<div class="smartdeck-deck-info">';
      html += '<span class="smartdeck-deck-date">' + esc(displayDate) + "</span>";
      html += '<span class="smartdeck-deck-title">' + title + "</span>";
      html += '<span class="smartdeck-deck-revision">' + esc(revision) + "</span>";
      html += "</div>";
      html += '<div class="smartdeck-deck-actions">';

      if (!isArchived) {
        html +=
          '<a href="/smartdeck/display/' +
          esc(deck.deck_id) +
          '" class="small">Display</a>';
        html +=
          '<button type="button" class="small smartdeck-archive-btn" data-deck-id="' +
          esc(deck.deck_id) +
          '">Archive</button>';
      }

      html +=
        '<button type="button" class="small smartdeck-delete-btn" data-deck-id="' +
        esc(deck.deck_id) +
        '">Delete</button>';
      html += "</div>";

      // Anything that would keep part of this deck off the projector, surfaced here
      // rather than on the display page so it is read before class, not during.
      if (!isArchived && deck.problems && deck.problems.length) {
        html += '<ul class="smartdeck-deck-note">';
        deck.problems.forEach(function (problem) {
          html += "<li>" + esc(problem) + "</li>";
        });
        html += "</ul>";
      }

      html += "</div>";

      return html;
    });

    container.innerHTML = rows.join("");

    // Attach event handlers
    container.querySelectorAll(".smartdeck-archive-btn").forEach(function (btn) {
      btn.addEventListener("click", handleArchive);
    });
    container.querySelectorAll(".smartdeck-delete-btn").forEach(function (btn) {
      btn.addEventListener("click", handleDelete);
    });
  }

  function renderTemplateList(elementId, templates) {
    const container = document.getElementById(elementId);
    if (!templates || templates.length === 0) {
      const kind = elementId.includes("slide") ? "Slide" : "Deck";
      container.innerHTML =
        '<p class="ce-empty">No ' + kind + ' Templates yet.</p>';
      return;
    }

    const rows = templates.map(function (template) {
      const name = esc(template.name || template.path);
      return '<div class="smartdeck-template-row">' + name + "</div>";
    });

    container.innerHTML = rows.join("");
  }

  async function handleArchive(e) {
    const btn = e.target;
    const deckId = btn.getAttribute("data-deck-id");
    if (!deckId) return;

    try {
      const response = await fetch("/smartdeck/api/decks/" + deckId + "/archive", {
        method: "POST",
      });
      const result = await response.json();
      if (result.ok) {
        load(); // Refresh the entire UI
      } else {
        alert("Could not archive deck: " + (result.problems || []).join("; "));
      }
    } catch (e) {
      alert("Archive failed: " + e);
    }
  }

  async function handleDelete(e) {
    const btn = e.target;
    const deckId = btn.getAttribute("data-deck-id");
    if (!deckId) return;

    if (!window.confirm("Delete this deck?")) {
      return;
    }

    try {
      const response = await fetch("/smartdeck/api/decks/" + deckId + "/delete", {
        method: "POST",
      });
      const result = await response.json();
      if (result.ok) {
        load(); // Refresh the entire UI
      } else {
        alert("Could not delete deck: " + (result.problems || []).join("; "));
      }
    } catch (e) {
      alert("Delete failed: " + e);
    }
  }

  // Initial load
  load();
})();
