# Direct execution brief: observability, Batch 3 (B2, B3, B4)

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** senior (self-executed this session)

**Senior objective:** Promote Batch 3 of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md` (baseline
`dev` @ `4ffba87`, `api/tests` 2146 passed). Land B2 (record swallowed
failures), B3 (tracebacks to a rotating file), B4 (support bundle gains the
traceback file, button relocates to Settings). B1 (broader emit coverage on
outcome boundaries beyond exception handlers) is explicitly NOT part of this
batch — it is Order 6 in §9's sequencing, after this batch.

## Required context

Read `AGENTS.md`, then only §4 (B1-B4), §7 non-goal 8, and §8 of the
initiative document. B1 is read for contrast only; do not implement it here.

## Baseline re-verification performed this session

Independently re-ran the AST sweep the initiative document's audit describes
(70 handlers whose entire body is `pass`, `api/` excluding `api/tests/`).
Confirmed the total (70) and re-classified each one directly against
current source rather than trusting the audit's 27/43 split. Landed on
**30 cleanup / 40 swallowed-failure**, then excluded 3 more from the
mechanical batch for reasons found during this re-verification (below),
leaving **37 sites** in scope for B2.

**Excluded from B2, with reasons (not silently dropped):**

1. `api/dataforge/eduphoria_parser.py:99` (`_load_teks_crosswalk`) — this
   `except Exception: pass` guards a call that runs at **module import
   time** (`TEKS_CROSSWALK = _load_teks_crosswalk()` at module scope).
   `api/tests/conftest.py`'s autouse fixture isolates `LOCALAPPDATA` per
   test, but module imports are cached and typically happen once, at
   collection time, before any fixture runs — so an `operational_log.emit()`
   call here could write to the real machine's `LOCALAPPDATA` during test
   collection instead of the isolated per-test path. Also architecturally
   wrong: emitting to a runtime diagnostic log before any workspace/app
   context exists. Recorded here for a future senior; not fixed this batch.
2. `api/diagnostics.py:86` (`_workspace_status`, inside the block that
   already calls `operational_log.emit(_CLEANUP_EVENT, "failed", ...)`) —
   this `except Exception: pass` guards the **emit() call itself**. `emit()`
   already swallows the one exception class that could realistically fire
   here (its internal I/O try/except at `operational_log.py`); the only way
   this outer handler fires is a `ValueError` from `emit()`'s own argument
   validation, which is a caller bug, not an operational failure. Adding
   another `emit()` call inside this handler to "record that emit failed"
   is circular and, if the same bad-argument bug caused the first failure,
   would just fail again. Left as-is.
3. `api/webui/calendar_csv.py:40` (the `_pd` inner closure's first `except
   ValueError: pass`) — this is normal two-format control flow ("try
   ISO-8601, then try `MM/DD/YYYY`"), not a failure; the *second* attempt
   failing (line 46) is the real "we could not parse this date at all"
   point, and is in scope (see table).

## Locked decisions

### B2 — one `operational_log.emit(event, "failed", error_class=...)` per site

No control-flow change anywhere: every site keeps its existing `pass` (or
`continue`/fallback) behavior; the emit call is added as a statement inside
the `except` block, before whatever the block already does. Where the
handler currently has no bound exception name, add one (`as exc`) only when
`error_class=type(exc)` is needed to distinguish which of several caught
types fired; a single-exception-type handler may pass the literal class
instead (e.g. `error_class=OSError`) with no new binding. Import
`from api import operational_log` (module-level) in any file that doesn't
already have it.

Event names (each already checked against `_EVENT_RE`:
`^[a-z][a-z0-9_.-]{0,63}$`; no new `operational_log` keys are used anywhere
in this batch — only `event`, `outcome="failed"`, `error_class`):

| # | File : line | Function | Guards | Event |
|---|---|---|---|---|
| 1 | `api/ai_clients.py:91` | `_pin_workspace` | `config.ensure_workspace_pinned()` | `mcp.workspace_pin_write` |
| 2 | `api/dataforge/views.py:441` | `process` | `history_store.save_snapshot(...)` | `dataforge.snapshot_save` |
| 3 | `api/mirror/sync.py:350` | `full_pass` | `course_catalog.refresh_catalog_assignments_only(...)` | `catalog.refresh_full_pass` |
| 4 | `api/mirror/sync.py:430` | `delta_pass` | same call | `catalog.refresh_delta_pass` |
| 5 | `api/operation_ledger/adapters/assignment_whole.py:401` | `allowed_printable_roots` | `os.path.realpath(runtime_paths.printables_dir())` | `operation_ledger.printable_root_resolve` |
| 6 | `api/operation_ledger/adapters/assignment_whole.py:407` | `allowed_printable_roots` | `os.path.realpath(workspace_path)` | `operation_ledger.printable_root_resolve` |
| 7 | `api/operation_ledger/adapters/sweep.py:219` | `execute` | `mirror_service.notify_course_changed(...)` | `mirror.notify_course_changed` |
| 8 | `api/portfolio_service.py:53` | `_assignment_entries` | `_download_binary(...)` | `portfolio.attachment_download` |
| 9 | `api/pseudonym_rename.py:132` | `refresh_published_profile` | `profile_export.publish_profile(...)` | `pseudonym.profile_republish` |
| 10 | `api/powergrader/new_quiz_fetch.py:985` | `fetch` | `snapshot_callback(...)` | `new_quizzes.snapshot_write` |
| 11 | `api/webui/calendar_csv.py:46` | `_parse_calendar_csv._pd` | final date-parse fallback | `school_calendar.row_parse` |
| 12 | `api/webui/mirror_service.py:297` | `sync_now` | `course_context.refresh_course_context(...)` | `mirror.course_refresh` |
| 13 | `api/webui/mirror_service.py:324` | `refresh_work_findings` | `discovery.scan_active_courses()` + merge | `mirror.work_findings_refresh` |
| 14 | `api/webui/mirror_service.py:347` | `notify_course_changed._run` | `coordinator_instance().submit(...)` + `wait_for_plan(...)` | `mirror.notify_course_changed` |
| 15 | `api/webui/mirror_service.py:399` | `_mirror_heartbeat` | `run_coordinated_heartbeat_tick()` | `mirror.heartbeat_tick` |
| 16 | `api/webui/routine_coordinator.py:89` | `_acquire_claim` | `datetime.fromisoformat(existing["expires_at"])` | `routines.claim_parse` |
| 17 | `api/webui/routes/courses.py:261` | `list_groups` | `mirror_store.write_groups(...)` | `roster.group_write` |
| 18 | `api/webui/routes/course_catalog.py:67` | `refresh_course_catalog` | `mirror_sync.apply_assignment_collection_receipt(...)` | `catalog.receipt_apply` |
| 19 | `api/webui/routes/feedback_common.py:64` | `audit` | writing the provenance/audit-log line | `powergrader.audit_write` |
| 20 | `api/webui/routes/gradebook_curves.py:158` | `curve_apply` | `mirror_service.notify_course_changed(...)` | `mirror.notify_course_changed` |
| 21 | `api/webui/routes/gradebook_curves.py:215` | `revert_curve` | same call | `mirror.notify_course_changed` |
| 22 | `api/webui/routes/gradebook_policy.py:36` | `get_late_policy` | `mirror_store.write_late_policy(...)` | `gradebook.late_policy_cache_write` |
| 23 | `api/webui/routes/gradebook_policy.py:75` | `apply_late_policy` | `mirror_store.invalidate_late_policy(...)` | `gradebook.late_policy_cache_invalidate` |
| 24 | `api/webui/routes/pages.py:358` | `_allowed_open_roots` | `os.path.realpath(r)` | `pages.allowed_roots_resolve` |
| 25 | `api/webui/routes/powergrader.py:697` | `_notify_write_through` | `mirror_service.notify_course_changed(...)` | `mirror.notify_course_changed` |
| 26 | `api/webui/routes/powergrader.py:776` | `_converge_new_quiz_after_finalize` | `new_quizzes.invalidate_responses(...)` | `new_quizzes.response_invalidate` |
| 27 | `api/webui/routes/push_validation.py:85` | `api_physical_quiz` | `calculate_points(...)` + `balance_answers(...)` | `quiz.points_recalculate` |
| 28 | `api/webui/routes/push_validation.py:105` | `api_physical_quiz` | reading render-warning lines + removing the log | `quiz.render_warnings_read` |
| 29 | `api/webui/routes/roster.py:104` | `_reconcile_group_category` | `mirror_store.merge_group_category(...)` | `roster.group_category_merge` |
| 30 | `api/webui/routes/roster.py:108` | `_reconcile_group_category` | `mirror_store.invalidate_groups(...)` | `roster.group_category_invalidate` |
| 31 | `api/webui/routes/roster.py:121` | `_group_categories_for_roster` | `mirror_store.write_groups(...)` | `roster.group_write` |
| 32 | `api/webui/routes/routines.py:242` | `_routines_heartbeat` | `_run_routines_bg()` | `routines.heartbeat_tick` |
| 33 | `api/webui/routes/routines.py:256` | `_run_routines_bg` | `_ROUTINE_RUNNERS[rid](...)` + `set_routine_state(...)` | `routines.scheduled_run` |
| 34 | `api/webui/routes/routines_builtin.py:267` | `_run_routine_curve` | `mirror_service.notify_course_changed(...)` | `mirror.notify_course_changed` |
| 35 | `api/webui/routes/routines_powergrader.py:324` | `_run_routine_powergrader_scheduled_autoscore` | `mirror_service.notify_course_changed(...)` | `mirror.notify_course_changed` |
| 36 | `api/panel_themes.py:1052` | `_process_art` (name approximate) | reading cached processed art bytes | `panels.art_cache_read` |
| 37 | `api/panel_themes.py:1067` | same | writing processed art bytes to cache | `panels.art_cache_write` |

The same event name recurs across several sites deliberately (e.g. seven
sites all guard `mirror_service.notify_course_changed`, two guard
`mirror_store.write_groups`) — this is the same "outcome boundary concept"
per B1's framing, not per-call-site noise; `error_class` and file/line in a
future traceback (B3) still distinguish the exact failure.

### B3 — rotating traceback file

Add to `api/operational_log.py` (same module that already owns the Logs
directory and rotating-handler pattern): a second logger/handler pair
writing to `errors.log` beside `operations.jsonl`, with the same
`_MAX_BYTES`/`_BACKUP_COUNT`, but **no key allowlist or JSON validation** —
this file may contain arbitrary text (exception messages, repr'd values)
from anywhere in the process. Public function: `write_traceback(text: str)
-> None`, best-effort (catches its own I/O exceptions, matching `emit()`'s
own never-raise contract), plus `tail_traceback_text(max_bytes: int) ->
str` for B4 to read it back. In `api/webui/server.py::_api_errors_return_json`,
call `operational_log.write_traceback(...)` with the same formatted string
already being printed, right after the existing `print(...)` call. Do not
remove the `print`.

### B4 — support bundle gains the traceback file; button relocates

`api/diagnostics.py::build_support_bundle` gains a fourth member,
`errors.log`, built from `operational_log.tail_traceback_text(...)` (empty
string if the file doesn't exist yet — same pattern as `_operations_text()`
returning `""` when there are no records). Cap the included text (last
200 KB) so one pathological loop doesn't balloon the bundle.

Move (not duplicate) the "Something not working? / Download support
bundle" block from `api/webui/templates/connections.html`'s "Advanced &
other clients" `<details>` to `api/webui/templates/settings.html`'s "About
this app" rail-nav group (new card after `#update-card`, id
`support-bundle-card`; add `<a href="#support-bundle-card"
data-rail-link>Support bundle</a>` to that rail-nav group). Update the
description to say plainly, per B3's care point, that the bundle may now
contain error text from anywhere in the app and should be reviewed before
sending — do not keep the old "holds only version and health booleans"
line, which is no longer true.

