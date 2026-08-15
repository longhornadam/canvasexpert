# Glass — classroom display initiative

**Status:** Closed GREEN — Slice 3 accepted. Supersedes Panels.

**Opened:** 2026-08-15

**Current next pointer:** Slice 4 (privacy inversion) in section 8 is next and requires only
sections 5.1–5.3 of this brief. Outstanding senior decisions in section 11 remain carried
forward; no further class-mode design decision is required to start Slice 4.

## 1. Authority and disposition

Glass is one local page that shows the important information for the current classroom, resolved
from the clock and the School Calendar. It replaces Panels entirely. It is the third and final
attempt at a classroom display in this repository; the two prior attempts are closed and their
paths are guarded.

| Lineage | Disposition |
| --- | --- |
| Scenes | Origin brainstorm, preserved at `docs/reference/Architecture Narrative - Scenes.md`. Context only, not authority. |
| Glass (2025) | Removed in `3e4e58e` (−1,895 lines). The name is reused here; none of the code is. |
| SmartDeck | Removed in `0f09ee9` (108 files, −6,047 lines). Paths guarded by `api/tests/test_retired_paths.py`. |
| Panels | Current. Retired by this initiative — see section 9. |

Both prior attempts died carrying an authoring platform: deck/slide/pane registries, widget
systems, template libraries, and MCP write surfaces for layout. **Glass has no authoring.** One
layout, in code, changed by editing code. This is the single most important constraint in this
document, and it is what makes a third attempt defensible.

The prior motivation for a swappable third-party host (Classroomscreen compatibility) is
withdrawn. Glass runs full-screen in a browser on the same machine that drives the projector.
There is no embed contract, no port-stability promise, and no saved-URL durability requirement.

## 2. Settled decisions

These are resolved. Do not re-litigate them during execution.

1. **Two modes, not seven states.** Class mode when a class of this teacher's is meeting or about
   to meet; board mode otherwise. Board mode is school-facing and carries no student data.
2. **Course, not section.** The teacher runs one Canvas course per class (three courses, three
   student groups). `course_id` fully identifies the room. No section binding, no section filter,
   no per-section due-date work.
3. **Period and course are 1:1.** A schedule block maps fixed `raw_periods` to one `course_id`.
   The bell schedule decides *when* a period happens; the Teacher Schedule decides *what* it is.
   A day that reorders, shortens, or splits periods requires no special case.
4. **Mirror-only.** Glass reads the local mirror, the local catalog, and the workspace Library. It
   never calls Canvas. A live call would place network latency and token failure on a classroom
   wall.
5. **15-minute data freshness is sufficient.** Correctness at bell boundaries is a separate
   concern and is handled by the resolver's `valid_until`, not by the poll.
6. **Real names on the wall.** Pseudonymization is the MCP boundary, not the display boundary.
   `student_name` is classroom-facing per `docs/contracts/classroom-facing-data-contract.md` and
   `api/audience.py`. Glass renders shortened display names ("Marcus T.") and applies
   `audience.classroom_only()` plus `SCORE_FLOOR_PERCENT`.
7. **Rung 0 at rest.** The Identity Vault stays plaintext. Encryption was evaluated and rejected:
   losing the pseudonym map mid-year is unacceptable, the teacher runs at least four machines, and
   a key that must be distributed to four machines will be stored in plaintext beside the data it
   protects. Security comes from section 5 instead.
8. **Learning Objectives is kept as-is.** `api/learning_objectives.py` is independent of Panels
   and already implements source-bound, date-ranged, digest-verified, agent-authored objectives.
9. **Bell schedule authoring is in scope.** See section 7.

## 3. Data budget

Glass may read exactly these. Anything else requires new sync work and is out of scope.

