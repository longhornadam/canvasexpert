# PowerGrader Refactor Stage 0: OpenRouter Debug Bug Fix

## Goal

Fix one small existing bug before refactoring: `pg_start()` references `session_id` in the OpenRouter exception path before `session_id` is assigned.

This is a targeted behavior fix. Do not refactor anything in this stage.

## Files To Change

- `api/webui/routes/powergrader.py`

## Exact Instructions

1. Open `api/webui/routes/powergrader.py`.
2. Find `def pg_start(...)`.
3. Inside `pg_start()`, find these initial local variables:

   ```python
   privacy_steps: list[dict] = []
   privacy_artifacts: dict = {}
   ```

4. Immediately after them, add:

   ```python
   session_id = str(uuid.uuid4())
   ```

5. Later in the same function, near the session-building block, remove the existing later assignment:

   ```python
   session_id = str(uuid.uuid4())
   ```

6. Do not move any other code.
7. Do not rename any variables.
8. Do not change response JSON.

## Why This Is Needed

The OpenRouter exception handler calls `_write_openrouter_debug_file(...)` with `session_id=session_id` before the current later `session_id` assignment runs. If OpenRouter scoring raises, the route can fail with `UnboundLocalError` instead of returning the intended debug JSON.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Both tests must pass.

## Acceptance Criteria

- `session_id` is assigned before any OpenRouter error path can use it.
- There is only one `session_id = str(uuid.uuid4())` assignment inside `pg_start()`.
- Existing focused tests pass.
