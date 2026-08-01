/**
 * Tests for api/webui/static/pages/panels_clipboard.js -- the Panels console's
 * copy-link/copy-embed logic. Needs a DOM-shaped thing (document.createRange,
 * window.getSelection, document.execCommand, an <input>-like element), so
 * there is a small stub below. The stub models only what panels_clipboard.js
 * touches; it is not a DOM emulator.
 *
 * Run via `node --test api/tests/panels/`, or through test_panels_js.py with pytest.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import vm from "node:vm";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const SOURCE = path.join(HERE, "..", "..", "webui", "static", "pages", "panels_clipboard.js");

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SOURCE, "utf8"), sandbox);
const { copyPanelText } = sandbox;

/** Stands in for the embed <input readonly>: supports .select()/.setSelectionRange(). */
function makeInputElement(value) {
  return {
    value,
    focused: false,
    selectedAll: false,
    selectionRange: null,
    focus() { this.focused = true; },
    select() { this.selectedAll = true; },
    setSelectionRange(start, end) { this.selectionRange = [start, end]; },
  };
}

/** Stands in for the address <code>: no .select(), only reachable via Range. */
function makeCodeElement() {
  return { tagName: "CODE", rangeSelected: false };
}

function makeDocStub({ execCommandResult = true, throwOnExecCommand = false } = {}) {
  let rangeTarget = null;
  return {
    createRange() {
      return { selectNodeContents(el) { rangeTarget = el; } };
    },
    execCommand(cmd) {
      assert.equal(cmd, "copy");
      if (throwOnExecCommand) throw new Error("execCommand blocked");
      if (rangeTarget) rangeTarget.rangeSelected = true;
      return execCommandResult;
    },
  };
}

function makeWinStub({ clipboardWriteText } = {}) {
  let removedRanges = 0;
  let addedRange = null;
  const selection = {
    removeAllRanges() { removedRanges += 1; },
    addRange(range) { addedRange = range; },
  };
  return {
    navigator: clipboardWriteText ? { clipboard: { writeText: clipboardWriteText } } : {},
    getSelection() { return selection; },
    _selectionState: () => ({ removedRanges, addedRange }),
  };
}

test("async Clipboard API success never touches the execCommand fallback", async () => {
  const doc = makeDocStub();
  let execCalled = false;
  doc.execCommand = () => { execCalled = true; return true; };
  const win = makeWinStub({ clipboardWriteText: async () => {} });
  const el = makeInputElement("embed code");

  const ok = await copyPanelText("embed code", el, true, doc, win);

  assert.equal(ok, true);
  assert.equal(execCalled, false);
  assert.equal(el.selectedAll, false); // the async path needed no selection at all
});

test("embed (input) fallback selects via .select()/.setSelectionRange, not a DOM Range", async () => {
  const doc = makeDocStub({ execCommandResult: true });
  const win = makeWinStub({ clipboardWriteText: async () => { throw new Error("denied"); } });
  const el = makeInputElement("<iframe src=\"...\"></iframe>");

  const ok = await copyPanelText(el.value, el, true, doc, win);

  assert.equal(ok, true);
  assert.equal(el.focused, true);
  assert.equal(el.selectedAll, true);
  assert.deepEqual(el.selectionRange, [0, el.value.length]);
});

test("address (code) fallback selects via Range/Selection, never .select()", async () => {
  const doc = makeDocStub({ execCommandResult: true });
  const win = makeWinStub({ clipboardWriteText: async () => { throw new Error("denied"); } });
  const el = makeCodeElement();

  const ok = await copyPanelText("http://127.0.0.1:8765/panels/whats-due", el, false, doc, win);

  assert.equal(ok, true);
  assert.equal(el.rangeSelected, true);
  const state = win._selectionState();
  assert.equal(state.removedRanges >= 1, true);
  assert.ok(state.addedRange);
});

test("no Clipboard API present goes straight to the execCommand fallback", async () => {
  const doc = makeDocStub({ execCommandResult: true });
  const win = makeWinStub({}); // navigator.clipboard is absent
  const el = makeInputElement("text");

  const ok = await copyPanelText("text", el, true, doc, win);

  assert.equal(ok, true);
  assert.equal(el.selectedAll, true);
});

test("execCommand('copy') === false is reported as failure, not success", async () => {
  const doc = makeDocStub({ execCommandResult: false });
  const win = makeWinStub({});
  const el = makeInputElement("text");

  const ok = await copyPanelText("text", el, true, doc, win);

  assert.equal(ok, false);
});

test("a thrown exception during the fallback is failure, never success", async () => {
  const doc = makeDocStub({ throwOnExecCommand: true });
  const win = makeWinStub({});
  const el = makeInputElement("text");

  const ok = await copyPanelText("text", el, true, doc, win);

  assert.equal(ok, false);
});
