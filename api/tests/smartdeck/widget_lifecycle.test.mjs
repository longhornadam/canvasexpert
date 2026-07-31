/**
 * Tests for the widget lifecycle in api/webui/static/smartdeck/display.js.
 *
 * This is the part of the display page a pure function cannot cover: whether mounting
 * and unmounting balance, and whether a slide-scoped timer's interval actually stops
 * when its slide goes away. It needs a DOM-shaped thing, so there is a stub below.
 *
 * The stub is deliberately small and deliberately fake. It models only what display.js
 * touches, and it is not a DOM emulator -- do not grow it to chase broader coverage. If
 * a question needs real DOM or CSS semantics, answer it in a real browser instead.
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
const STATIC = path.join(HERE, "..", "..", "webui", "static", "smartdeck");

const ELEMENT_IDS = [
  "sd-display-root", "sd-clock-skew-warning", "sd-date-banner", "sd-slide-stage",
  "sd-deck-widgets", "sd-not-scheduled", "sd-shuffle", "sd-home", "sd-maximize",
  "sd-minimize", "sd-close", "sd-shuffle-hint",
];

function makeElement(id = "") {
  return {
    id, children: [], hidden: false, disabled: false, className: "", type: "",
    dataset: {}, style: {}, listeners: {}, text: "",
    classList: { add() {}, remove() {} },
    get textContent() { return this.text; },
    set textContent(value) { this.text = String(value); this.children = []; },
    get innerHTML() { return ""; },
    set innerHTML(_value) { this.text = ""; this.children = []; },
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(key, value) { this[key] = value; },
    addEventListener(event, fn) { (this.listeners[event] ||= []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn()); },
    /** Every timer widget in this subtree, however deeply nested. */
    timers() {
      const own = this.className === "sd-timer" ? [this] : [];
      return own.concat(this.children.flatMap((child) => child.timers()));
    },
  };
}

/**
 * Load display.js over a stub document with a controllable clock and an interval
 * registry, then run its DOMContentLoaded handler against `payload`.
 */
async function bootDisplay(payload, { nowISO = "2026-08-14T09:30:00" } = {}) {
  const elements = Object.fromEntries(ELEMENT_IDS.map((id) => [id, makeElement(id)]));
  elements["sd-display-root"].dataset.deckId = "deck-under-test";
  const documentListeners = {};

  let now = new Date(nowISO).valueOf();
  const RealDate = Date;
  class FrozenDate extends RealDate {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
  }

  const intervals = new Map();
  let nextIntervalId = 1;

  const sandbox = {
    console,
    Date: FrozenDate,
    Set, Math, String, Number, Array, Object, Promise, JSON, Boolean,
    window: { location: { href: "" } },
    fetch: async () => ({ ok: true, json: async () => payload }),
    setInterval(fn, ms) { const id = nextIntervalId++; intervals.set(id, { fn, ms }); return id; },
    clearInterval(id) { intervals.delete(id); },
    document: {
      getElementById: (id) => elements[id] || (elements[id] = makeElement(id)),
      createElement: () => makeElement(),
      addEventListener: (event, fn) => (documentListeners[event] ||= []).push(fn),
      documentElement: { requestFullscreen: () => Promise.resolve() },
      exitFullscreen: () => Promise.resolve(),
      fullscreenElement: null,
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(STATIC, "slide_select.js"), "utf8"), sandbox);
  vm.runInContext(fs.readFileSync(path.join(STATIC, "display.js"), "utf8"), sandbox);

  await Promise.all((documentListeners.DOMContentLoaded || []).map((fn) => fn()));
  await new Promise((resolve) => setTimeout(resolve, 0));  // let the fetch chain settle

  return {
    elements,
    sandbox,
    /** Live 1s intervals, i.e. running timer countdowns. */
    countdowns: () => [...intervals.values()].filter((entry) => entry.ms === 1000).length,
    show: (index) => vm.runInContext(`showSlide(payload.slides[${index}])`, sandbox),
    stageTimers: () => elements["sd-slide-stage"].timers().length,
    deckTimers: () => elements["sd-deck-widgets"].timers().length,
    setNow: (iso) => { now = new Date(iso).valueOf(); },
    tickWallClock: () => [...intervals.values()]
      .filter((entry) => entry.ms === 5000).forEach((entry) => entry.fn()),
  };
}

