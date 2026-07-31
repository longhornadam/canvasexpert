# Brief — A slide shows at every meeting of its block

**Status:** retired · GREEN · **Author:** Claude Code (session of 2026-07-31)
· **Executor:** Codex · **Lane:** one vertical improvement · **Branch:** `dev`

## Why this exists

The previous batch (`0bcc9ec`) replaced the weekday-keyed block filter with an ordered list
of meetings per day. That work is correct and its gate passed. One decision inside it, D5,
was wrong, and this brief reverses it.

D5 said: when a block meets more than once in a day, a slide bound to that block binds to the
**first** meeting, and the later meetings are named in a problem. Per-meeting binding was
deferred because it looked like it required changing `display.js`'s slide-id contract.

It does not. And the deferral has a teacher-visible cost on the ordinary school day.

## The actual defect

On `Bell Schedule - Bobcat Hour.csv` — the routine day type, six of the eight rows in the
shipped `Day Calendar 2026-27.csv` — the teacher's periods 4 and 5 straddle the bobcat hour.
The block correctly resolves as two entries:

```
ELA 7 Pre-AP GT  11:19-12:09     (period 4)
ELA 7 Pre-AP GT  13:17-14:07     (period 5)
```

`_resolve_slides` in `api/webui/routes/smartdeck.py` gives the slide `start`/`end` from the
first entry only. `chooseSlide` at `api/webui/static/smartdeck/slide_select.js:46-47` matches
a single window. So on the projector the slide shows 11:19-12:09, then the display falls to
"Nothing else scheduled" and **never returns for period 5** — a full 50-minute class with no
slide, every ordinary day.

Before `0bcc9ec` the window was `11:19-14:07`, which covered period 5 and also incorrectly
covered the bobcat hour. So the data model got more correct while the projector got less
useful. Both should be correct.

## Locked decisions

| # | Decision |
|---|---|
| D1 | A slide bound to a block shows at **every** meeting of that block that day, and at none of the gaps between them. This reverses D5 of the retired `schedule-meetings-model` brief. |
| D2 | Carry the meetings as a `windows` list on the resolved slide. Do **not** emit one resolved slide per meeting and do not derive per-meeting slide ids: `display.js` identifies slides by id, and a repeated or synthesised id would wedge the rotation. The id contract is untouched by this batch. |
| D3 | `start` and `end` stay on the resolved slide, equal to the first window, so existing payload consumers and tests keep working. `windows` is authoritative when present. |
| D4 | Both "this block also meets later" diagnostics become obsolete under D1 and are removed, not reworded. A block meeting twice is ordinary operation. |

## What is not in this batch

- **Different content per meeting.** A Review slide and an EXAM slide for the same block still
  cannot be distinguished; the one slide shows at both. That needs slide-level targeting and
  is a separate batch. D1 is strictly better than today either way.
- **The A/B lunch split** inside one period. Still unrepresented, as before.
- **The teacher-facing em-dash sweep.** Opportunistic only.

## First, on this machine

1. `git status` clean, `dev` at `44f9cb5`. `dev` is **80 commits ahead of `origin/dev`**;
   this is expected and you should not push.
2. Baseline: `python -m pytest -q` reports **1915 passed, 1 skipped**. Stop and report if not.
3. `node` must be on PATH (`v22.14.0` here). `api/tests/smartdeck/test_display_js.py` runs the
   `.mjs` suites through pytest and **skips silently without node**, which would hide every
   change in step 2. Confirm the two suites actually run before you trust a green result.

## Step 1 — `windows` on the resolved slide

`api/webui/routes/smartdeck.py`, `_resolve_slides`.

It currently builds `blocks_by_name` (first entry wins) and `blocks_by_name_all` (every
entry). Collapse those to one map of name to the full ordered list, and emit:

```python
"windows": [{"start": b["start"], "end": b["end"]} for b in matches],
"start": matches[0]["start"] if matches else None,
"end": matches[0]["end"] if matches else None,
```

`matches` is every resolved block with that name, already sorted by start time by
`resolve_day`. An unresolved block keeps `windows: []` with `start`/`end` `None`, exactly as
today (`test_smartdeck_display_data_unresolved_block_marked_with_null` covers this).

