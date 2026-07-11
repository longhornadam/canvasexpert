# Toyota handoff 13e: coordinated routines, Desk state, and receipts

## Objective

Give foreground, background, and launch execution one coordinator and durable outcomes,
without repeated arming or changing machine-local scheduling.

## Files and ownership

- `api/webui/routes/routines.py`, `routines_builtin.py`, `routines_powergrader.py`.
- New/extracted `api/webui/routine_coordinator.py`, sole owner of `_ROUTINES_LOCK` and
  the machine-local atomic run-claim record.
- `_routines_panel.html`, `workbench_base.html`, scoped `routines.js`, Workbench CSS.
- `test_routine_receipts.py`, `test_routine_work_adapter.py`, scheduled PG tests, docs.

Every trigger calls the coordinator. It atomically claims `(routine_id, scheduled_due)`;
claims expire after two hours and are recovered with a redacted Attention record. Two
simultaneous triggers execute exactly once. Enabled is the persistent opt-in; disabled
or not-due checks do not invoke and write no receipt.

An invoked run writes exactly one receipt: `no_effect` when it proves no work, otherwise
applied/partial/failed/blocked. Classify effect from the actual returned result and
domain policy, never `_ROUTINE_DEFS.writes`; scheduled PowerGrader may write only under
its existing per-job opt-in/policy. Foreground/background/launch use identical paths.
Failures and stale/uncertain claims create Work Registry Attention; later success clears
only the matching material version. Custom Python remains isolated and gets no false
generic idempotency promise.

```powershell
node --check api/webui/static/routines.js
py -m pytest api/tests/test_routine_receipts.py api/tests/test_routine_work_adapter.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_route_contract.py
git diff --check
```

Test disabled/not-due, no-effect, effect, partial, exception, stale claim, simultaneous
triggers, all three entry paths, Attention lifecycle, and receipt redaction. Render the
panel through `workbench_base.html` with lifespan off and fake runners only. Stop if any
entry bypasses the coordinator or exactly-once claim cannot be proved. One commit; reply
with hash, trigger matrix, receipt matrix, concurrency evidence, and zero-live-run proof.
