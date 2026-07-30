# SmartDeck slice 4 — Display view, auto-advance, timer widget

**Lane:** Toyota.
**Depends on:** slice 1 (`resolve_day`), slice 2 (`deck_store.load_deck`).
**Parallel with:** slice 3 — agree `GET /smartdeck/display/{deck_id}` and they don't collide.
**Design spine:** `docs/reference/smartdeck-design.md` §3.1, §3.2, §4.

## Goal

A fullscreen projector view that holds one SmartDeck, watches the clock, and swaps Slides at
period boundaries with no server round-trip. Plus one widget — the timer — proving the
deck-scope vs. slide-scope lifecycle.

## The one architectural decision this slice must get right

§3.1 says auto-advance is client-side and should survive a briefly-unavailable backend. §5.3
says content resolution happens server-side. Those coexist **only if the Display route ships
the entire deck, fully resolved, in one payload.**

So: **`GET /smartdeck/display/{deck_id}` inlines everything.** Every slide, every widget, and
every slide's resolved `start`/`end` clock times for today, in the initial HTML. After that
response, the page makes **zero** further fetches. No per-slide endpoint, no polling, no
websocket. Unplug the backend mid-class and the projector keeps advancing correctly to the end
of the day.

This also bounds §3.2's snapshot semantics: content is frozen at the moment Display is clicked,
for the whole deck at once — not per slide as each one comes up.

## Files to change

### NEW `api/webui/templates/smartdeck_display.html`

**Does not extend `base.html`.** A projector view must not carry app nav, header chrome, or
settings links — a class should never see the teacher's UI. Standalone document: link the
existing `static/ui/tokens.css` for consistent type and color, and nothing else from the app
shell.

Embed the payload as `<script type="application/json" id="deck-payload">…</script>` and parse
it in JS. Do **not** interpolate deck text directly into markup or into a JS string literal —
authored titles and bodies are arbitrary text and will contain quotes, `<`, and newlines.

### EDIT `api/webui/routes/smartdeck.py` (slice 3's file — coordinate)

```
GET /smartdeck/display/{deck_id}   -> smartdeck_display.html, fully inlined
```

Build the payload: `deck_store.load_deck(deck_id)` → for each slide resolve its `block` through
`deps.resolve_schedule_for(deck["date"])` → attach `start`/`end`. Slides whose block doesn't
resolve are included with `start: null` and a reason, and the client skips them (see edge cases).

Payload shape:

```json
{"deck_id": "2026-08-14.r2", "date": "2026-08-14", "title": "...",
 "server_time": "2026-08-14T09:14:22",
 "deck_widgets": [ {...} ],
 "slides": [ {"id": "s1", "block": "4th/5th", "start": "10:35", "end": "12:05",
              "layout": "title_body", "title": "...", "body": "...",
              "widgets": [ {...} ], "problem": null } ]}
```

`server_time` is included so the client can detect a badly-skewed projector clock and say so
rather than silently showing the wrong slide. Compare once at load; warn if off by >2 minutes.

### NEW `api/webui/static/smartdeck/display.js`

Vanilla JS, no dependencies. Responsibilities:

**Auto-advance.** One `setInterval` (~5s is plenty — nothing here needs per-second precision
except the timer's own display). Each tick: compute local wall-clock `HH:MM`, find the slide
whose `[start, end)` contains it, swap if it differs from the current one. Times are local
wall-clock strings end to end — **no `Date` timezone arithmetic, no UTC conversion.** A bell at
10:35 is 10:35.

**Slide render.** `layout` → a DOM builder per layout from the contract's small v1 vocabulary.
Insert authored text with `textContent`, never `innerHTML`.

**Widget lifecycle** — the part worth care:

- `scope: "deck"` widgets mount **once** on load and are never unmounted by a slide change. A
  deck-scoped 5-minute timer started during 1st period keeps counting through the advance into
  2nd period. Do not re-create it, do not reset it.
- `scope: "slide"` widgets mount when their slide becomes current and unmount when it stops
  being current. State is not preserved across a remount — a slide timer that scrolls off and
  comes back starts fresh.

Structurally: keep deck widgets in a container **outside** the slide container, and re-render
only the slide container on advance. Get that DOM split right and the lifecycle rule enforces
itself instead of needing bookkeeping.

**Timer widget.** Params `duration_seconds`, `label`, `autostart`. Countdown display, and touch
interaction for start / pause / reset (the projector is a touchscreen — targets ≥44px, no
hover-only affordances). At zero: a visible state change, no audio in v1.

**Corner chrome.** Persistent, low-prominence: Maximize (`requestFullscreen`), Minimize (exit
fullscreen), Close (back to `/smartdeck`). It must stay reachable while a slide is showing (§4).
Exact icon set is an open design item — keep it plain and don't invent a new control language.

### NEW `api/webui/static/smartdeck/display.css`

Projector-first sizing: readable from the back of a room. Large base type, high contrast,
generous line height. Consume `tokens.css`; add no new palette.

### NEW `api/tests/test_smartdeck_display.py`

Route-level tests. The clock/lifecycle logic is JS and won't be unit-tested here — so the
route tests must at minimum prove the payload contract that the JS depends on.

## Edge cases (each needs a test or an explicit handled state)

1. **No slide matches the current time** (before first bell, lunch, after dismissal) → a neutral
   "nothing scheduled right now" state showing the next slide's block and start time. Not a
   blank screen, not the last slide left up.
2. **Two slides claim overlapping windows** (authoring error) → first by `start` wins
   deterministically; do not flicker between them.
3. **Slide whose block didn't resolve** (`start: null`) → skipped by advance, never shown.
4. **All slides unresolvable** → the deck renders the "not scheduled" state with the reasons,
   rather than an empty document.
5. **Deck date is not today** → render, but banner it clearly. The teacher may be previewing
   tomorrow's deck; auto-advance against today's clock would be nonsense.
6. **Projector clock skewed >2 min from `server_time`** → visible warning.
7. **Deck with zero widgets** → renders fine; no empty widget container in the layout.
8. **Deck-scoped timer running across an advance** → still running, same remaining time.
9. **`deck_id` not found / archived** → clean error page, not a traceback.
10. **Backend killed after load** → advance keeps working for the rest of the day. Verify by
    hand: load Display, stop `qf_ui.py`, confirm the next boundary still advances.

## Test command

```bash
py -m pytest api/tests/test_smartdeck_display.py -v
```

Then:

```bash
py -m pytest api/tests
```

Manual verification (this slice is mostly visual — do it):

1. `cd api; py qf_ui.py`, save a two-slide deck for today via MCP with a deck-scoped timer.
2. Open Display. Confirm the correct slide for the current time.
3. Temporarily edit the Bell Schedule CSV so a boundary lands ~1 minute out, reload, and watch
   the advance happen with the timer still counting.
4. Stop the backend. Confirm the next advance still fires (edge case 10).

## Acceptance criteria

- The Display response contains every slide and every resolved time. Assert in the route test
  that all slides appear in the payload — **and** that no second endpoint exists for fetching
  one slide.
- After load, the page issues zero network requests. Verify in devtools; state it in the PR.
- A deck-scoped timer survives a slide advance with its remaining time intact.
- A slide-scoped widget unmounts on advance.
- No `innerHTML` with deck-authored text: `grep -n "innerHTML" api/webui/static/smartdeck/display.js`
  shows no line where authored title/body/label flows in.
- The view carries no app nav or settings affordance.
- Off-schedule times show the neutral state, not a blank or stale slide.
- `py -m pytest api/tests` is green.

## Guardrails

- **#2 (FERPA):** no student data in this slice. Feeds are not implemented — if a `feed` key
  reaches the client, slice 2's validator has a hole; stop and report it.
- **#4 (local-only):** same app, same `127.0.0.1` bind, no new process, no external asset. No
  CDN font, no CDN script — everything from `static/`.

## Do not touch

- `deck_store.py`, `df.py`, `deck_schedule.py` — call them; don't edit them.
- `templates/base.html` — this view deliberately doesn't use it.
- `templates/smartdeck.html` and `smartdeck.js` — slice 3's management screen.
- Feed resolution / Canvas Mirror. Still not this slice.
