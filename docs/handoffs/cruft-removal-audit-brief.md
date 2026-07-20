# Cruft-removal & de-duplication audit — brief for a fresh senior session

> **SENIOR INVESTIGATION, not a locked executor brief.** This is a hunting license with
> leads, method, and guardrails — not a mechanical checklist. Read `AGENTS.md`, this file,
> and the contracts named below. Produce a **ranked excision list with evidence before
> cutting anything.**

## Why this exists

The codebase grew from ~35k to ~126k lines in about two weeks of heavy AI-assisted
building. A lot of real capability landed — but rapid AI-built code reliably accretes
overbuild, speculative generality, and duplicated effort. 1.0-beta is code-complete and
accepted (`docs/reference/1.0beta-acceptance-record.md`); the goal now is to **cut fat
without losing behavior**, with a particular eye on **CanvasExpert pieces talking to both
CanvasMirror AND live Canvas when only one is needed.**

## Method (deletion-first, contract-guided, test-guarded)

1. **The 1129 tests are the safety net — lean on them, don't add more.** After every
   excision: `py -m pytest api/tests` + `py -m pytest engine/tests` must stay green. Green
   after deletion = safe. If a test exists *only* to cover deleted cruft, delete it too. Do
   NOT build synthetic harnesses or new test infra to gain confidence — the suite is the bar.
2. **Use the machine contracts as the "what's actually used" oracle**, the way Batch 8 used
   them to prove 4 adapters were dead:
   - `docs/contracts/canvas-transport-owners.json` + `test_canvas_mutation_ownership.py`
   - `api/tests/test_transport_ownership.py` (the direct-HTTP owner allowlist)
   - `docs/reference/mutation-reconciliation-map.md`, `canvas-read-spine-contract.md`
3. **Verify against code, never doc prose.** This project's docs have repeatedly been stale
   (the reconciliation map mislabeled curves; the spine status column lied about batch
   completion). Trust `rg` + tests, not comments.
4. **Delete atomically** (code + its test + its contract entry), like the Batch 8 retirement.
5. **Prefer deletion over refactor.** If it's genuinely used, leave it. If it's dead or a
   duplicate path, cut it. Don't gold-plate replacements.

## Leads, highest-confidence first

### 1. CanvasMirror-vs-live duplication (the named target)

The spine §21 open-risk list already names these — verify each against code and decide
migrate-to-mirror / downgrade-to-fallback-only / delete:
- **#5 duplicate structure acquisition** — Course Catalog and the private mirror
  independently fetch assignments.
- **#6 Roster/Course Info bypass** — `api/webui/routes/courses.py` still fetches users,
  sections, groups, memberships, modules, assignments **live** (with N+1 group reads) despite
  mirror scopes existing.
- **#7 Create picker bypass** — module/assignment-group pickers have direct live routes.
- **#10 Student Report/portfolio bypass** — `api/report_local_reads.py` is migrated, but
  `api/portfolio_service.py` and `api/student_packet.py` keep `requests.Session()` live
  fallbacks. **Check whether those fallbacks are ever exercised or are dead.**
- **Concrete entry list:** `api/tests/test_transport_ownership.py` allowlists exactly the
  ~15 files doing direct HTTP. The webui routes on that list doing *reads*
  (`courses.py`, `reports.py`, `roster_canvas.py`) are the audit targets. For each read: is
  it redundant with a `read_service` scope? If yes, migrate + delete the live path. If it's a
  genuine write-decision-boundary read (design law 5.7) or a real fallback, keep it and say so.

### 2. Dead code beyond the four retired adapters

Batch 8 proved dead code hides in plain sight. Hunt more:
- Registered/exported symbols with **no non-test producer or consumer** (e.g., `known_kinds()`
  has no production caller; the generic `/api/operations/{kind}/prepare` accepts any KIND).
- `api/webui/mirror_reads.py` is an explicitly-annotated compatibility shim slated for removal
  once the routine/sweep/curve read call sites migrate — **check if they can migrate now**,
  then delete the shim + its test.

### 3. Overbuilt abstractions / speculative generality

- The **bounded coordinator** (`api/mirror/coordinator.py`, 346 lines + telemetry, self-rated
  "high risk"): does the full priority/dependency/coalescing/cancellation machinery earn its
  keep, or would a simpler debounced per-course refresh do? Weigh it against how it's actually
  invoked.
