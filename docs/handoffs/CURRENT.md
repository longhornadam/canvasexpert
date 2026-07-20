> **EXECUTOR AUTHORITY.** Read `AGENTS.md`, this file, and only the references routed
> below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

# Reconcile the submissions mirror after scheduled-routine curve writes

Status: **GREEN (awaiting accept)**

Risk: **low** - adds one fire-and-forget, self-guarding per-course submission refresh to the
scheduled curve routine, plus one contract label correction and a test. No Canvas write,
transport, read-path, or `notify_course_changed` behavior change; a failed refresh is repaired
by the existing heartbeat exactly as PowerGrader and the direct curve routes already rely on.

Depends on: Batch 7 unit 01r (contract truth-fix, `6f9dbf8`) and unit 01 (`7a703c2`).

## Teacher-visible result

After the scheduled curve routine changes grades, mirror-backed grade reads (Home, reports,
gradebook views) pick up the new scores on the same fire-and-forget + heartbeat path the manual
curve buttons and PowerGrader already use, instead of serving pre-curve scores until the next
full heartbeat happens to run. The manual Apply/Revert curve buttons already did this; their
behavior is unchanged. No new UI.

## Acceptance criteria

- [x] `_run_routine_curve` calls `mirror_service.notify_course_changed(course_id)` exactly once
      per course that curved at least one assignment, after that course's assignment loop
      finishes (coalesced) - never inside `_curve_apply_core`, never per assignment/student. A
      course that curved nothing fires no call; flag (non-apply) mode fires nothing.
- [x] `mirror_service` imported into `routines_builtin.py`; the call is best-effort
      (`try/except Exception: pass`), matching the PowerGrader precedent.
- [x] No new submissions stale-mark; failure handling is fire-and-forget + heartbeat backstop.
- [x] Contract: `routines_builtin.py _curve_apply_core` changes `none` -> `targeted`, reason
      naming the coalesced caller-side `notify_course_changed` -> `refresh_submissions_course_delta`.
- [x] Named acceptance gate passes, including the ownership scan and the unit-01r none-label guard.

## Explicit non-goals

- No change to the manual curve buttons or PowerGrader (already reconciled).
- No new submissions stale-mark, no per-record merge, no read-service change, no change to
  `notify_course_changed` itself.
- Did not touch the dead ledger `curve.py` adapter (Batch 8) or the late sweep (`n/a`).
- Per-student overrides/extensions (`private.assignments`, family 3) remain unit 03.

## Locked decisions

- Reuse `notify_course_changed`; PowerGrader heartbeat-net failure semantics (no new flag);
  reconcile both apply and revert (the direct-route revert was already reconciled in 01r; the
  routine only applies, never reverts, so no routine revert path exists); coalesce one refresh
  per course at end of that course's batch.

## Scope

- `api/webui/routes/routines_builtin.py` (`mirror_service` import; coalesced notify in
  `_run_routine_curve`)
- `docs/contracts/canvas-transport-owners.json` (`_curve_apply_core` `none` -> `targeted`)
- `api/tests/test_routines_builtin_curve.py` (new focused reconciliation test)

## Named acceptance gate

```powershell
py -m pytest api/tests/test_routines_builtin_curve.py api/tests/test_canvas_mutation_ownership.py api/tests/test_mirror_reads_helper.py api/tests/test_gradebook_routes.py -q
```

## Execution result

**GREEN — 2026-07-19.** Senior authored and executed. No commit yet - awaiting accept.

- Changed files: `api/webui/routes/routines_builtin.py` (import `mirror_service`; per-course
  `course_applied` flag; one coalesced `notify_course_changed(cid)` after each course's curve
  batch), `docs/contracts/canvas-transport-owners.json` (`_curve_apply_core` `none`->`targeted`),
  `api/tests/test_routines_builtin_curve.py` (new).
- Gate: `py -m pytest api/tests/test_routines_builtin_curve.py api/tests/test_canvas_mutation_ownership.py api/tests/test_mirror_reads_helper.py api/tests/test_gradebook_routes.py -q`
  → **31 passed**.
- Proven: apply mode curving course A (below floor) and not course B (above floor) fires exactly
  one `notify_course_changed(A)` and none for B; flag mode fires none. `_curve_apply_core` is
  reconciled via its caller (same pattern as PowerGrader autopush), so the none-label guard is
  satisfied and the owner is honestly `targeted`.
- Deviations: none.
