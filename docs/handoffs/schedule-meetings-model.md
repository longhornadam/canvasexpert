# Brief — Model the school day as an ordered list of meetings

**Status:** GREEN; complete; retiring · **Author:** Claude Code (session of 2026-07-31)
· **Executor:** external · **Lane:** one vertical improvement · **Branch:** `dev`

## Why this exists

The schedule resolver describes a school day with two independent mechanisms, and only one of
them is keyed to the calendar:

- **The day calendar** maps a date to a named bell schedule. Fully date-driven. "Friday
  Schedule on a Monday" is one row in a CSV.
- **`weekdays` on a teacher block** filters by `date.weekday()`. A weekly recurrence.

Whenever the school runs a day type off its usual weekday — exam week, a pep rally, the day
after a holiday — the two disagree, and `weekdays` wins by dropping blocks the teacher
actually teaches.

The user's real semester exam schedule (Dec 15-19 2025, Bammel Middle School) was transcribed
and run through the current parser. It breaks the model in four separate ways, documented
below. That schedule is the acceptance target for this batch.

The deeper correction, decided by the user this session: **at this school a period and a
course are the same thing.** Period 4 *is* ELA 7 Pre-AP GT. There is no rotation in which
period 4 hosts a different course on a different day. Given that identity, "which classes do
I have today" is fully determined by "which periods occur today," which is a property of the
day's bell schedule alone. `weekdays` is therefore not merely unused here — it is redundant
by construction, and can only ever subtract a class that should have met.

## The actual defect

Monday Dec 15 resolves correctly today, and it is already the motivating case: its bell times
are byte-for-byte `api/default_docs/Calendars/Bell Schedule - Friday.csv` running on a Monday.
A homeroom block pinned to `weekdays: [4]` disappears on that day.

Tuesday Dec 16 (`7th Review, 6th Review, Homeroom, 4th Study Hall, 6th EXAM, 7th EXAM`) fed
to `parse_bell_schedule` and `resolve_day` with the user's four real blocks:

```
parsed period_ids: ['7', '6', 'homeroom', '4']      <- six rows in, four out
PARSE PROBLEM: Duplicate period_id 6; using the last row
PARSE PROBLEM: Duplicate period_id 7; using the last row
resolved: ELA 7  p[6, 7]  12:40-15:55
RESOLVE PROBLEM: block 'Athletics' omitted: periods ['1'] not in schedule
RESOLVE PROBLEM: block 'Computer Science' omitted: periods ['2'] not in schedule
RESOLVE PROBLEM: block 'ELA 7 Pre-AP GT' omitted: periods ['5'] not in schedule
```

Both Review meetings are silently discarded. The teacher has four separate meetings of their
ELA 7 sections that day and the model reports one 3h15m block. Friday Dec 19 resolves to
nothing at all with four warnings, though the teacher has homeroom 10:15-12:00.

Four assumptions in `api/webui/deck_schedule.py` that real days violate:

| # | Assumption | Where | Violated by |
|---|---|---|---|
| A1 | A period occurs at most once per day | `period_map = {p["period_id"]: p ...}`, `resolve_day` | 6th Review + 6th EXAM on the same day |
| A2 | Period order is chronological | `period_ids[0]` → start, `period_ids[-1]` → end | Tue runs 7, 6, 4, 6, 7; Pep Rally runs 1, 2, 3, 5, 4, 6, 7 |
| A3 | A multi-period block is one continuous window | same | Bobcat Hour puts `bobcat` between 4 and 5 |
| A4 | Everything on the schedule is a class period | CSV columns | Volleyball game, early dismissal, A/B lunch split |

A2 is already a live defect on shipped defaults: block `[4, 5]` against
`Bell Schedule - Pep Rally.csv` resolves to `11:35-11:30`, end before start, with no problem
emitted. `parse_bell_schedule` validates start/end per row; nothing validates the composed
envelope.

## Locked decisions

Decided by the user this session. Do not relitigate.

