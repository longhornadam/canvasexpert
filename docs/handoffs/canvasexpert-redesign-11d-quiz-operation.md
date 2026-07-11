# Toyota handoff 11d: QuizForge streaming operation adapter

## Objective

Migrate QuizForge whole-class and differentiated pushes into the ledger without losing
streaming progress, subprocess isolation, dry-run validation, or per-course partial truth.

## Files

- New `api/operation_ledger/adapters/quiz.py`
- Adapter registry/executor extensions for progress events
- `api/webui/routes/push_streaming.py`
- `api/webui/routes/push_validation.py` only if review snapshot needs pure validation output
- `api/webui/static/push/quiz.js`
- `api/webui/static/push/core.js` only for operation progress consumption
- New `api/tests/test_quiz_operation.py`
- Existing QuizForge push/route tests

## Contract

Preparation runs existing dry-run/validation and freezes normalized source, settings,
whole/differentiated manifests, and targets. Apply uses a server-owned operation ID; query
strings may not carry arbitrary manifests after migration. Progress is keyed by operation
and target. Subprocess completion produces per-target receipts; lost clients do not cancel
or repeat successful targets. Retry unresolved targets only.

Idempotency must prove how an existing pushed quiz/variant is recognized before live
enablement. Until then, the adapter may remain prepare/review-only and the legacy immediate
path must remain visibly separate—not silently used after “Apply.”

```powershell
node --check api/webui/static/push/quiz.js
node --check api/webui/static/push/core.js
py -m pytest api/tests/test_quiz_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Live-fire requires an explicit disposable-course matrix for whole, differentiated, partial,
disconnect/reconnect, and retry. Stop if deterministic idempotency is unresolved.

## Required implementer reply

One commit; report hash/files, command/pass results, whole/differentiated state matrix,
disconnect/reconnect/partial/retry/idempotency evidence, progress/receipt behavior, console
count, and exact live-fire authorization/results if performed.

Both CourseExpert and standalone Quiz surfaces use the adapter. It is apply-capable only
after returned-ID/postcondition idempotency is proved; otherwise stop rather than ship an
ambiguous prepare-only mode. Persist before send, record the returned quiz ID, and make
timeout/disconnect `sent_unknown` Attention. Same-title matching never proves success or
authorizes retry.
