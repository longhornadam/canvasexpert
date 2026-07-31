# Brief — Bind SmartDeck blocks to Canvas courses; ungate non-student course reads

**Status:** current, awaiting execution · **Author:** senior (Claude Code) · **Executor:** external
· **Lane:** one vertical improvement · **Branch:** `dev`

## Objective

Two changes to one seam: give a teacher's schedule block an explicit Canvas course identity, and stop
gating MCP course reads that carry no student data.

1. **Block → course binding.** Add an optional `course_id` string to `blocks[]` in `Teacher Schedule.json`,
   set from a dropdown in the Settings block editor. The existing **Course** field (`blocks[].label`) stays
   free display text. Once a block carries `course_id`, an authoring assistant can read the schedule and
   call the course-scoped read tools for that course with no new plumbing.
2. **Gate correction.** `_course_gate_check` restricts 8 MCP tools to Current courses. Three disk-only reads
   whose own docstrings say *"No student data"* are gated anyway, plus `refresh_mirror`. Remove the gate from
   those four. Keep it on the four that return student data.

A Canvas course ID and an assignment list are not personally identifiable student information. FERPA covers
rosters, submissions, and grades — those keep their gate. The assistant can already enumerate every course
name and ID through `list_courses()`, which has no gate at all, so this makes the read tools consistent with
what it can already see.

## Locked decisions

Decided by the user; do not relitigate or "improve" these.

| # | Decision |
|---|---|
| D1 | `label` (UI "Course") stays free display text. `course_id` is separate. Never derive one from the other. |
| D2 | `course_id` is a **string**, type-checked only. **No** Current-course membership validation on save — a binding to an unknown or deleted course must persist and be *reported*, never rejected. |
| D3 | The picker lists **all saved courses**, Current first, Previous in a second group. |
| D4 | Ungate `get_course_assignments`, `get_modules`, `list_sections`, `refresh_mirror`. |
| D5 | Keep the gate on `get_roster`, `get_submissions`, `get_gradebook_snapshot`, `get_seating_context`. |
| D6 | `refresh_mirror` requires widening `mirror_service.enqueue_sync` to all saved courses. This intentionally widens the web UI's Sync now button too. The automatic heartbeat sweep stays Current-only. |
| D7 | Land everything in one batch. Steps 5-6 are proven by tests; the user has no live Canvas courses yet and will hand-verify those later. |
| D8 | Do not strip `course_id` from `get_teacher_schedule` output. An assistant's read→edit→write round-trip echoes what it read; redacting would silently delete the teacher's binding. |

## Preflight

Run before writing. If any assumption is false, stop and report **RED** — the repository has drifted.

1. `git log -1` is on `dev`. Preserve the four unstaged `docs/handoffs/smartdeck-slice*.md` deletions; do not
   revert them.
2. Locate by **symbol, not line number** — anchors below are indicative only:
   `_course_gate_check` in `api/mcp_server/tools.py` is called by exactly 8 functions
   (`list_sections`, `get_course_assignments`, `get_modules`, `get_roster`, `get_seating_context`,
   `get_submissions`, `get_gradebook_snapshot`, `refresh_mirror`).
3. `api/webui/mirror_service.py` → `enqueue_sync` filters on `config.active_courses()` and raises
   `ValueError("Not a Current course.")`. If it no longer does, step 6 needs rethinking.
4. Baseline the suite: `py -m pytest api/tests -q`. Expect **7 pre-existing failures** —
   `test_beta075_imports`, `test_canvas_mutation_ownership`, two in `test_noteforge_physical_routes`, two in
   `test_presentation_contracts` (`test_all_live_templates_use_layouts_and_no_inline_styles`,
   `test_legacy_presentation_layer_is_gone`), `test_transport_ownership`. These are unrelated and confirmed
   identical at a clean HEAD worktree. Do not fix them. If the count differs, report RED before writing.

## Scope

### 1. `api/webui/deck_schedule.py` — validate the key

In `validate_teacher_schedule`, beside the existing `label` type check:

```python
if "course_id" in block and not isinstance(block.get("course_id"), str):
    problems.append(f"block '{name}' course_id must be a string")
```

Type check only (D2). This module is the offline schedule parser and imports no `config` — keep it that way.
Add `course_id` to the schema example in the module docstring.

No storage work is needed: the format is additive and unknown block keys already survive a round-trip
(`test_schedule_routes.py::test_get_api_schedule_returns_blocks_verbatim_including_unknown_keys`).

### 2. `api/webui/routes/schedule.py`, `api/webui/schedule_setup.py` — serve the options

