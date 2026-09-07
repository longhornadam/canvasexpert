# SIS Grade Bridges

This guide explains how to operate and recover SIS grade bridges. The
[SIS Grade Bridge Contract](../contracts/sis-grade-bridge-contract.md) is the normative behavior
and safety authority; this guide does not replace it. Current operation status belongs only in the
[active brief](../handoffs/sis-grade-bridge-first-family.md), never in this guide.

## 1. Outcome and family model

A grade bridge turns several mutually exclusive differentiated assignments into one ordinary
whole-course gradebook column. Students keep working in their assigned source version. CanvasExpert
copies eligible final grades to the bridge, excludes the sources from final-grade calculation and
SIS sync, and makes the bridge the only counted and SIS-enabled member of the family.

The exact bridge title names the family. Initial discovery accepts only source titles matching
`<bridge title> - <non-empty variant label>`. For example, an invented bridge named
`Fictional Checkpoint` may discover `Fictional Checkpoint - Amber` and
`Fictional Checkpoint - Teal`. After registration, CanvasExpert uses the frozen assignment IDs and
titles rather than discovering them again by name.

The bridge description tells students that it is not the real quiz or assignment, exists only to
sync the grade, and directs them to open their color-tagged version from the Canvas Dashboard or
To Do list.

## 2. What preview must prove

Every source must be in the selected Current course, published, point-graded, and visible only to
overrides. The family must contain at least two exact sources with one common points value,
assignment group, and effective due date. Active membership may not overlap. A missing active
assignment is reported as an uncovered warning and never becomes an invented score.

One family uses exactly one targeting kind:

- Direct-student targeting requires non-empty `student_ids` assignment overrides.
- A Canvas Differentiation Tag override uses `group_id`. Its Group must resolve in the selected
  course and explicitly return `non_collaborative=true`; its Group Category must also resolve in
  that course. The assignment itself must not be a group assignment, and the complete paginated
  Group membership must be read before review is frozen. Canvas may omit `non_collaborative` from
  the category representation; exact Group-level `true` remains authoritative.

Preview blocks on collaborative groups, section overrides, actual group assignments, mixed target
kinds, incomplete membership, course/category mismatch, active overlap, source identity drift,
duplicate bridge titles, or inconsistent points, group, or due date.

The final bridge shape is the exact family title, the common points/group/date,
`submission_types=["none"]`, point grading, no overrides, and whole-course visibility. Its final
state is published, counted, and SIS-enabled. Every source's final state is excluded and
SIS-disabled.

## 3. Which grades move

Only an assigned active student's final numeric row with `workflow_state=graded`, or an explicitly
excused final row, is eligible. Points are copied exactly; percentages are not scaled. An explicit
late-policy status may be carried when Canvas accepts it.

Pending-review scores, unsubmitted work, uncovered active students, inactive assignees, blanks,
and other non-final rows are counted and skipped. A blank never becomes zero. Submission text,
comments, rubric rows, attempts, timestamps, and New Quiz item scores are not copied.

## 4. Four-tool workflow

| Tool | Use |
|---|---|
| `list_sis_grade_bridges(course_id)` | List student-free registrations for one Current course. An unregistered Attention operation will not appear here. |
| `preview_sis_grade_bridge(course_id, family_title)` | Perform live reads, enforce the family laws, create one private ledger operation, and return only aggregate review plus opaque apply coordinates. |
| `apply_sis_grade_bridge(operation_id, batch_id, review_digest)` | Apply only the exact frozen preview after a live drift check. |
| `confirm_sis_grade_bridge_passback(operation_id, observed_last_sync_at)` | Confirm one otherwise-ambiguous passback from exact teacher-observed Canvas Grade Sync evidence, with no passback resend. |

A teacher who asks for the passback has authorized it: the assistant runs preview and apply and
then reports the source count, aggregate grade-state buckets, warnings, and invariants it saw.
The authorization covers the course and family they named, or all already registered bridges when
they say so explicitly, and does not cover a different family, an unbounded write, or an invariant
failure. An assistant choosing the family itself should summarize the preview first. Confirmation
still requires the teacher's exact evidence; it is never inferred from the original request.

Each family is an independent operation. A failure or Attention state in one family neither rolls
back another family nor authorizes work around the blocked step.

## 5. Ordered write and verification lifecycle

For a new family, apply proceeds in this order:

1. Create the bridge unpublished, excluded from final-grade calculation, and SIS-disabled.
2. Publish it while it remains excluded and SIS-disabled; verify that safe state.
3. Write and verify every eligible grade or excused status.
4. Exclude and SIS-disable every source, verifying each assignment.
5. Activate the bridge as counted and SIS-enabled, and verify its complete shape and description.
6. Request grade passback for only the bridge with
   `POST /api/v1/courses/<course_id>/post_grades` and JSON
   `{"assignments": [<bridge_id as integer>]}`.
7. After accepted or evidence-confirmed passback, save the student-free registration and verified
   bridge-state digest, run central assignment-catalog invalidation, and retain the private receipt.

A registered update starts with grade copying after the saved bridge digest and live family state
verify. Every outbound mutation has a persisted before-send marker and an exact postcondition.
Source cutover and bridge activation cannot begin until all eligible grade writes verify. Grade
writes request the targeted submissions refresh; CanvasMirror data never authorizes a write.

