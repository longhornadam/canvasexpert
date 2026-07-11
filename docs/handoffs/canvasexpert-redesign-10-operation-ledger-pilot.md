# Toyota handoff 10: prepared-operation engine with PageForge pilot

> **Ferrari design accepted.** The authoritative design is
> `docs/reference/operation-ledger-design.md`. The contract remains
> `docs/contracts/operation-ledger-contract.md`. Implement from the design
> document; any deviation requires Ferrari escalation.

## Objective

Implement the Operation Ledger Contract and migrate one lower-risk creation kind—PageForge
page creation—to the prepared/review/apply/receipt path. Legacy immediate routes remain.

## Files

- New `api/operation_ledger/models.py`
- New `api/operation_ledger/operations.py`
- New `api/operation_ledger/batches.py`
- New `api/operation_ledger/registry.py`
- New `api/operation_ledger/executor.py`
- New `api/operation_ledger/claims.py`
- New `api/operation_ledger/recovery.py`
- New `api/operation_ledger/adapters/page.py`
- New `api/webui/routes/operations.py`
- `api/webui/server.py`
- `api/webui/templates/course_expert.html`
- `api/webui/static/push/page.js`
- `api/webui/static/write_review.js` only if required to display immutable batch review
- `api/tests/test_route_contract.py`
- New `api/tests/test_operation_ledger.py`
- New `api/tests/test_page_operation.py`
- `api/tests/test_webui_template_contracts.py`

## Page adapter

Preparation accepts the existing validated PageForge source reference, explicit targets,
and delivery settings. Server reparses/validates source, normalizes settings, verifies
targets against active/available courses, and stores a source digest. Review freezes
per-course effects and module-item implications. Apply revalidates source digest and
checks for an existing exact page/module relationship before POST.

Before each Canvas call, atomically claim and flush the target attempt/payload digest.
Confirmed success flushes returned IDs before continuing. Timeout, disconnect, crash
window, or unparseable response becomes `sent_unknown`; automatic resend is forbidden.
Recovery uses a returned ID or exact Page-specific postcondition to prove applied/absent;
otherwise it remains Attention. Same-title matching is never proof. Stale claims use the
contract lease/recovery rules.

Idempotency is deterministic by source digest + course + normalized title/delivery, but a
same-title page not created by this operation is never claimed as success. Preflight may
block on ambiguous foreign content. After page creation, persist/receipt the returned page
ID immediately as an adapter checkpoint before module attachment. Retry resumes module
attachment against that recorded page ID; it must not create a second page. A successful
target's receipt/object ID is authoritative. Partial success receipts each course. Retry
unresolved targets or unresolved dependency steps only. Reversal is described
truthfully: delete/unpublish only if a separately validated API path exists; otherwise
unsupported.

## UI

The Page panel gains Prepare publication. Prepared operations appear in the right ledger.
Review uses the shared dialog with Cancel focus. Existing immediate `/api/content/push`
remains for compatibility, but both CourseExpert and standalone Page surfaces use the
ledger after acceptance. All mutation routes reuse the slice-06a CSRF/same-origin/loopback
guard.

## Tests/runtime

Test schema/atomic/concurrency/corruption, source changes after review, stale targets,
duplicate apply, partial failure, retry, receipt projection/redaction, and unsupported
arbitrary kind/endpoint. Also test crash after write-ahead, timeout after send, stale claim
recovery, exact reconciliation, unresolved ambiguity, and every mutation-guard rejection.

```powershell
node --check api/webui/static/push/page.js
py -m pytest api/tests/test_operation_ledger.py api/tests/test_page_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Rendered fictional prepare/review/cancel/invalidated review/partial fixture. A live-fire
page creation/deletion test requires explicit user authorization and a disposable course.

Stop if the adapter would accept browser-defined Canvas paths or cannot make retry
idempotent.

## Required implementer reply

One commit; report hash/files, all persistence/adapter commands and pass counts, operation
state matrix, partial/retry/idempotency/redaction evidence, rendered review behavior,
console count, and whether separately authorized live-fire occurred.
