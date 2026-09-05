# SIS Grade Bridge Contract

Status: accepted product and safety contract.

## 1. Purpose and boundary

An SIS grade bridge projects the final grades from one family of mutually exclusive,
student-differentiated Canvas assignments into one ordinary whole-course Canvas assignment.
The bridge is the only member of the family that counts toward the Canvas final grade and the
only member enabled for SIS grade passback. The differentiated source assignments remain the
student work and evidence surfaces.

CanvasExpert owns the projection and the Canvas writes. It never connects to an SIS directly,
stores SIS credentials, or treats CanvasMirror as mutation authority. The assistant invokes a
bounded CanvasExpert tool; CanvasExpert re-reads and validates live Canvas state, applies through
the Operation Ledger, and asks Canvas to run its configured grade-passback integration.

## 2. Family identity and configuration

A family is course-scoped and has one exact bridge title, an ordered set of exact Canvas source
assignment IDs, and (after creation) one exact bridge assignment ID. Those IDs, the title, and a
digest of the last verified bridge state are student-free configuration and may live in the
synced workspace settings. Raw student IDs, names, grades, statuses, and per-student digests never
enter that settings record.

Initial adoption may discover source assignments only by the exact pattern
`<bridge title> - <non-empty variant label>`. Preparation freezes the exact returned IDs and
titles. Discovery blocks on an exact bridge-title collision, fewer than two sources, a duplicate
normalized source title, or any source outside the selected Current course. After successful
creation, every later run uses the registered IDs; it never rediscovers or retargets by name.

## 3. Required source invariants

Before any write, CanvasExpert must prove from live Canvas that:

- every source is published, graded in points, visible only to overrides, and assigned through
  explicit student overrides;
- all sources have the same points possible, assignment group, and one common effective source
  due date;
- no active student is assigned to more than one source;
- every registered source ID still has its frozen title and belongs to the same course; and
- a registered bridge ID, when present, still names the exact expected assignment.

An active student assigned to no source is a warning and receives no invented bridge score.
Inactive source assignees are ignored. A student assigned to multiple sources blocks the entire
operation. A source with `workflow_state=pending_review` is not final even when it has a numeric
partial score; it is reported and skipped. `unsubmitted` and other ungraded source rows are also
reported and skipped.

## 4. Bridge shape and grade law

The bridge is an ordinary Canvas assignment with:

- the exact family title, no variant suffix;
- the common source points possible, assignment group, and due date;
- `submission_types=["none"]`, point grading, and no assignment overrides;
- whole-course visibility (`only_visible_to_overrides=false`);
- a clear student-facing explanation that the bridge is not the real quiz/assignment and exists
  only to sync the grade, directing students to open the color-tagged version assigned to them
  from the Canvas Dashboard or To Do list; and
- final state `published=true`, `omit_from_final_grade=false`, and `post_to_sis=true`.

Every source's final state is `omit_from_final_grade=true` and `post_to_sis=false`. The bridge is
therefore the sole counted and SIS-synced gradebook item in the family.

For an assigned active student, CanvasExpert copies a final numeric score exactly as points; it
does not scale percentages. An excused final source becomes excused on the bridge. A source's
explicit `late_policy_status` may be copied when Canvas accepts that status on the no-submission
bridge. Submission text, comments, rubric rows, attempts, and New Quiz item scores are never
copied. A blank or non-final source never becomes zero.

## 5. Review and assistant behavior

The assistant-facing surface is three specific tools: list configured bridges, preview one
family, and apply the exact preview. It is not a generic Canvas mutation tool.

Preview performs live reads inside CanvasExpert and returns only assignment-level facts,
aggregate counts, warnings, opaque operation/batch identifiers, and the review digest. It never
returns student names, Canvas/SIS student IDs, or per-student grades. Apply accepts only the
opaque operation ID, batch ID, and review digest produced by preview. The Operation Ledger
revalidates live state and refuses drift before the first write.

A teacher may authorize the complete preview/apply cycle in the same request by naming the
course and family or by explicitly requesting all already-registered bridges. Otherwise the
assistant summarizes the preview before apply. Any blocking problem always stops regardless of
preauthorization.

## 6. Ordered write protocol

Initial creation uses this order:

1. Create the bridge unpublished, excluded from final-grade calculation, and not SIS-enabled;
   persist its returned ID before continuing.
2. Publish the bridge while it remains excluded and not SIS-enabled, and verify that exact safe
   state. Canvas rejects grade writes to an unpublished assignment.
3. Write and verify every eligible final grade/status to the exact bridge ID.
4. Patch and verify every source to excluded-from-final-grade and not SIS-enabled.
5. Patch and verify the bridge to counted and SIS-enabled.
6. Ask Canvas to post that exact bridge assignment to the configured SIS using the documented
   `{\"assignments\": [<bridge_id>]}` JSON body.
7. Persist the student-free registration and the digest of the verified final bridge state.

An update of an existing registered bridge starts at step 3. If the current bridge-state digest
differs from the last verified digest, preparation blocks as an external/manual bridge edit;
CanvasExpert never silently overwrites it. A deliberate repair/adopt workflow is outside this
contract's first implementation.

Each Canvas call is a separate, write-ahead-checkpointed ledger step. An uncertain bridge-create
or grade-passback outcome remains `sent_unknown` and is never resent by guess. Exact assignment
and submission IDs plus exact postconditions are the only reconciliation evidence. A partial
cutover remains visible in Attention and resumes only unfinished, exactly verifiable steps.

## 7. Reconciliation and receipts

Successful assignment create/patch work invalidates the course assignment catalog. Successful
grade writes request the existing targeted per-course submissions refresh. The bridge operation
does not claim that Canvas and the SIS are transactional: a successful Canvas grade-passback
request proves that Canvas accepted the request, not that an inaccessible SIS record was read
back.

Every apply attempt produces the standard private Operation Ledger receipt. Assistant results
expose only content-free step states, aggregate counts, the bridge assignment ID/URL when known,
and Canvas's passback acceptance state.

## 8. Non-goals

- No direct Skyward client or Skyward credential.
- No name-based retargeting after registration.
- No percentage scaling, score invention, or copying a `pending_review` score.
- No generic assistant grade-write tool.
- No browser automation of the Canvas Grade Sync modal.
- No automatic bridge creation in Forge authoring flows in this first implementation.
- No batch transaction across several families; assistants invoke the reviewed pair once per
  configured family.
