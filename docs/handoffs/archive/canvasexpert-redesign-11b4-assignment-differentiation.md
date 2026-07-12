# Toyota handoff 11b4: AssignmentForge differentiation

## Objective and commit boundary

Implement the accepted design in `docs/reference/assignment-differentiation-design.md`:
enable canonical AssignmentForge files with `tiers` through the existing
`content.assignment` operation while preserving one target per selected course,
PII-minimized durable state, exact-ID idempotency, partial truth, and shared
Course Expert/standalone review.

One bounded commit on `dev`. Do not archive this handoff. No live Canvas write is
authorized.

## Required architecture

### Safe group resolver

Add `api/operation_ledger/adapters/assignment_groups.py` as the adapter-owned Canvas read
boundary. It uses injected/default `canvas_client._canvas_get_all` calls and
server-owned `config.get_selected_group_category_id(course_id)` to:

1. require a selected category;
2. list its groups from `GET /api/v1/group_categories/{category_id}/groups`, falling back
   on `GET /api/v1/courses/{course_id}/groups` filtered by `group_category_id` when the
   first endpoint is permission-blocked;
3. match every authored group name exactly once after trim/casefold;
4. read accepted memberships from `GET /api/v1/groups/{group_id}/memberships` with
   `filter_states[]=accepted`;
5. read active student enrollments from `GET /api/v1/courses/{course_id}/enrollments`
   with `type[]=StudentEnrollment`, `state[]=active`, and pagination;
6. reject missing/ambiguous/empty groups, overlapping referenced memberships, and any
   roster coverage difference;
7. return a safe snapshot plus a transient mapping of group ID to sorted student IDs.

The safe snapshot is JSON-safe and contains only selected category ID, roster count and
SHA-256 digest, and ordered tier entries `{index,label,group_name,group_id,student_count,
membership_digest}`. The transient student mapping must be stripped before any return
from `capture_baseline`, checkpoint, operation write, receipt, response, or log.

### Assignment adapter

Modify `api/operation_ledger/adapters/assignment.py`:

- `build_payload` accepts validated tiers from `af.tier_payloads(data)` and freezes only
  label, group, title, and description. Tier ordering is source ordering. Reject duplicate
  normalized group names as well as the existing parser's duplicate labels.
- Tier data, dependencies, dates, publish/SIS, and explicit Auto-Score policy participate
  in `source_digest`.
- If tiers are present, reject `rubric_path`. Printable is allowed only if one upload can
  be durably checkpointed once and reused for every tier; otherwise reject that
  combination during build. Do not silently omit a dependency.
- `capture_baseline` stores the safe group snapshot and all existing same-title assignment
  IDs. Before first write, any same-title match is drift. On retry, exact IDs already
  checkpointed under `create_tier_assignment:*` are allowed; any unknown match is drift.
- `freeze_review` adds `tiered=true`, `tier_count`, and safe tier rows with label, group,
  and student count. It explicitly states one Canvas assignment/gradebook column per tier
  and `only_visible_to_overrides=true`.
- Whole-class execution behavior and step keys remain unchanged.

For tiered execute, re-fetch the transient group snapshot and compare its safe projection
exactly to the fresh baseline passed by the executor before any write. For each tier index
in order:

1. Verify a completed `create_tier_assignment:{i}` by exact assignment ID. Otherwise
   persist `before_send`, POST the normal assignment payload with the tier description
   and `only_visible_to_overrides: true`, and checkpoint returned assignment ID/URL.
2. Verify a completed `create_tier_override:{i}` by exact override ID at
   `/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}`. Otherwise
   persist `before_send`, POST one `assignment_override` containing transient
   `student_ids`, a non-identifying title based on the tier label, and common due/unlock/
   lock dates, then checkpoint the override ID. Never persist or diagnose the request body.
3. If `module_name` is set, create/reuse the module once and attach each assignment with
   tier-indexed durable item steps and exact-ID verification.
4. If scheduled Auto-Score is enabled, upsert one job per tier assignment with a
   `schedule_autoscore:{i}` step and deterministic queue job ID. Queue failure after a
   Canvas assignment yields partial and retry must not duplicate the job.

Definitive failure before any successful tier write may be `failed`; definitive failure
after any successful tier step is `partial`; uncertain transport/missing ID is
`sent_unknown`. Stop downstream writes for that target on any non-applied step result.
Top-level target IDs may remain null for tiered targets; the step projection is canonical.