Delete the `also meets ... this slide shows at the ... meeting only` problem (D4). Keep every
other problem in that function unchanged — the missing-block, no-id, duplicate-id, and
not-an-object cases all still apply.

## Step 2 — `chooseSlide` matches any window

`api/webui/static/smartdeck/slide_select.js`. Keep the file pure: no DOM, no globals. It is
evaluated as text in a bare `vm` context by the test harness.

Add one helper and route both existing time checks through it:

```js
/** Every time window a Slide occupies today, newest shape first, legacy shape second. */
function windowsOf(slide) {
  if (!slide) return [];
  if (Array.isArray(slide.windows) && slide.windows.length) {
    return slide.windows.filter(
      (w) => w && typeof w.start === "string" && typeof w.end === "string");
  }
  return hasTime(slide) ? [{ start: slide.start, end: slide.end }] : [];
}
```

The legacy fallback is what keeps the 15 existing `slide_select.test.mjs` cases meaningful;
do not delete it.

- `chooseSlide`'s current-slide search becomes: the first slide, in authored order, having
  **some** window with `start <= nowHHMM < end`.
- `nextSlideAfter` must scan **windows, not slides**, and report the specific upcoming start.
  `display.js:179` renders `` `Next: ${nextSlide.block} at ${nextSlide.start}` ``, so return
  the slide with `start` overridden to that window's start:

```js
function nextSlideAfter(slides, nowHHMM) {
  let best = null;
  for (const slide of slides) {
    for (const w of windowsOf(slide)) {
      if (w.start <= nowHHMM) continue;
      if (best === null || w.start < best.start) best = { slide, start: w.start };
    }
  }
  return best ? { ...best.slide, start: best.start } : null;
}
```

This keeps `chooseSlide`'s documented return shape (`reason`, `slide`, `nextSlide`) exactly as
it is. `display.js` needs **no change at all** — confirm that rather than assuming it.

Update the `@param state.slides` docblock to describe `windows`.

## Step 3 — retire the obsolete resolver warning

`api/webui/deck_schedule.py`, end of `resolve_day`: remove the `block '...' resolved twice for
...; slides bind to the first meeting` problem and the `seen_names`/`reported_names`
bookkeeping that feeds it (D4). Under D1 the statement it makes is false, and it fires on the
routine Bobcat Hour day for a correctly configured block.

`validate_teacher_schedule` now rejects duplicate block names, so multiple entries sharing a
name always mean one block meeting several times. Nothing else depends on this warning; grep
for the string before deleting to confirm.

## Step 4 — correct the `Exam Review Day` default

`api/default_docs/Calendars/Bell Schedule - Exam Review Day.csv` was added last batch as a
discoverable example of the new format, but its times are garbled: homeroom spans two hours
and 4th period Study Hall lasts five minutes. Replace with the real Tuesday it was modelled
on:

```
period_id,start,end,label
7,08:35,09:30,Review
6,09:35,10:30,Review
homeroom,10:35,11:00,
4,11:05,12:35,Study Hall
6,12:40,14:15,EXAM
7,14:20,15:55,EXAM
```

No test names this file, but `test_default_resolved_runs_never_invert` globs the whole
`Calendars` directory and must still pass.

## Verification

- **Gate:** `python -m pytest -q`, 0 failures. Confirm from the output that
  `slide_select.test.mjs` and `widget_lifecycle.test.mjs` ran rather than skipped.
- New cases in `api/tests/smartdeck/slide_select.test.mjs`:
  1. A slide with two windows is current inside the **second** window.
  2. The same slide is **not** current in the gap between its windows.
  3. During that gap, `nextSlide.start` is the second window's start, not the first's.
  4. A legacy slide carrying only `start`/`end` still behaves exactly as before.
- New case in `api/tests/test_smartdeck_display.py`: the display payload for a block that
  meets twice carries two `windows`, and `start`/`end` equal the first window (D3).
