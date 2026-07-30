# Brief: one day context, many sources, audience-tagged

**Scoped 2026-07-30. Not started.** One vertical slice, large. Route card for the consuming
surface is `docs/reference/glass-module-map.md`; read it before starting. Also read
`docs/reference/project-state.md` §*What this means for scope* and `AGENTS.md`
§*Non-negotiable guardrails* and §*Risk and verification*.

Everything a classroom screen might show is date- or time-keyed, and today each kind lives in
its own mechanism — or in none:

| Thing | Today |
|---|---|
| Bell schedule, day types | `Library/Glass/bell-schedule.json` → `api/schedule/` |
| No-school, grading periods, report cards | district CSV → `settings.json.calendars` |
| Games, dances, performances, picture day, spirit week | **nowhere** |
| Library hours, tutorial hours, club schedules | **nowhere** |
| Birthdays | **nowhere** — no birth-date field exists anywhere in the repo |
| Positive achievements, missing work | `api/mirror/` — never surfaced to a screen |

So the only way to put "Picture day" on the projector is to author a whole per-date scene with
the words hand-typed into a pane's static `data`. Every new *kind* of announcement wants a new
*mechanism*.

This slice replaces that with **one merged query, five sources, one audience filter, one
injection seam**, so the sixth source is a function plus a vocabulary entry rather than a new
mechanism, and new content is data entry rather than code.

---

## 1. The boundary this slice establishes

The boundary is **not** "student data vs. not." It is **classroom-facing vs. teacher-facing**,
and the teacher owns it.

**Classroom-facing.** Names, birthdays, missing assignments, numerical scores at or above 90%
(4+/5 and equivalent), positive achievements, STAAR Masters, bell schedule, school schedule,
events, games, performances, library hours, tutorial schedules, club schedules, teacher names.

**Teacher-facing only.** Scores below 90% (<4/5), behavioral punishment, Special Ed and 504
designations, social security number, address, phone numbers, parent email, student ID number,
economic designations, STAAR below Masters.

Schools routinely put birthdays and full names on signage and announce outstanding
achievements publicly. The app's job is to **offer caution, ask, and defer to the teacher** —
never to self-lock. Nothing is restricted unless it is on the teacher-facing list or the
teacher says so; **assume opt-in** otherwise.

Two statements in the repo are therefore **wrong and get rewritten**, not preserved:

- `api/default_docs/Glass/Glass Pane contract.txt:18` — "no … student/private data".
- `api/mcp_server/tools.py:571` — "Public schedule/calendar context only; no Canvas or
  student reads."

Of the classroom-facing items, per-student **missing assignments by name** on a wall is the
one most likely to be re-scoped later. It defaults to on per "assume opt-in." That is a
teacher toggle, not a code block, and this brief does not add one.

## 2. Locked decisions

1. **The assistant receives availability, never values.** `get_glass_context` reports
   `{"birthdays": true, "achievements": true, …}` and names the contract; the local host
   resolves real values at render time and injects them. The assistant authors panes
   generically — "if birthdays are available, render them like this." Precedent for a
   mirror+local join is `get_seating_context` (`docs/mirror.md` → *MCP reads and the refresh
   tool*).
2. **The sandbox is the enforcement boundary, and it already holds.** Panes are
   `sandbox="allow-scripts"`, opaque origin, `no-referrer`, inline CSP with
   `default-src 'none'; connect-src 'none'; form-action 'none'`, assets inlined
   (`api/webui/routes/glass.py:41`). A pane receiving a first name cannot exfiltrate it. This
   is precisely why injecting student data **locally** is safe while sending it to the
   assistant is not. Do not weaken any of it.
3. **The audience split is enforced in code, not prose.** Per `project-state.md`, "a model
   instruction is not an enforcement boundary." Every emitted item carries an `audience`;
   Glass renders `classroom` only.
4. **One events file, three shapes, closed kind vocabulary.** No RRULE, no iCal, no
   recurrence engine.
5. **Birthdays are MM-DD, teacher-entered, no birth year**, stored per student through the
   existing `roster_student_settings` path.
