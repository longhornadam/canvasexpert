# Toyota handoff 05b: curve-event PRIVATE storage relocation

## Objective

Move only curve-event persistence out of `api/webui/` into the machine-local PRIVATE
root established by 05a. Curve preview, apply, list, revert, reports, and routine
behavior must remain compatible. This slice does not convert curve events into
Operation Ledger receipts and does not add new Canvas calls.

## Why this handoff has an explicit storage seam

05a's receipt store owns the existing process lock and atomic-file mechanics, but its
lock and writer were private implementation details. This slice must expose the small
shared primitives below before using them; do not duplicate a second curve-specific
lock or atomic-write implementation.

## Authorized files

- `api/operation_ledger/paths.py`
  - Add `curve_events_file()` returning the machine-local
    `private/curve_events.v1.json` path.
  - Add `curve_migration_backups_dir()` returning the machine-local
    `private/migration-backups/` directory.
- `api/operation_ledger/storage.py`
  - Preserve all 05a receipt behavior.
  - Add `storage_lock()` as a context manager over the existing `_LOCK`.
  - Add `atomic_write_bytes(path: Path, payload: bytes)` and
    `atomic_write_json(path: Path, document: dict)`. Both create the parent,
    write a same-directory temp file, flush and `os.fsync` it, atomically replace
    the destination, and clean up a temp file after failure. They may safely be
    called while `storage_lock()` is held. No repository or synced-workspace path
    may be used by these helpers.
- `api/webui/gradebook_service.py`
  - Keep `CURVE_EVENTS_PATH` as the legacy repo-local path export for compatibility,
    but never write through it after this slice. Add a clearly named legacy-path
    alias if useful.
  - Make `_load_curve_events()` and `_save_curve_events(events)` the only curve
    persistence wrappers. Their existing list-in/list-out caller contract remains.
  - The new live document is exactly `{"version": 1, "events": [...]}`. Validate
    the version, list type, and required event envelope (`id`, `course_id`,
    `assignment_id`, `applied_at`, `reverted`, and `students`) before use. Preserve
    all existing event fields and student records byte-for-byte at the JSON value
    level; do not redact or reshape curve history in this slice.
- Existing callers in `api/webui/routes/gradebook_curves.py`,
  `api/webui/routes/routines_builtin.py`, and `api/webui/routes/reports.py` may
  receive only mechanical import/path changes. Do not change their Canvas methods,
  response shapes, or curve calculations.
- `api/tests/test_gradebook_routes.py` and new
  `api/tests/test_curve_event_migration.py`.

## Migration state machine

All first-access decisions and writes run under `storage_lock()`:

1. If the new file exists, validate and use it. It wins when the legacy file also
   exists; do not read, delete, or overwrite the legacy file in that case.
2. If neither file exists, return the existing empty event list.
3. If only the legacy `api/webui/curve_events.json` exists, read its bytes and validate
   the legacy shape `{"events": [...]}`. Reject malformed JSON, a non-object root,
   a missing/non-list `events`, or an event missing the required envelope.
4. Before changing the legacy source, atomically copy its exact bytes to
   `migration-backups/curve_events.<UTC timestamp>.json`. Compute a SHA-256 prefix
   in memory and verify the backup has the same checksum.
5. Atomically write the versioned new document, reread it, validate it, and compare
   its `events` value with the validated legacy events. Only after every check passes
   may the legacy repo-local file be deleted.
6. If any read, validation, backup, checksum, write, reread, comparison, or delete
   step fails, preserve the legacy source, do not use the new record created by that
   failed attempt, and surface only the fixed redacted error code
   `curve_event_storage_unavailable` to the existing caller/error projection. Never
   include paths, exception text, checksums beyond a short test-only prefix, names,
   grades, comments, or event contents in logs or responses.

The migration must be safe for concurrent first access in one process: exactly one
thread performs the migration and all callers subsequently read the verified new
file. No backup, temp file, or new live record may be created under the repository.

## Required tests

Test all of the following with a temporary injected PRIVATE root and a temporary
legacy source path; no fixture may contain real student data:

- new-only read and write;
- legacy-only migration, exact event preservation, verified backup, and legacy removal;
- both-present new-wins with legacy untouched;
- malformed legacy, missing events, malformed event envelope, checksum mismatch,
  backup-write failure, new-write failure, reread mismatch, and delete failure;
- source preservation and fixed redacted error on every failed migration;
- concurrent first access with one backup and one resulting live record;
- existing curve apply/list/revert behavior and routine/report readers remain green;
- no curve-event path, backup, temp file, student name, grade, comment, or raw event
  content appears under the repository or synced workspace.

```powershell
py -m pytest api/tests/test_gradebook_routes.py api/tests/test_curve_event_migration.py
git diff --check
```

Run the focused tests plus the route contract tests. Use redacted temporary-root path
evidence only. One commit; reply with hash, state/checksum matrix, concurrency result,
curve/revert parity, and confirmation that no migration artifact remains under the repo.

## Forbidden changes / escalation

- Do not change Canvas endpoints, curve formulas, apply/revert semantics, routine
  enablement, report contents, activity semantics, or Operation Ledger schemas.
- Do not use `storage._LOCK` or `_atomic_write_unlocked` directly from gradebook code;
  use the new named interfaces.
- Do not silently fall back from an invalid existing new file to legacy data.
- Stop and report if the current callers require a changed return type or if a failure
  cannot preserve the legacy source and leave the verified live path unchanged.
