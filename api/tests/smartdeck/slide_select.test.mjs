/**
 * Tests for api/webui/static/smartdeck/slide_select.js -- the pure decision half of the
 * display page. No DOM and no stubbing: slide_select.js touches no browser globals, so
 * it is evaluated as text in a bare vm context and called directly.
 *
 * Run via `node --test api/tests/smartdeck/`, or through test_display_js.py with pytest.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import vm from "node:vm";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const SOURCE = path.join(HERE, "..", "..", "webui", "static", "smartdeck", "slide_select.js");

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SOURCE, "utf8"), sandbox);
const { chooseSlide } = sandbox;

/** A resolved slide. start/end null models a block that did not resolve today. */
function slide(id, start, end, block = id) {
  return { id, block, start, end, layout: "title_only", title: id, body: "", widgets: [] };
}

const DAY = [
  slide("s1", "08:00", "08:50", "1st Period"),
  slide("s2", "09:00", "09:50", "2nd Period"),
  slide("s3", "10:00", "10:50", "3rd Period"),
];

function decide(slides, nowHHMM, extra = {}) {
  return chooseSlide({
    slides, nowHHMM, shuffleOn: false, shuffleIndex: 0, homeFallbackActive: false, ...extra,
  });
}

test("shows the block that is current", () => {
  const d = decide(DAY, "09:30");
  assert.equal(d.reason, "clock");
  assert.equal(d.slide.id, "s2");
});

test("start is inclusive and end is exclusive", () => {
  assert.equal(decide(DAY, "09:00").slide.id, "s2");
  assert.equal(decide(DAY, "08:50").reason, "none", "08:50 is past the end of 1st period");
  assert.equal(decide(DAY, "09:49").slide.id, "s2");
});

test("nothing current, and nothing pressed, means none", () => {
  const d = decide(DAY, "07:00");
  assert.equal(d.reason, "none");
  assert.equal(d.slide, null);
});

test("authored order breaks a tie between slides on the same block", () => {
  const tied = [slide("first", "09:00", "09:50"), slide("second", "09:00", "09:50")];
  assert.equal(decide(tied, "09:30").slide.id, "first");
});

test("slides whose block did not resolve are never chosen", () => {
  const unresolved = [slide("ghost", null, null), slide("real", "09:00", "09:50")];
  assert.equal(decide(unresolved, "09:30").slide.id, "real");
  assert.equal(decide(unresolved, "07:00").reason, "none");
});

test("an empty deck reports empty rather than throwing", () => {
  const d = decide([], "09:30");
  assert.equal(d.reason, "empty");
  assert.equal(d.slide, null);
  assert.equal(chooseSlide({}).reason, "empty", "a missing slides key is also empty");
});

test("Home holds slide 1 when nothing is current", () => {
  const d = decide(DAY, "07:00", { homeFallbackActive: true });
  assert.equal(d.reason, "home_fallback");
  assert.equal(d.slide.id, "s1");
});

test("Home defers to the clock when something is current", () => {
  const d = decide(DAY, "09:30", { homeFallbackActive: true });
  assert.equal(d.reason, "clock", "the clock wins, so the caller can spend the fallback");
  assert.equal(d.slide.id, "s2");
});

test("Home falls back to slide 1 even when no block resolved at all", () => {
  const broken = [slide("a", null, null), slide("b", null, null)];
  assert.equal(decide(broken, "09:30", { homeFallbackActive: true }).slide.id, "a");
});

test("shuffle drives by index and ignores the clock", () => {
  const at = (i) => decide(DAY, "07:00", { shuffleOn: true, shuffleIndex: i }).slide.id;
  assert.equal(at(0), "s1");
  assert.equal(at(2), "s3");
  assert.equal(at(3), "s1", "index wraps");
  assert.equal(at(-1), "s3", "a negative index wraps rather than showing nothing");
});

test("shuffle beats an active Home fallback", () => {
  const d = decide(DAY, "07:00", { shuffleOn: true, shuffleIndex: 1, homeFallbackActive: true });
  assert.equal(d.reason, "shuffle");
  assert.equal(d.slide.id, "s2");
});

test("next slide is the soonest upcoming one", () => {
  assert.equal(decide(DAY, "07:00").nextSlide.id, "s1");
  assert.equal(decide(DAY, "08:55").nextSlide.id, "s2");
});

test("next slide is chosen by time, not authored position", () => {
  // Authored out of order, which used to make the page advertise the wrong block.
  const outOfOrder = [
    slide("late", "14:00", "14:50", "7th Period"),
    slide("early", "09:00", "09:50", "2nd Period"),
  ];
  assert.equal(decide(outOfOrder, "07:00").nextSlide.id, "early");
});

test("next slide is null once the day is over", () => {
  const d = decide(DAY, "23:00");
  assert.equal(d.reason, "none");
  assert.equal(d.nextSlide, null);
});

test("a slide with no resolved time is never offered as next", () => {
  assert.equal(decide([slide("ghost", null, null)], "07:00").nextSlide, null);
});
