# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** Batch 7 unit 01 was accepted at `7a703c2`.
> Executor authority for the current unit lives in `CURRENT.md`.

## Current unit

**Batch 7 unit 02 — Grades/curves (routine path).** `CURRENT.md` is authored, GREEN,
and awaiting accept. Adds one coalesced per-course `notify_course_changed` to
`_run_routine_curve`; contract `_curve_apply_core` `none` → `targeted`. 31-test gate green.

Prior unit **01r — contract truth reconciliation** is ACCEPTED (committed `6f9dbf8`,
archived as `archive/1.0beta-07b-contract-truth-reconciliation.md`): it corrected the false
curve/rubric/autopush labels a four-pass audit found and added the none-label guard test.

## Sequence

1. **01r — contract truth reconciliation** — ACCEPTED (`6f9dbf8`).
2. **Unit 02 — Grades/curves (routine path)** — GREEN, awaiting accept (`CURRENT.md`).
3. **Unit 03 — Per-student assignment overrides** (`private.assignments`, family 3):
   decide the reconciliation shape for overrides/extensions (no invalidate function covers
   this scope yet). Verify the "none" gap claims against code first — the audit found the
   map is not reliable ground truth for what is a gap.
4. **Batch 8** — retire the four confirmed-dead ledger adapters (`curve.py`,
   `late_policy.py`, `roster_membership.py`, `roster_group_set.py`); each deletion must also
   remove its `registry.register(...)` line and import, and its contract entry, in the same
   change. Optional scanner hardening (guard against transport-wrapper rename / out-of-`api/`
   Canvas writes).