6. **`_parse_calendar_csv`, `no_count_dates`, and the district CSV import path are not
   touched.** Nine call sites read `no_count_dates` for late-work math
   (`work_registry/providers/late_work.py`, `operation_ledger/adapters/sweep.py`,
   `webui/gradebook_service.py`, `webui/routes/gradebook_extensions.py`,
   `webui/routes/powergrader_late.py`, `webui/routes/routines_builtin.py` twice,
   `webui/routes/pages.py`, `api/schedule/calendar.py`). A dance does not cancel class.
7. **`api/schedule/` stays pure.** It remains the time-of-day engine with no `keyring` reach.
   The merger is a new consumer of it, not a change to it. Time-of-day *structure* and
   date-keyed *content* are different things joined on a date; do not merge the models.
8. **No new storage format for source 5.** Achievements come from the mirror on disk.
9. **No web UI calendar grid, and no default-pane approval bypass.**

## 3. The merged query

New module **`api/glass/day_context.py`**: `day_context(date, lookahead_days=14)` merges five
sources and tags every item with an audience. Glass is the only consumer today
(`webui/routes/glass.py`, `mcp_server/tools.py`), so it lives under `api/glass/`; it may
import `api.webui.config` and `api.mirror`, unlike `api/schedule/`.

| # | Source | Existing entry point | Emits |
|---|---|---|---|
| 1 | Bell schedule | `loader.discover_bell_schedule()`, `resolver.resolve()` | day type, blocks, current block |
| 2 | District calendar | `config.get_combined_calendar_for_range()` | `no_school`, `grading_period_end`, `report_card` |
| 3 | School events | **new** `api/webui/school_events.py` | `game`, `dance`, `assembly`, `performance`, `spirit`, `tutorial`, `club`, `library`, `other` |
| 4 | Birthdays | `config.roster.get_roster_student_settings()` + identity vault, scoped by `loader.load_section_map()` | `birthday` |
| 5 | Achievements / missing work | `api/mirror/queries.py` | `achievement`, `missing_work` |

### 3.1 Source 4 uses the seam the code already left open

`loader.load_section_map()` (`api/schedule/loader.py:460`) parses
`Library/Glass/section-map.json` into `SectionMap{block_id → SectionRef{course_id,
section_name}}`. It is implemented, validated, tested
(`api/tests/schedule/test_schedule_loader.py:430`), ships a template, and is **read by no
production code**. Its docstring states it exists "so a later batch can answer '4th period is
Canvas section X' without the schedule and the roster becoming coupled today."

**This batch is that consumer.** `current_block → section_map → course_id → roster settings`
is how the wall shows *this* class's birthdays rather than the whole school's. Invent no new
mapping. The merger owns the join, so `api/schedule/` and the roster stay uncoupled (§2.7).

Storage: add `"birthday"` to `ALLOWED_STUDENT_PATCH_KEYS` (`api/webui/routes/roster.py:42`)
and validate `MM-DD` in `api/roster_context.py` beside `normalize_seating_context`. It then
persists through `config.roster.update_roster_student_settings` with **no new storage path**.
Display name comes from the identity vault; default to first name plus last initial — the
cautious default the policy permits the teacher to widen.

### 3.2 Source 5 is mirror-only with the floor enforced in code

`api/mirror/queries.py` already serves `course_assignments` / `course_submissions` from disk,
offline, with `data_freshness()`. Reuse it and add no Canvas call. A stale or missing mirror
means "no achievements" — not an error, and never a live fetch (mirror design law 6). The
**≥90% floor is a constant in the policy module**, applied before an item can be tagged
`classroom`, so 88% can never be emitted as classroom-facing regardless of what a pane asks
for.

### 3.3 The policy module

New **`api/audience.py`**: pure, with no route, config, Canvas, or vault imports — exactly the
posture its sibling `api/roster_context.py` documents. Holds `CLASSROOM_FACING` and
`TEACHER_FACING` vocabularies, `SCORE_FLOOR_PERCENT = 90`, and `classroom_safe(item) -> bool`.
Unit-testable with no app state, and the one place the two lists are encoded.

