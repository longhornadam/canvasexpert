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
- By reconciliation state: `none` 29, `n/a` 19, `targeted` 7, `invalidate` 1.
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

**Gap — duplicate implementation:** `operation_ledger/adapters/curve.py`
(ledger path) and `webui/routes/gradebook_curves.py` (direct route) both
apply curves independently; neither reconciles. Batch 7 should decide which
one is canonical before wiring reconciliation into both.

### 2. Assignment/Quiz/Module structure (`catalog.assignments`, `catalog.modules`, `new_quiz.metadata`)

**Gap — no reconciliation, uniformly:** every assignment, quiz, page, rubric,
quick-assignment, and module-placement create/patch call in
`operation_ledger/adapters/` (`assignment_whole.py`, `assignment_tiered.py`,
`quick_assignment.py`, `page.py`, `rubric.py`, `quiz_steps.py`,
`module_placement.py`) verifies against live Canvas via `_canvas_get` inside
its own `reconcile()` step, but none calls a CanvasMirror invalidate/merge
function for the catalog projection. This is the largest single Former
Program 9 gap by owner count (19 entries) and the core of the operation
ledger's step-9 debt described in spine 14.1.

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

**Gap — duplicate, unreconciled implementation:** the operation-ledger path
for the identical operations — `operation_ledger/adapters/roster_membership.py`
and `operation_ledger/adapters/roster_group_set.py` — has no mirror
invalidate call at all. Two independent implementations of the same Canvas
writes exist; only one reconciles. Batch 7 should confirm whether the
ledger-path adapters are still live callers or dead code before deciding
whether to delete or reconcile them (Former Program 10 concern, not just 9).

### 5. Gradebook configuration (`gradebook.late_policy`)

**Covered (invalidate):** `webui/routes/gradebook_policy.py
apply_late_policy` calls `mirror_store.invalidate_late_policy` after a
verified apply — a whole-scope stale-mark, not a precise merge, hence
reconciliation state `invalidate` rather than `targeted`.

**Gap — duplicate, unreconciled implementation:** the ledger-path
`operation_ledger/adapters/late_policy.py LatePolicyAdapter` implements the
same `gradebook.late_policy` KIND with no invalidate call. Same
duplicate-implementation question as family 4.

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

1. **Submissions/comments** (family 1): wire grade-curve writes to the same
   `mirror_service.notify_course_changed` targeted refresh PowerGrader already
   uses. Resolve the curve duplicate-implementation question first (ledger
   `curve.py` vs. direct `gradebook_curves.py`). The late sweep is out of scope
   here — it is CanvasExpert-owned (`n/a`), not a reconciliation gap.
2. **Catalog structure** (family 2): the largest gap by count (19 owners).
   Needs a targeted assignment/module/quiz-metadata invalidate or merge
   function analogous to `merge_group_category`, then wiring into each
   adapter's `reconcile()`.
3. **Per-student assignment facts** (family 3): decide the reconciliation
   shape for overrides/extensions (`private.assignments`) — no existing
   invalidate function covers this scope yet.
4. **Groups duplicate implementation** (family 4) and **late-policy
   duplicate implementation** (family 5): confirm live-caller status of the
   ledger-path adapters (`roster_membership.py`, `roster_group_set.py`,
   `late_policy.py`); either delete the dead path (Former Program 10) or
   reconcile it to match its already-working sibling.

No entry in this document is `unknown`-scoped; the JSON contract carries zero
`unknown`-scope owners today (grep it directly rather than trusting this
count if the contract changes).
