# Mutation Reconciliation Map

Routing scope: read this only when the active handoff is Batch 6/7 work on
Canvas mutation ownership or targeted reconciliation. It groups
[`docs/contracts/canvas-transport-owners.json`](../contracts/canvas-transport-owners.json)
(the machine authority — every call-level fact, classification, scope, and
reconciliation state lives there, keyed by path + qualified symbol + detector
+ call_index) into the next exact vertical families. This document does not
duplicate those facts; it names which family is already covered and which
gaps are next. **No gap named here is GREEN.**

`api/tests/test_canvas_mutation_ownership.py` enforces the JSON against the
live `api/` tree: any unlisted mutation-shaped call, any stale listed owner,
any duplicate key, or any out-of-vocabulary classification/scope/state fails
the suite.

## Current totals (from the JSON, 2026-07-19)

- **56 owners total.**
- By classification: `canvas_mutation` 44, `canvas_read_acquisition` 5,
  `canvas_upload` 2, `generic_transport_internal` 2, `canvas_mutation_native` 1,
  `diagnostic_probe` 1, `external` 1.
- By reconciliation state: `none` 19, `n/a` 19, `targeted` 7, `invalidate` 11.
- By scope (an owner may touch more than one): `private.submissions` 9,
  `catalog.assignments` 8, `private.groups` 8, `private.assignments` 7,
  `none` 7, `catalog.modules` 6, `focused_evidence` 6, `new_quiz.metadata` 5,
  `gradebook.late_policy` 2, `private.submission_comments` 2,
  `new_quiz.responses` 1. `catalog.assignment_groups`, `private.roster`, and
  `unknown` are currently unused (no live mutation touches them).

## Vertical families

### 1. Grades, comments, and curves (`private.submissions`, `private.submission_comments`)

**Covered (targeted):** PowerGrader's two grade-push owners —
`api/powergrader/session_actions.py push_grades` and
`api/powergrader/autopush_executor.py run_autopush_for_session` — both
converge through `_notify_write_through` in `api/webui/routes/powergrader.py`,
which calls `mirror_service.notify_course_changed` (a narrow per-course
submissions delta refresh). This is the only submissions-scope family with a
real, tested targeted reconciliation path today.

**Gap — no reconciliation:** every grade-curve owner
(`operation_ledger/adapters/curve.py`, `webui/routes/gradebook_curves.py`
(`curve_apply`, `revert_curve`), `webui/routes/routines_builtin.py`
(`_curve_apply_core`)) writes `posted_grade` directly and never calls a mirror
invalidate/refresh function. This is a Former Program 9 exit-gate target:
curves write the exact grade scope PowerGrader already reconciles, so the fix
is likely "point them at the same `mirror_service.notify_course_changed` hook,"
not new machinery.

**Not a gap — late sweep is CanvasExpert-owned:** the late-sweep owners
(`operation_ledger/adapters/sweep.py SweepAdapter.execute` and
`webui/routes/routines_builtin.py _run_routine_sweep`) write
`seconds_late_override` per student, but late-work identification is entirely
internal to CanvasExpert — `work_registry/providers/late_work.py` recomputes
affected students from `due_at`/`submitted_at` with the school-day calculation
and uses the mirror `late` flag only as a prefilter (which the sweep does not
change: it overrides seconds on already-timestamp-late submissions). No mirror
consumer reads `seconds_late_override`, so no submissions-projection
reconciliation is owed. Recorded `n/a`, not a Former Program 9 gap.

**Duplicate implementation — resolved 2026-07-19 (dead ledger path):** the
ledger adapter `operation_ledger/adapters/curve.py` (`gradebook.curve` KIND) is
**dead** — no non-test producer emits that KIND (the generic
`/api/operations/{kind}/prepare` endpoint is only ever called with
`gradebook.sweep` and the content KINDs). The live curve writers are
`webui/routes/gradebook_curves.py` (direct route) and
`routines_builtin.py _curve_apply_core` (scheduled routine); neither reconciles.
Batch 7 wires reconciliation into those two live paths only; Batch 8 retires the
dead ledger adapter (Former Program 10). Do not reconcile the ledger adapter.

