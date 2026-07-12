# Toyota handoff 11d3: Quiz progress and browser cutover

## Prerequisites and objective

After Ferrari accepts 11d1 and 11d2, add durable PII-safe progress, make long apply
nonblocking to the event loop/lost browser, migrate both Quiz surfaces to `content.quiz`,
and fail-close the old browser live-write routes. One commit. No live Canvas write.

## Durable event contract

Extend operation records with `events` and monotonic `next_event_seq`. Events contain only
`seq`, `created_at`, `target_index`, `step_key`, `state`, and fixed `message_code` from an
allowlist (`step.started`, `step.applied`, `step.skipped`, `step.failed`,
`step.sent_unknown`, `operation.<terminal>`). No target/course/student ID, title, path,
payload/digest, diagnostic, URL, or free text. Bound retained events to 2,000 while sequence
remains monotonic.

Refactor the fenced `ExecutionContext` transaction so `before_send` and `checkpoint_step`
append their event atomically with the step mutation. `_finish_operation` appends one
terminal event and immutable receipt. Add tests for fencing, ordering, truncation, PII
allowlist, and no event on stale claims.

Add PII-minimized `GET /api/operations/{operation_id}/events?after=<seq>` SSE. It replays
stored later events, emits SSE IDs, polls for new events, supports reconnect without
duplication, and closes at terminal status. Unknown IDs are 404; invalid sequence is 400.

Run executor apply/retry via `asyncio.to_thread` (or equivalent supported worker thread) so
SSE remains responsive and browser request cancellation cannot kill the worker. Operation
status/claims fence duplicate apply. App startup invokes recovery; after exact reconciliation
it computes/finalizes recovered operation status, terminal event, and at most one receipt.

## Browser cutover

Modify shared push code and `push/quiz.js`:

- register/use `content.quiz` without routing Quiz through `/api/content/push`;
- whole request is `{mode:"whole",path,settings:<object>}`;
- differentiated request is ordered `{mode:"differentiated",variants:[{path,group_name}],
  settings:<object>}`; no course manifest, group ID, student ID, or Canvas URL;
- `/api/groups` returns only safe category/group IDs, names, and `student_count`; remove all
  student IDs from its browser response and DOM datasets;
- server-frozen review renders whole/differentiated plan, settings, group/count and safe
  extra-time effects;
- after confirmation open operation SSE before/with apply, render fixed-code progress, and
  reconnect from last sequence. Lost UI never cancels/repeats successful work;
- operation list offers `Watch progress` for applying Quiz operations and normal retry only
  for unresolved terminal states;
- printable generation remains a separate local-only post-success action and never changes
  operation truth.

After both surfaces pass runtime tests, change `/api/push/stream`,
`/api/push-multi-whole/stream`, `/api/push-variants/stream`, and `/api/push-multi/stream` to
HTTP 410 PII-safe no-write compatibility responses. Keep `/api/push/preview`, implemented by
the accepted no-network planner. Manual CLI tools remain explicit CLI-only compatibility.

## Tests and runtime acceptance

Test SSE replay/live/reconnect/terminal close, event PII allowlist, responsive concurrent
apply, simulated client cancellation with worker completion, duplicate apply fencing,
startup recovery/final receipt idempotency, safe groups response, whole and differentiated
selected-target envelopes, cancellation/no apply, zero legacy-route calls, four old routes
410/no runner invocation, preview no network, operation-list watch/retry semantics, and
printable post-success only.

```powershell
node --check api/webui/static/push/core.js
node --check api/webui/static/push/quiz.js
py -m pytest api/tests/test_quiz_progress.py api/tests/test_quiz_browser_runtime.py api/tests/test_quiz_differentiated_operation.py api/tests/test_quiz_operation.py api/tests/test_operation_routes.py api/tests/test_operation_ledger.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
py -m pytest api/tests
git diff --check
```

Rendered acceptance is mandatory on `/course-expert` Quiz whole/differentiated modes and
`/push/quiz`: one CSRF/shared script set, safe group counts/no IDs, prepare/review/cancel
with intercepted/fake responses, progress/reconnect rendering, zero legacy call, and zero
new console errors. No Apply against real Canvas.

Stop if events cannot be atomic with checkpoints, apply cancellation can kill the worker,
startup recovery can duplicate receipts, browser group data still needs raw IDs, or legacy
routes cannot be fail-closed without another caller. Report commit/files, event/reconnect/
cancel/recovery matrices, browser request captures, focused/full counts, console count,
configured-workspace nonmutation, and no-live-write confirmation. Do not archive handoffs.
