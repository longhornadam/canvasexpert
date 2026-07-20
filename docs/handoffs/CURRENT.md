> **EXECUTOR AUTHORITY.** Read `AGENTS.md`, this file, and only the references routed
> below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

# Correct the Canvas-transport reconciliation contract and make the "none" label self-enforcing

Status: **READY**

Risk: **low** - JSON/doc label corrections plus one new enforcement test. **No runtime code
change.** It corrects three false labels that misdirect planning and adds a test that converts
the most error-prone label ("none" = unreconciled gap) from unverified prose into a machine
check. A senior audit (2026-07-19) traced every reconciliation claim to code: all 18 reconciled
claims (11 `invalidate` + 7 `targeted`) are true, and completeness holds - so this is a
truth-in-labeling repair, not a reconciliation-behavior change.

Depends on: current `dev` (Batch 7 unit 01 accepted at `7a703c2`). This precedes Batch 7 unit 02
(routine curve reconciliation), which will be re-authored slimmer once this lands.

## Teacher-visible result

None directly (internal correctness). Observable evidence: the machine contract stops recording
already-reconciled curve writes as unreconciled gaps and stops tagging a non-catalog rubric
create as a catalog scope; a new test fails if any future `none`-labeled owner actually calls a
reconcile function.

## Acceptance criteria

- [ ] `docs/contracts/canvas-transport-owners.json`: `gradebook_curves.py` `curve_apply` and
      `revert_curve` change `reconciliation` `none` -> `targeted`. Scope stays
      `["private.submissions"]`. Each reason names the real path: an inline
      `mirror_service.notify_course_changed(course_id)` on the success branch
      (`gradebook_curves.py:157` / `:214`) -> `sync.refresh_submissions_course_delta`, the same
      narrow per-course submissions delta refresh PowerGrader uses. The prior `none` reason was
      false ("no mirror invalidate call").
- [ ] Same file: `rubric.py` `RubricAdapter.execute` **call_index 1** (create rubric) changes
      `scopes` `["catalog.assignments"]` -> `["none"]`. `reconciliation` stays `none`. Reason:
      `rf.canvas_rubric_payload` builds a **Course-level** `rubric_association`
      (`association_type: "Course"`, `purpose: "bookkeeping"`; `rf.py:175-178`) with no
      assignment linkage - assignment association is deferred to the `content.assignment` adapter
      (`rubric.py` docstring) - so the create touches nothing in the assignments catalog
      projection. call_index 2 (student page) is already `["none"]`/`none`; leave it.
- [ ] Same file: `autopush_executor.py` `run_autopush_for_session` reason text corrected to
      enumerate **both** reconciling entry points - the three `powergrader.py` wrapper callers via
      `_notify_write_through`, AND the direct scheduled-autoscore caller
      `routines_powergrader.py:295`, which reconciles inline via
      `mirror_service.notify_course_changed` (`:307-310`). `reconciliation` stays `targeted`; no
      scope/classification change.
- [ ] New guard test in `api/tests/test_canvas_mutation_ownership.py`: for every owner with
      `reconciliation == "none"` whose `path` is a first-party served module (exclude the
      standalone sandbox scripts `qf_pusher.py`/`push_tiers.py`, which are `n/a` anyway), assert
      the owner's **enclosing function source** contains no reconcile-call token
      (`notify_course_changed`, `invalidate_`, `merge_group_category`, `_reconcile_`,
      `_notify_write_through`, `refresh_submissions`). A hit means the owner is mislabeled; the
      test fails naming the owner. Reuse the existing AST scan to locate each owner's function
      node and scan its source segment.
- [ ] **Efficacy evidence:** the executor demonstrates the guard test FAILS against the pre-fix
      curve labels (run it before applying the JSON edit, or against a fixture with curves set
      back to `none`) and PASSES after. Report both outputs - a test that only passes post-fix
      does not prove it catches the class.
- [ ] `docs/reference/mutation-reconciliation-map.md` family 1 + Batch 7 seed 1 corrected: the
      direct curve routes (`gradebook_curves.py`) were ALREADY reconciled (`targeted`), not a
      gap; the only real curve gap is the scheduled routine path (`_curve_apply_core` /
      `_run_routine_curve`), still open for unit 02. Recompute the "Current totals" counts from
      the edited JSON (do not hand-edit numbers) so `targeted` becomes 9, `none` 17,
      `catalog.assignments` scope 7, `none`-scope 8. Keep the dead-adapter and late-sweep notes.
- [ ] The named acceptance gate passes, including the existing ownership scan and the new guard.

The executor reports evidence; it does not redefine, narrow, or self-accept these criteria.

## Explicit non-goals

- **No runtime code change.** Add/remove no reconciliation call. The routine curve code gap
  (`_curve_apply_core` / `_run_routine_curve`) is unit 02, not this brief - leave it `none`.
- No change to any correctly-labeled owner, and no classification changes.
- The guard test covers only the `none` -> actually-reconciled direction (the error class found).
  It does not attempt to verify `targeted`/`invalidate` paths (that audit was done manually).