`GET /api/schedule` already returns blocks verbatim, so `course_id` flows out with no change. Add the
option list to that payload:

```python
"courses": [{"id": str(c["id"]),
             "name": config.course_display_name(c["id"]),
             "active": bool(c.get("active", True))}
            for c in config.saved_courses()]
```

Reuse `config.course_display_name` (`api/webui/config/courses.py`) — do not re-derive `nickname or name`.
Use `saved_courses()`, not `active_courses()` (D3).

In readiness, follow the existing `unknown_schedule_ids` pattern in `_day_calendar_detail` and report
bindings matching no saved course as `pieces.teacher_schedule.unknown_course_ids`. Report, never refuse (D2).

### 3. `api/webui/static/settings/class_schedule.js` — the dropdown

- `renderBlocks`: after the Course input, add `<select data-field="course_id">` — blank "— none —", then
  `<optgroup label="Current">` and `<optgroup label="Previous">` split on `active`, matching option selected.
- A `block.course_id` matching nothing in the list is appended as an extra selected option labeled
  `"<id> (not a saved course)"`, so saving cannot silently drop it.
- **Empty state:** when the list is empty (no courses bookmarked yet — the user's situation before the school
  year), disable the select and show a one-line hint pointing at Settings → Current courses. An empty list is
  normal, not an error.
- `loadState`: stash `data.courses` on `state`.
- `readBlocks`: mirror the existing `label` handling exactly — set `block.course_id` when non-empty, `delete`
  it when blank. Keep starting from `Object.assign({}, row._sourceBlock)` so other unknown keys survive.

### 4. `api/webui/templates/settings.html` — correct the hint

The "Your blocks" paragraph claims *"Course is what shows on the deck."* That is false: the display payload
sends `{id, block, layout, title, body, widgets, start, end}` and the only block identifier on the projector
is the **Block name** in the up-next line (`static/smartdeck/display.js`, the `Next: … at …` string). Reword
so Course reads as a teacher-facing label, and add one line for the new field: optional, links the block to a
Canvas course so an assistant can pull that course's assignments when authoring.

Keep the `AI Connections` link — `test_presentation_contracts.py` asserts `href="/connections">AI Connections</a>`.

### 5. `api/mcp_server/tools.py` — ungate three disk-only reads

Delete the `_course_gate_check` call and its `if err:` block from `list_sections`,
`get_course_assignments`, and `get_modules`. Update each docstring: scope is any saved course.

Leave `_course_gate_check` itself in place and leave it applied to `get_roster`, `get_seating_context`,
`get_submissions`, `get_gradebook_snapshot` (D5).

### 6. `api/mcp_server/tools.py`, `api/webui/mirror_service.py` — ungate `refresh_mirror`

Deleting the tool's gate alone does nothing: `enqueue_sync` filters independently and its `ValueError` is
caught and returned by `refresh_mirror`. Both must change.

- `enqueue_sync`: `config.active_courses()` → `config.saved_courses()`, and update the `ValueError` text,
  which no longer concerns Current courses.
- Delete the gate call in `refresh_mirror`.
- **Do not touch `enqueue_heartbeat_refreshes`** — it stays `active_courses()`, so an archived course is
  mirrored only on explicit request and never swept in the background. This is the containment for D6.

`api/webui/routes/mirror.py` (Sync now) inherits the widening by design. `_run_course_refresh`'s manual
branch already calls `sync_now(course_id)` directly; no change needed there.

### 7. Docs

- `docs/mcp-server.md` — *"Every `course_id` tool is scoped to Current courses"* becomes false. Split it:
  student-data tools scoped to Current; catalog and mirror tools accept any saved course.
- `save_teacher_schedule`'s docstring in `api/mcp_server/tools.py` and the matching paragraph in
  `docs/mcp-server.md` say *"No course_id."* State it precisely: no `course_id` **parameter**, no Canvas
  call, and a teacher-set block `course_id` passes through untouched (D8).
- `docs/reference/smartdeck-module-map.md` says "schema v14, 19 tools total" — stale since v15. Fix.

No file under `docs/contracts/` encodes the course gate, so no public contract changes. If you find one that
does, stop and report RED.

## Non-goals

- **Do not** add `course_id` to `resolve_day`'s output dict or the display payload. A course ID on a
  classroom projector is noise for students. Leaving it out is also what keeps this away from
  `docs/contracts/classroom-facing-data-contract.md`.
