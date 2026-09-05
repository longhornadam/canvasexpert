# SIS grade bridge — implementation and first three live families

**Status:** YELLOW — TWO PASSBACK CONFIRMATIONS PENDING

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

1. MCP schema version 33 exposes exactly four specific bridge tools:
   `list_sis_grade_bridges(course_id)`,
   `preview_sis_grade_bridge(course_id, family_title)`, and
   `apply_sis_grade_bridge(operation_id, batch_id, review_digest)`, plus the narrow recovery tool
   `confirm_sis_grade_bridge_passback(operation_id, observed_last_sync_at)`.
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
   Source targeting may be all explicit-student overrides or all verified Canvas Differentiation
   Tag overrides. A tag requires a same-course `non_collaborative=true` Group, same-course resolved
   category, complete paginated membership, and a source that is not a group assignment; section,
   collaborative-group, mixed-target, incomplete, and course-mismatched families fail closed.
5. On success, source assignments are excluded and SIS-disabled; the bridge is whole-course,
   published, counted, SIS-enabled, and submitted to Canvas grade passback. The student-free
   registration and final bridge-state digest persist in synced settings.
6. Catalog assignment scope is invalidated after successful structural work; successful grade
   writes invoke the existing targeted submissions refresh. No mirror record authorizes a write.
7. Retry/reconcile never duplicates the bridge, never resends an uncertain create or passback,
   and resumes only exact unfinished steps. A standard private ledger receipt is created.
8. The existing 49 MCP tools remain unchanged in schema v31; immutable v32 contains 52 tools; v33
   contains 53 tools; and the live registry exactly matches v33. MCP instructions and
   `docs/mcp-server.md` explain the one-command preauthorization and evidence-confirmation rules
   without weakening review for unbounded writes.
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
12. The passback-confirmation tool accepts only an unresolved SIS-bridge operation whose sole
    incomplete outbound effect is passback, validates a parseable teacher-observed `Last Sync`
    timestamp at or after the persisted `post_grades` outbound marker, records student-free
    external evidence, and resumes without issuing `POST /post_grades`. Missing, older, or
    structurally inapplicable evidence fails without ledger mutation. A focused law test proves
    both the no-resend recovery and refusal cases.
13. A focused contract/example test proves exact Differentiation Tag membership resolution and
    grade copying through complete paginated Group membership. Law tests refuse collaborative
    groups, actual group assignments, category/course mismatches, section or mixed target kinds,
    incomplete membership, and active overlap. No Group, category, member, or student identity is
    returned through MCP or persisted in synced bridge registration.
14. Before any push to `dev`, add one canonical `docs/guides/sis-grade-bridges.md` future-session
    guide and route `docs/README.md`, `api/README.md`, `docs/mcp-server.md`, and the Gradebook
    module map to it. The guide must cover the teacher outcome and naming model; source/bridge
    invariants; direct-student and Differentiation Tag targeting; final-grade eligibility; the
    four-tool list/preview/apply/confirm workflow; full write order; preauthorization limits;
    privacy and storage boundaries; mirror/live-read ownership; passback request and honest
    acceptance semantics; the observed HTTP-500/Last-Sync recovery; retry/Attention behavior;
    receipts and registration; recurring `Update all grades` behavior; verification commands;
    and a future-session continuation checklist pointing to this active brief. Examples use only
    invented courses, titles, IDs, counts, and timestamps. No runtime identity, real assignment
    title, per-student value, private path, credential, or copied live response enters the guide.

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
- Add thin functions/wrappers in `api/mcp_server/tools.py` and `server.py`; preserve immutable
  `tool_schema_v32.json`, bump `contract.py::TOOL_SCHEMA_VERSION` to 33, and add immutable
  `tool_schema_v33.json`.
- Map `gradebook.sis_bridge` to `catalog.assignments` in
  `api/operation_ledger/catalog_reconcile.py`. The adapter invokes the existing
  `mirror_service.notify_course_changed(course_id)` once after confirmed grade writes.
- Update `docs/contracts/canvas-transport-owners.json`, current totals/family text in
  `docs/reference/mutation-reconciliation-map.md`, the adapter map, MCP documentation, and the
  MCP server's shared instructions.
- Add the guide and cross-links required by acceptance criterion 14. The contract remains the
  normative behavior authority; the guide explains operation and recovery without duplicating or
  weakening contract rules. Do not add a second architecture contract or a transient run log.
- Tests mirror modules: `api/tests/test_sis_grade_bridge.py`,
  `api/tests/test_sis_grade_bridge_operation.py`, and
  `api/tests/mcp_server/test_sis_grade_bridge_tools.py`; update only the existing schema/ownership
  contract tests needed for v33.

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
- Human passback confirmation is allowed only under contract section 5. It is an evidence-backed
  ledger transition and registration resume, never a second Canvas passback request.
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

**Traffic light:** YELLOW. The implementation and named gate pass. The first family is fully
applied, evidence-confirmed without a passback resend, registered, invalidated, receipted, and
verified. The two later independent families each passed preview, copied and verified every
eligible grade, and reached the exact safe final Canvas assignment state, but each family's one
passback request returned an ambiguous HTTP 500. Neither request was resent; both registrations
and their catalog invalidations remain correctly blocked.

**Commits:** base implementation `d4009008a89050d431da1ed6127b9e414c60851f`; one scoped
follow-up commit contains schema v33 confirmation, Differentiation Tag support, and this result.
Its resolved hash is reported in the executor's chat return after creation because a commit cannot
contain its own hash.

**Changed files:**

