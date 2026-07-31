# Brief: let the assistant store the class schedule

Status: **READY FOR EXECUTION**. Authored 2026-07-31.

> Supersedes nothing. The preceding class-schedule brief landed GREEN and was retired in the
> same batch that authored this one; its examples feature was removed in that batch (see
> **Why the examples are gone** below). Git history is its record. Do not go looking for it.

## Objective

The Settings blocks editor covers one of the schedule's three parts. The other two are CSV
files a teacher types by hand, and one of them is priced per school day: a full year is roughly
175 rows. In the live workspace today `Day Calendar 2026-27.csv` has **8 rows**, which is what a
teacher does when the chore is that size. SmartDeck then cannot resolve any date past the eighth.

Give the teacher's assistant two write tools so a conversation can finish the setup the editor
starts, and expand a date range server-side instead of pushing 175 rows through the MCP
boundary.

**Teacher-visible outcome.** The teacher tells their assistant when the semester starts and
ends, which bell schedule the ordinary day uses, which weekdays differ, and which dates are
holidays. The assistant writes the day calendar and the blocks. Settings reflects it, and
SmartDeck goes ready, without the teacher typing a CSV.

## Why the examples are gone, and why that is not this brief's problem

Three shipped example schedule sets used to compensate for hand-authored JSON. They were cut in
the batch that authored this brief, for a reason that also constrains this one: **`Calendars` is
in `LIBRARY_SUBFOLDERS`, so every workspace is already seeded with real district bell schedules
and a day calendar.** The CSV shape is on disk before anyone asks. The examples demonstrated a
shape that was never missing, and loading one merged invented dates into real resolution.

The surviving `alternating-day-split` set now lives at `api/tests/fixtures/class_schedule/` as a
pure test fixture, exercised by `api/tests/test_schedule_fixture.py`. **Do not move it back
under `api/default_docs/`** and do not add a loader for it.

## Locked decisions

Confirmed with the user. Do not relitigate.

1. **Two new tools, not three.** `save_teacher_schedule` and `save_day_calendar`. There is
   deliberately **no `save_bell_schedule`**: a bell schedule is about eight rows, changes once a
   year, and is the highest-consequence data in the set. A wrong bell time is wrong on a
   classroom projector all day. The day calendar is the opposite trade (high volume, low risk
   per row), which is why it gets the tool.
2. **`save_teacher_schedule` reuses `schedule_setup.save_blocks()` verbatim.** That function
   already validates via `deck_schedule.validate_teacher_schedule`, preserves every unknown
   top-level key including `_comment`, writes `version` only when absent, keeps block order, and
   writes atomically through `tempfile.mkstemp` + `os.replace`. **Do not add a second write path
   to `Teacher Schedule.json`.** This is the single largest cost saver in the brief.
3. **`save_day_calendar` is generative, not row-by-row.** It takes a range plus rules and expands
   the rows itself. Emitting 175 rows through an MCP call is the thing this tool exists to avoid.
4. **Precedence, fixed:** `date_schedules` beats `weekday_schedules` beats `default_schedule_id`.
   `skip_dates` removes a date outright. Saturdays and Sundays are never emitted.
5. **An omitted date means no school.** This is the existing model's load-bearing convention and
   the reason a single-bell-schedule default was rejected. `skip_dates` is how a holiday is
   expressed; do not invent a `no_school` schedule_id.
6. **Every `schedule_id` is validated against the bell schedules actually on disk, and an unknown
   one refuses the whole write.** The response returns the available ids so the assistant can
   correct itself in one turn. An agent must not be able to create the
   `unknown_schedule_ids` state the Settings panel now reports.
7. **The tool owns one named file and refuses to clobber another.** `label` produces
   `Day Calendar <label>.csv`. If that file exists, refuse unless `replace=True`; on replace,
   **move the old file aside** with a timestamp, never unlink. This follows the codebase's
   moves-never-deletes rule (`deck_store.delete_deck`).
8. **Overlap with a *different* day-calendar CSV is a warning, not a refusal.** `load_day_calendar`
   merges every matching CSV in the folder and the last filename in sorted order wins, so a
   second file can shadow dates. Report the overlapping count and the winning filename in the
   response; the teacher decides.
9. **No safety gate, no vault, no course gate.** A schedule holds no student data and has no
   `course_id`. `api/mcp_server/tools.py` already documents this exemption class for
   `save_deck` / `list_active_decks` / `archive_deck`. These two tools join it. Do not bolt on a
   `feedback_scrub` or `pseudonym` call.
