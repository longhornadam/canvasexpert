# Toyota handoff 13b1: late-sweep operation adapter

## Objective

Migrate late-sweep corrections to kind `gradebook.sweep` with server-authoritative
recalculation and per-student PRIVATE receipts.

## Files

- New `api/operation_ledger/adapters/sweep.py`
- `api/webui/routes/gradebook_sweep.py`
- `api/webui/gradebook_service.py`
- `api/webui/static/gradebook/sweep.js`
- New `api/tests/test_sweep_operation.py`
- Existing gradebook/schooldays/roster-config tests

## Contract

Client preview rows are display-only. Prepare records range/settings and a preview;
review/apply reruns school-day, calendar, lateness, and extra-time calculations against
current Canvas/roster state. Changed calculations invalidate review. Idempotency uses
course/assignment/student/current override/target digest. Partial results and retry are per
student. Reversal is unsupported unless exact prior lateness overrides are captured and a
restore path is separately proven.

Test weekends, calendars, extra time, stale roster, missing objects, drift, partial,
repeat, retry, and redaction. Live-fire requires explicit disposable targets.

## Verification and handoff reply

```powershell
node --check api/webui/static/gradebook/sweep.js
py -m pytest api/tests/test_sweep_operation.py api/tests/test_gradebook_routes.py api/tests/test_schooldays.py api/tests/test_roster_config.py api/tests/test_route_contract.py
git diff --check
```

Stop if apply must trust client rows or persist identity outside PRIVATE storage. One
commit; report hash/files, calculation/drift/partial/retry results, commands/pass counts,
redaction/receipt evidence, runtime console count, and live-fire authorization state.