- `api/operation_ledger/adapters/sis_grade_bridge.py`
- `api/sis_grade_bridge.py`
- `api/mcp_server/{tools.py,server.py,contract.py,tool_schema_v33.json}`
- `api/tests/{test_sis_grade_bridge_operation.py,test_beta075_mcp.py}`
- `api/tests/mcp_server/test_sis_grade_bridge_tools.py`
- `docs/contracts/sis-grade-bridge-contract.md`
- `docs/reference/{operation-ledger-module-map.md,mutation-reconciliation-map.md}`
- `docs/mcp-server.md` and this brief
- Documentation-only release follow-up: `docs/guides/sis-grade-bridges.md`, `docs/README.md`,
  `api/README.md`, `docs/mcp-server.md`, `docs/reference/gradebook-module-map.md`, and this brief

**Verification evidence:**

- `py -m pytest api/tests/test_sis_grade_bridge.py api/tests/test_sis_grade_bridge_operation.py api/tests/mcp_server/test_sis_grade_bridge_tools.py api/tests/test_operation_ledger.py api/tests/test_canvas_mutation_ownership.py api/tests/test_beta075_mcp.py api/tests/test_route_contract.py -p no:randomly -q`
  — 83 passed.
- `py -m compileall -q api/sis_grade_bridge.py api/operation_ledger/adapters/sis_grade_bridge.py api/platform_services/config/sis_grade_bridge.py api/mcp_server`
  — passed.
- `git diff --check` — passed.
- The focused adapter gate was 22 passed and pins safe publish-before-grade ordering,
  string grade transport, exact `{\"assignments\": [<integer bridge ID>]}` passback shape, one
  description-only in-flight repair, no duplicate create, complete paginated Differentiation Tag
  membership and grade copying, and refusal of every locked unsafe tag-target case.
- Schema checks preserve v31 at 49 tools and immutable v32 at 52 while the live v33 registry has
  53. Passback confirmation tests prove strict timestamp/evidence checks and zero resend.
- Documentation gate: `py -m pytest api/tests/test_beta075_mcp.py -p no:randomly -q` — 6 passed;
  `git diff --check` — passed; added-document-link path check — 10 checked, zero missing.
- PII-free first live preview: three 100-point sources, one common group/date, no original bridge,
  no overlap; 25 active, 24 assigned, one uncovered, 22 eligible final, zero pending-review, two
  unsubmitted, zero inactive or other non-final rows.
- Fresh read-only final-state audit: 22 of 22 eligible grades matched with zero read errors; all
  three sources were excluded and SIS-disabled; the bridge was published, whole-course, counted,
  SIS-enabled, override-free, and carried the exact required student-facing description.
- The evidence-confirmation issued zero passback POSTs and completed the first registration,
  assignment-catalog invalidation, and applied receipt.

**Historical transport deviations:** Canvas first rejected grading while the bridge was
unpublished, so the durable protocol now verifies a safe published-but-omitted/SIS-disabled state
before grade writes. Grade
transport was aligned with Canvas's documented string form. The first passback attempt then
returned a definite 400 because the mocked scalar payload did not satisfy Canvas's required
`assignments` array. The one senior-authorized corrected retry used the official integer-array
shape and returned HTTP 500 `internal_server_error`; it exposed no job/status ID or URL. Read-only
course and section queries with `include[]=passback_status` returned no passback status, timestamp,
or message, so success or failure cannot be proven and the request must not be resent by guess.
The teacher's exact post-request Last Sync evidence later confirmed acceptance without a resend.

**PII-free later-family aggregate:**

- Family 2: three verified tag-target sources; 25 active/assigned, zero uncovered/overlap/inactive,
  23 eligible final, zero pending-review/other, and two unsubmitted. Its independently derived
  common due date/group passed. The one passback POST followed 23 of 23 verified grades and the
  complete structural cutover, then returned HTTP 500. One private receipt exists; registration
  and catalog invalidation did not run.
- Family 3: three verified tag-target sources; 25 active/assigned, zero uncovered/overlap/inactive,
  20 eligible final, zero pending-review/other, and five unsubmitted. Its independently derived
  common due date/group passed. The one passback POST followed 20 of 20 verified grades and the
  complete structural cutover, then returned HTTP 500. One private receipt exists; registration
  and catalog invalidation did not run.
- For both tag families, complete membership resolved to aggregate variant counts 11/5/9 with no
  overlap or uncovered active student. All Groups and categories resolved in the selected course,
  every Group explicitly returned `non_collaborative=true`, no source was a group assignment, and
  the category-level flag was absent as permitted by the contract. All three sources and the safe
  whole-course bridge, including the required description, passed a fresh read-only audit.

**Follow-up live deviation:** both later independent passback requests returned the same ambiguous
HTTP 500 after Canvas state and grades had verified. Each ledger contains one persisted outbound
marker, a blocked passback step, pending registration, and no resend. No runtime identity or
per-student grade value entered source, tests, docs, logs, configuration, or this result.

**Unresolved decision:** obtain exact post-request Canvas Grade Sync Last Sync evidence separately
for each blocked bridge. If supplied, criterion 12 permits confirming each existing operation and
finishing registration/catalog invalidation without another passback POST. Without that evidence,
both operations must remain stopped.

**Documentation release gate:** passed. The canonical guide covers acceptance criterion 14 and is
linked from all four routed documents. The contract remains normative; the guide contains only
synthetic examples and generic future-session operation/recovery guidance. No code, schema, or test
file changed in this documentation pass. One scoped documentation commit contains this release
gate; its resolved hash is reported in chat because a commit cannot contain its own hash. Nothing
was pushed.

**Current continuation state:** the first operation is complete. Two independent operations have
verified Canvas structures and grades and remain in Attention pending each exact bridge row's
teacher-observed post-request Last Sync evidence. No passback resend is authorized or needed for
confirmation.