10. **No staging or review queue.** These write live, like `save_deck`. The teacher asked for it
    in conversation, the file is local and theirs, and Settings shows the result immediately.
11. **Do not add a `schedules` field to a block.** Considered and cut previously; its values
    would be filename slugs that break silently on a rename. Still true.
12. **UI stays small.** One new readiness signal, one line of copy. No day-calendar editor.

## Non-goals

Explicit. An executor that builds any of these has exceeded scope.

- No `save_bell_schedule`, and no edits to the seeded district calendars under
  `api/default_docs/Calendars/`. Those are sanctioned real public times per `AGENTS.md`
  guardrail 3.
- No day-calendar UI: no date picker, no CSV grid, no per-date override table, no range
  generator in the browser. The assistant is the generator now.
- No change to `deck_schedule.resolve_day` or to its output keys. `smartdeck_feeds`,
  `display.js`, and `slide_select.js` must see zero churn.
- No change to the three read tools (`get_teacher_schedule`, `get_bell_schedule`,
  `get_day_schedule`) or to their payload shapes.
- No re-adding an examples catalog, an example loader, or `api/default_docs/Examples/`.
- No migration. Pre-launch, single user, per `docs/reference/project-state.md`.
- Do not add a `pieces` field to `readiness()` that no surface renders. That was just cleaned
  up; the payload carries only what the panel draws.

## Routed references

Read only these, and only the sections named.

| Need | Read |
|---|---|
| Workflow, guardrails, test commands, risk table | `AGENTS.md` |
| Scope posture | `docs/reference/project-state.md` |
| Settings ownership, the name-vs-label rule, the readiness-payload rule | `docs/reference/settings-module-map.md` |
| SmartDeck ownership, storage layout, block schema | `docs/reference/smartdeck-module-map.md` |
| MCP tool surface, exemption classes, doc conventions | `docs/mcp-server.md` |
| Web UI route/page/JS load order | `api/webui/README.md` |
| Template families, CSS ownership, JS-hook rule | `docs/reference/webui-presentation-system.md` §§ Template API, CSS ownership |

## Hard constraints

- No em-dashes in any copy, comment, or docstring. Calm teacher-facing voice; no ALL-CAPS
  emphasis, no compliance banners, no taglines.
- No `style="` in any template.
- Files in `FEATURE_CSS` may not contain `font-family:`, hex colors, `rgb(`/`hsl(`,
  `border-radius:`, or `box-shadow:`. Tokens only.
- Shared `ce-*` component classes may never appear in a JS selector. Use an `id` or `data-*`.
- Tests derive paths from the repository. No developer-specific absolute paths, no private data,
  no real student names.
- Every MCP tool response stays token-lean. Return counts and paths, not the expanded rows.

## Preflight

Stop and report if any of these is false.

1. `api/webui/schedule_setup.py` `save_blocks()` validates through
   `deck_schedule.validate_teacher_schedule`, preserves unknown top-level keys, sets `version`
   only when absent, and writes via `tempfile.mkstemp` + `os.fsync` + `os.replace`.
2. `api/webui/deps.py` `load_day_calendar()` still iterates `sorted(glob(...))` and calls
   `day_calendar_mapping.update(mapping)`, so the last filename in sorted order wins a duplicate
   date.
3. `api/webui/deps.py` `list_bell_schedule_files()` still derives `schedule_id` through
   `api/webui/routes/calendar.py` `_file_key()`.
4. `api/mcp_server/contract.py` has `TOOL_SCHEMA_VERSION = 14`, `_SUPPORTED_SCHEMA_VERSIONS`
   ending at 14, and `tool_schema_v14.json` declares exactly 19 tools.
5. `api/mcp_server/tools.py` `_CONTRACT_FILES` has exactly five kinds, and `get_authoring_contract`
   skips `_staging_appendix` for `kind == "deck"` only.
6. `api/tests/test_beta075_mcp.py` asserts `contract.live_contract(server.mcp)` equals
   `contract.load_contract()`, so a new tool fails that test until the schema file exists.
7. `api/webui/schedule_setup.py` contains no example catalog functions, and
   `api/default_docs/Examples/` does not exist.
8. Baseline: `py -m pytest api/tests` is green. Record the count.

## Findings that correct common assumptions