- The **operation-ledger content-adapter decomposition** and the **webui presentation-system
  template-family migration** — evaluate whether the abstraction layers pay for their
  indirection.
- Smell signals: single-implementation "registries," one-caller "frameworks," config
  parameters never set to anything but the default, layers that only forward.

### 4. Duplicate read/helper layers

Three read layers coexist: `mirror_reads.py` (shim) + `mirror/read_service.py` +
`mirror/queries.py`. And multiple "get submissions" paths (mirror / live / focused /
powergrader). Map them; collapse redundancy.

### 5. Test cruft (last, and carefully)

After code excision, prune tests that only covered deleted paths, and the ad-hoc per-file
fake-Canvas scaffolding (`_ln_get`/`_ln_send` repeated across dozens of files) where the
covered code is gone. **Keep the contract/architecture tests** (mutation-ownership,
transport-ownership, read-spine, privacy scan, none-label guard) — those are the net that
makes aggressive removal safe.

### 6. Follow the growth

`git log --stat` the two-week window and rank files/dirs by lines added. The biggest
additions — the redesign (`canvasexpert-redesign-*`), `operation_ledger`, `powergrader`,
the webui presentation system, the coordinator — are the richest hunting grounds.

## Guardrails

- Keep both suites green after every change; a red suite means stop and reassess.
- Never remove a genuine write-decision-boundary live read (design law 5.7) or a
  security/fail-closed guard (vault conflict, disposable-root cleanup, student-free
  projection boundaries). Verify redundancy first.
- Preserve the accepted 1.0-beta behavior and the machine contracts; if a removal would
  change a contract, that's a senior decision, not a mechanical cut.

## First move

Produce two artifacts before cutting: (a) a **dead-symbol reachability scan** (exported/
registered symbols with no non-test caller), and (b) a **CanvasMirror-vs-live duplication
inventory** (every live read with whether an equivalent mirror scope exists). Rank by
lines-removed-per-risk, then excise top-down, suite-green at each step.

## Audit findings — 2026-07-20 (evidence-verified against code, not doc prose)

