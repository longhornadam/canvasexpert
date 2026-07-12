# 11d3: Operation polling endpoint

Status: **completed; reference only.** This file does not authorize new work.

## Objective

Add a single GET endpoint that returns the current target/step states from the
durable operation ledger. This replaces the SSE/event-log/browser-cutover design
with a simple polling approach. The ledger's checkpointed step state is the source
of truth.

## What this is NOT

- No SSE, no event log, no monotonic sequence numbers
- No `asyncio.to_thread` or non-blocking apply
- No browser migration, no legacy route shutdown
- No startup recovery changes (recovery already works, verified in 11b4)

## Implementation

Add `GET /api/operations/{operation_id}/status` to `api/webui/routes/operations.py`.
It returns a PII-minimized projection of the operation's current state:

```json
{
  "operation_id": "op-...",
  "kind": "content.quiz",
  "status": "applying",
  "targets": [
    {
      "target_key": "<hash>",
      "state": "applied",
      "steps": [
        {"step_key": "create_quiz:0", "state": "applied"},
        {"step_key": "create_item:0:1", "state": "applied"}
      ]
    }
  ]
}
```

Rules:
- No course IDs, no returned object IDs, no URLs, no diagnostics, no payloads
- Returns 404 for unknown operation IDs
- Read-only — no claim, no mutation, no Canvas calls
- Existing `list_operations_pii_minimized` pattern is the reference

## Tests

- Unknown operation ID returns 404
- Known operation returns correct status/target/step states
- Response contains no course IDs, object IDs, URLs, or diagnostics
- Endpoint makes no Canvas calls

## Reference pattern

`api/operation_ledger/operations.py::list_operations_pii_minimized` and the
existing `GET /api/operations` route in `api/webui/routes/operations.py`.

```powershell
py -m pytest api/tests/test_operation_routes.py api/tests/test_route_contract.py
py -m pytest api/tests
```