- **A day calendar file is identified by its header, not its name.** `load_day_calendar` skips
  anything starting with `bell schedule` and otherwise accepts any CSV whose header line contains
  both `date` and `schedule_id`. So the new file is discovered automatically, and a badly chosen
  name can collide with the teacher's own file.
- **`schedule_id` is a filename slug, not an id the teacher picks.** It is
  `re.sub(r'[^a-z0-9]+', '_', stem.lower()).strip('_')` over the bell schedule filename. The
  assistant cannot invent one; it must read `get_bell_schedule` or the ids this tool returns on
  refusal. Say so in the authoring contract.
- **A block's `name` is a slide's binding key.** `routes/smartdeck.py` `_resolve_slides` builds
  `{b["name"]: b}`. `label` is display text only, and two blocks may share a label. An agent that
  writes `name` from a course title renames blocks and breaks existing slides. This exact defect
  shipped once in the Settings editor; do not reintroduce it through the tool.
- **`validate_teacher_schedule` rejects a duplicate `name` only when the two blocks'
  `effective_weekdays()` intersect.** Disjoint weekday sets are legal and load-bearing: it is how
  one course is first period on Monday and fifth on the Friday schedule with slides still finding
  it. The authoring contract must teach this, or an assistant will "fix" it into unique names.
- **`readiness()` returns `count`, not `date_count`/`block_count`.** Those duplicates were removed.

---

# Unit 1: `save_teacher_schedule`

**Depends on nothing. Parallel-safe with unit 2.**

`api/mcp_server/tools.py`, beside `save_deck` (line 1071):

```python
def save_teacher_schedule(blocks: list) -> dict:
    """Replace the teacher's blocks in Teacher Schedule.json."""
```

- Delegate straight to `schedule_setup.save_blocks(blocks)`. Reject a non-list before calling.
- Success: `{"ok": True, "count": n, "path": ...}`. Failure:
  `{"ok": False, "problems": [...]}` with the validator's own strings, unmodified. Never raise.
- Register in `api/mcp_server/server.py` beside `save_deck` (line 208), returning `_compact(...)`.

**Docstring must state** the no-course-id / no-student-data exemption, in the same shape as
`save_deck`'s, so `docs/mcp-server.md`'s exemption list stays honest.

**Tests** appended to `api/tests/test_mcp_server_tools.py`: writes blocks; preserves `_comment`
and block order on an existing file; refuses invalid blocks and leaves the file byte-identical;
refuses a non-list; rejects two same-named blocks whose weekdays intersect; accepts two
same-named blocks whose weekdays are disjoint.

---

# Unit 2: `save_day_calendar`

**Depends on nothing. Parallel-safe with unit 1.** This is the unit that removes the chore.

New helper in `api/webui/schedule_setup.py` (the module that owns schedule writes), not in the
MCP layer, so the Settings panel could call it later without a second implementation:

```python
def save_day_calendar(label, start_date, end_date, default_schedule_id,
                      weekday_schedules=None, date_schedules=None,
                      skip_dates=None, replace=False) -> tuple[dict | None, list]
```

Expansion rules, in order:

1. Walk every date from `start_date` to `end_date` inclusive.
2. Skip Saturday and Sunday always. Skip anything in `skip_dates`.
3. `date_schedules[date]` wins; else `weekday_schedules[weekday]` (0=Mon..4=Fri, the numbering
   `school-events.json` and the `weekdays` block field already use); else `default_schedule_id`.
4. Validate every resulting `schedule_id` against `deps.load_bell_schedules()`. Any unknown id
   refuses the whole write, writing nothing, and the problem list names the unknown ids and the
   available ones.
5. Refuse on an inverted or unparseable range, an empty result, or a `skip_dates`/`date_schedules`
   entry outside the range (a silently ignored holiday is worse than a refusal).

Write `Day Calendar <label>.csv` into the Calendars folder, header `date,schedule_id`, rows in
date order, atomically via the same `mkstemp`/`fsync`/`replace` pattern `save_blocks` uses. Reject
a `label` that is empty, contains a path separator, or normalizes to a `bell schedule` prefix.

Return `{"ok": True, "path", "count", "first", "last", "overlap": {"count", "files"}}` where
`overlap` counts dates already covered by a *different* day-calendar CSV and names it. Compute
the winner by sorted filename, matching `load_day_calendar`.