| # | Decision |
|---|---|
| D1 | A period and a course are the same thing at this school. The day's period list determines the day's classes. Do not reintroduce any per-block recurrence rule. |
| D2 | Retire the `weekdays` axis entirely rather than re-keying it to `schedule_id`. The meetings model subsumes it. |
| D3 | A bell schedule is an **ordered list of meetings**, not a map keyed by period. Duplicate `period_id` in one day is legal and must round-trip. |
| D4 | A block whose periods do not occur today is **silently absent**, never a problem. Typos are caught at save time, not once per day. |
| D5 | Slide-to-block binding stays one slide per block per day in this batch. When a block meets more than once, the slide binds to the **first** meeting and the later ones are named in a problem. Per-meeting slides are a separate batch; do not change `display.js`'s slide-id contract here. |
| D6 | Resolved-block fields `name`, `label`, `start`, `end`, `raw_periods`, `schedule_id` keep their current names and meanings. New fields are additive. |

## What is not in this batch

- **Per-meeting slides.** D5 defers this. It needs a slide-targeting syntax and a `display.js`
  id change, and it is not required to fix the data loss.
- **A/B lunch split inside one period.** Needs a nested-segment concept; the exam schedule's
  `A Lunch / B Lunch` rows are out of scope. Leave them unrepresented.
- **Authoring UI for bell schedules.** CSVs are still hand-authored or uploaded as today.
- **The teacher-facing em-dash sweep** (~290 occurrences). Fix opportunistically in files you
  are already editing; do not open the sweep.

## First, on this machine

1. `git status` should be clean and `dev` should be at `71d8600`. `dev` is **76 commits ahead
   of `origin/dev`** and this is expected; do not push as part of this batch.
2. `core.hooksPath` was set to `.githooks` this session. `.githooks/pre-commit` now runs and
   blocks retired paths (`api/tests/test_retired_paths.py`) plus tokens and PII.
3. Baseline: `python -m pytest -q` reports **1925 passed, 1 skipped**. If it does not, stop
   and report what differs.

## Step 1 — `parse_bell_schedule` returns ordered meetings

`api/webui/deck_schedule.py`.

Add an optional `label` column. Accept duplicate `period_id`. Return a list sorted by `start`,
each entry:

```python
{"seq": 0, "period_id": "7", "start": "08:35", "end": "09:30", "segment": "Review"}
```

- `seq` is the 0-based index **after** sorting by `start`, so it is the day's true running
  order even when the CSV lists periods out of sequence.
- `segment` carries the CSV's `label` value (`Review`, `EXAM`, `Study Hall`, `Volleyball
  Game`) or `""`. It is named `segment` and not `label` so it cannot be confused with a
  teacher block's `label`, which is a different thing (D6).
- Delete the duplicate-`period_id` problem and the last-row-wins behaviour. Duplicates are
  now legal (D3).
- Keep the existing per-row time validation and the `end` before `start` row check.
- A row whose `period_id` matches no teacher block is still returned. That is how the
  volleyball game and an early dismissal reach `get_bell_schedule` (A4, partial).

## Step 2 — `resolve_day` groups consecutive meetings

Replace the `period_map` lookup and the `first`/`last` envelope with a single walk.

A block **claims** a meeting when `str(meeting["period_id"])` is in
`[str(p) for p in block["raw_periods"]]`.

Walk the day's meetings in `seq` order. Group each **maximal run of consecutive meetings
claimed by the same block** into one resolved entry:

```python
{"name": ..., "label": ..., "start": run[0]["start"], "end": run[-1]["end"],
 "raw_periods": block["raw_periods"], "schedule_id": ...,
 "period_ids": ["6", "7"], "segments": ["EXAM", "EXAM"], "seq": run[0]["seq"]}
