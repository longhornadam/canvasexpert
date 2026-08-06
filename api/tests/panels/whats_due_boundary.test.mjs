import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import vm from "node:vm";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const SOURCE = path.join(HERE, "..", "..", "webui", "static", "panels", "panel.js");
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SOURCE, "utf8"), sandbox);
const { msUntilMinutes } = sandbox.window.Panel;

test("future boundary includes the twenty-second cushion", () => {
  const now = new Date(2026, 7, 17, 8, 30, 0, 0);

  assert.equal(msUntilMinutes(545, now), 35 * 60 * 1000 + 20 * 1000);
});

test("a boundary already passed today does not arm a timer", () => {
  const now = new Date(2026, 7, 17, 9, 6, 0, 0);

  assert.equal(msUntilMinutes(545, now), null);
});

test("display strings are rejected instead of parsed", () => {
  const now = new Date(2026, 7, 17, 8, 30, 0, 0);

  assert.equal(msUntilMinutes("545", now), null);
  assert.equal(msUntilMinutes(NaN, now), null);
  assert.equal(msUntilMinutes(1440, now), null);
});