MCP wrapper `save_day_calendar` in `tools.py` + registration in `server.py`. The response must
not include the expanded rows.

**Tests** in a new `api/tests/test_schedule_day_calendar_write.py`: weekends excluded; precedence
across all three sources; `skip_dates` omits a date entirely; unknown `schedule_id` refuses and
writes nothing; out-of-range `skip_dates` refuses; existing file refuses without `replace`;
`replace` moves the old file aside and the aside copy still parses; overlap count and winning
filename correct against a second CSV; the written file round-trips through
`deck_schedule.parse_day_calendar` with zero problems; idempotency, meaning the same call twice
with `replace=True` produces identical bytes.

---

# Unit 3: schema version and the authoring contract

**Depends on units 1 and 2** (the live registry must already have both tools).

1. New `api/mcp_server/tool_schema_v15.json`: copy v14, add the two tools, set
   `schema_version: 15`. Tool count goes 19 to 21.
2. `contract.py`: `TOOL_SCHEMA_VERSION = 15`, append `15` to `_SUPPORTED_SCHEMA_VERSIONS`.
   Leave v1 through v14 untouched; they are the compatibility record.
3. New `api/default_docs/AI Authoring/Author a Class Schedule.txt`, and
   `_CONTRACT_FILES["schedule"] = "Author a Class Schedule.txt"`. Add `"schedule"` to the
   direct-write set alongside `"deck"` so `_staging_appendix` is skipped: these tools write live
   and there is no review queue to describe.

   The contract must teach, in teacher-facing prose: what the three parts are; that `name` is what
   a slide points to and must stay steady; that `label` is display text and may repeat; that
   `raw_periods` order picks the first period's start and the last period's end; the `weekdays`
   numbering and that absent means every day; that two blocks may share a name when their
   weekdays are disjoint, with the Monday/Friday example; that `schedule_id` comes from the bell
   schedule filename and must be read, never invented; and that a date left out of the day
   calendar is a no-school day.
4. `docs/mcp-server.md`: add both tools, and extend the exemption paragraph so the
   no-course-id / no-student-data class lists them.
5. `docs/reference/settings-module-map.md`: note that `schedule_setup` now owns two write paths
   and that the MCP tools call the same functions the panel does.

**Gate.** `py -m pytest api/tests/test_beta075_mcp.py api/tests/test_mcp_server_tools.py api/tests/test_beta075_connections.py api/tests/test_canvasagent_instructions.py`

---

# Unit 4: the two UI changes

**Depends on unit 2.** Small on purpose.

1. **Coverage, not row counts.** `readiness()` gains one field, `day_calendar.covers_today`
   (bool) and keeps `last`. `api/webui/static/settings/class_schedule.js` `renderReadiness` adds
   one `detail()` line when the calendar is present but today is not in it:

   > Your day calendar does not cover today. It runs through 2026-09-11, so SmartDeck has no
   > times after that. Ask your assistant to extend it, or add the dates in your Calendars folder.

   A date count told a teacher nothing; "today is not covered" is the fact that matters. Keep the
   line out of the ready path, and do not add a second notice.

2. **One line where the examples disclosure used to be**, at the end of
   `#class-schedule-card` in `api/webui/templates/settings.html`, after the Calendars button:

   > Your assistant can set the bell schedule and day calendar up for you. Connect it under
   > AI Connections, then tell it your semester dates and which days are different.

   Link the existing AI Connections surface. No new panel, no new rail link.

**Acceptance.** With a day calendar that ends before today, `/settings` shows the coverage line
and names the last date. With one that covers today, it does not. `/settings` renders with zero
new browser console errors at 1280px and 375px.

**Gate.** `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_schedule_routes.py`

---

# Acceptance criteria (whole brief)

Independently checkable, authored before execution.

1. `save_teacher_schedule` writes blocks and, on an existing file, leaves `_comment`, `version`,
   unknown top-level keys, and block order untouched. Verified by diffing the file, not by
   trusting the response.
2. `save_teacher_schedule` with an invalid block writes nothing and returns the validator's
   problem strings.
3. `save_day_calendar` for a full semester produces one CSV with one row per weekday in range,
   holidays absent, and `deck_schedule.parse_day_calendar` reports zero problems on it.
4. `save_day_calendar` with an unknown `schedule_id` writes nothing and names both the unknown id
   and the available ids.
5. `save_day_calendar` refuses an existing target without `replace`, and with `replace` the prior
   file survives under a timestamped name.
