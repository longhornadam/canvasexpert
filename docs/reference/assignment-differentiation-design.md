# AssignmentForge differentiation design

**Origin:** Historical 11b4 discovery
**Decision date:** 2026-07-12
**Status:** Implemented design reference; the former 11b4 handoff is archived.

## Existing path and product constraint

`api/webui/af.py::tier_payloads(data)` produces one variant per authored tier with a
label, Canvas group name, common student-visible title, and a tier-specific description.
The description may replace the base description or append the authored scaffolding
panel. Because Canvas assignment overrides cannot vary an assignment description,
AssignmentForge differentiation requires **one Canvas assignment per tier**.

The legacy `api/push_tiers.py` proves the broad Canvas shape for quizzes—create an
assignment-backed object, create an ad-hoc student override, and set
`only_visible_to_overrides`—but it is not reusable operation-ledger code. It writes
student IDs into manifests/state and uses the CLI Canvas client. It must not be called by
the Assignment adapter.

Canvas officially supports `assignment[only_visible_to_overrides]` on assignment create
and `assignment_override[student_ids][]` on override create. The latter is the compatible
shape for ordinary, non-group assignments; `group_id` is not assumed because Canvas
documents it for group assignments/differentiation-tag configurations. Sources:

- <https://developerdocs.instructure.com/services/canvas/resources/assignments>
- <https://developerdocs.instructure.com/services/canvas/resources/groups>

## Locked decisions

### State and target ownership

- One `content.assignment` operation remains one target per selected Canvas course.
- A course target owns ordered tier substeps. Tiers are not separate operations or
  top-level targets because selection, review, drift, partial truth, and retry are
  course-scoped.
- Step keys are stable by authored tier index: `create_tier_assignment:{index}` and
  `create_tier_override:{index}`. Optional module and Auto-Score dependencies use the
  same index suffix.
- The safe receipt/result projection includes step key, state, returned object ID/URL,
  and error code so every created tier assignment/override remains visible without
  exposing student IDs.

### Group authority and preparation

- Canvas groups are authoritative. The selected group category comes from
  `config.get_selected_group_category_id(course_id)`, which is teacher-controlled in
  Roster. The browser does not submit a category or student list.
- The adapter never creates group sets, groups, or memberships. Missing configuration or
  groups blocks preparation and directs the teacher to Roster.
- Each authored `tier.group` must match exactly one group name, case-insensitively, within
  the selected category. Matching outside that category is forbidden.
- Preparation reads active student enrollments and accepted group memberships, then
  blocks unless every referenced group is nonempty, referenced memberships do not
  overlap, and their union exactly covers the active-student roster.
- The durable baseline stores category/group IDs, labels/names, counts, and deterministic
  membership/roster digests only. Raw student IDs and names are never stored in an
  operation, review, receipt, diagnostic, log, fixture, or repo file.
- Apply re-fetches transient student IDs, recomputes the safe snapshot, and requires an
  exact match to the frozen snapshot before the first write. Membership drift blocks.

### Canvas write order and safety

Each tier assignment is created with `only_visible_to_overrides: true` in the initial POST,
so a tier with no override stays invisible to students. The exact ordered write steps per
tier (create assignment, persist ID, create ad-hoc override, module attach, optional
Auto-Score job) live in `api/operation_ledger/adapters/assignment_tiered.py` — treat that
adapter as authoritative rather than duplicating the sequence here.

Printable upload remains supported only when the existing adapter can reuse one confirmed
file upload safely across all tier descriptions; otherwise preparation must fail closed
with an explicit unsupported-combination error. Rubric association remains outside 11b4.

### Idempotency, drift, and retry

- Same-title matching never proves success and never supplies a returned ID.
- Before the first write, any pre-existing same-normalized-title assignment blocks the
  target, preserving the existing whole-class invariant.
- After partial execution, exact assignment and override IDs from durable steps are the
  only success proof. Known step IDs are excluded from same-title drift; unknown matches
  still block.
- Timeout/disconnect or missing returned IDs are `sent_unknown` and stop downstream work.
- A definitive failure after any earlier tier step succeeded yields target/operation
  `partial`. Retry verifies every completed exact ID and resumes the first unfinished
  step without duplicating assignments, overrides, module items, or queue jobs.
- Reversal remains unsupported; deleting tier assignments after submissions is not
  authorized.

### UI semantics

Server-frozen review shows the selected course, common assignment settings, and every
tier's label, group name, and student count. It warns that Canvas will create one
gradebook assignment per tier and that only that group's students can see each assignment.
No student identity is rendered. Both Course Expert and standalone Assignment use the
existing shared operation gateway.

## Explicit exclusions

- No group/group-set/membership creation or mutation.
- No local roster tier fallback, automatic roster splitting, or client-supplied IDs.
- No extra-time expansion in this slice; existing extension operations remain separate.
- No assignment-rubric association or tier deletion/reversal.
- No live Canvas write without a separately authorized disposable-course matrix.
