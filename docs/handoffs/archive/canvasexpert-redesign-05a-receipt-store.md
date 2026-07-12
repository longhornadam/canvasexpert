# Toyota handoff 05a: machine-local receipt store and read API

## Objective

Implement only the immutable receipt subset of the Operation Ledger Contract. Do not
integrate routines, curve storage, generic operations, or Canvas writes.

## Files and behavior

- New `api/operation_ledger/{__init__,paths,storage,receipts}.py`.
- New `api/webui/routes/receipts.py`; register in `api/webui/server.py`.
- `api/webui/activity.py` may receive only the content-free projection helper.
- New `api/tests/test_receipt_store.py`; update route contract tests.

Resolve `%LOCALAPPDATA%\CanvasExpert\workbench\private` in `paths.py`; tests inject a
temporary root. Implement schema/version validation, process lock, temp+fsync+atomic
replace, quarantine, immutable create, and PII-minimized list projection. Implement
`GET /api/receipts` and local PRIVATE detail GET. Do not describe the app as
authenticated. No mutation route or CSRF mechanism is introduced yet.

Test empty/round-trip/duplicate immutable ID/concurrent create/atomic failure/corrupt and
unknown version/quarantine/list redaction/detail hydration/activity failure independence.

```powershell
py -m pytest api/tests/test_receipt_store.py api/tests/test_route_contract.py
git diff --check
```

Run the receipt GETs with lifespan off and confirm no private content in list/network
logs. Stop if storage resolves into the repository or synced workspace. One commit;
reply with hash, path evidence using a redacted temp root, schema cases, and pass counts.