## 6. Passback, Attention, and recovery

A successful Canvas response means Canvas accepted the passback request. It is not proof that
CanvasExpert read the downstream SIS. The operation does not register the bridge until passback is
accepted or confirmed under the contract.

Canvas can return an HTTP 500 after receiving a passback request. That outcome is ambiguous: do
not resend, do not register, and leave the operation in Attention. Do not treat the bridge's safe
Canvas state, a missing registration, or an unrelated course/section status as passback proof.

The only human-evidence recovery is the exact bridge row's teacher-observed Canvas Grade Sync
`Last Sync` timestamp. It must be timezone-aware and at or after that operation's persisted
`post_grades` before-send marker. For example, a synthetic observation such as
`2031-02-03T16:20:00-06:00` is usable only when it came from the exact synthetic bridge row and is
not older than the stored marker.

Before confirmation, inspect the private Operation Ledger through the read-only
`api.operation_ledger.operations.list_operations()` and `get_operation(operation_id)` APIs, or the
application's supported Attention tooling. Keep the returned private baseline out of terminal and
chat output. Verify the exact `gradebook.sis_bridge` operation, one unresolved target, all
structural and grade steps applied, one ambiguous `post_grades` step, pending registration, and the
persisted outbound marker. Never edit ledger files directly. Then call
`confirm_sis_grade_bridge_passback` once with that operation ID and exact timestamp. Confirmation
records student-free evidence, issues zero `POST /post_grades` calls, and resumes only
registration, catalog invalidation, and receipt completion. Missing, approximate, older, or
wrong-row evidence leaves the operation unchanged.

An uncertain create or passback is never retried by guess. Reconciliation may mark a step applied
only from its defined postcondition. Return to the active brief for any Attention state not covered
by exact confirmation evidence.

## 7. Recurring “Update all grades” behavior

“Update all grades” is conversational shorthand, not a scheduler or fifth tool. When the teacher
explicitly requests all already registered bridges, list them and run a separate live preview/apply
cycle for each. Each preview re-reads current Canvas submissions, copies newly eligible final rows,
keeps non-final rows skipped, checks the saved bridge digest, repeats passback for that bridge, and
produces its own receipt. Do not invent a shared due date or a multi-family transaction.

Inspect Attention operations before starting a new preview. Because an Attention family may be
unregistered even though its bridge already exists, absence from `list_sis_grade_bridges` is not
permission to create another bridge. Resume or confirm the existing ledger operation instead.

## 8. Privacy, storage, and read ownership

- Live roster, overrides, tag memberships, submissions, grades, Group/category IDs, and grade
  evidence stay inside the local token-holding process and private Operation Ledger.
- Preview and MCP results expose aggregate counts, warnings, booleans, opaque review coordinates,
  content-free step states, and the bridge reference when known—never a student identity or
  per-student grade.
- Synced bridge registration contains only the course-scoped family/source/bridge mapping and the
  verified bridge-state digest. It contains no roster, membership, submission, or grade evidence.
- The standard receipt is private. Documentation, fixtures, commits, terminal output, and reports
  use only synthetic examples or aggregate, student-free evidence.
- CanvasMirror and the course catalog may support navigation and refresh after a write, but bridge
  preview, drift checks, postconditions, and reconciliation use live Canvas reads owned by the
  Operation Ledger adapter.
- CanvasExpert holds the Canvas credential locally and does not store an SIS credential or call an
  SIS directly.

## 9. Verification commands

For the MCP documentation/schema release gate:

```powershell
py -m pytest api/tests/test_beta075_mcp.py -p no:randomly -q
git diff --check
```

For implementation changes, run the exact named gate in the
[active brief](../handoffs/sis-grade-bridge-first-family.md#7-named-verification-gate), including
its compile check. Link checks must resolve every new relative documentation target from the file
that contains it.

## 10. Future-session continuation checklist

1. Read [`AGENTS.md`](../../AGENTS.md), then the single
   [active brief](../handoffs/sis-grade-bridge-first-family.md).
2. Read this guide's sections 4-10. Read contract sections 5-7 for apply/passback recovery; read
   contract sections 2-7 before changing family validation or write behavior.
3. Treat the active brief's Execution result as the only current-operation pointer. Do not copy
   that state into this guide or reconstruct it from chat.
4. Inspect the private ledger with `operations.list_operations()` and
   `operations.get_operation(operation_id)`, or the supported Attention tooling. Select by exact
   operation identity and kind, keep private baselines out of output, and never open or edit ledger
   storage as a workaround.
5. Never infer or resend passback. Confirm only from the exact teacher-observed Grade Sync row and
   a timezone-aware `Last Sync` at or after that operation's persisted request marker.
6. After confirmation, verify zero passback POSTs during recovery, completed registration and
   catalog invalidation, an applied receipt, and the aggregate Canvas grade/structure
   postconditions.
7. Run the active brief's current gate, update its traffic-light result, and keep runtime titles,
   IDs, names, per-student grades, private paths, credentials, and copied live responses out of
   source control and reports.
