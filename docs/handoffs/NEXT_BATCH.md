# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** Batch 7 unit 01 was accepted at `7a703c2`.
> Executor authority for the current unit lives in `CURRENT.md`.

## Current unit

**Batch 7 unit 01r — contract truth reconciliation.** `CURRENT.md` is authored and
READY. A four-pass senior audit (2026-07-19) traced every reconciliation claim to code:
all 18 reconciled claims (11 `invalidate` + 7 `targeted`) are TRUE and `api/`
completeness holds — but three labels are false and must be corrected before more
reconciliation code is built on top of them:

- `gradebook_curves.py` `curve_apply` / `revert_curve`: `none` → `targeted` (they already
  call `notify_course_changed`).
- `rubric.py` `execute` #1: scope `catalog.assignments` → `none` (Course-level bookkeeping
  rubric, no catalog impact).
- `autopush_executor.py` `run_autopush_for_session`: reason text must also name the direct
  `routines_powergrader.py` caller.

01r also adds a guard test asserting no `none`-labeled first-party owner calls a reconcile
function — turning the curve-class mislabel into a build failure. Doc/JSON/test only, no
runtime change.

## Sequence

1. **01r — contract truth reconciliation** (current; `CURRENT.md`).
2. **Unit 02 — Grades/curves (routine path only).** Re-authored slimmer after 01r lands:
   with curves corrected, unit 02 is just the scheduled-routine gap
   (`routines_builtin.py` `_curve_apply_core` / `_run_routine_curve`, still honest `none`)
   plus its coalesced per-course `notify_course_changed` and test. Locked decisions:
   reuse `notify_course_changed`; PowerGrader heartbeat-net failure semantics (no new stale
   flag); reconcile apply and revert; coalesce one refresh per course at end of batch.
3. **Unit 03 — Per-student assignment overrides** (`private.assignments`, family 3):
   decide the reconciliation shape for overrides/extensions (no invalidate function covers
   this scope yet). Verify the "none" gap claims against code first — the audit found the
   map is not reliable ground truth for what is a gap.
4. **Batch 8** — retire the four confirmed-dead ledger adapters (`curve.py`,
   `late_policy.py`, `roster_membership.py`, `roster_group_set.py`); each deletion must also
   remove its `registry.register(...)` line and import, and its contract entry, in the same
   change. Optional scanner hardening (guard against transport-wrapper rename / out-of-`api/`
   Canvas writes).