- Do not touch the dead ledger adapters (Batch 8).

## Locked decisions

- Curves are `targeted` (they use the PowerGrader hook, just inline rather than via the helper).
- Rubric create scope is `none` (Course-level bookkeeping association, no catalog impact).
- The guard test enforces the `none`-must-not-reconcile invariant and must be proven to catch
  the curve case, not merely pass after the fix.
- Map totals are recomputed from the JSON, never hand-typed, to prevent re-drift.

## Scope

- `docs/contracts/canvas-transport-owners.json` (curve x2 reconciliation; rubric #1 scope;
  autopush reason text)
- `docs/reference/mutation-reconciliation-map.md` (family 1, Batch 7 seed 1, Current totals)
- `api/tests/test_canvas_mutation_ownership.py` (new guard test)

## Read only these references

- `AGENTS.md`; this brief
- `docs/contracts/canvas-transport-owners.json` (the four entries to edit)
- `api/webui/routes/gradebook_curves.py`: `curve_apply` (~:157) and `revert_curve` (~:214) -
  proof of the `notify_course_changed` success-branch call
- `api/webui/rf.py`: `canvas_rubric_payload` (:147, association block :175-178) and
  `api/operation_ledger/adapters/rubric.py` docstring - proof of Course-level association
- `api/webui/routes/routines_powergrader.py`: `run_autopush_for_session` call (:295) + inline
  reconcile (:307-310)
- `api/tests/test_canvas_mutation_ownership.py` - the existing AST scan to extend
- `docs/reference/mutation-reconciliation-map.md` - family 1, Batch 7 seed 1, Current totals

Do not read: `docs/handoffs/archive/`, unrelated module maps, or the whole 1.0beta spine.

## Preflight - stop if these facts are false

```powershell
rg -n "notify_course_changed" api/webui/routes/gradebook_curves.py
rg -n "association_type|purpose|rubric_association" api/webui/rf.py
rg -n "run_autopush_for_session|notify_course_changed" api/webui/routes/routines_powergrader.py
rg -n "\"reconciliation\": \"none\"" docs/contracts/canvas-transport-owners.json
```

- `curve_apply` and `revert_curve` call `mirror_service.notify_course_changed` on success.
- `rf.canvas_rubric_payload` sets `association_type: "Course"`, `purpose: "bookkeeping"`.
- `routines_powergrader.py` calls `run_autopush_for_session` and then `notify_course_changed`.

If any fact is false, return RED without changes.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_canvas_mutation_ownership.py -q
```

- Include the before/after guard-test evidence (fails on pre-fix curves, passes after).
- No broad matrix; this is a contract/test-only slice.

## Stop conditions

- **RED:** a first-party `none` owner legitimately contains a reconcile token for a *different*
  scope in the same function (heuristic false positive) that cannot be excluded without
  per-scope call-graph analysis - report the owner and the collision instead of weakening the
  test into uselessness.
- **YELLOW:** the existing AST test cannot cheaply expose each owner's function source segment
  for token scanning - report the seam before restructuring the scanner.

## Execution result

**GREEN — 2026-07-19.** All acceptance criteria met. Senior authored and executed
(no external implementer this unit). No commit yet — awaiting accept.

- Changed files: `docs/contracts/canvas-transport-owners.json` (curve_apply +
  revert_curve `none`→`targeted`; rubric execute#1 scope `catalog.assignments`→`none`;
  autopush reason text expanded to name the `routines_powergrader.py` direct caller),
  `docs/reference/mutation-reconciliation-map.md` (family 1 Covered/Gap rewrite, family 2
  rubric note, Batch 7 seed 1, recomputed Current totals), `api/tests/test_canvas_mutation_ownership.py`
  (new `test_no_none_owner_actually_reconciles` guard + `test_synthetic_mislabeled_none_owner_is_flagged`
  proof + `_FunctionSourceCollector`/`RECONCILE_TOKENS` support).
- Before/after guard evidence: pre-fix, `test_no_none_owner_actually_reconciles` FAILED
  naming exactly `gradebook_curves.py::curve_apply` and `::revert_curve`
  (`['notify_course_changed']`) and nothing else — confirming it catches the class and that
  no other `none` owner secretly reconciles. Post-fix it passes.
- Gate: `py -m pytest api/tests/test_canvas_mutation_ownership.py -q` → **9 passed**.
  Broader: `... test_course_catalog.py test_operation_ledger.py -q` → **79 passed**. JSON valid.
- Recomputed totals (from JSON, not hand-typed): reconciliation `none` 17, `n/a` 19,
  `targeted` 9, `invalidate` 11; scope `catalog.assignments` 7, `none` 8. Matches the map.
- Deviations: none. No runtime code changed. No RED/YELLOW hit — no first-party `none` owner
  had a cross-scope reconcile-token collision, so the guard needed no exclusion carve-out.
