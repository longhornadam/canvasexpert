/* Shared Canvas-write review dialog — single implementation.
 * Exposes window.CE_WRITE_REVIEW.confirm(options) → Promise<boolean>.
 * No dependencies on page-specific scripts or globals.
 */
(function () {
  "use strict";

  var REVIEW = window.CE_WRITE_REVIEW = window.CE_WRITE_REVIEW || {};

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/[&<>"']/g, function (c) {
        return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
                 "\"": "&quot;", "'": "&#39;" })[c];
      });
  }

  REVIEW.confirm = function confirm(options) {
    options = options || {};
    return new Promise(function (resolve) {
      var previousFocus = document.activeElement;
      var backdrop = document.createElement("div");
      var titleId = "ce-review-title-" + Math.random().toString(36).slice(2);
      var targets = options.targets || [];
      var details = options.details || [];
      var warnings = options.warnings || [];
      backdrop.className = "ce-review-backdrop";

      var targetHtml = targets.length
        ? '<ul class="ce-review-list">' + targets.map(function (t) {
            var label = t.name || t.label || "Target";
            var id = t.id ? " (#" + t.id + ")" : "";
            return "<li>" + esc(label) + esc(id) + "</li>";
          }).join("") + "</ul>"
        : '<p class="hint">No target selected.</p>';

      var detailsHtml = details.length
        ? '<ul class="ce-review-list">' + details.map(function (d) {
            return "<li>" + esc(d) + "</li>";
          }).join("") + "</ul>"
        : "";

      var warningsHtml = warnings.length
        ? '<div class="ce-review-warning"><strong>Canvas effects</strong><ul>' +
          warnings.map(function (w) {
            return "<li>" + esc(w) + "</li>";
          }).join("") + "</ul></div>"
        : "";

      backdrop.innerHTML =
        '<div class="ce-review-dialog" role="dialog" aria-modal="true" aria-labelledby="' + titleId + '">' +
          '<h3 id="' + titleId + '">' + esc(options.title || "Review Canvas write") + "</h3>" +
          '<p class="ce-review-action">' + esc(options.action || "Review this Canvas change before continuing.") + "</p>" +
          '<div class="ce-review-section"><strong>Target</strong>' + targetHtml + "</div>" +
          (detailsHtml ? '<div class="ce-review-section"><strong>Change</strong>' + detailsHtml + "</div>" : "") +
          warningsHtml +
          '<div class="ce-review-actions">' +
            '<button type="button" class="secondary ce-review-cancel">' + esc(options.cancelText || "Cancel") + "</button>" +
            '<button type="button" class="danger ce-review-confirm">' + esc(options.confirmText || "Write to Canvas") + "</button>" +
          "</div>" +
        "</div>";

      function close(ok) {
        document.removeEventListener("keydown", onKey);
        backdrop.remove();
        if (previousFocus && typeof previousFocus.focus === "function") {
          previousFocus.focus();
        }
        resolve(ok);
      }

      function onKey(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          close(false);
          return;
        }
        // Trap Tab/Shift+Tab between Cancel and Confirm
        if (event.key === "Tab") {
          var focusable = backdrop.querySelectorAll(
            ".ce-review-cancel, .ce-review-confirm"
          );
          if (focusable.length < 2) return;
          var first = focusable[0];
          var last = focusable[focusable.length - 1];
          if (event.shiftKey) {
            if (document.activeElement === first) {
              event.preventDefault();
              last.focus();
            }
          } else {
            if (document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }
        }
      }

      backdrop.addEventListener("click", function (event) {
        if (event.target === backdrop) close(false);
      });

      // Wait for DOM then wire buttons
      document.body.appendChild(backdrop);

      var cancelBtn = backdrop.querySelector(".ce-review-cancel");
      var confirmBtn = backdrop.querySelector(".ce-review-confirm");

      if (cancelBtn) {
        cancelBtn.addEventListener("click", function () { close(false); });
      }
      if (confirmBtn) {
        confirmBtn.addEventListener("click", function () { close(true); });
      }

      document.addEventListener("keydown", onKey);

      // Focus Cancel first (safe default), not the destructive action
      if (cancelBtn) {
        cancelBtn.focus();
      } else if (confirmBtn) {
        confirmBtn.focus();
      }
    });
  };
})();