| Source | Path | Carries |
| --- | --- | --- |
| Mirror roster | `_System/Canvas Mirror/<course_id>/roster.v1.json` | students, sections map, enrollments |
| Mirror assignments | `…/assignments.v1.json` | slim assignment index |
| Mirror submissions | `…/submissions/<assignment_id>.v1.json` | `missing`, `excused`, scores, attempts |
| Catalog | `api/course_catalog.py` v3 | assignments, modules with item positions, assignment groups, **pages with `body_text`** |
| School Calendar | `Library/Calendars/School Calendar.json` | days, day kinds, `schedule_id`, grading periods, events |
| Bell schedules | `Library/Calendars/Bell Schedule*.csv` | period meetings with start/end/segment |
| Teacher Schedule | `Library/Calendars/Teacher Schedule.json` | blocks: name, `raw_periods`, label, `course_id` |
| Learning Objectives | `workspace.learning_objectives_path()` | objectives with effective ranges and source digests |
| Roster student settings | `config.get_roster_student_settings()` | birthdays, teacher-entered celebrations |

Canvas Page bodies are already mirrored as normalized plain text (`PAGE_KEYS` at
`api/course_catalog.py:50`, acquired with `include[]=body`). A page contributes words; the layout
contributes everything else.

**Known absent:** assignment overrides / `all_dates`. Both `ASSIGNMENT_KEYS`
(`api/course_catalog.py:36`) and `store.normalize_assignment` (`api/mirror/store.py:565`) carry a
single scalar `due_at`. Harmless under decision 2.2 (one section per course); it becomes a defect
only if the teacher ever adopts multi-section courses.

## 4. Local schedule facts

Current workspace state, verified 2026-08-15. These are inputs, not code.

- School Calendar covers **2026-08-19 → 2027-05-27**, revision 1, school year `2026-27`.
- Day assignment: **127 days** Bobcat Hour (Mon–Thu), **44 days** Homeroom (Fri). Homeroom First
  and House Days are authored but assigned to zero dates; they are called ad hoc during the year.
- Teacher blocks: period **2** → Fundamentals of Computer Science; periods **4/5** → Pre-AP
  Language Arts 7; periods **6/7** → Language Arts 7. Periods 1 and 3 are unassigned.
- All four bell schedules carry a `lunch` row where applicable, authored for **B lunch**. The
  teacher's lunch assignment may change; switching to A lunch is a two-line edit per file and is
  the motivating case for section 7.

Consequences that the resolver must handle correctly:

- **The lunch-bearing period moves.** 4th period on Homeroom and Homeroom First; 5th period on
  House Days; inside Bobcat Hour on Mon–Thu.
- **The 4/5 block contains lunch on every schedule.** There is no day on which it is a clean
  teaching stretch.
- **The 4/5 block is non-contiguous on Bobcat Hour days** — 11:19–12:09, then Bobcat Hour
  12:11–1:13, then 1:17–2:07. `day_schedule.resolve_day` already emits one entry per consecutive
  run (`api/webui/day_schedule.py:243-267`); Glass must use run boundaries, never block
  boundaries, for "time remaining."

## 5. Privacy posture

Rung 0 makes the shape of the data on disk the entire security model. Three requirements follow.

**5.1 Invert the polarity — the mirror becomes pseudonymous at rest.** Today the mirror stores
real names (`store.normalize_student`, `api/mirror/store.py:495-507`) and correctness depends on
every MCP tool remembering to call `pseudonym.gate()`. That gate is opt-in per tool with no
chokepoint in `api/mcp_server/server.py`; a new tool that forgets it leaks.

Move every real identifier into the Identity Vault. Key every mirror file by pseudonym. After
this change an agent reading the entire mirror tree sees pseudonyms **because that is what is
stored**, not because a filter ran. `pseudonym.gate()` demotes to a belt-and-braces check.

Free text is the exception and cannot be pseudonymized structurally. Submission `body`
(`api/mirror/store.py:592, 647`) and `submission_comments[].comment` (`:611`) are stored raw with
no scrub at write time. Choose one: scrub at write via `feedback_scrub.scrub_text`; or hold raw
prose in the vault-protected store. The mirror is disposable and Canvas is truth
(`api/mirror/store.py:14`), so lossy scrubbing is cheaper than it appears. PowerGrader's
requirement decides this.