- **Do not** touch `api/webui/sf.py`. The deck format is a strict allowlist; no `feed`, no new slide keys.
- **Do not** wire `api/smartdeck_feeds.py`. `missing_assignments` stays `not_yet_available`.
- **Do not** collapse, auto-fill, or derive `name` ↔ `label` (D1).
- **Do not** edit `api/webui/config.py` — dead code shadowed by the `api/webui/config/` package.
- **Do not** touch `LLM_Modules/*_Base.md`.
- **Do not** fix the 7 pre-existing test failures.

## Acceptance criteria

Each is independently checkable.

1. A block with `"course_id": "9000001"` written through `POST /api/schedule/teacher` or MCP
   `save_teacher_schedule` persists and returns byte-identical from `GET /api/schedule` and
   `get_teacher_schedule`, with `name`, `label`, `raw_periods`, `weekdays`, and any unknown keys intact.
2. A non-string `course_id` is rejected by `validate_teacher_schedule` with a problem naming the block.
3. A `course_id` matching no saved course still saves, and appears in
   `pieces.teacher_schedule.unknown_course_ids`. Saving does not fail.
4. `GET /api/schedule` includes `courses`, with Previous entries flagged `active: false`.
5. The Settings editor renders a `data-field="course_id"` select with Current/Previous optgroups, alongside
   still-separate `name` and `label` inputs. With no saved courses it renders a disabled select plus a hint.
6. Editing an unrelated field and saving does not drop an existing `course_id`.
7. `get_course_assignments`, `get_modules`, and `list_sections` no longer return
   `"is not a Current course"` for a saved-but-Previous course.
8. `get_roster`, `get_submissions`, `get_gradebook_snapshot`, and `get_seating_context` still do.
9. `enqueue_sync` accepts a Previous course; `enqueue_heartbeat_refreshes` still queues Current courses only.
10. The projector is unchanged: `/smartdeck/display/{deck_id}/data` contains no `course_id`, and the up-next
    line still shows the Block name.
11. `docs/mcp-server.md` no longer claims every `course_id` tool is Current-scoped.

## Verification gate

```bash
py -m pytest api/tests/test_deck_schedule.py api/tests/test_schedule_routes.py api/tests/test_presentation_contracts.py api/tests/test_mcp_server_tools.py api/tests/test_mirror_service.py
```

Then the full suite, which must show **the same 7 failures and no eighth**:

```bash
py -m pytest api/tests -q
```

**Tests to invert** — these currently assert the gate and must now assert success on a Previous course. Keep
the test, flip the expectation; do not delete:

- `test_get_course_assignments_rejects_non_current_course`
- `test_get_modules_rejects_non_current_course`
- `test_list_sections_rejects_non_current_course`
- `test_refresh_mirror_rejects_non_current_course`

**Tests that must keep passing unchanged** (this is the FERPA line):
`test_get_roster_rejects_non_current_course`, `test_get_submissions_rejects_non_current_course`,
`test_get_gradebook_snapshot_rejects_non_current_course`.

**New tests to write:**

- `test_deck_schedule.py` — non-string `course_id` produces a problem; a string passes; unknown-key tolerance
  still holds.
- `test_schedule_routes.py` — criteria 1, 3, 4.
- `test_presentation_contracts.py` — criterion 5. Extend the existing panel tests; do not rewrite
  `test_class_schedule_editor_edits_block_periods_and_course_separately`.
- `test_mcp_server_tools.py` — `save_teacher_schedule` preserves `course_id` and rejects a non-string one.
- `test_mirror_service.py` — criterion 9.

### Manual verification, no live Canvas required

The user has no Canvas courses connected yet. The schedule and deck MCP tools make no Canvas call and need
no token, so most of this is still hand-verifiable.

Start the app (this is the verify config from `.claude/launch.json`; it leaves the normal UI on 8765 alone):

```bash
py -m uvicorn api.webui.server:app --host 127.0.0.1 --port 8766 --lifespan off
```

1. Open `http://127.0.0.1:8766/settings`. With no saved courses, confirm the disabled select and hint.
2. Seed two fake courses — the bookmark route takes plain form fields and does no Canvas validation:

   ```bash
   curl -X POST http://127.0.0.1:8766/settings/courses/bookmark -d "course_id=9000001&course_name=Test Course A&nickname=Test A"
   ```

   Add a second, then `curl -X POST http://127.0.0.1:8766/settings/courses/9000002/set-active -d "active=false"`
   to get a Previous entry. Confirm both optgroups render. Clean up with
   `POST /settings/courses/{id}/remove`.
3. Bind a course, **Save blocks**, reload, confirm it stuck. Check
   `fetch('/api/schedule').then(r => r.json())` in the browser console — no console errors.
