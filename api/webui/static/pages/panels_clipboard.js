/**
 * Panels console clipboard: copying the link (a <code> address) and copying
 * the embed code (a readonly <input>) need different native selection
 * mechanisms before document.execCommand("copy") has anything to act on.
 * Selecting an <input>'s value via DOM Range/Selection selects nothing --
 * an input has no exposed text node for a Range to walk -- and a <code>
 * element has no .select() method. Kept separate from the console page's
 * own DOM wiring so this split is testable without a browser.
 *
 * Loaded as a plain script before the console page's inline script. Read
 * directly, as text, by api/tests/panels/panels_clipboard.test.mjs.
 */

/** Select a non-input element's whole text via Range/Selection. */
function selectRangeText(el, doc, win) {
  var range = doc.createRange();
  range.selectNodeContents(el);
  var selection = win.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

/** Select an <input>/<textarea>'s value the native way. */
function selectInputText(el) {
  el.focus();
  el.select();
  if (typeof el.setSelectionRange === "function") {
    el.setSelectionRange(0, String(el.value || "").length);
  }
}

/**
 * Copy `text` to the clipboard. Tries the async Clipboard API first; falls
 * back to selecting `fallbackEl` (the visible source of `text`) and calling
 * document.execCommand("copy"). `isInput` picks the selection mechanism that
 * fits `fallbackEl` -- true for the embed <input>, false for the address
 * <code>. Returns a Promise<boolean>: true only on a demonstrated copy.
 * document.execCommand("copy") === false, or a thrown exception, is failure,
 * never reported as success.
 */
function copyPanelText(text, fallbackEl, isInput, doc, win) {
  function execCommandCopy() {
    try {
      if (isInput) {
        selectInputText(fallbackEl);
      } else {
        selectRangeText(fallbackEl, doc, win);
      }
      var ok = doc.execCommand("copy");
      if (!isInput) {
        win.getSelection().removeAllRanges();
      }
      return ok === true;
    } catch (e) {
      return false;
    }
  }

  if (win.navigator && win.navigator.clipboard && win.navigator.clipboard.writeText) {
    return win.navigator.clipboard.writeText(text).then(
      function () { return true; },
      function () { return execCommandCopy(); }
    );
  }
  return Promise.resolve(execCommandCopy());
}
