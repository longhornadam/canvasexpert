# SIS grade bridge — implementation and first three live families

**Status:** APPLY AUTHORIZED — THREE SEQUENTIAL RUNTIME FAMILIES

**Opened:** 2026-09-04

**Execution model:** One implementation executor. The senior accepts against this brief and
returns ordinary corrections to the same executor/context.

## 1. Objective

Deliver one complete assistant-invokable SIS grade-bridge path and use it sequentially for the
first three user-authorized existing differentiated assignment families in one Current Canvas
course. CanvasExpert must discover and freeze each exact family, create the whole-course bridge
when absent, copy only final source grades, make the bridge the sole counted/SIS-enabled family
member, submit the bridge through Canvas's configured SIS grade-passback endpoint, reconcile
local projections, and return a PII-free receipt summary for each independent operation.

The live course and family are supplied only at runtime from the user's local configuration and
conversation. Do not put their names, IDs, assignment titles, rosters, or grade values in source,
tests, fixtures, documentation, logs, or commits.

## 2. Acceptance criteria

1. MCP schema version 32 exposes exactly three new specific tools:
   `list_sis_grade_bridges(course_id)`,
   `preview_sis_grade_bridge(course_id, family_title)`, and
   `apply_sis_grade_bridge(operation_id, batch_id, review_digest)`.
2. Initial preview discovers only exact `<family_title> - <variant>` source titles, performs the
   live invariants in `docs/contracts/sis-grade-bridge-contract.md` sections 2-5, creates and
   freezes one `gradebook.sis_bridge` ledger operation, and returns no student identity or
   per-student grade.
3. Apply follows contract section 6 exactly. Every outbound Canvas mutation has a persisted
   `before_send` marker, an exact postcondition check, an honest failure classification, and a
   machine-checked transport-owner entry.
4. Finalized numeric/excused source rows are copied; pending-review, unsubmitted, uncovered, and
   inactive rows are counted but never converted to scores. Overlapping active memberships,
   mixed points/groups/due dates, title/ID drift, bridge collisions, missing Current-course
   scope, and a changed registered bridge digest fail closed before mutation.
5. On success, source assignments are excluded and SIS-disabled; the bridge is whole-course,
   published, counted, SIS-enabled, and submitted to Canvas grade passback. The student-free
   registration and final bridge-state digest persist in synced settings.
6. Catalog assignment scope is invalidated after successful structural work; successful grade
   writes invoke the existing targeted submissions refresh. No mirror record authorizes a write.
7. Retry/reconcile never duplicates the bridge, never resends an uncertain create or passback,
   and resumes only exact unfinished steps. A standard private ledger receipt is created.
8. The existing 49 MCP tools remain unchanged in schema v31; v32 contains 52 tools and the live
   registry exactly matches it. MCP instructions and `docs/mcp-server.md` explain the one-command
   preauthorization rule without weakening review for unbounded writes.
9. A mocked end-to-end example proves create, 2+ source variants, grade copy, source cutover,
   bridge activation, passback, config registration, receipt, and reconciliation. Focused law
   tests prove overlap refusal, common-due-date refusal, pending-review skip, drift refusal,
   uncertain-create stop, uncertain-passback stop, and PII-free MCP output.
10. After the mocked gate passes, run one live preview against the user-authorized Current course
    and family. The senior-accepted live baseline is three 100-point sources, one common
    date/group, no bridge, no overlap, 25 active students, 24 assigned, one uncovered, 22 eligible
    final, zero pending-review, and two unsubmitted. If it matches, apply the preauthorized cycle.
    Report only aggregate counts and states. If any locked invariant differs, stop YELLOW without
    live writes.
11. After the first family completes, invoke the same preview/apply pair separately for the two
    additional user-authorized runtime families in the same course. Each must independently have
    exactly the three expected differentiated variants, pass every contract invariant, derive its
    own common source due date, and produce its own ledger operation, registration, passback
    acceptance, reconciliation, and receipt. A blocking preview stops only that family; do not
    reinterpret this as a cross-family transaction or invent a shared due date.

## 3. Explicit non-goals

- No Gradebook/Web UI page, button, or browser automation.
- No Forge authoring-flow changes and no automatic bridge creation during quiz/assignment push.
- No multiple-family batch transaction or all-or-nothing rollback; the three authorized families
  are three sequential, independently reviewed ledger operations.
- No percentage scaling, pending-review score copying, direct SIS client, SIS credential, or SIS
  readback claim.
- No repair/adopt flow for an externally edited registered bridge.
- No edits to the user's existing changes under `api/webui/static/push/` or
  `api/webui/static/ui/components.css`.

## 4. Locked design and insertion points

Read `AGENTS.md`, then only:

- `docs/reference/project-state.md`;
- `docs/contracts/sis-grade-bridge-contract.md` sections 1-8;
- `docs/contracts/operation-ledger-contract.md` sections "Boundary and storage" through
  "Invariants and forbidden behavior";
