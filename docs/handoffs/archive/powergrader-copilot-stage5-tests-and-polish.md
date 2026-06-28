# PowerGrader Copilot Stage 5: Tests, Copy, And Final Polish

## Goal

Add enough coverage and polish to make the Copilot flow safe for teachers.

This stage should not introduce new architecture. It should harden the flow created in Stages 1-4.

## Files Likely To Change

- `api/tests/test_powergrader_copilot_packet.py`
- `api/tests/test_powergrader_import_results.py`
- `api/tests/test_powergrader_packet.py`
- `api/webui/static/powergrader_queue.js`
- `api/webui/static/powergrader_queue.css`
- `api/webui/templates/powergrader_queue.html`
- `api/powergrader/copilot_packet.py`
- `api/powergrader/import_results.py`

## Required Backend Tests

Run all required tests with fictional names only.

### Test: three files per batch

Assert each batch folder contains exactly:

- one file starting `01 -`
- one file starting `02 -`
- one file starting `03 -`

Do not count the parent README as a batch upload file.

### Test: no ZIP dependency

Assert Copilot metadata has folder/file paths and does not require `packet_zip`.

Legacy `packet_zip` may still exist, but Copilot UI should use batch folders.

### Test: batch statuses

Create a session with two batches:

- Import batch 1.
- Assert batch 1 is `imported`.
- Assert batch 2 remains `pending`.
- Re-import batch 1 with revised feedback.
- Assert feedback updates and batch 1 remains `imported`.

### Test: wrong batch blocked

Paste batch 2's result into batch 1.

Assert:

- response `ok` is false
- error mentions wrong batch
- no AI fields changed
- no batch status changed

### Test: old import still works

Create a session without `copilot_packet`.

Call import with no `batch_id`.

Assert current legacy behavior still works.

## Frontend Static Checks

Run:

```powershell
rg -n -F "{{" api/webui/static/powergrader_queue.js api/webui/static/powergrader_setup.js
rg -n -F "{%" api/webui/static/powergrader_queue.js api/webui/static/powergrader_setup.js
```

Both commands should return no matches.

## Route Contract

If no new route was added, this must remain unchanged:

```powershell
py -m pytest api/tests/test_route_contract.py
```

If a new route was intentionally added, update `api/tests/test_route_contract.py` in the same change and document why in the test comment.

## Full API Tests

Run:

```powershell
py -m pytest api/tests
```

All tests must pass except existing intentional skips.

## Teacher-Facing Copy Requirements

The queue UI must include this exact idea in visible text:

```text
This is one PowerGrader session. Do not start a new PowerGrader session for later batches.
```

Each batch card must communicate:

```text
Start a new Copilot chat for this batch. Upload files 01, 02, and 03 from this folder.
```

Avoid vague phrases like:

- "continue in another session"
- "start another grading session"
- "upload the packet"

Use:

- "batch"
- "same PowerGrader session"
- "fresh Copilot chat"
- "three numbered files"

## Safety/Privacy Copy Requirements

The UI and generated files must not imply Copilot is guaranteed private. Use practical wording:

```text
These files use pseudonyms and remove obvious student identifiers before you upload them. Review the files before sending them to Copilot.
```

Do not say:

```text
FERPA safe
guaranteed anonymous
impossible to identify
```

## Final Manual Smoke Checklist

Use fake/local data only.

1. Start packet mode session.
2. Confirm session creates `copilot_packet`.
3. Open Copilot batch parent folder.
4. Confirm each batch folder has exactly 3 numbered upload files.
5. Open a StudentWork file and confirm it contains pseudonyms, not real names.
6. Queue page shows batch tracker.
7. Copy prompt works.
8. Paste valid JSON into Batch 1.
9. Batch 1 becomes imported.
10. AI suggestion appears on matching student.
11. Batch 2 remains pending.
12. Wrong-batch paste is rejected.
13. Teacher can still approve and push normally.

## Acceptance Criteria

- The Copilot flow is clear enough for a teacher to follow without developer explanation.
- One PowerGrader session tracks all batches.
- Each batch uses exactly 3 numbered upload files.
- Batch import status is visible and persistent.
- Batch validation prevents cross-batch paste mistakes.
- Full API tests pass.