Three parallel investigations ran: dead-symbol reachability scan, CanvasMirror-vs-live
duplication inventory (against `api/tests/test_transport_ownership.py`'s allowlist), and an
overbuilt-abstraction evaluation of the coordinator / operation-ledger / presentation system.
Git growth ranking (`git log --numstat` since 2026-06-13) cross-checked the leads. **Status:
findings only, nothing executed yet** — awaiting senior scope decision on Tier 2/3 below.

### Tier 1 — dead code, mechanical delete, lowest risk (delete atomically: code + test + registration, suite-guarded after each)

1. `ExtensionAdapter` (`api/operation_ledger/adapters/extension.py`, 386 lines) + `gradebook.extension`
   registration in `api/operation_ledger/__init__.py` + `api/tests/test_extension_operation.py`.
   Zero production callers — the live due-date-extension feature
   (`api/webui/routes/gradebook_extensions.py::extend_due`) calls `_canvas_send()` directly and
   never touches the ledger. Built during a redesign, never wired to any frontend caller (`grep`
   for `gradebook.extension` across `*.py`/`*.js`/`*.md` hits only the adapter, its test, and two
   archived handoffs).
2. `reversal_descriptor` Protocol method (`api/operation_ledger/registry.py:25`) + its 7 adapter
   implementations (`adapters/{assignment,extension,page,quick_assignment,quiz,rubric,sweep}.py`).
   Only test files call it; production hardcodes `"reversal_supported": False`
   (`api/operation_ledger/operations.py:315`) instead of calling the adapter. Shrinks to 6
   implementations once #1 above is deleted.
3. `known_kinds()` (`api/operation_ledger/registry.py:44`). Only 2 test callers
   (`test_quiz_operation.py:154`, `test_quiz_tier_operation.py:233`), no route/CLI/MCP caller.
4. `process_inbox` (`api/feedback_artifacts.py:540`), `reidentify_dir` (line 566), `write_bundle`
   (line 223). Dead folder-drop CLI workflow; only `test_feedback_pipeline.py` exercises it. The
   live AI-feedback path (`api/powergrader/ai_workflow.py`, `import_results.py`) calls
   `pseudonymize_submissions`/`write_safe_and_private`/`reidentify`/`parse_results` directly
   in-process instead.
5. `call_canvas_get_all` (`api/work_registry/providers/__init__.py:292`). Superseded by the
   `WorkCourseReads` typed class (`discovery.py`); only test callers remain. (Its private helper
   `_call_live_get_all` stays alive — `WorkCourseReads` calls it directly.)
6. `pg_modules` route + `load_module_picker` (`api/webui/routes/powergrader.py:155-161`,
   `api/webui/routes/powergrader_setup_support.py:4-60`) + `test_powergrader_module_picker.py`.
   Orphaned — the live PowerGrader setup page (`powergrader/setup_core.js:320,343`) fetches
   modules from `/api/course-catalog` instead; nothing in current UI calls this route.
7. `project_local` (`api/work_registry/providers/powergrader.py:13`, also in its `__all__`).
   Zero callers anywhere, including tests.
8. `mirror_service._run_course_structure` (`api/webui/mirror_service.py:80-89`) / coordinator
   scope `"course_structure"`. No production caller ever submits this scope
   (`enqueue_heartbeat_refreshes` only submits `["course.refresh"]`; the Sync button defaults the
   same way) — latent double-fetch risk that is currently dead code.

### Tier 2 — confirmed live duplication needing a mirror-first migration (pattern already proven in-repo, not a pure deletion)

9. `api/webui/routes/courses.py::course_detail` fetches modules unconditionally live
   (`courses.py:144-213`, comment at 152 admits "Modules stay a live read this batch"), despite
   `catalog.modules` already existing and being consumed correctly by
   `push.py::get_modules` (`push.py:27-50`). Fix: add a `_local_modules` helper mirroring
   `_local_assignments`'s pattern.
10. `api/webui/routes/reports.py::api_students` (`reports.py:171-183`, used by
    `student_reports.js:33`) and `portfolio_merged`'s "all students" cohort (`reports.py:290-300`)
    both do an always-live `_canvas_get_all(/users)` despite `private.roster` already existing and
    being consumed correctly by `courses.py::_local_students`. Fix: same mirror-first pattern.

### Tier 3 — real findings, bigger judgment calls; not mechanical cuts, need a dedicated brief each

- **Mirror coordinator** (`api/mirror/coordinator.py`, 346 lines): the dependency graph
  (`_DEPENDENCIES`/`_ordered_scopes()`), `cancel()` plumbing, and 2 of 6 priority tiers
  (`preflight`, `focus`) are speculative — every production caller submits exactly one scope, and
  `cancel()` has zero non-test callers. The coalescing-by-key + bounded-pool + foreground-yield
  core (wired into `server.py`'s request middleware) is real and load-bearing. Estimated ~50%
  size reduction (346 → ~140-170 lines) but this is a scheduling-semantics refactor, not a
  deletion — real regression risk if foreground-yield behavior isn't preserved exactly.
- **`engine/orchestrator.py::QuizForgeOrchestrator` + `main()`**: appears to be a dead legacy CLI
  pipeline — the live entry point (`api/webui/routes/push_validation.py:64-69`) bypasses it
  entirely and imports engine internals directly, and `engine/dev/README.md` states its own
  directory is experimental-only. But 3 integration test files
  (`test_orchestrator.py`, `test_full_migration.py`, `test_backwards_compatibility.py`) exercise
  real parse/validate/package logic *through* the orchestrator's interface. Retiring it means
  re-pointing those tests at the direct engine APIs first — a small project of its own.

### Confirmed NOT cruft (checked against code, cleared)

- `api/webui/mirror_reads.py` shim — still has 3 live call sites
  (`routines_builtin.py:55,152,224`, `gradebook_curves.py:36`), migration explicitly not done yet
  per its own pinning test (`test_routine_reads.py:299-301`). Do not touch until those call sites
  migrate.
- The 6 remaining operation-ledger adapters (assignment/quiz/page/rubric/quick_assignment/sweep)
  — genuinely polymorphic dispatch, each with real distinct production call paths.
- WebUI presentation/template-family system — already consolidated; the 5 legacy files it
  retired (`style.css`, `workbench.css`, `workbench_base.html`, `_workbench_header.html`,
  `_course_picker.html`) are confirmed gone from disk. No further action.
- Every other live-fallback read audited in `courses.py` (roster, groups, assignments),
  `reports.py::list_assignments_full`, `student_packet.py`, `portfolio_service.py`,
  `roster_canvas.py`/`roster.py` group-membership reads (write-decision-boundary, design law 5.7),
  and `push.py`'s module/assignment-group pickers (already mirror-first) — all test-verified
  genuine fallbacks or already-correct, not duplication.

## Execution result — 2026-07-20

**Tier 1 + Tier 2:** executed by an external tool (Deepseekv4Flash). Verified the diff against
this brief before building on it — clean and matches items 1-10 above (`ExtensionAdapter` +
`reversal_descriptor` + `known_kinds()` + the `feedback_artifacts.py` folder-drop cluster +
`call_canvas_get_all` + `pg_modules`/`load_module_picker` + `project_local` +
`mirror_service._run_course_structure`/`course_structure` scope all removed; `courses.py`
modules and `reports.py` roster reads migrated to mirror-first).

**Tier 3 — mirror coordinator:** the same external tool had also started this (not requested
yet at that point) and left it half-finished: `_Job.dependencies`/`cancel_requested`/`cancelled`
were stripped from the dataclass but `_worker`/`_job_view`/`cancel()` still referenced them,
so every worker thread crashed on `AttributeError` the moment a job dequeued — the root cause
of 9 of the 10 failures seen when this was picked back up (the 10th, a vault test, was an
unrelated pre-existing flake that passes in isolation). Finished the simplification
consistently: removed `_DEPENDENCIES`/`_ordered_scopes`, the `cancel()` method, and the
`cancel_requested`/`cancelled` fields entirely (confirmed via grep — no runner ever returns a
`cancelled` outcome, and no route ever called `.cancel(`), and dropped `"cancelled"` from the
terminal-state sets since it's now unreachable. Kept the coalescing-by-key, bounded two-worker
pool, and foreground-yield mechanism untouched (still load-bearing, still wired into
`server.py`'s request middleware). `api/mirror/coordinator.py`: 346 -> 281 lines. Rewrote
`api/tests/test_mirror_coordinator.py` to match (dependency/cancellation tests replaced with
coalescing-promotion and cross-course failure-isolation tests; yield tests unchanged).

**Tier 3 — orchestrator retirement:** deleted `engine/orchestrator.py`
(`QuizForgeOrchestrator` + `main()`, ~350 lines) after confirming zero callers besides its own
3 integration test files (`engine/dev/` scratch scripts still reference it but are explicitly
experimental-only per `engine/dev/README.md`, not part of the `engine/tests` gate). Consolidated
`test_orchestrator.py`'s parametrized full-pipeline test and `test_full_migration.py`'s
`test_full_orchestrator_pipeline` into one `test_full_pipeline_parse_validate_package_and_log`
that calls the same direct engine APIs (`import_quiz_from_llm`, `calculate_points`,
`balance_answers`, `QuizValidator`, `package_quiz`, `generate_log`, `generate_fail_prompt`)
without the orchestrator's dead dropzone-scanning/archive-to-`old_quizzes` machinery. Deleted
`test_backwards_compatibility.py` outright — its one test depended on a `User_Docs/samples`
directory that doesn't exist in this repo, so it already returned before any assertion; it
verified nothing.

**Suite state:** `api/tests` 1098 passed, 1 skipped. `engine/tests` 117 passed (down from 121 —
exactly the 4 dead-path tests removed: the 3-extension `test_full_pipeline` parametrization and
`test_sample_quizzes`).

## Tier 4 — 2026-07-20 (continuing the audit per user direction: cleanup first, then a
## separate runtime-diagnostics initiative for live-fire debugging)

Three parallel investigations: a post-cut orphan check (did Tiers 1-3 leave anything else
unreferenced?), the read-layer duplication map from the original brief's lead #4 (never
previously investigated), and an audit of the largest-growth files not yet individually
reviewed. All findings verified with `rg`, not doc prose.

### Executed (atomic delete, test-guarded at each step)

- `load_module_picker` (`api/webui/routes/powergrader_setup_support.py`) — orphaned after
  `pg_modules` was retired in Tier 1; zero callers anywhere.
- `process_inbox`, `reidentify_dir` (`api/feedback_artifacts.py`) — orphaned after `write_bundle`
  was retired in Tier 1. `process_inbox` called the now-nonexistent `write_bundle` and
  `reidentify_dir` called `reidentify`/`parse_results`/`reidentified_csv`, none of which were
  ever imported in this file — both were already broken, not just dead. Removed the now-unused
  `parse_student_analysis_file` import alongside.
- `bundle_paths()` (`api/webui/routes/feedback_common.py`) — same legacy `2_ForLLM` folder
  scheme as the above, zero callers; removed the now-unused `glob` import.
- `_groups_from_categories` (`api/work_registry/providers/roster_warnings.py`) — zero callers;
  `_fetch_groups` duplicates the same shaping logic inline instead of calling it.
- `storage.write_operations_document`, `storage.write_claims_document`,
  `storage.read_claims_document` (`api/operation_ledger/storage.py`) — zero callers anywhere,
  including tests. (Kept `_atomic_write_*_unlocked` — still used internally by
  `modify_claims`/`modify_operations`.)
- `mirror/queries.py::assignment` and `::roster_freshness` — zero non-test callers (`assignment`)
  or zero callers at all (`roster_freshness`); updated `test_mirror_queries.py`'s two assertions.
- `migrate_legacy_tier`, `active_tier_ids`, `set_group_label` (singular) —
  `api/webui/config/roster.py`. Zero production callers; `migrate_legacy_tier` actively
  contradicts the current V3 roster design (Canvas groups are source of truth, `tier_id` is an
  `OBSOLETE_PATCH_KEY`). Removed the now-unused `re` import, updated the `config/__init__.py`
  re-export list, deleted 5 now-pointless tests in `test_roster_config.py`, and removed the dead
  `fake_set_group_label` monkeypatch in `test_roster_routes.py`.
- `_get_group_memberships` (`api/webui/routes/roster.py`) + `roster_canvas.get_group_memberships`
  (`api/webui/routes/roster_canvas.py`) — a wrapper/impl pair with zero callers, sitting right
  next to the real write-boundary membership logic (`_reconcile_group_category`) that derives
  membership from an already-fetched snapshot instead. Deleting this was the file's only direct
  HTTP call, so `roster_canvas.py` came off the `ALLOWED_DIRECT_HTTP` allowlist in
  `test_transport_ownership.py` — confirmed by rerunning
  `test_transport_owner_allowlist_has_no_stale_entries`, which caught the drift immediately.
- Unused import `ASSIGNMENTS_PATH` (`api/course_catalog.py`).
- 13 unused imports left over from the `routines.py` file split (`timezone`, `_canvas_get`,
  `_canvas_get_all`, `_parse_iso_local`, `_school_days_late`, and 9 `_autoscore_*`/
  `_parse_routine_dt` names re-imported from `routines_powergrader` alongside
  `PowerGraderRoutineDeps`, which is the only one actually used).
- `_write_openrouter_debug_file`, `_build_safe_ai_packet` compatibility aliases
  (`api/webui/routes/powergrader.py`) — zero non-test callers; production reaches the same
  behavior via `privacy.write_openrouter_debug_file`/`packet.build_safe_ai_packet` directly.
  Updated `test_powergrader_packet.py`'s two call sites to import and call those modules
  directly instead of through the alias. (The file's other 6 compatibility aliases —
  `_mode_label`, `_load_session`, `_save_session`, `_privacy_step`, `_write_privacy_audit_file`,
  `_vault` — all have real, heavy call-site usage within the same file; verified individually,
  not touched.)

**Found broken mid-execution, fixed:** the `_get_group_memberships` deletion tripped
`test_transport_owner_allowlist_has_no_stale_entries` immediately, as designed — fixed by
removing `roster_canvas.py`'s now-stale allowlist entry. A `test_routine_receipts.py::
test_concurrent_runs_execute_once` failure appeared once in a full-suite run and passed cleanly
in isolation — a pre-existing thread-timing flake unrelated to this batch, same shape as the
vault-test flake noted in the Tier 1-3 execution result.

**Suite state after Tier 4:** `api/tests` 1093 passed, 1 skipped (1098 minus 5 tests that only
covered deleted `migrate_legacy_tier`/`active_tier_ids` behavior). `engine/tests` unaffected,
117 passed.

### Investigated and confirmed NOT cruft (no action)

- **Read-layer map** (`mirror_reads.py` / `mirror/read_service.py` / `mirror/queries.py`):
  cleanly partition by concern — `read_service.py` is the typed local-only reader every other
  layer builds on, `queries.py` is the mirror-backed twin of the always-live
  `gradebook_queries.py` interface (a deliberate matched pair, not duplication), and
  `mirror_reads.py` is the one place that adds mirror-first/live-fallback for its 3 legacy call
  sites. No two of them answer the same question via a different implementation.
- **Eleven distinct "get submissions" paths** mapped across mirror/live/focused/PowerGrader/MCP/
  Reports/Work-dashboard consumers — each partitions cleanly by granularity, consumer, or an
  already-established live-fallback/write-boundary pattern. No collapsible duplication found.
- `api/mirror/store.py`, `api/mirror/new_quizzes.py` (beyond the flagged items below),
  `api/course_catalog.py` (beyond the one import), `api/webui/config/` package (beyond the
  roster.py cluster above) — every exported function verified to have a real caller.
  `api/qf_materials/qf` is a sample-content directory (space in the real dirname truncated the
  original brief's path), not code — cleared.

### `api/operation_ledger/recovery.py` — wired in, 2026-07-20 (was flagged, now resolved)

Traced the exact failure mode by reading `claims.py`/`executor.py`/`recovery.py` together:
without recovery running, a crash between sending a Canvas write and recording its result
leaves that target's claim unreconciled. `claims.acquire_claim`'s own docstring says it
"Raises `ClaimConflictError` if the target has any unreconciled claimed record" — so every
later retry (`executor._execute_target:206-213`) hits that conflict and returns
`{"state": "blocked", "error_code": "claim_conflict"}` **without ever reaching Canvas**, forever
— because nothing in production calls `claims.detect_expired_claims()` except `recovery.py`
itself and its tests. This isn't a duplicate-write risk; it's a permanent dead end for that one
operation, fixable today only by hand-editing `operations.json`/`claims.json`.

Wired `recover_pending_operations()` into `api/webui/server.py`'s startup (`_lifespan`),
alongside the other one-shot try/except-guarded bootstrap calls (`workspace.ensure_workspace()`,
`ai_ta.build_library()`), positioned before `_load_custom_routines()`/the heartbeat threads so
any stuck claims are cleared before a scheduled routine could try to claim the same targets.
On a normal run with nothing stuck, this is a single JSON read and an early return — no Canvas
calls happen unless there's an actual `claimed`/`sent_unknown` target to reconcile. Also added an
`operational_log.emit("operation_ledger.recovery", "ok", duration_ms=..., count=...)` call at
the end of the scan, so a recovery event (or the fact that one never ran) is visible in the
existing local diagnostics log (`operations.jsonl`) rather than silent — the visibility this
whole next phase is aiming for. No new tests added (matches this codebase's existing
convention: lifespan wiring itself is untested glue, same as `_load_custom_routines`/the
heartbeat threads); the reconciliation logic itself is unchanged and still fully covered by the
existing `test_operation_ledger.py` suite (30 passed, all three `recover_pending_operations`
call sites exercised the new logging line without error). Full suite: 1093 passed, 1 skipped.

`models.is_terminal_target_state` and `models.validate_target_state_transition` remain
unwired (still zero production callers) — they weren't needed for this fix and are lower
priority; can revisit if a future unit needs target-state guard rails elsewhere.
- **`mirror_reads.py` vs `routine_reads.py::read_scope`**: confirmed genuine implementation
  duplication (both do mirror-first/live-fallback for the same three scopes), but it's a
  deliberately staged migration — `test_routine_reads.py:294-301` pins the current split
  (`grading_debt`/`download` migrated, `sweep`/`curve` not yet) as an explicit non-goal for this
  batch. Not touched. For a future unit: the end state is retiring `mirror_reads.py` by porting
  `routines_builtin.py`'s sweep/curve call sites onto `routine_reads.read_scope` (the more
  general, already-tested replacement), not the reverse.
- **Dead-flexibility parameters, self-documented, low value to touch:** `write_response_snapshot`/
  `write_fetch_snapshot`'s `latest` parameter (`api/mirror/new_quizzes.py`) is computed by both
  callers and immediately discarded (`del latest`) — but the docstring already says so
  explicitly ("accepted for caller compatibility but unused"). Same shape, smaller: 
  `write_quiz_metadata`'s `state=`/`error_code=` and `store.py`'s `write_assignments`/
  `merge_submissions` `state=` parameters are schema-supported but never called with a
  non-default value. Left alone — already self-explanatory, and cutting them means touching
  caller signatures for marginal benefit.
- `storage.upsert_claim` (`api/operation_ledger/storage.py`) — only test callers (9 sites), but
  as fixture-setup scaffolding for tests that verify other real behavior, not as dead-cruft
  coverage. Left alone.