### Safe step receipts/results

Modify `api/operation_ledger/executor.py` so `_receipt_targets` and
`_project_target_results` include a PII-safe ordered `steps` projection with only
`step_key`, `state`, `returned_object_id`, `returned_object_url`, and `error_code`.
Do not expose payload digests, diagnostics, course IDs, student data, or outbound markers.
Preserve existing fields and whole-class compatibility.

### Shared browser review

Modify `api/webui/static/push/core.js` only as needed so a frozen Assignment review lists
every safe tier row and the multi-gradebook-column/visibility warning. Existing
`pushContent("af", ...)` remains the only Assignment call path; do not add a legacy or
parallel endpoint. Update misleading tier availability text in `api/README.md`,
`api/webui/README.md`, and Assignment templates after enablement.

## Required tests

Add focused tests (new `api/tests/test_assignment_tier_operation.py` is preferred) with
temp/private roots and fake Canvas only:

- build/frozen review for 2+ tiers and source-order preservation;
- selected category happy path, permission fallback, exact group-name matching;
- missing selection/group, ambiguous group, empty group, overlap, uncovered/extra member,
  and Canvas read failure all block before any write;
- operation baseline contains no raw student IDs/names and response/receipt projections
  contain only safe counts/digests/step fields;
- successful two-tier order is assignment0, override0, assignment1, override1, with
  `only_visible_to_overrides=true` in each create;
- override requests receive correct transient IDs, but persisted ledger/receipts/logged
  diagnostics do not;
- timeout/missing ID at each POST stops downstream work as `sent_unknown`;
- definitive second-tier failure yields partial and retains first-tier IDs;
- retry verifies exact assignment/override IDs, ignores those known IDs in same-title
  drift, resumes unfinished work, and duplicates nothing;
- unknown same-title assignment blocks retry;
- module and explicit Auto-Score either work per the contract or unsupported combinations
  fail during prepare—never silently disappear;
- whole-class Assignment tests remain unchanged and passing;
- Node runtime/template contract proves safe tier review and no `/api/content/push` call.

## Verification

```powershell
node --check api/webui/static/push/core.js
node --check api/webui/static/push/assignment.js
py -m pytest api/tests/test_assignment_tier_operation.py api/tests/test_assignment_operation.py api/tests/test_operation_routes.py api/tests/test_operation_ledger.py api/tests/test_push_service.py api/tests/test_powergrader_autoscore_queue.py api/tests/test_webui_template_contracts.py
py -m pytest api/tests
git diff --check
```

Rendered fake/no-apply checks are mandatory on `/course-expert` Assignment and
`/push/assignment`: one CSRF meta, shared operation globals, tier review wording, selected
target envelope, and zero new console errors. Do not click Apply against real Canvas.

## Forbidden changes and stop conditions

- No student names/IDs in repo files, ledger, receipts, browser, logs, or diagnostics.
- No group/group-set/membership mutation, local tier fallback, roster splitting, extra-time
  expansion, rubric association, reversal, QuizForge work, or global Auto-Score policy.
- Do not change canonical `LLM_Modules/AssignmentForge_Base.md` unless its current tier
  semantics directly contradict this accepted design; stop and report the contradiction.
- Stop if the selected group category cannot be read without broadening permissions, raw
  IDs cannot stay transient, exact override GET/IDs are unavailable, a required existing
  dependency cannot be made tier-safe without another architecture decision, or a named
  insertion point is absent.

Reply with commit hash/files, write-order matrix, PII-negative evidence, partial/retry/
unknown-title evidence, focused/full counts, rendered console count, configured-workspace
non-mutation, and explicit no-live-write confirmation.

## Ferrari acceptance

Accepted 2026-07-12 after independent review of commit `879d3cc`.

- Focused acceptance suite: 174 passed.
- Full API suite: 604 passed, 1 skipped.
- Safe selected-group resolution, coverage/overlap blocks, ordered tier assignment and
  override writes, module/Auto-Score dependencies, exact-ID retry, and unknown-title drift
  passed with fake Canvas only.
- Restart recovery exact-verifies tier assignments, overrides, module items, and queue jobs
  without authorizing duplicate sends.
- Durable ledger/review/result/receipt projections contain no raw student IDs or names.
- Course Expert locally validated the four-tier fixture; standalone Assignment rendered the
  shared operation path and tier warning. Both routes had zero browser-console errors.
- No target was selected during rendered checks and no live Canvas write occurred.