```

Sort the result by `start`. This rule produces the correct answer on every case tested:

| Day | Block | Today | After |
|---|---|---|---|
| Friday sched | `[4, 5]` | `11:19-13:38` | `11:19-13:38`, one entry (unchanged) |
| Bobcat Hour | `[4, 5]` | `11:19-14:07`, swallows `bobcat` | two entries: `11:19-12:11`, `13:17-14:11` |
| Pep Rally | `[4, 5]` | `11:35-11:30`, inverted | one entry `10:50-12:55` (5 then 4 are consecutive) |
| Tue Dec 16 | `[6, 7]` | `12:40-15:55`, reviews lost | two entries: `08:35-10:30` Review, `12:40-15:55` EXAM |

Also in this step:

- **Absence is silent (D4).** Delete the `block '...' omitted: periods [...] not in schedule
  '...'` problem. A block with no claimed meetings today simply produces no entry.
- **Keep** the existing "resolved twice" diagnostic only in the form D5 requires; the
  resolver itself no longer treats multiple entries as an error.
- Assert in a test that a run's `end` is never earlier than its `start`.

## Step 3 — retire the `weekdays` axis

`api/webui/deck_schedule.py`:

- Delete `_weekday_set`, `_block_meets`, and `effective_weekdays`. **`effective_weekdays` is
  already dead** — defined at line 175 and called from nowhere in the repository, tests
  included. Verify with a repo-wide search before deleting.
- `validate_teacher_schedule`: drop every weekday check. Replace the "same name on
  overlapping weekdays" rule with two rules that follow from D1:
  - two blocks must not claim the same `period_id`;
  - block `name` must be unique.
- `parse_teacher_schedule`: ignore a legacy `weekdays` key silently. Existing files must not
  start failing.
- **Save-time period validation (D4).** Add a check that every `raw_periods` entry appears in
  at least one bell schedule in the workspace. This is the replacement for the per-day
  omission warning, and it is the only place a typo like period `8` should surface. It needs
  the bell schedules, so it belongs in the write path (`api/webui/schedule_setup.py` or
  `api/webui/routes/schedule.py`), not in the pure `deck_schedule` module — keep
  `deck_schedule.py` free of file IO as its module docstring requires.

`api/webui/static/settings/class_schedule.js`:

- Remove the Days column, the `weekdays` array at line 11, the checkbox rendering around
  lines 154-157, and the read-back at lines 191-201. Stop writing `weekdays`; strip it from
  loaded blocks so the next save cleans the file.
- Remove the trailing sentence "Leave the days unchecked when a block meets every school
  day." from the help text.
- `api/webui/static/pages/settings.css` lines 67-70 hold `.ce-schedule-weekdays`,
  `.ce-schedule-field-label`, `.ce-schedule-day-list`, and `.ce-schedule-day-list label`.
  All four are reachable only from the Days markup at `class_schedule.js:154` — confirm with
  a repo-wide search, then remove them. Do not introduce a raw hex colour or a forbidden
  selector; `test_presentation_contracts.py` scans this directory.

Docs and templates carrying the `weekdays` contract, all of which need updating:
`api/default_docs/SmartDecks/Teacher Schedule.template.json`,
`api/default_docs/AI Authoring/Author a Class Schedule.txt`,
`docs/reference/smartdeck-module-map.md`, `docs/reference/settings-module-map.md`,
and the MCP tool schema `api/mcp_server/tool_schema_v15.json` if it describes the block shape
(check v13 and v14 as well; if they are frozen historical copies, leave them alone and say so).

## Step 4 — consumers

- `api/webui/routes/smartdeck.py`, `_resolve_slides`: `blocks_by_name = {b["name"]: b for b
  in blocks}` currently keeps the **last** entry for a repeated name. Per D5 change it to keep
  the **first**, and append a problem naming each later meeting, e.g. `slide 'x': block 'ELA
  7' also meets 12:40-15:55; this slide shows at the 08:35 meeting only`.
- `api/smartdeck_feeds.py`, `_bell_schedule_feed`: `day_type = blocks[0]["schedule_id"]`
  returns `None` whenever the teacher has no class that day, which is wrong on a day like
  Friday Dec 19. Read `day_type` from the day calendar directly instead of from the first
  resolved block. The `current_block` time scan already works and gets **more** accurate with
  per-meeting entries; leave its logic alone.