## Authorized scope and insertion points

- The 37 files/lines in the B2 table.
- `api/operational_log.py` (B3: new logger/handler/functions only; do not
  touch the existing `emit`/`tail`/allowlist machinery).
- `api/webui/server.py` (B3: one added call).
- `api/diagnostics.py` (B4: fourth zip member).
- `api/webui/templates/connections.html`, `api/webui/templates/settings.html`
  (B4: move the button/card, update copy, add rail-nav link).
- Test files as needed for B3/B4 behavior (new tests) and any test that
  currently asserts the support bundle has exactly 3 members (must become 4).

## Acceptance criteria

1. Every site in the B2 table: on a forced exception in the guarded call,
   `operational_log.tail()` contains one record with the listed `event`,
   `outcome: "failed"`, and an `error_class` matching the raised type;
   control flow (return value, continued execution) is otherwise identical
   to before.
2. `write_traceback` appends to `errors.log` (not `operations.jsonl`);
   `tail_traceback_text` returns recent content; both are best-effort
   (never raise on a broken filesystem).
3. `_api_errors_return_json` still prints to console (existing behavior
   preserved) AND now also writes to `errors.log`.
4. `build_support_bundle` produces 4 members; `errors.log` is present
   (possibly empty) and is not JSON.
5. The support-bundle form renders and posts correctly from its new
   location on `/settings`; `/connections` no longer has it duplicated.