- **The acceptance case.** A deck slide bound to a block on periods `[4, 5]`, resolved against
  `Bell Schedule - Bobcat Hour.csv`. The step 2 algorithm above was prototyped against these
  inputs and produces exactly this; reproduce it and state the observed results in the
  execution report:

  | now | reason | showing | next |
  |---|---|---|---|
  | `11:30` | `clock` | ELA 7 Pre-AP GT | - |
  | `12:30` | `none` | (none) | ELA 7 Pre-AP GT at **13:17** |
  | `13:30` | `clock` | ELA 7 Pre-AP GT | - |

  The `12:30` row is the one that proves `display.js` needs no change: `nextSlide.start` is
  the second window's start, which is what `display.js:179` already renders.
- Browser check per `AGENTS.md`: load a SmartDeck display route in the local app
  (`.claude/launch.json` has `canvas-expert-verify` on port 8766), confirm required globals
  and state, and confirm **zero new console errors**. Source-text tests do not prove browser
  behaviour.
- `git status` clean. Do not push.

## Execution result

**Traffic light:** GREEN

**Commit:** `81f0bb2` (`Support repeated SmartDeck meeting windows`). No push, merge, or
branch was created.

**Changed files:**

- `api/webui/routes/smartdeck.py` — resolved slides carry every ordered block window;
  first `start`/`end` are preserved; obsolete repeated-meeting problem removed.
- `api/webui/static/smartdeck/slide_select.js` — current/next selection scans `windows`,
  with legacy `start`/`end` fallback; `display.js` unchanged.
- `api/webui/deck_schedule.py` — obsolete repeated-block diagnostic/bookkeeping removed.
- `api/default_docs/Calendars/Bell Schedule - Exam Review Day.csv` — corrected seed times.
- `api/tests/smartdeck/slide_select.test.mjs`, `api/tests/test_smartdeck_display.py`,
  `api/tests/test_smartdeck_routes.py`, `api/tests/test_deck_schedule.py` — focused
  regressions and updated expectations for ordinary repeated meetings.

**Evidence:**

- Current preflight: clean `dev`; `HEAD == origin/dev == 80f297d`; remote refresh completed;
  `origin/main == c75b6f5`.
- Baseline before edits: `python -m pytest -q` → `1915 passed, 1 skipped`.
- Focused implementation gate: `python -m pytest -q api/tests/test_smartdeck_display.py
  api/tests/test_deck_schedule.py` → `56 passed`.
- Direct Node suites: `node --test api/tests/smartdeck/slide_select.test.mjs
  api/tests/smartdeck/widget_lifecycle.test.mjs` → `25 passed`.
- Pytest Node bridge: `python -m pytest -q api/tests/smartdeck/test_display_js.py -vv`;
  explicitly ran and passed `slide_select.test.mjs` and `widget_lifecycle.test.mjs`.
- Named full gate: `python -m pytest -q` → `1916 passed, 1 skipped in 64.03s`.
- Bobcat Hour acceptance reproduced exactly: `11:30` → `clock`, ELA 7 Pre-AP GT;
  `12:30` → `none`, next ELA 7 Pre-AP GT at `13:17`; `13:30` → `clock`, ELA 7 Pre-AP GT.
- Browser check: local `canvas-expert-verify` on `127.0.0.1:8766`, live display route
  loaded with a temporary student-free deck; root/control state and not-scheduled render
  were present, with zero browser error/warning logs. The four synthetic files were removed
  afterward (`4 removed, 0 remaining`), and port `8766` is no longer listening.
- `git diff --check` passed; no obsolete repeated-meeting warning references remain in
  implementation or tests.

**Deviations:** The Node directory form `node --test api/tests/smartdeck/` is not accepted
by this Windows Node 22 invocation; both suites were run explicitly by file and through the
pytest bridge, so no coverage was skipped.

**Unresolved decisions:** none.

## Retiring this brief

Per `AGENTS.md`, close GREEN work by accepting it and retiring this brief in the same batch;
Git history is its record. If any step lands RED or YELLOW, leave the brief current and record
the status here. If `windows` turns out to be consumed by a surface not named in step 1, stop
and report rather than widening the change.