4. Confirm `Teacher Schedule.json` under the workspace `SmartDecks` folder carries the key with `name` and
   `label` unchanged.
5. Criterion 10: open a deck's display page and its `/data` endpoint.

**Deferred to the user, not the executor:** criteria 7 and 8 by hand. With no courses,
`get_course_assignments` and `get_modules` return "No local course catalog found" both before and after this
change, because that catalog is only created by a web-UI refresh. `refresh_mirror` needs a live Canvas call.
Tests are the acceptance evidence for those (D7).

## Guardrails

- **FERPA (#2):** a course ID and an assignment list are not student data — that is the premise of steps 5-6.
  The four student-data tools keep their scope. Do not put a real course ID in a fixture; generate one.
- **No district config in source (#3):** the picker is populated from saved courses at runtime. No course ID,
  name, or nickname in any `.py`, `.js`, or template default.
- **Local-only (#4):** unchanged. Do not alter the bind address or add routes reachable off the machine.
- **Secrets (#1):** no token touches this change. Do not log request bodies from the mirror path.

## Risk seams

The senior will inspect these specifically:

1. `enqueue_sync` — the one authorization boundary that widens. Confirm `enqueue_heartbeat_refreshes` is
   untouched, or archived courses start syncing in the background.
2. `readBlocks` in `class_schedule.js` — the `Object.assign` from `_sourceBlock` is what preserves unknown
   keys. Breaking it silently drops teacher data on every save.
3. The three student-data gate tests. If any of them changes, the change is wrong.

## Stop conditions

Report **RED** and stop if: preflight fails; a `docs/contracts/` file turns out to encode the course gate;
the gate cannot be removed from a tool without touching a student-data path; or the full suite shows a
failure outside the known 7.

Report **YELLOW** if the Settings empty-state copy or the reworded Course hint needs a product call, or if a
test cannot be written without new fixtures.

## References

Read only these, plus `AGENTS.md`:

- `api/webui/deck_schedule.py` — `validate_teacher_schedule`, `resolve_day`, module docstring schema example
- `api/webui/schedule_setup.py` — `_day_calendar_detail` (the report-never-refuse pattern), `save_blocks`
- `api/webui/routes/schedule.py`, `api/webui/routes/smartdeck.py` — `_resolve_slides`, display payload
- `api/webui/static/settings/class_schedule.js`, `api/webui/templates/settings.html`
- `api/webui/config/courses.py` — `saved_courses`, `active_courses`, `course_display_name`
- `api/mcp_server/tools.py` — `_course_gate_check`, the 8 gated tools, `list_courses`, `save_teacher_schedule`
- `api/webui/mirror_service.py` — `enqueue_sync`, `enqueue_heartbeat_refreshes`, `_run_course_refresh`
- `api/default_docs/AI Authoring/Author a Class Schedule.txt` — the `name`-vs-`label` rule behind D1
- `docs/mcp-server.md` — the gate-posture paragraphs only

**Status: complete**

## Execution result

**Execution status: GREEN**

- Commit: none; changes remain on `dev` in the working tree.
- Changed files: `api/mcp_server/tools.py`, `api/tests/test_beta075_mcp.py`,
  `api/tests/test_deck_schedule.py`, `api/tests/test_mcp_server_tools.py`,
  `api/tests/test_mirror_service.py`, `api/tests/test_presentation_contracts.py`,
  `api/tests/test_schedule_routes.py`, `api/webui/deck_schedule.py`,
  `api/webui/mirror_service.py`, `api/webui/routes/schedule.py`,
  `api/webui/schedule_setup.py`, `api/webui/static/settings/class_schedule.js`,
  `api/webui/templates/settings.html`, `docs/mcp-server.md`, and
  `docs/reference/smartdeck-module-map.md`.
- Verification: the focused gate passed 207 tests with the two known presentation
  failures; the changed-surface run passed 201 tests; `git diff --check` passed.
  The full `py -m pytest api/tests -q` run passed 1,756 tests and reproduced exactly
  the seven pre-existing failures named in preflight, with no eighth failure.
- Deviation: D6 requires the manual worker to sync Previous courses, but
  `enqueue_sync` dispatches through `sync_now`, which independently filtered to
  Current courses. `sync_now` was therefore widened to `saved_courses()` with the
  same saved-course error text; `enqueue_heartbeat_refreshes()` remains unchanged
  and Current-only. The existing beta MCP assertion for the ungated catalog read
  was updated to its new no-local-catalog result.
- Unresolved decisions: none. Live Canvas refresh and the student-data gate behavior
  remain deferred to the user as directed by D7; no live course was available for
  manual verification.