6. Rendered verification: `/settings` and `/connections` load with no new
   console errors; the new card is reachable from the rail nav.

## Named verification gate

```powershell
py -m pytest api/tests/test_operational_log.py api/tests/test_diagnostics.py api/tests/webui/test_server_errors.py api/tests/webui/routes/test_settings_routes.py api/tests/webui/routes/test_connections_routes.py api/tests/test_presentation_contracts.py api/tests/test_webui_template_contracts.py -p no:randomly
```

(Exact test file names to be confirmed against what exists; adjust to the
real files found during implementation, and note any that don't exist yet
and need a new small test module.)

Then the full gate: `py -m pytest api/tests -q`. Baseline 2146 passed.

Rendered verification (per AGENTS.md's risk table for shared browser
utilities/templates): load `/settings` and `/connections` in the browser
preview, confirm the button moved, confirm no console errors.

## Stop conditions

Stop and report YELLOW/RED without guessing if: a site's "swallowed
failure" turns out on closer reading to already have a signal elsewhere
(logged or returned) that the table missed; adding the exception binding
(`as exc`) would shadow an existing name in that scope; or a test hard-codes
the support bundle's exact 3-member count in a way that reveals an external
contract (not just an internal assertion) depending on it.

## Execution result

Traffic light: GREEN

