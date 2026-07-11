# Toyota handoff 10r: operation-ledger acceptance repair

## Objective

Repair the accepted-design deviations found during Ferrari review of slice 10. Preserve
the existing `content.page` product behavior and public routes while making multi-step
execution crash-safe, recovery truthful, and claim/storage coordination process-safe.

One bounded implementation commit. Do not begin slice 11 work in this commit.

## Authoritative decisions

The amended `docs/reference/operation-ledger-design.md` is authoritative. In particular:

- `target.baseline` remains the immutable review-time baseline. Additive
  `target.apply_baseline` stores the apply-time read; do not replace `baseline`.
- Every Canvas mutation step is durably marked `claimed` with
  `outbound_started_at` before sending. A successful response is checkpointed before the
  next Canvas call.
- An ambiguous outbound step is never reset to `pending` merely because a later GET does
  not find its effect. Absence after a possibly-sent create is not proof of absence.
- A different PID is not evidence that a worker died. An unexpired claim always blocks.
  Expiry permits recovery, not blind resend. A superseded worker is fenced from persisting
  a late result.
- A target is `applied` only when every required step is proven applied or idempotently
  skipped. A page ID alone does not prove module placement.

## Exact files and interfaces

### Process-safe document mutation

- Add `api/operation_ledger/file_lock.py` with context manager
  `interprocess_lock(path: pathlib.Path)`. Use only the standard library:
  `msvcrt.locking` on Windows and `fcntl.flock` on POSIX. Lock one initialized byte and
  always unlock/close in `finally`.
- Add `ledger_lock_file()` to `api/operation_ledger/paths.py`, adjacent to the ledger
  JSON documents. One lock owns both documents; separate per-document locks are
  forbidden because claim fencing must be atomic with the target checkpoint.
- In `api/operation_ledger/storage.py`, retain the module `RLock`, then acquire the
  ledger interprocess lock around every operations/claims read-modify-write. Add
  `modify_ledger(mutator)`, which supplies both documents under that one lock. Plain
  reads may continue relying on atomic replacement.
- Rewrite `api/operation_ledger/operations.py:update_operation` to perform one
  `storage.modify_operations` transaction. The current separate `find_operation` then
  `upsert_operation` sequence is forbidden.

No new package or requirements entry is allowed.

### Execution checkpoints and fencing

- In `api/operation_ledger/executor.py`, add `ExecutionContext`, constructed only by
  `_execute_target`, with exact methods:
  - `before_send(step_key: str, payload_digest: str) -> dict`
  - `checkpoint_step(step: dict, *, returned_object_id: str | None = None,
    returned_object_url: str | None = None) -> dict`
  - `has_outbound_started() -> bool`
- Both mutation methods use `storage.modify_ledger` to verify that `claim_id` is still
  the current claim and update the target while holding the same ledger lock. If not,
  raise `LostClaimError` without changing operation state.
- `before_send` upserts the named step as `claimed`, records the current `attempt_id`,
  `payload_digest`, and `outbound_started_at`, and flushes before the adapter sends.
- `checkpoint_step` replaces that step and persists any returned target object ID/URL.
  It must flush before another Canvas request is allowed.
- Extend `registry.OperationAdapter.execute` to accept the context as its final argument:
  `execute(payload, target, apply_baseline, claim, context)`.
- `_execute_target` stores fresh state under `apply_baseline`, leaving `baseline`
  unchanged. It catches ordinary `Exception` from adapter execution:
  - before any outbound marker: persist `failed`, `error_code="adapter_exception"`;
  - after any outbound marker: persist `sent_unknown`,
    `error_code="adapter_exception_after_send"`.
  Store only the exception class name as PRIVATE diagnostic; never log or return the
  exception message. Release the current claim after the durable result. Continue other
  targets and always derive final status/write a receipt.
- A `LostClaimError` must not overwrite recovered target state. Return a minimized
  `sent_unknown` result for aggregation and leave the durable target untouched.

### Claim and recovery rules

- In `api/operation_ledger/claims.py`, remove PID inequality from
  `_is_claim_expired`. Expiry is determined by a valid elapsed lease; malformed lease is
  expired/fail-closed.
- `acquire_claim` must reject every existing `claimed` claim whose lease has not expired.
  It must also reject an expired-but-unreconciled claim; only recovery may mark that claim
  `expired` before a new attempt.