- `api/mcp_server/tools.py`: update the `get_day_schedule` docstring for the new fields, and
  `get_bell_schedule` for the meeting shape. Both are ungated and student-free; that does not
  change.
- `api/webui/deps.py`: `load_bell_schedules` and `resolve_schedule_for` need no logic change,
  but re-read their docstrings and correct any that describe the old shape.

## Step 5 — fixtures and defaults

`api/tests/fixtures/class_schedule/` currently encodes an A/B rotation via `weekdays`: period
1 is Algebra Foundations on Mon/Wed and Pre-Algebra on Tue/Thu. That contradicts D1 and cannot
survive step 3. Rewrite it as a rotation that is expressible under the meetings model, which
is also how real A/B schools number periods:

- `Bell Schedule - Example Day A.csv` — periods 1, 2, 3, 4
- `Bell Schedule - Example Day B.csv` — periods 5, 6, 7, 8
- `Bell Schedule - Example Short Day.csv` — all eight, compressed
- `Day Calendar - Example Alternating Day Split.csv` — alternate A/B, and **place at least one
  short day on a non-Friday**, which is the regression this batch exists to prevent
- `Teacher Schedule.json` — eight blocks, one per period, no `weekdays`

Add one default that makes the new format discoverable, modelled on the real exam Tuesday and
exercising duplicate `period_id` plus a `label`:
`api/default_docs/Calendars/Bell Schedule - Exam Review Day.csv`.

New tests in `api/tests/test_deck_schedule.py` (the existing weekday tests at lines ~350-500
are removed by step 3, so this replaces roughly that volume):

1. A duplicate `period_id` round-trips and resolves to two entries with distinct `segments`.
2. A non-contiguous block (`[4, 5]` with `bobcat` between) resolves to two entries.
3. A reordered schedule (`5` before `4`) resolves to one entry with `start` < `end`.
4. A block whose periods do not occur today yields no entry **and no problem**.
5. A run's `end` is never earlier than its `start`, over every default bell schedule.

New test in `api/tests/test_schedule_fixture.py`:

6. The short day resolves the **same class set** whichever weekday the day calendar puts it
   on. This is the user's original concern, locked.

## Verification

- **Gate:** `python -m pytest -q` reports 0 failures. This is a schema change across the
  resolver, settings UI, feeds, and MCP surface, so the full API suite is the declared
  integration gate for this batch rather than a focused subset.
- The four exam-week days transcribed from the schedule in this brief resolve without data
  loss: Tuesday yields four ELA 7 meetings across two entries, Friday yields homeroom.
- Browser check, per `AGENTS.md`: load the class-schedule settings route and a SmartDeck
  display route in the local app, confirm the Days control is gone, confirm required globals
  and state, and confirm **zero new browser console errors**. Source-text tests do not prove
  browser behaviour.
- `git status` clean. Do not push (see preflight 1).

## Execution result

- **Traffic light:** GREEN.
- **Commit:** `0bcc9ec` (`Model school days as ordered meetings`).
- **Changed:** ordered Bell Schedule meetings with duplicate IDs and labels; consecutive-run
  resolution with additive meeting fields; weekday-axis retirement and save-time period checks;
  SmartDeck/feed/MCP consumers; Settings UI; defaults, fixtures, and focused regressions.
- **Evidence:** baseline `1925 passed, 1 skipped`; focused changed-surface matrix `232 passed`;
  full API suite `1915 passed, 1 skipped`; browser check returned Settings and Display 200,
  confirmed the Days control absent, and recorded zero console/page errors.
- **Deviations:** none. The lower final count reflects intentional removal of the obsolete
  weekday test block and replacement with the meetings-model coverage. MCP schema v13/v14 were
  left unchanged because they contain no Teacher Schedule block-shape contract. No unresolved
  decisions.

## Retiring this brief

Per `AGENTS.md`, close GREEN work by accepting it and retiring this brief in the same batch;
Git history is its record. If any step lands RED or YELLOW, leave the brief current and record
the status here. A public contract change discovered mid-flight — for example if the MCP block
shape turns out to be a frozen external contract — is RED: stop and report.