6. Calling `save_day_calendar` twice with identical arguments and `replace=True` yields identical
   bytes.
7. `contract.live_contract(server.mcp) == contract.load_contract()` with 21 tools at
   `schema_version: 15`, and v14 is byte-identical to before.
8. `get_authoring_contract("schedule")` returns the new document with no staging appendix.
9. After a real `save_day_calendar` plus `save_teacher_schedule`, `/settings` reports ready and
   MCP `get_day_schedule` resolves a date in range with an empty `problems` list.
10. `/settings` shows the coverage line only when today is uncovered.
11. No existing test was modified except `_SUPPORTED_SCHEMA_VERSIONS`-driven counts. Every other
    change to a test file is an addition.
12. `resolve_day` and its output keys are unchanged; `git diff` touches neither
    `api/webui/deck_schedule.py` `resolve_day` nor `api/smartdeck_feeds.py`.

# Verification gate

Per unit, run that unit's named gate. Risk is **High** by `AGENTS.md` (a new scheduled write
path), so the batch owes happy, failure, and idempotency evidence plus a user diff review, then
one integration run:

```powershell
py -m pytest api/tests
```

Then, in the running app (`cd api; py qf_ui.py`, http://127.0.0.1:8765):

1. `/settings` with the current workspace: Class schedule reports blocks missing and the day
   calendar present, and no console errors.
2. Call `save_day_calendar` through MCP for a two-week range using a real seeded `schedule_id`,
   with one Friday override and one holiday. **Open the written CSV yourself** and confirm the
   row count, the override, and the absent holiday.
3. Call it again without `replace` and confirm the refusal wrote nothing.
4. Call `save_teacher_schedule` with two blocks sharing a name on disjoint weekdays, then **diff
   `Teacher Schedule.json`** and confirm only `blocks` changed.
5. MCP `get_day_schedule` for an ordinary date and for the Friday override: different times, both
   with empty `problems`.
6. Reload `/settings` and confirm the readiness line flipped to ready.

**Verification caveats.** The in-app Browser pane does not composite, so screenshots and
`IntersectionObserver` are unavailable there; verify layout by measurement or in a real browser.
`api/tests/conftest.py` unsets `OneDrive`, so `workspace_root()` is `None` unless the test
monkeypatches `workspace.library_folder`; a schedule test that skips this silently exercises the
empty-workspace path and passes for the wrong reason.

**Do not verify by writing to the live workspace's real `Day Calendar 2026-27.csv`.** Use a
distinct label, and remove the test file afterward.

# Stop conditions

Stop and report rather than guessing when:

- Any preflight item is false.
- A test that existed before this brief needs editing beyond the schema-version counts.
- `save_blocks` turns out to need a signature change to serve the MCP caller.
- The day-calendar write would need a change to `load_day_calendar`'s discovery or merge rules.
- FastMCP will not expose a `dict` or `list` parameter cleanly, forcing a JSON-string argument.
  That is a public contract question, not an executor call.
- A safety gate, vault call, or course gate appears necessary for either tool.

# Adjacent, deliberately excluded

Named so a later agent does not mistake them for oversights.

- **The seeded bell schedules are one district's real times.** Every workspace gets Pearland's.
  For any other district they are wrong, and there is no in-app way to author a replacement.
  That is the real argument for a future `save_bell_schedule`, and it is a seeding decision
  first. Not this brief.
- **`list_calendar_files()` shows every CSV**, including bell schedules, so the Academic calendars
  panel renders useless buttons like "Load Bell Schedule Bobcat Hour". A new day-calendar file
  adds one more. Pre-existing; cheap fix is to skip files whose header identifies them.
- **The dead status strip.** `{% block status_strip %}` in `base.html` is overridden by no
  template and `.ce-status-strip` rules still occupy `ui/layouts.css`. Inert under the current
  flex header. Removing it needs its own decision about whether the strip is coming back.
- **`class_schedule.js` has no executed test.** It touches the DOM on load, and the only JS
  harness in the repo (`api/tests/smartdeck/*.test.mjs`) covers DOM-free modules. Its field
  wiring is guarded by a source-text assertion in `test_presentation_contracts.py`, which is
  weaker than it looks: that is how the name/label collapse shipped. Extracting the block
  mapping into a testable pure module is a real follow-up.

# Execution result

_Not yet executed._