**5.2 Make pseudonym assignment deterministic.** `Vault.get_or_assign`
(`api/feedback_vault.py:295-321`) selects the first unused registry word, which depends on local
vault state. With four machines on OneDrive, the dangerous path is not a conflict copy — those are
detected and `get_roster` fails closed (`api/tests/test_vault_conflict.py:157`) — but a **stale
sequential write**: machine B assigns from a not-yet-propagated vault and wins last-writer-wins,
silently. Every pseudonym machine A already emitted then points at the wrong student.

Derive the pseudonym from a stable student key with deterministic probing on collision. The banned
set must be derived from the vault, not from locally-known roster tokens, or a machine synced to
fewer courses computes a different set. Manual `set_pseudonym` overrides
(`api/feedback_vault.py:355`) are recorded data and survive unchanged.

This also makes the vault reconstructible: re-derivation from Canvas produces the identical map.
That is the property Rung 1 was going to buy, obtained without a key to lose.

**5.3 Close the gate gap.** Wrap the response path in `api/mcp_server/server.py` so gating is
structural rather than remembered.

**Accepted residual risk, recorded deliberately:** a code-executing agent running as the same OS
user can read the vault, and can read the Canvas token from the OS keyring
(`api/platform_services/config/canvas.py:32`) and refetch the roster from Canvas directly. The
vault also syncs to district OneDrive in cleartext. The control is agent scoping — MCP-only for
chat agents, repo-scoped for coding agents — not cryptography.

## 6. The resolver

### 6.1 Interface

One call, consumed by one page.

```
get_current_context(at=None) -> {
  resolved_at,                 # when this was computed
  at,                          # the EFFECTIVE now — real or overridden
  simulated,                   # bool: was `at` supplied?

  date, day_kind, schedule_id, day_label,

  mode,                        # "class" | "board"
  state,                       # see 6.2

  block: { name, label, course_id, period_ids, starts_at, ends_at } | null,
  next:  { name, label, course_id, starts_at } | null,

  valid_until,                 # when this answer expires
}
```

Notes binding on implementation:

- **`section_id` is deliberately absent.** Reintroduce it as a field on `block`, never on the
  envelope, only if the teacher adopts multi-section courses.
- **`period_ids` is a list, not a scalar.** The 4/5 and 6/7 blocks each span two bell periods; a
  singular `period` field would have to lie about one of them.
- **`valid_until` is the timer contract.** One field: this answer is good until T. It replaces the
  `next_change` / `next_change_minutes` pair Panels used.
- **`next` is populated in both `in_class` and `up_next`**, so class mode can render "then: ELA
  6/7" without a second call.
- The resolver requires **both** the teacher's resolved runs and the raw meeting list for the day.
  `day_schedule.resolve_day` returns only claimed blocks; the unclaimed meetings (lunch, homeroom,
  Bobcat Hour) are what distinguish `lunch` from `free`.

### 6.2 State machine

Evaluated in order against the effective clock.

```
1. day = school_calendar.resolve_date(at.date, known_schedule_ids)
   day.state != "ready"                      -> BOARD / no_school | repair state
2. runs  = resolve_day(day.schedule_id, …)   # teacher's claimed runs
   meetings = bell_schedules[day.schedule_id]  # every meeting
3. at inside a run with a course_id          -> CLASS / in_class
4. at inside a run without a course_id       -> BOARD / free
5. at inside an unclaimed meeting whose
   period_id is "lunch"                      -> BOARD / lunch
6. at inside any other unclaimed meeting     -> BOARD / free
7. at before the first meeting of the day    -> BOARD / before_school
8. at at or after the last meeting's end     -> BOARD / after_school
9. at in a gap immediately preceding a run
   that has a course_id                      -> CLASS / up_next
10. otherwise                                -> BOARD / free
```

| state | mode | course shown |
| --- | --- | --- |
| `in_class` | class | current run |
| `up_next` | class | **upcoming** run — the room walks in to its own information |
| `lunch` | board | none; renders "class resumes at HH:MM" |
| `free` | board | none — periods 1 and 3, homeroom, Bobcat Hour, unclaimed blocks |
| `before_school` | board | none |
| `after_school` | board | none |
| `no_school` | board | none |

A Teacher Schedule block with no `course_id` (planning, duty, advisory) resolves to `free`. There
is no separate `conference` state; it does not change what appears on the wall.