- `docs/reference/operation-ledger-module-map.md`;
- `docs/reference/mutation-reconciliation-map.md` families 1-3;
- `docs/mirror.md` sections "Design laws", "Sync passes", and "MCP reads and the refresh tool";
- `docs/mcp-server.md` sections "Tools", "Scoring Packet Workflow", and "Token-lean results";
- `api/README.md` sections "Web UI", "What each push does automatically", and "Confirmed Canvas
  API facts / limits".

Implementation ownership:

- Add `api/platform_services/config/sis_grade_bridge.py`; re-export it from
  `api/platform_services/config/__init__.py` and add its single settings key to
  `config/_io.py::SYNCED_KEYS`. Store only the contract's student-free mapping and whole-bridge
  digest.
- Add `api/operation_ledger/adapters/sis_grade_bridge.py` with kind
  `gradebook.sis_bridge`; register/export it through both adapter and ledger `__init__.py` files.
  This adapter owns every live Canvas read, mutation, step order, postcondition, retry, and
  reconcile decision for the family.
- Add `api/sis_grade_bridge.py` as the shared assistant-facing use case. It owns list, creation of
  one prepared operation plus frozen batch, validation of opaque apply coordinates, invocation of
  the ledger executor, and PII-free result shaping. Do not call FastAPI routes from MCP.
- Add thin functions/wrappers in `api/mcp_server/tools.py` and `server.py`; bump
  `contract.py::TOOL_SCHEMA_VERSION` to 32 and add immutable `tool_schema_v32.json`.
- Map `gradebook.sis_bridge` to `catalog.assignments` in
  `api/operation_ledger/catalog_reconcile.py`. The adapter invokes the existing
  `mirror_service.notify_course_changed(course_id)` once after confirmed grade writes.
- Update `docs/contracts/canvas-transport-owners.json`, current totals/family text in
  `docs/reference/mutation-reconciliation-map.md`, the adapter map, MCP documentation, and the
  MCP server's shared instructions.
- Tests mirror modules: `api/tests/test_sis_grade_bridge.py`,
  `api/tests/test_sis_grade_bridge_operation.py`, and
  `api/tests/mcp_server/test_sis_grade_bridge_tools.py`; update only the existing schema/ownership
  contract tests needed for v32.

## 5. Required execution details

- Use synthetic course/assignment/student IDs and invented titles in every test.
- The bridge create payload starts unpublished, `omit_from_final_grade=true`, and
  `post_to_sis=false`; use `submission_types=["none"]`, point grading, the frozen group/points/date,
  and no overrides.
- The bridge description must state that it is not the real quiz/assignment, exists only to sync
  the grade, and directs students to open their assigned color-tagged version from the Canvas
  Dashboard or To Do list.
- Step keys are content-free and index-based: `create_bridge`, `copy_grade:<n>`,
  `publish_bridge`, `exclude_source:<n>`, `activate_bridge`, `post_grades`, and
  `register_bridge`. Never put a student ID, title, or grade in a step key or safe result.
- Canvas rejects grade writes to an unpublished assignment. The required order is
  `create_bridge`, `publish_bridge`, `copy_grade:<n>`, source exclusion, activation, passback,
  and registration. The published bridge must remain omitted from final-grade calculation and
  SIS-disabled until every eligible grade write verifies; no source cutover or bridge activation
  may occur before that point.
- Store raw per-student preparation/apply evidence only inside the private ledger baseline.
  `freeze_review` returns aggregate counts and warnings only.
- Only `workflow_state=graded` with a numeric score, or an explicitly excused final row, is
  eligible. A pending-review numeric score remains skipped.
- Exact score comparison uses numeric equality with a small serialization tolerance; status
  comparison is exact. Do not copy submission timestamps or New Quiz item data.
- Grade passback calls `POST /api/v1/courses/<course_id>/post_grades` with only the bridge ID in
  Canvas's documented `{\"assignments\": [<bridge_id>]}` JSON shape.
  A successful Canvas response means `accepted`; do not claim an SIS readback.
- On successful apply, capture the final full bridge-state digest before registering. Future
  preview compares this to the saved digest and blocks external/manual target drift.
- The live validation may read private Canvas data inside the local process, but stdout/chat/report
  contains only counts, workflow-state buckets, boolean invariants, and operation states.

## 6. Preflight and stop conditions

Before writing:

1. Confirm branch `dev` is equal to `origin/dev` and preserve the five known unrelated user edits.
2. Confirm the adapter protocol, Canvas client, MCP schema snapshot, mutation-owner scanner,
   config synced-state owner, and targeted submissions-refresh seam named above still exist.
3. Confirm no live bridge registration exists for the runtime family before the initial live
   preview.

