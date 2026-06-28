# PowerGrader Refactor Stage 4: Extract Session Mutation Workflows

## Goal

Move AI result import, grade-save, and Canvas push mutation logic out of `api/webui/routes/powergrader.py`.

Routes should parse form values and return `JSONResponse`. Business logic should live in `api/powergrader/`.

## Files To Change

- `api/webui/routes/powergrader.py`

## Files To Create

- `api/powergrader/import_results.py`
- `api/powergrader/session_actions.py`

## Create `import_results.py`

Create this function:

```python
def import_results_into_session(
    session_id: str,
    results_text: str,
    *,
    load_session,
    save_session,
    vault_factory,
) -> tuple[dict, int]:
    ...
```

Return:

- `(payload, status_code)`
- Use status code `200` for normal success/failure payloads.
- Use status code `404` only when the session is missing, matching current route behavior.

Move the current body logic from `pg_import_results()` into this helper.

Preserve all current response payloads exactly:

- Missing session:

  ```python
  {"ok": False, "error": "Session not found."}
  ```

- Empty paste:

  ```python
  {"ok": False, "error": "Paste the AI result JSON first."}
  ```

- Missing safe bundle:

  ```python
  {"ok": False, "error": "Safe AI Packet student response bundle is missing."}
  ```

- Parse error:

  ```python
  {"ok": False, "error": f"Could not parse JSON: {e}"}
  ```

- Validation failure:

  ```python
  {
      "ok": False,
      "error": "Validation failed. Fix the JSON and paste again.",
      "validation": verdict,
  }
  ```

- Success:

  ```python
  {
      "ok": True,
      "updated": updated,
      "validation": verdict,
      "unresolved": unresolved_count,
  }
  ```

Important dependencies:

```python
import json
import os
from datetime import datetime

import feedback_pipeline as fp
```

## Create `session_actions.py`

Create:

```python
def save_grade(
    session_id: str,
    *,
    user_id: str,
    teacher_score: str,
    teacher_feedback: str,
    status: str,
    load_session,
    save_session,
) -> tuple[dict, int]:
    ...
```

Move the current body logic from `pg_grade()` into this helper.

Preserve:

- Score parsing.
- Empty score means `None`.
- Invalid score error text: `"Invalid score value."`
- Valid statuses: `"approved"`, `"skipped"`, `"pending"`.
- Invalid status falls back to `"approved"`.
- Missing student error text.
- Success payload: `{"ok": True, "approved": approved}`.

Also create:

```python
def push_grades(
    session_id: str,
    *,
    user_ids: str,
    load_session,
    save_session,
    canvas_send,
) -> tuple[dict, int]:
    ...
```

Move the current body logic from `pg_push()` into this helper.

Preserve:

- Empty `user_ids` means all approved and not posted.
- Non-empty `user_ids` is JSON.
- Invalid JSON error text: `"Invalid user_ids JSON."`
- Payload structure sent to Canvas.
- Error text for empty payload:

  ```python
  f"{st['real_name']}: nothing to push (no score or feedback)."
  ```

- Marking successful students with `posted = True` and `status = "posted"`.
- Appending `push_log` only if there are pushes or errors.
- Success payload shape: `{"ok": not errors, "pushed": pushed, "errors": errors}`.

Important dependencies:

```python
import json
from datetime import datetime
```

## Update Routes

In `api/webui/routes/powergrader.py`:

1. Import:

   ```python
   from powergrader import import_results, session_actions
   ```

2. Replace `pg_import_results()` body with:

   ```python
   payload, status_code = import_results.import_results_into_session(
       session_id,
       results,
       load_session=_load_session,
       save_session=_save_session,
       vault_factory=_vault,
   )
   return JSONResponse(payload, status_code=status_code)
   ```

3. Replace `pg_grade()` body with:

   ```python
   payload, status_code = session_actions.save_grade(
       session_id,
       user_id=user_id,
       teacher_score=teacher_score,
       teacher_feedback=teacher_feedback,
       status=status,
       load_session=_load_session,
       save_session=_save_session,
   )
   return JSONResponse(payload, status_code=status_code)
   ```

4. Replace `pg_push()` body with:

   ```python
   payload, status_code = session_actions.push_grades(
       session_id,
       user_ids=user_ids,
       load_session=_load_session,
       save_session=_save_session,
       canvas_send=_canvas_send,
   )
   return JSONResponse(payload, status_code=status_code)
   ```

5. Keep route function names and decorators unchanged.

## Do Not Do

- Do not change frontend JavaScript.
- Do not change endpoint paths.
- Do not change response JSON.
- Do not change Canvas payloads.
- Do not remove compatibility aliases from earlier stages.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Both tests must pass.

## Acceptance Criteria

- `pg_import_results()`, `pg_grade()`, and `pg_push()` are thin wrappers.
- Mutation behavior is preserved.
- Existing focused tests pass.
- Route contract unchanged.