Calendar repair states (`unconfigured`, `invalid_calendar`, `outside_coverage`,
`unknown_schedule`) keep the distinction Panels drew: a repair state names the repair, a genuine
non-school day does not nag for setup. Reuse `school_calendar.state_message()`.

### 6.3 The clock rule

**Glass never reads the browser clock.** Not for the header time, not for the countdown, not for
due-date labels. The server sends `at`; the page ticks forward locally from it between resolves.

This is what makes `?at=2026-09-02T10:15` a simulator rather than a debug flag. Every region —
header, countdown, due labels, today's objective, birthdays — moves together. Panels violated this
(`panel.js:msUntilMinutes` and `whats_due`'s `whenLabel` both read `new Date()`), which is why its
`now=` seams were never usable end to end.

`simulated: true` must be visible on the page. A display left running with `?at=` pinned would
otherwise show a fixed false time indefinitely.

Every payload function must accept and honor `at`. Panels already had `now=` on every date-reading
projection and no route ever passed it; do not repeat that.

### 6.4 Refresh

- Re-resolve at `valid_until` plus a short delay. This is a correctness timer.
- Poll data every 15 minutes. This is a freshness backstop, not a correctness mechanism.
- **One page, one lifecycle.** Panels ran nine independent copies of `load()` + `setInterval`, and
  `panel.js:onResize` installed a 400 ms interval per `List` that was never cleared
  (`api/webui/static/panels/panel.js:77, 112`). At Panels' 15-minute cadence that leaked ~32
  intervals per day; at Glass's re-resolve cadence it would be far worse. Glass owns exactly one
  timer set and tears down on re-render.

## 7. Bell schedule write surface (in scope)

MCP can today read bell schedules (`get_bell_schedule`) and change which schedule a date uses
(`preview_school_calendar_change` / `apply_school_calendar_change`,
`api/mcp_server/server.py:409-430`). It **cannot author or edit a bell schedule** — no write path
exists anywhere in `api/mcp_server/` or `api/webui/routes/`.

This is an unimplemented part of the existing contract, which names "edit Bell Schedule, Teacher
Schedule, grading-period, and public-event definitions" as one of three operation families
(`docs/contracts/canonical-school-calendar-contract.md:186`). Teacher Schedule, events, calendar
days, and game scores all have write pairs; bell schedules are the sole exception.

Add `preview_bell_schedule` / `apply_bell_schedule` following the established preview/apply
boundary: normalized mutation, base revision or file digest, deterministic `preview_digest`,
before/after projection, apply re-derives from the mutation and refuses an altered projection.
Validation reuses `day_schedule.parse_bell_schedule` problems plus a check that no existing
`School Calendar` day references a `schedule_id` the edit would orphan.

Motivating cases: a pep rally or late-start schedule announced mid-year; switching the teacher's
own lunch between A and B. Both are currently hand-editing a CSV in a synced folder.

## 8. Execution slices

Slices 1, 2, and 3 are closed GREEN. Slice 4 is next.

**Slice 1 — resolver and clock.** `get_current_context()` per section 6, with `?at=` honored end
to end and a test that simulates a full Bobcat Hour day, a full Homeroom day, and a full House Day
minute by minute across every state transition. No UI. Panels stays running and untouched.

**Slice 2 — board mode.** The school-facing frame: date and schedule header, today's events,
forward-window events and academic dates, sports results, Bobcat Hour clubs and tutorials, grading
period countdown. All from `School Calendar.json`. Zero student data, therefore zero privacy
surface — this is the correct first UI.

**Slice 3 — class mode.** The class frame uses this first-pass inventory and order, selected for
working classroom usefulness rather than a final visual hierarchy:

1. Period header: class name, current/up-next phase, time remaining or time until start, and next
   class.
2. Learning objective: the reviewed Learning Objectives document remains the default source.
3. What's due: published assignments due today through the next seven days.
4. Missing work: shortened classroom names and missing assignment titles, capped at twelve rows.
5. Celebrations: birthdays and teacher-entered celebrations in the next seven days, capped at
   twelve rows.
6. Random Name: a button that chooses a shortened classroom name from the current course roster
   at any time while class mode is displayed. The selection happens in the browser and can repeat.

The period header and Random Name control are always usable when their schedule/roster inputs are
available. Each other region degrades independently with a plain status message; stale mirror
regions show an `As of` timestamp and do not pretend to be current. The first pass uses the
existing full-screen layout and can be rearranged later without changing these data boundaries.

**Slice 4 — privacy inversion.** Section 5.1 through 5.3. This is a pre-launch clean cutover:
no migration code, dual-read shim, or legacy mirror compatibility is authorized.

**Slice 5 — bell schedule write pair.** Section 7.

**Slice 6 — retire Panels.** Section 9.

## 9. Panels retirement

Deleted: `api/webui/routes/panels.py`, `api/webui/panel_data.py`, nine `panel_*.html` templates,
`panels.html`, `api/webui/static/panels/`, `api/webui/static/pages/panels*.{css,js}`,
`docs/reference/panels-route-card.md`, and the Panels tests.

Retained, because they are independent of Panels and Glass consumes them: `api/panel_themes.py`
and its MCP tools (rename deferred), `api/learning_objectives.py` and its four MCP tools,
`api/webui/day_schedule.py`, `api/webui/school_calendar.py`, `api/webui/clock_time.py`,
`api/audience.py`.

Add every deleted path to `api/tests/test_retired_paths.py` with its reason, matching the
SmartDeck rows. Update the frozen MCP tool schema if the tool set changes. Update `README.md`,
`docs/README.md`, and `AGENTS.md`.

## 10. Defects to fix in flight

Found during the 2026-08-15 audit. Each is a real defect in current Panels behavior and must not
be reproduced in Glass.

| Defect | Location | Requirement |
| --- | --- | --- |
| Stale mirror renders as current | `panel_data.py:534` passes no `max_age_hours`, so `_state_with_age` no-ops and any non-empty `last_success_at` reads `current` | Glass passes `config.mirror_serve_max_age_hours()` and shows a permanent "as of HH:MM", not a boolean |
| `state` is three different channels | Panels merges resolver errors, data states, and calendar states into one field every template branches on | Glass separates `mode`, `state`, and per-region status |
| Naive hour arithmetic on `now` | `panels.py:265` computes `now.hour * 60 + now.minute` with no `.astimezone()` | Normalize `at` once at the boundary; never recompute local minutes downstream |
| Whole page dies with one region | — | Regions degrade independently; Glass never blanks |
| Bare `except` turns a broken calendar into a normal day | `panels.py:161-170` returns `"ready"` on any failure | Repair states surface as repair states |

## 11. Open decisions — not authorized

Selected by a senior, with independent acceptance criteria, only when a slice is ready.

- **Objective source.** The Learning Objectives document is the decided default and the reviewed
  digest workflow is retained. Whether a Canvas page may *also* drive a Glass region directly, as
  a second lower-ceremony path, is undecided.
- **Free-text disposition** (section 5.1) pending PowerGrader's verbatim-prose requirement.
- **`up_next` lead-in bound.** Currently "the whole gap before a claimed run." Whether to cap it
  (so a long unclaimed stretch does not read as passing period) is untested.
- **Theme surface.** `panel_themes.py` is strictly palette, typeface, and one ornament layer, and
  no theme can change layout or row count. Whether Glass keeps that contract, and whether a
  distinct `up_next` treatment needs its own derived variables, is deferred to Slice 3.
- **Bobcat Hour vocabulary.** `bobcat_hour` as a `period_id` is district-specific. Whether Glass
  keys off that literal or off a general "unclaimed meeting with calendar events in its window" is
  a Slice 2 decision.

## 12. Verification gates

- Slice 1 closes only with the three simulated full days passing, including: the non-contiguous
  4/5 block on Bobcat Hour days; the lunch transition on all three lunch-bearing schedules; the
  `up_next` handoff across every gap; and `before_school` / `after_school` boundaries.
- No Glass code path may import a Canvas client. Assert this in tests, as Panels did.
- Rendered verification per `api/webui/README.md` before any slice with UI closes.
- `api/tests/dataforge/test_data_never_committed.py` must continue to pass; no workspace data
  enters the repository.

## 13. Slice 1 execution result

**Traffic light:** GREEN

**Commit:** `2d55ee5` (implementation); closure report in the follow-up commit.

**Changed files:** `api/webui/glass.py`, `api/tests/webui/test_glass.py`, and this execution report.

**Verification:** `py -m pytest api/tests/webui/test_glass.py api/tests/webui/test_day_schedule.py api/tests/webui/test_school_calendar.py -p no:randomly` — 99 passed. `py -m pytest api/tests/webui -p no:randomly` — 389 passed. `py -m compileall -q api/webui/glass.py api/tests/webui/test_glass.py` — passed. `git diff --check` — passed.

**Deviations:** No UI, route, Canvas client, Panel, or schedule-seed changes. The supplied Bell Schedules PDF was inspected because the seed CSVs do not currently contain explicit `lunch` rows; Glass handles explicit lunch intervals, including intervals overlapping a claimed run, without guessing or rewriting those sources.

**Unresolved decisions:** Slice 2 board regions, the lunch authoring surface, and the remaining open decisions in section 11 remain deferred.

## 14. Slice 2 execution result

**Traffic light:** GREEN

**Commit:** `7c983b4` (implementation); closure report in the follow-up commit.

**Changed files:** `api/webui/glass_board.py`, `api/webui/routes/glass.py`, `api/webui/templates/glass.html`, `api/webui/static/pages/glass.js`, `api/webui/static/pages/glass.css`, `api/webui/glass.py`, `api/webui/server.py`, `api/webui/README.md`, `api/tests/webui/test_glass_board.py`, `api/tests/webui/routes/test_glass.py`, `api/tests/test_route_contract.py`, and this execution report.

**Verification:** `py -m pytest api/tests/webui/test_glass.py api/tests/webui/test_glass_board.py api/tests/webui/routes/test_glass.py api/tests/test_route_contract.py -p no:randomly` — 19 passed. `py -m pytest api/tests/webui api/tests/test_route_contract.py -p no:randomly` — 404 passed. Rendered `/glass?at=2026-09-02T12:15:00-05:00` at 1280×720: 200 response, no horizontal or vertical overflow, required global present, and zero browser console errors.

**Deviations:** Glass is available at direct `/glass` and `/glass/data` routes with no primary-nav link, preserving the full-screen display contract. Panels remains running and untouched; class-mode content remains deferred to Slice 3.

**Unresolved decisions:** Slice 3 class-mode region inventory and the remaining open decisions in section 11 remain deferred.

## 15. Slice 3 execution result

**Traffic light:** GREEN

**Commit:** `ae46825` (implementation); this closure report is in the follow-up commit.

**Changed files:** `api/webui/glass_class.py`, `api/webui/glass_board.py`,
`api/webui/routes/glass.py`, `api/webui/templates/glass.html`,
`api/webui/static/pages/glass.js`, `api/webui/static/pages/glass.css`, `api/webui/README.md`,
`api/tests/webui/test_glass_class.py`, `api/tests/webui/routes/test_glass.py`, and this execution
report.

**Verification:** `py -m pytest api/tests/webui/test_glass.py api/tests/webui/test_glass_class.py api/tests/webui/test_glass_board.py api/tests/webui/routes/test_glass.py api/tests/test_route_contract.py -p no:randomly` — 21 passed. `py -m pytest api/tests/webui api/tests/test_route_contract.py -p no:randomly` — 406 passed. Compileall and `git diff --check` passed. Rendered class mode at 1280×720 with a 200 response, class frame visible, board frame hidden, working Random Name click, no horizontal or vertical overflow, and zero browser console errors.

**Deviations:** The first pass chooses the existing full-screen grid, a seven-day due/celebration window, twelve-row caps for missing work and celebrations, and repeat-allowed browser-side random selection. Existing local-only classroom privacy projections are reused; no Canvas client, live call, new persistence, or student identifier is emitted to the browser.

**Unresolved decisions:** Theme treatment, objective source alternatives, free-text disposition, and the remaining section 11 decisions stay deferred. Slice 4 privacy inversion is the next authorized batch.