Return RED before implementation if a named seam is absent or its contract contradicts this
brief. Return YELLOW before live apply if the preview differs from acceptance criterion 10, if
the Canvas token cannot create/grade/patch, or if the grade-passback endpoint is unavailable.
Never work around a passback refusal with browser automation.

## 7. Named verification gate

Run:

```powershell
py -m pytest api/tests/test_sis_grade_bridge.py api/tests/test_sis_grade_bridge_operation.py api/tests/mcp_server/test_sis_grade_bridge_tools.py api/tests/test_operation_ledger.py api/tests/test_canvas_mutation_ownership.py api/tests/test_beta075_mcp.py api/tests/test_route_contract.py -p no:randomly -q
py -m compileall -q api/sis_grade_bridge.py api/operation_ledger/adapters/sis_grade_bridge.py api/platform_services/config/sis_grade_bridge.py api/mcp_server
git diff --check
```

Then run the bounded live preview/apply matrix from acceptance criterion 10. Do not run the full
API suite unless focused failures show unexpected coupling.

## 8. Execution result

**Traffic light:** YELLOW. The implementation gate passes and the first family's Canvas grade and
assignment state is fully verified, but Canvas returned an ambiguous internal-server error to the
single corrected passback retry. Registration and central catalog invalidation cannot run without
definitive passback acceptance. Per the locked sequence, the two remaining authorized families
were neither previewed nor mutated.

**Commit:** the single scoped implementation commit containing this result; its resolved hash is
reported in the executor's chat return after creation.

**Changed files:**

- `api/platform_services/config/{sis_grade_bridge.py,__init__.py,_io.py}`
- `api/operation_ledger/{adapters/sis_grade_bridge.py,adapters/__init__.py,__init__.py,catalog_reconcile.py}`
- `api/sis_grade_bridge.py`
- `api/mcp_server/{tools.py,server.py,contract.py,tool_schema_v32.json}`
- `api/tests/{test_sis_grade_bridge.py,test_sis_grade_bridge_operation.py,test_beta075_mcp.py}`
- `api/tests/mcp_server/test_sis_grade_bridge_tools.py`
- `docs/contracts/{sis-grade-bridge-contract.md,canvas-transport-owners.json}`
- `docs/reference/{operation-ledger-module-map.md,mutation-reconciliation-map.md}`
- `docs/mcp-server.md` and this brief
- the preceding completed direct brief was removed so `docs/handoffs/` retains one current brief

**Verification evidence:**

- `py -m pytest api/tests/test_sis_grade_bridge.py api/tests/test_sis_grade_bridge_operation.py api/tests/mcp_server/test_sis_grade_bridge_tools.py api/tests/test_operation_ledger.py api/tests/test_canvas_mutation_ownership.py api/tests/test_beta075_mcp.py api/tests/test_route_contract.py -p no:randomly -q`
  — 72 passed.
- `py -m compileall -q api/sis_grade_bridge.py api/operation_ledger/adapters/sis_grade_bridge.py api/platform_services/config/sis_grade_bridge.py api/mcp_server`
  — passed.
- `git diff --check` — passed.
- The mocked adapter/ownership focus was 20 passed and pins safe publish-before-grade ordering,
  string grade transport, exact `{\"assignments\": [<integer bridge ID>]}` passback shape, one
  description-only in-flight repair, and no duplicate create.
- PII-free first live preview: three 100-point sources, one common group/date, no original bridge,
  no overlap; 25 active, 24 assigned, one uncovered, 22 eligible final, zero pending-review, two
  unsubmitted, zero inactive or other non-final rows.
- Fresh read-only final-state audit: 22 of 22 eligible grades matched with zero read errors; all
  three sources were excluded and SIS-disabled; the bridge was published, whole-course, counted,
  SIS-enabled, override-free, and carried the exact required student-facing description.
- Four standard private blocked receipts exist for the operation's completed attempts.

**Live deviation:** Canvas first rejected grading while the bridge was unpublished, so the durable
protocol now verifies a safe published-but-omitted/SIS-disabled state before grade writes. Grade
transport was aligned with Canvas's documented string form. The first passback attempt then
returned a definite 400 because the mocked scalar payload did not satisfy Canvas's required
`assignments` array. The one senior-authorized corrected retry used the official integer-array
shape and returned HTTP 500 `internal_server_error`; it exposed no job/status ID or URL. Read-only
course and section queries with `include[]=passback_status` returned no passback status, timestamp,
or message, so success or failure cannot be proven and the request must not be resent by guess.
The local registration remains absent and catalog invalidation remains pending. The two later
families have no preview, operation, bridge, or mutation from this execution.

**Unresolved decision:** obtain definitive external Canvas/SIS integration evidence for the
ambiguous corrected passback request. Only after its outcome is known may the same ledger action be
reconciled or explicitly retried; registration and the two remaining independent family cycles
stay blocked until then.