function timerWidget(id, scope, extra = {}) {
  return {
    id, scope, kind: "timer",
    params: { duration_seconds: 3600, label: id, autostart: true, ...extra },
  };
}

/**
 * Build a display payload. Note the shape: /smartdeck/display/{id}/data resolves each
 * Slide's widget references into full widget objects, so slides carry objects here, not
 * ids. Passing ids instead silently mounts nothing.
 */
function deckWith(widgets, slideWidgetIds) {
  const byId = Object.fromEntries(widgets.map((w) => [w.id, w]));
  const hh = (n) => String(n).padStart(2, "0");
  return {
    ok: true, deck_id: "deck-under-test", date: "2026-08-14", title: "Lifecycle",
    server_time: "2026-08-14T09:30:00", problems: [], widgets,
    slides: slideWidgetIds.map((ids, i) => ({
      id: `s${i + 1}`, block: `${i + 1} Period`, layout: "title_only",
      title: `Slide ${i + 1}`, body: "", widgets: ids.map((id) => byId[id]),
      start: `${hh(8 + i)}:00`, end: `${hh(8 + i)}:50`,
    })),
  };
}

test("a slide-scoped timer stops when its slide goes away", async () => {
  const page = await bootDisplay(deckWith(
    [timerWidget("w1", "slide"), timerWidget("w2", "slide")], [["w1"], ["w2"]]));

  page.show(0);
  assert.equal(page.countdowns(), 1, "slide 1's timer is running");
  page.show(1);
  assert.equal(page.countdowns(), 1, "slide 2's timer replaced it rather than joining it");
  assert.equal(page.stageTimers(), 1);
});

test("slide-scoped timers do not accumulate over a long rotation", async () => {
  const page = await bootDisplay(deckWith(
    [timerWidget("w1", "slide"), timerWidget("w2", "slide")], [["w1"], ["w2"]]));

  for (let i = 0; i < 40; i++) page.show(i % 2);
  assert.equal(page.countdowns(), 1,
    "one countdown per visible slide; anything more is an interval outliving its DOM");
});

test("a deck-scoped timer survives slide changes and mounts only once", async () => {
  const page = await bootDisplay(deckWith(
    [timerWidget("shared", "deck")], [["shared"], [], ["shared"]]));

  page.show(0);
  assert.equal(page.deckTimers(), 1, "mounted by the first slide that references it");
  const running = page.countdowns();

  page.show(1);
  assert.equal(page.deckTimers(), 1, "still mounted on a slide that does not reference it");
  assert.equal(page.countdowns(), running, "and still counting");

  page.show(2);
  assert.equal(page.deckTimers(), 1, "not mounted a second time by the slide that does");
});

test("the not-scheduled state also stops slide-scoped timers", async () => {
  const page = await bootDisplay(deckWith([timerWidget("w1", "slide")], [["w1"]]));

  page.show(0);
  assert.equal(page.countdowns(), 1);

  page.setNow("2026-08-14T23:00:00");
  page.tickWallClock();
  assert.equal(page.elements["sd-not-scheduled"].hidden, false, "the panel is showing");
  assert.equal(page.countdowns(), 0, "the timer went away with the slide");
});

test("a timer that is not autostarted registers no countdown until started", async () => {
  const page = await bootDisplay(deckWith(
    [timerWidget("w1", "slide", { autostart: false })], [["w1"]]));

  page.show(0);
  assert.equal(page.countdowns(), 0);
  assert.equal(page.stageTimers(), 1, "it is on screen, just not running");
});

test("re-showing the slide already on screen does not remount its widgets", async () => {
  const page = await bootDisplay(deckWith([timerWidget("w1", "slide")], [["w1"]]));

  page.show(0);
  const before = page.countdowns();
  page.show(0);
  assert.equal(page.countdowns(), before);
  assert.equal(page.stageTimers(), 1);
});