### 2. Assignment/Quiz/Module structure (`catalog.assignments`, `catalog.modules`, `new_quiz.metadata`)

**Covered (invalidate):** after each successfully-applied ledger operation,
the central `operation_ledger.catalog_reconcile` hook marks the affected
whole catalog scope stale through `course_catalog.invalidate_scope`. The
kind-to-scope mapping is deliberately conservative: assignments and quizzes
invalidate `catalog.assignments` plus `catalog.modules`, quick assignments
invalidate assignments, and a page invalidates modules only when it has a
module placement. Rubrics and bare pages invalidate no catalog scope. This
whole-scope stale-mark is intentional; Canvas remains truth and the next
catalog refresh refetches the collection. The ownership contract records ten
honest `none` → `invalidate` call-owner transitions for these catalog scopes.
It deliberately leaves `new_quiz.metadata` (including `ensure_item`) and
both rubric owners at `none`; neither has an invalidate in this unit.

**No catalog scope exists (by design, not a gap):** page bodies
(`PageAdapter.execute` create-page call, `RubricAdapter.execute`
create-student-page call) and rubric-body-only creates have no dedicated
catalog scope in the allowed vocabulary — this matches spine 7.1 ("page
bodies are not a 1.0-beta requirement") and is recorded as scope `none`, not
`unknown`.

### 3. Per-student assignment facts (`private.assignments`)

**Gap — no reconciliation:** tier overrides
(`assignment_tiered.py`), quiz overrides (`quiz_steps.py create_override`),
and extension/override adapters (`extension.py`) all create/update Canvas
assignment overrides with no mirror invalidate call.
`webui/routes/gradebook_extensions.py extend_due` (a direct, non-ledger
route) has the same gap. No dedicated scope existed for "effective due
date/override" facts in the locked vocabulary; `private.assignments` is the
closest fit since overrides are inherently per-student, not catalog data —
confirmed against the JSON rather than left `unknown`.

### 4. Groups and membership (`private.groups`)

**Covered (targeted):** the direct webui path —
`webui/routes/roster_canvas.py` (`create_canvas_group`,
`canvas_add_group_membership`, `canvas_remove_group_membership`) and
`webui/routes/roster_groups.py create_group_set` — is reconciled via
`_reconcile_group_category` (`api/webui/routes/roster.py`), which live-merges
the one changed category (`mirror_store.merge_group_category`) and falls back
to a whole-document `invalidate_groups` stale-mark only on failure. This is
the most complete reconciliation family in the codebase today.

**Duplicate implementation — resolved 2026-07-19 (dead ledger path):** the
operation-ledger adapters `operation_ledger/adapters/roster_membership.py`
(`roster.membership`) and `operation_ledger/adapters/roster_group_set.py`
(`roster.group_set`) are **dead** — no non-test producer emits those KINDs. The
live, already-reconciled path is the direct route above. Nothing for Batch 7
here; Batch 8 retires both dead adapters (Former Program 10).

### 5. Gradebook configuration (`gradebook.late_policy`)

**Covered (invalidate):** `webui/routes/gradebook_policy.py
apply_late_policy` calls `mirror_store.invalidate_late_policy` after a
verified apply — a whole-scope stale-mark, not a precise merge, hence
reconciliation state `invalidate` rather than `targeted`.

**Duplicate implementation — resolved 2026-07-19 (dead ledger path):** the
ledger adapter `operation_ledger/adapters/late_policy.py LatePolicyAdapter`
(`gradebook.late_policy` KIND) is **dead** — no non-test producer emits that
KIND. The live path is the direct route above, which already reconciles via
`invalidate`. Nothing for Batch 7 here; Batch 8 retires the dead adapter.

### 6. New Quiz native grading (`new_quiz.responses`, `focused_evidence`)

**Covered (targeted/invalidate mix):** the specialized native item
score/feedback transport (`powergrader/new_quiz_grader.py apply`) converges
through `powergrader.py _converge_new_quiz_after_finalize`, which calls both
`new_quizzes.invalidate_responses` (`new_quiz.responses`, whole-scope
stale-mark) and `_notify_write_through` (`private.submissions`, targeted
delta refresh). This is the only native-mutation owner and it is the only
`canvas_mutation_native` classification in the contract.

**Read-acquisition, not mutation (by design):** the GraphQL preview and
signed-launch handshake calls in `new_quiz_grader.py _signed_context`, the
Student Analysis report-create call in `new_quiz_fetch.py _create_report`,
and the native-file-resolution JWT/launch exchange in
`new_quiz_fetch.py _native_file_transport` all issue HTTP POST but change no
Canvas content — spine 14.3 explicitly protects the report-create call as a
"read acquisition with a Canvas-side generated artifact." Classified
`canvas_read_acquisition`, reconciliation `n/a`, not gaps.

### 7. Uploads, diagnostics, external, and generic transport (expected `none`/`n/a`)

- **Uploads** (`assignment_whole.py upload_course_file`, two calls: the
  `/files` init POST and the follow-up upload-URL POST): scope `none` is the
  documented correct state per spine 14.2 ("never trigger course-wide binary
  refresh"), not a gap.
- **Diagnostics** (`diagnose_newquizzes.py _probe`): classified
  `diagnostic_probe`, scope `focused_evidence`, `n/a` — a standalone auth-probe
  CLI, read-only except one report-enqueue POST.
- **External** (`openrouter_client.py score`): classified `external`, not a
  Canvas write. Listed explicitly (not excluded) because it aliases
  `requests.post` onto a local name (`http_post = requests.post`) rather than
  calling it directly — the scanner has a dedicated alias-assignment detector
  for exactly this shape.
- **Generic transport internals** (`webui/canvas_client.py _canvas_send`,
  `api/canvas.py request`): the shared low-level HTTP call each owner above
  ultimately runs through. Classified `generic_transport_internal` rather
  than silently excluded, per the brief's requirement.
- **Sandbox/demo CLI scripts** (`api/qf_pusher.py`, `api/push_tiers.py`, both
  routed through `api/canvas.py`): these are standalone experimental tools
  with zero CanvasMirror or operation-ledger integration — reconciliation
  `n/a` because no reconciliation concept applies to them, not because
  reconciliation was skipped.

## Batch 7 seeds (named gaps, in priority order)

1. **Submissions/comments** (family 1): wire the two live grade-curve writers —
   `webui/routes/gradebook_curves.py` and `routines_builtin.py _curve_apply_core`
   — to the same `mirror_service.notify_course_changed` targeted refresh
   PowerGrader already uses. The ledger `curve.py` adapter is dead (see family 1)
   — do not reconcile it. The late sweep is out of scope — CanvasExpert-owned
   (`n/a`), not a reconciliation gap.
2. **Catalog structure** (family 2): **covered 2026-07-19** for
   `catalog.assignments` and `catalog.modules` by the central ledger post-apply
   stale-mark hook (ten `none` → `invalidate` contract transitions). Rubric
   library and `new_quiz.metadata` reconciliation remain outside this unit; a
   per-record merge remains a later refinement, not Batch 7 work.
3. **Per-student assignment facts** (family 3): decide the reconciliation
   shape for overrides/extensions (`private.assignments`) — no existing
   invalidate function covers this scope yet.
4. **Resolved 2026-07-19 — no Batch 7 work.** The duplicate ledger adapters
   (`roster_membership.py`, `roster_group_set.py`, `late_policy.py`, and
   `curve.py`) are confirmed dead: no non-test producer emits their KINDs, and
   their live direct-route/routine siblings already exist (groups and late policy
   already reconcile). These are **Batch 8** retirements (Former Program 10), not
   Batch 7 reconciliation targets.

## Batch 8 hygiene note (from the 2026-07-19 dead-path trace)

- Retire the four dead ledger adapters above and remove their contract entries in
  the same change (the ownership test fails on a listed owner no longer present,
  so adapter deletion and JSON pruning must land together).
- The generic `/api/operations/{kind}/prepare` endpoint accepts any registered
  KIND (gated only by `require_local_mutation`, not a kind allowlist). After the
  dead adapters are removed, consider allowlisting the KINDs the UI actually
  submits (`gradebook.sweep`, `content.*`) so a stale KIND cannot be hand-invoked.

No entry in this document is `unknown`-scoped; the JSON contract carries zero
`unknown`-scope owners today (grep it directly rather than trusting this
count if the contract changes).