Backed by a durable contract, **`docs/contracts/classroom-facing-data-contract.md`**: the two
lists, the 90% floor, the availability-not-values rule, "assume opt-in unless the teacher says
otherwise," "offer caution, ask, defer, never self-lock," and the absolute bar on SpEd/504 —
the item with real legal exposure.

## 4. The events file

`api/default_docs/Calendars/school-events.json`, seeded into `Library/Calendars/` by the
existing `_seed_folder_if_missing` call in `workspace.ensure_workspace()`
(`api/webui/workspace.py:738`). No seeding change is needed.
`deps.list_calendar_files()` globs `*.csv` only, so this file cannot leak into the calendar
picker — confirm that in preflight rather than assuming it.

```json
{
  "_comment": "One line per school event. Games, dances, tutorials, club and library hours.",
  "format": "canvasexpert.school_events/1",
  "events": [],
  "_example_events": [
    {"kind": "game",     "label": "Volleyball vs. Northside", "date": "2026-09-17",
     "detail": "Home, 5:30pm"},
    {"kind": "spirit",   "label": "Spirit Week", "start": "2026-10-06", "end": "2026-10-10"},
    {"kind": "tutorial", "label": "Math Tutorials", "weekdays": [1, 3],
     "from": "07:45", "to": "08:20",
     "effective": {"start": "2026-08-17", "end": "2026-12-18"}}
  ]
}
```

