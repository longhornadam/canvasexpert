# Toyota handoff 13a: late-policy operation adapter

## Objective

Migrate course-wide late-policy apply to registered kind `gradebook.late_policy`.

## Files

- New `api/operation_ledger/adapters/late_policy.py`
- `api/webui/routes/gradebook_policy.py`
- `api/webui/static/gradebook/policy.js`
- Gradebook template only for ledger summary hook
- New `api/tests/test_late_policy_operation.py`
- `api/tests/test_gradebook_routes.py`

## Contract

Prepare reloads current Canvas policy, freezes before/after normalized settings, and scopes
one explicit course. Apply detects drift and is idempotent when Canvas already equals the
reviewed target. Receipt stores before/after PRIVATE detail. Reversal is
`restore_snapshot` only when the prior policy was fully captured and the restore endpoint
is proven; otherwise unsupported.

Legacy route remains compatible until migrated UI acceptance. Test no-course, invalid
percentages, drift, already-equal, apply failure, repeat, and reversal truth. Runtime uses
fake Canvas; live-fire needs explicit disposable course authorization.

## Verification and handoff reply

```powershell
node --check api/webui/static/gradebook/policy.js
py -m pytest api/tests/test_late_policy_operation.py api/tests/test_gradebook_routes.py api/tests/test_route_contract.py
git diff --check
```

Stop if current policy cannot be captured completely or drift would be overwritten. One
commit; report hash/files, state matrix, commands/pass counts, receipt/reversal evidence,
runtime console count, and live-fire authorization state.
