# PowerGrader Copilot Stage 3: Batch-Specific Import Validation

## Goal

Allow teachers to paste Copilot JSON into a specific batch inside one PowerGrader session.

PowerGrader must validate that Batch 1 results belong to Batch 1, update only matching students, and mark the batch as imported or partial.

## Files To Change

- `api/powergrader/import_results.py`
- `api/webui/routes/powergrader.py`
- tests in `api/tests/`

## Endpoint Strategy

Do not add a new route unless necessary.

Extend the existing route:

```python
@router.post("/api/powergrader/session/{session_id}/import-results")
def pg_import_results(
    session_id: str,
    results: str = Form(""),
    batch_id: str = Form(""),
):
    ...
```

This keeps the route contract stable.

Pass `batch_id` to the helper:

```python
payload, status_code = import_results.import_results_into_session(
    session_id,
    results,
    batch_id=batch_id,
    load_session=_load_session,
    save_session=_save_session,
    vault_factory=_vault,
)
```

## Helper Signature

Update `import_results_into_session(...)`:

```python
def import_results_into_session(
    session_id: str,
    results_text: str,
    *,
    batch_id: str = "",
    load_session,
    save_session,
    vault_factory,
) -> tuple[dict, int]:
    ...
```

If `batch_id` is empty, preserve current behavior exactly.

If `batch_id` is provided, use batch-specific behavior below.

## Batch Lookup

Find batch metadata in:

```python
session.get("copilot_packet", {}).get("batches", [])
```

If `batch_id` is provided but no matching batch exists, return:

```python
{"ok": False, "error": f"Copilot batch '{batch_id}' was not found in this session."}
```

Status code: `200`.

## Expected Keys

Each batch has:

```python
batch["expected_results"] = [
    {"pseudonym": "Sparky McGee", "item_id": "42"}
]
```

Build:

```python
expected_keys = {(row["pseudonym"], str(row["item_id"])) for row in batch["expected_results"]}
```

After parsing results, build:

```python
result_keys = {(row.get("pseudonym"), str(row.get("item_id", ""))) for row in parsed}
```

If any result key is not in `expected_keys`, return a hard validation failure:

```python
{
    "ok": False,
    "error": "Validation failed. These results do not belong to this Copilot batch.",
    "validation": {
        "ok": False,
        "errors": [
            "results[0]: ('Name', '42') belongs to another batch or was not in this batch"
        ],
        "warnings": [],
        "n": len(parsed)
    }
}
```

Do not update session in this case.

## Batch Bundle For Existing Validator

Current `feedback_pipeline.validate_results(parsed, bundle, vault)` warns for every expected student not present. For batch imports, validate against a filtered bundle containing only the batch's expected students.

Create a private helper in `import_results.py`:

```python
def _bundle_for_batch(full_bundle: dict, expected_keys: set[tuple[str, str]]) -> dict:
    ...
```

It should preserve top-level fields and include only student responses whose `(pseudonym, item_id)` is in `expected_keys`.

Call:

```python
bundle_for_validation = _bundle_for_batch(bundle, expected_keys)
verdict = fp.validate_results(parsed, bundle_for_validation, vault)
```

This way missing warnings apply only to the selected batch.

## Updating Students

Keep current re-identification behavior:

```python
rows = fp.reidentify(parsed, vault)
```

Update matching `session["students"]` rows:

- `ai_score`
- `ai_feedback`

Only update resolved rows.

## Batch Status

After a successful batch import, update the matching batch object:

```python
batch["imported_at"] = datetime.now().isoformat(timespec="seconds")
batch["updated"] = updated
batch["last_validation"] = verdict
batch["last_unresolved"] = unresolved_count
```

Set:

```python
if updated >= len(expected_keys) and not unresolved_count:
    batch["status"] = "imported"
else:
    batch["status"] = "partial"
```

Allow re-importing the same batch. Re-import should overwrite AI suggestions for the students included in the pasted JSON and update the batch metadata/log again.

## Import Log

Current import log entry:

```python
session.setdefault("ai_import_log", []).append({
    "ts": ...,
    "updated": updated,
    "validation": verdict,
})
```

Extend it:

```python
{
    "ts": ...,
    "batch_id": batch_id or "",
    "updated": updated,
    "validation": verdict,
}
```

## Success Payload

For batch import success, return:

```python
{
    "ok": True,
    "updated": updated,
    "validation": verdict,
    "unresolved": unresolved_count,
    "batch_id": batch_id,
    "batch_status": batch["status"],
}
```

If no batch_id was provided, preserve the old success shape except adding empty `batch_id` is acceptable only if existing frontend still works.

## Tests To Add

Create or update `api/tests/test_powergrader_packet.py` or create `api/tests/test_powergrader_import_results.py`.

Use fictional names only.

Test 1: batch import updates only matching batch.

- Create a vault.
- Create a safe bundle with 2 students.
- Create a session with `copilot_packet.batches` containing `batch-01` for first student and `batch-02` for second.
- Import first student's result with `batch_id="batch-01"`.
- Assert first student's AI fields updated.
- Assert second student's AI fields unchanged.
- Assert batch-01 status is `imported`.
- Assert batch-02 remains `pending`.

Test 2: wrong batch paste fails.

- Use same setup.
- Paste second student's result into `batch_id="batch-01"`.
- Assert `ok is False`.
- Assert no student AI fields changed.
- Assert batch statuses unchanged.

Test 3: partial batch import.

- Batch has 2 expected results.
- Paste only 1 result.
- Assert `ok is True`.
- Assert status is `partial`.
- Assert validation warnings mention missing result for the second expected key.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_import_results.py
py -m pytest api/tests/test_route_contract.py
```

If the new test file does not exist, omit it from the command.

## Acceptance Criteria

- Existing import behavior still works when `batch_id` is omitted.
- Batch-specific imports reject results from another batch.
- Successful batch imports mark status as `imported` or `partial`.
- The same PowerGrader session accumulates results across batches.
- Route contract remains unchanged.