- Add `is_current_claim(claim_id, target_key, operation_id) -> bool`; it returns true only
  for the matching claim in state `claimed` and is used by `ExecutionContext` fencing.
- In `api/operation_ledger/recovery.py`, skip targets with an unexpired active claim.
  For an expired claim, atomically mark it expired, then reconcile. Never reconcile an
  active worker merely because its PID differs.

### PageForge step state machine

Edit `api/operation_ledger/adapters/page.py`; do not move Canvas ownership elsewhere.

Required step keys and order:

1. `create_page`
2. `create_module` only when the requested module does not already exist
3. `attach_module` when module placement was requested

For each Canvas POST, call `context.before_send(...)`, send, then immediately call
`context.checkpoint_step(...)` with the returned exact ID before proceeding. Capture the
module-item response ID instead of discarding it. Existing exact returned IDs are checked
and skipped; applied steps are never resent.

Replace `_find_or_create_module_id` with separated read and write helpers so module
creation cannot occur behind an uncheckpointed helper. More than one normalized exact
module-name match is ambiguous and blocks without writing.

`PageAdapter.reconcile` must inspect the stored steps:

- Exact page slug proves only `create_page`.
- Exact stored module ID proves only `create_module`/module selection.
- Exact stored module-item ID proves `attach_module`.
- If the attachment response ID was lost, one item in the exact stored module whose type
  is `Page` and whose `page_url` equals the exact stored page slug is an allowed
  adapter-specific postcondition; persist its item ID.
- Same-title page/module matching never proves ownership.
- If an outbound marker exists and neither exact ID nor the allowed attachment
  postcondition proves the effect, return `sent_unknown`, not `pending`.
- Return target `applied` only after all required steps are proven. Return `pending` only
  when no mutation step has an outbound marker.

Retry resumes the first unresolved dependency step and never repeats a proven earlier
step.

## Tests

Extend only the focused suites unless a directly affected contract test requires change:

- `api/tests/test_operation_ledger.py`
  - two spawned processes race for one claim; exactly one wins;
  - an unexpired claim owned by another PID is not expired;
  - expired claim requires recovery and cannot be stolen directly;
  - stale worker cannot checkpoint after recovery fencing;
  - concurrent operation target mutations do not lose updates.
- `api/tests/test_page_operation.py`
  - page response ID is visible in persisted storage before module lookup/send;
  - module response ID is persisted before attachment;
  - module-item response ID is persisted;
  - crash/exception after page success resumes without another page POST;
  - recovery with page ID plus unresolved attachment is not falsely applied;
  - exact attachment postcondition completes recovery;
  - absent effect after an outbound marker remains `sent_unknown`;
  - exception before send is failed; exception after send is Attention;
  - one target exception does not prevent later targets or the final receipt;
  - review baseline survives apply and apply baseline is stored separately;
  - API projections and diagnostics remain PII-minimized.

Multiprocessing tests must use top-level worker functions, temporary workspace paths, and
portable `spawn` semantics. No developer-specific path, token, real course, network call,
or timing-only assertion.

## Verification

```powershell
node --check api/webui/static/push/page.js
py -m pytest api/tests/test_operation_ledger.py api/tests/test_page_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
py -m pytest api/tests
py -m pytest engine/tests
git diff --check
```

Render `/course-expert?tab=page` with lifespan off at 1920x1080. Confirm the Page panel,
Prepare control, operation summary, no horizontal overflow, and zero new console
warnings/errors. No live Canvas test is authorized.

## Forbidden changes and escalation

- Do not begin any slice 11 adapter, alter public routes, remove legacy push APIs, change
  receipt status vocabulary, add a dependency, or weaken same-title/ambiguous-result
  rules.
- Do not make browser-defined Canvas paths possible.
- Stop if the exact module-item postcondition cannot be read through the existing Canvas
  wrappers, if cross-process locking cannot be proven under `spawn`, or if satisfying this
  handoff requires a schema migration rather than additive fields.

## Required implementer reply

Report one commit hash and file list; all command/pass counts; the target/step transition
matrix; page/module/module-item checkpoint evidence; multiprocessing and fencing evidence;
exception/receipt evidence; baseline preservation; rendered console/overflow results; and
confirmation of zero live Canvas/AI calls and no unrelated staging.