**Three shapes, exactly one per event.** `date` for a single day; `start`+`end` for an
inclusive span rendered as one line; `weekdays` (`0`=Monday…`6`, matching
`datetime.date.weekday()` and the bell schedule's `weekday_default`) with optional `from`/`to`
times and an optional `effective` range, so a semester's tutorial schedule stops at the
semester's end.

**Why the shipped file cannot reach a real projector.** The retired calendar-events brief
(`git show 08ce225:docs/handoffs/CanvasExpert-Calendar-Events-BRIEF.md`, §3) flagged that a
*populated fictional sample* in a *globbed* folder would put invented events on a real screen.
Here there is one fixed filename and the shipped copy has an empty `events` array — no glob
and no `sample` marker needed. The populated example lives under `_example_events`, reusing
the underscore-key convention `loader._is_comment_key` / `_is_comment_entry` already honors
for `_example_day_types`, which makes the example *structurally* unreadable rather than merely
fictional. Do not "simplify" this into globbing the folder.

Reader: **`api/webui/school_events.py`**, pure stdlib, sibling to `calendar_csv.py` — which
stays boring because late work depends on it. Unknown kinds and malformed rows are dropped,
not raised; a broken file means "no events," never a blank wall, matching the posture
`api/schedule/calendar.py` documents.

## 5. `glass:context/2`

Panes cannot fetch (`connect-src 'none'`), so the host must inject. Bump the one-way contract
rather than adding optional fields: pre-launch, one user, and `AGENTS.md` prefers clean breaks
over compatibility shims.

Fields: `instance_id`, `scene_date`, `data`, `local_time`, `current_block`, **`events`**,
**`birthdays`**, **`achievements`** — all already filtered to `classroom` by the host.

The literal `glass:context/1` appears in exactly seven places. That is the whole blast radius:

| Location | What it is |
|---|---|
| `api/webui/routes/glass.py:40` | the context object in `_pane_document` |
| `api/webui/routes/glass.py:42` | the bootstrap's **own** `message` listener |
| `api/webui/static/glass/display.js:14` | `context()`, re-posted every paint |
| `api/default_docs/Glass/Glass Pane contract.txt:15` | the enumerated field list |
| `api/tests/glass/test_glass_browser.py:157`, `:190` | exact-dict assertions |
| `api/tests/glass/test_glass_panes.py:160` | asserts the contract text contains the literal |

The bootstrap listener is the easy one to miss: change only the outer object and panes
silently stop receiving updates while everything still renders once.

**Fix while here.** `_scene_view` (`api/webui/routes/glass.py:47`) reads the calendar *inside*
`if schedule:`, so a teacher with a calendar but no bell schedule gets no calendar read at
all. Move the read out of that branch, widen it from a single day to the look-ahead window,
and add the new fields to the returned dict — `display.js` builds its context from that
payload. Look-ahead is one named constant, default **14 days**, matching
`get_glass_context(lookahead_days=14)`.

Unchanged: the display rail stays host-owned and pane source cannot supply rail text or error
detail.

## 6. The pane

`api/glass/panes.py` has no shipped-default-pane concept. Panes are drafts in
`To Review/Glass` that become immutable content-addressed revisions under
`Library/Glass/panes/<pane_id>/<digest>` only via `approve_pane`. That approval step is the
invariant the surface rests on; **add no bypass** (§2.9).

Ship the pane *source* as an authoring reference under `api/default_docs/Glass/`, which
already seeds into `Library/Glass/`, so the teacher or assistant drafts it via
`save_glass_pane_draft` and approves it through the normal path. It reads `context.events`,
`context.birthdays`, and `context.achievements` and needs no `data` — which is the point: one
generic pane, no per-date retyping.

## 7. Scope order

1. `api/audience.py` + `docs/contracts/classroom-facing-data-contract.md` — policy first;
   everything else references it.
2. `api/webui/school_events.py` + the shipped blank template.
3. Birthday field: `roster_context.py` validation, `ALLOWED_STUDENT_PATCH_KEYS`, roster inline
   edit.
4. `api/glass/day_context.py` — sources 1–3, then 4 (section-map join), then 5 (mirror).
5. `glass:context/2` — `_pane_document`, the bootstrap listener, `_scene_view`, `display.js`,
   contract and docs.
6. `get_glass_context` availability signals; `api/mcp_server/tool_schema_v11.json`.
7. Pane source under `api/default_docs/Glass/`.
8. `docs/reference/glass-module-map.md`, `docs/mcp-server.md`, `AGENTS.md` routing row.

## 8. Non-goals

Explicitly out; do not add opportunistically.

- Any change to `_parse_calendar_csv`, `no_count_dates`, or the `settings.json` calendar
  schema; any migration or teacher re-import.
- A web UI calendar grid or event authoring form. The events file is hand-edited and
  assistant-draftable.
- Any recurrence beyond the three shapes in §4. No RRULE, no monthly rules, no exceptions
  list.
- Annual recurrence as a general feature. Birthdays are MM-DD by construction; do not
  generalize.
- STAAR Masters and AP results as sources. The vocabulary should accommodate them; this slice
  does not import them.
- Canvas assignment due dates as calendar events, live Canvas calls for source 5, or any
  Canvas write.
- A teacher toggle for any individual classroom-facing item (§1).
- Surfacing bell-schedule `date_overrides` (pep rally, homeroom first) as events. Adjacent,
  cheap, deliberately separate.
- Pseudonymization or redaction machinery anywhere in this slice. Classroom-facing data is
  shown deliberately; teacher-facing data is excluded, not masked.

## 9. Preflight

Verify before writing. Stop if an assumption is false.

1. `deps.list_calendar_files()` really does glob `*.csv` only, so `school-events.json` cannot
   appear in the calendar picker.
2. `loader.load_section_map()` has no production caller, so this batch adding one is not a
   behavior change to an existing consumer.
3. `roster_student_settings` is keyed `[course_id][user_id]` and `update_roster_student_settings`
   accepts an arbitrary new key once it is in `ALLOWED_STUDENT_PATCH_KEYS`.
4. `api/mirror/queries.py` serves `course_assignments` / `course_submissions` with no Canvas
   call when the mirror is fresh, and `data_freshness()` is the gate to check.
5. `_event_sort_key` (`api/webui/config/calendars.py:67`) tolerates the new event shapes, or
   the merger sorts separately rather than being forced through it.
6. Confirm the seven `glass:context/1` sites in §5 and that no eighth exists.

## 10. Acceptance criteria

1. `api/audience.py` refuses every teacher-facing item as classroom-facing — including a score
   of 89.9%, a 504 designation, and a student ID — unit-tested with no app state.
2. A score below the floor can never reach a pane, whatever a pane or scene asks for.
3. A blank shipped `school-events.json` yields zero events, and `_example_events` is never
   read.
4. All three shapes resolve: a single date; a span as one line; a weekly entry appearing only
   on its weekdays and only inside its `effective` range.
5. Unknown `kind`, missing `label`, two shapes on one event, or `end` before `start` is
   dropped without raising. A missing, empty, or malformed file yields zero events and no
   crash.
6. `no_count_dates` and `grading_periods` from `get_combined_calendar_for_range` are
   byte-identical to before, and no teacher event enters `no_count_dates` or late-work math.
7. Birthdays resolve only for the section `section-map.json` maps to the current block. With
   no section map: no birthdays, no error.
8. A stale or missing mirror yields no achievements, no error, and **no live Canvas call**.
9. `get_glass_context` returns availability booleans and **no** birthday, name, or score
   value. Assert this explicitly — it is the guardrail the whole design rests on.
10. `/glass/display` renders events, birthdays, and achievements against a frozen clock via
    `?at=`, in a fictional temporary workspace.
11. Events reach a pane when a calendar is loaded but no bell schedule exists (§5).
12. `git grep` finds no real district dates, holiday names, school names, teacher names, or
    student data, and no student data in any fixture.

## 11. Verification gate

**Risk: High** — FERPA boundary, a new classroom-facing surface, and a shared pane contract.

```powershell
py -m pytest api/tests/test_calendar_events.py api/tests/test_mcp_server_tools.py `
             api/tests/schedule api/tests/glass api/tests/test_route_contract.py `
             api/tests/test_beta075_mcp.py
py -m pytest api/tests/glass/test_glass_browser.py   # confirm it RAN; a skip is not a pass
```

Because this changes a shared pane contract and `display.js`, load `/glass`,
`/glass/display`, preview, and `/roster` in the local app and confirm zero new browser console
errors, per `AGENTS.md` → *Risk and verification*. Rendered checks at 1280x720, 1920x1080,
1280x800, and 1920x1200 with no overflow, per the Glass route card — long district event names
and long student names are the new overflow risk. Browser checks use a fictional temporary
workspace only.

Then `py -m pytest api/tests` as the integration checkpoint. Baseline at the calendar-events
commit was 1747 passed, 0 failed, 0 skipped; report counts as numbers.

## 12. Stop conditions

Stop and report rather than working around, when:

- `no_count_dates` output changes for any input, or any late-work test needs adjusting.
- Any teacher-facing item can reach a pane, or any value rather than availability reaches
  `get_glass_context`.
- Source 5 wants a live Canvas call instead of a mirror read.
- A pane needs network, storage, parent access, or a default-pane approval bypass.
- The design starts to need a `settings.json` calendar schema change, a migration, or a
  teacher re-import.
- The section-map join turns out to require coupling `api/schedule/` to the roster.
- Reading events requires globbing `Library/Calendars`.
- Long event or student names cannot be made to fit without redesigning a pane rather than its
  numbers. Report what does not fit.

## 13. Splitting, if it is too large for one brief

This is deliberately one slice because the audience filter and the injection seam are what
make the sources cheap, and building them for one source then retrofitting is worse. If it
must split, the clean seam is:

- **13a** — §3.3 policy, sources 1–3, `glass:context/2`, the pane. Public data, Low risk.
- **13b** — sources 4 and 5 on the same spine. Private data, High risk.

In that order, never the reverse: 13b without the policy module would put classroom-facing
judgements in pane source.

## 14. Open questions for the teacher

None are blocking; defaults are chosen and stated so work can proceed.

1. **Birthday display name.** Defaulting to first name plus last initial. Full name is
   permitted by §1 and is a one-line change if wanted.
2. **Missing work by name on the wall.** Defaulting to on per "assume opt-in" (§1). Say so if
   it should be counts-only or teacher-facing.
3. **Report cards on a classroom screen.** Assuming yes; students care when grades go home.
4. **Look-ahead window.** 14 days, matching the existing MCP default. A term-long view is a
   different product.

## 15. Execution result

_Not started._
