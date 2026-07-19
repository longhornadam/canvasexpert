# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** DeepSeek V4 Flash must read `AGENTS.md`,
> `docs/handoffs/CURRENT.md`, and only the references routed by that brief. It must not use
> this file to widen or reinterpret its assignment.

## Current state

Batch 6 is complete (units 01–06 accepted; `6103fca`, `f482042`, `5bc929c`, `ae69f26`,
`047e882`, `1d85660`). **Batch 7 — mutation reconciliation coverage — is now active.** Its
immediate unit is **01 — catalog structure reconciliation** (senior-authored from unit 06's
machine map). The brief in `CURRENT.md` is the sole implementation authority.

## Batch 7 remaining units (author after each acceptance)

Sequenced from the reconciliation map, live paths only (dead ledger adapters are Batch 8):

1. **Catalog structure** (current) — whole-scope stale-mark after ledger assignment/quiz/module
   writes, via a central executor+recovery hook.
2. **Grades/curves** — wire the two live curve writers (`gradebook_curves.py`,
   `routines_builtin.py _curve_apply_core`) to `mirror_service.notify_course_changed`.
3. **Per-student assignment overrides** (`private.assignments`) — decide the reconciliation shape
   for tier/quiz/extension overrides; no invalidate covers that scope yet.

(Late sweep is CanvasExpert-owned `n/a`, not a Batch 7 unit. Groups and late policy already
reconcile on their live routes.)

## Then Batch 8 — transport ownership + beta acceptance

Retire the four dead ledger adapters (`curve.py`, `late_policy.py`, `roster_membership.py`,
`roster_group_set.py`) with their contract entries, consider kind-allowlisting the generic
operations endpoint, then run the full acceptance matrix (spine §19 + §16.1 targets). See the
map's "Batch 8 hygiene note".

## Batch table status

- Batches 0–6: delivered/accepted.
- Batch 7: active; unit 01 (catalog structure reconciliation) is current.
- Batch 8: not started; final beta checkpoint.

---

Overwrite this file—never append—when the senior accepts `CURRENT.md` or changes the
authoritative batch.
