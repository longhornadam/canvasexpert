# Toyota handoff 05b: curve-event PRIVATE storage relocation

## Objective

Move only curve-event persistence out of `api/webui/` into the machine-local PRIVATE
root established by 05a. Curve/revert behavior must not otherwise change.

## Files and migration

- `api/webui/gradebook_service.py` and its existing curve-event callers.
- `api/operation_ledger/paths.py` (consume, do not redesign).
- `api/tests/test_gradebook_routes.py` and a focused migration test module.

On first access, prefer the new file. If only legacy `api/webui/curve_events.json`
exists: take the same storage lock, copy it to a machine-local
`migration-backups/curve_events.<timestamp>.json`, fsync, verify checksum and schema,
atomically write the new live record, reread and compare, then remove the repo-local
source. Never create a backup/temp file in the repository and never print contents.
If any verification fails, preserve the source, do not switch paths, and return a
redacted migration error. Concurrent first access performs one migration.

```powershell
py -m pytest api/tests/test_gradebook_routes.py api/tests/test_curve_event_migration.py
git diff --check
```

Test new-only, legacy-only, both-present-new-wins, corrupt legacy, checksum/write failure,
concurrent access, and exact curve/revert parity. Stop if legacy data would be deleted
before verified durable replacement. One commit; reply with hash, state matrix, checksums
redacted to prefixes, and confirmation no migration artifact remains under the repo.