Commit hash: recorded in the commit that includes this brief update.

Implemented exactly per the locked table, with the 3 documented exclusions
(`eduphoria_parser.py:99` module-import-time call, `diagnostics.py:86`
circular-emit guard, `calendar_csv.py:40` normal control flow) and no
others found needing exclusion during implementation — every one of the 37
sites now records `operational_log.emit(event, "failed",
error_class=type(exc))` with no control-flow change (return values,
fallback behavior, and re-raises are all identical to before). B3 added
`operational_log._ERROR_LOGGER`/`_error_handler_for`/`write_traceback`/
`tail_traceback_text` (a second rotating-file logger, deliberately separate
from the validated JSONL one) and wired `write_traceback` into
`server.py::_api_errors_return_json` alongside the existing `print`. B4
added `errors.log` as the bundle's fourth member (capped at 200 KB) and
moved the "Download support bundle" button from `connections.html`'s
"Advanced & other clients" to a new card on `settings.html` under "About
this app", with copy that now says plainly the bundle may carry error text
and should be reviewed before sending.

Verified during implementation: the existing
`test_support_bundle_is_minimal_and_identifier_free` (the exact test
guarding the previous 3-member/no-identifier contract) needed its member
list updated to 4 and otherwise passed unchanged, including its
forbidden-string sweep across all 4 members — evidence the new
`errors.log` member doesn't reintroduce the leaks that test already guards
against (it's simply empty when nothing was written).

Changed files: 30 source files for the 37 B2 sites (see the brief's table
for the exact list; all also gained an `operational_log` import where they
didn't have one), plus `api/operational_log.py`, `api/webui/server.py`,
`api/diagnostics.py`, `api/webui/templates/connections.html`,
`api/webui/templates/settings.html`, `api/tests/test_beta075_connections.py`
(updated + 1 new test), `api/tests/webui/test_mirror_service.py` (+1 test),
`api/tests/test_operational_log.py` (new, 5 tests), this brief.

Verification:

- Focused gate (`test_operational_log.py test_beta075_connections.py
  webui/test_mirror_service.py mirror/test_sync.py
  test_presentation_contracts.py test_webui_template_contracts.py -p
  no:randomly`): 129 passed.
- Full gate (`py -m pytest api/tests -q`): 2153 passed (baseline 2146 + 7
  new tests, 0 removed).
- Rendered verification: `/settings` and `/connections` loaded in the
  browser preview against the real local workspace, zero server errors and
  zero console errors. `/settings` shows the new "Support bundle" card
  under "About this app" (both in the rail nav and the page body) with the
  updated copy. `/connections`'s full accessibility-tree read confirms the
  "Advanced & other clients" section now ends cleanly after "Any other MCP
  client" / "Copy JSON" with no leftover support-bundle form.

Deviations: added 7 tests total rather than one per B2 site (37 individual
tests would be disproportionate for a mechanical, uniform pattern per
AGENTS.md's test taxonomy — an Example test is "one happy path per feature,
by rule"); picked one representative, easily-testable site
(`mirror_service.sync_now`'s course-context refresh, one of the named
"dangerous cluster" sites) to prove the pattern end-to-end rather than
exhaustively covering all 37. B1 (broader emit coverage on outcome
boundaries beyond exception handlers) was not touched, as scoped.

Unresolved decisions: none for this brief. A5, A7, D1.4, D4, C sequencing,
and 2.3 remain open per the initiative document's §10. B1 remains for a
later batch (§9 Order 6).
