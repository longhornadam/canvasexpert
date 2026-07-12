# Toyota handoff 13c: curve and curve-revert operation adapter

## Objective

Migrate curve apply/revert and legacy curve events to kind `gradebook.curve` with canonical
receipts and explicit drift decisions.

## Files

- New `api/operation_ledger/adapters/curve.py`
- `api/webui/routes/gradebook_curves.py`
- `api/webui/gradebook_service.py`
- `api/webui/static/gradebook/curves.js`
- New `api/tests/test_curve_operation.py`
- `api/tests/test_gradebook_routes.py`

## Contract

Prepare reruns curve math server-side and freezes original/target score snapshots. Apply
detects current-score drift; it must block and require new review, not warn then overwrite.
Per-student results are receipted. Revert is a new reviewed operation restoring captured
originals only when current scores still equal the applied snapshot; otherwise block.

Legacy migrated curve events remain readable but new operations write canonical receipts.
Test all curve models, do-no-harm, drift, partial, repeat, revert availability, double
revert, and redaction. Stop if old behavior must overwrite drift to pass.

## Verification and handoff reply

```powershell
node --check api/webui/static/gradebook/curves.js
py -m pytest api/tests/test_curve_operation.py api/tests/test_gradebook_routes.py api/tests/test_route_contract.py
git diff --check
```

One commit; report hash/files, commands/pass counts, curve-model/drift/partial/repeat/revert
matrix, receipt migration evidence, runtime console count, and live-fire authorization.
