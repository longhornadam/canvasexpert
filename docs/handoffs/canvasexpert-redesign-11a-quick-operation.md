# Toyota handoff 11a: Quick Assignment operation adapter

## Objective

Migrate Quick Assignment from immediate `/api/content/push` execution to registered kind
`content.quick_assignment` using the accepted ledger foundation.

## Files

- New `api/operation_ledger/adapters/quick_assignment.py`
- Adapter registry file from slice 10
- `api/webui/static/course_expert/quick_assignment.js`
- `api/webui/templates/course_expert.html` only if summary markup is missing
- New `api/tests/test_quick_assignment_operation.py`
- `api/tests/test_push_service.py`

## Contract

Server owns title, points, dates, publish/SIS settings, explicit target validation,
review summary, and idempotency. Drift checks exact existing assignment identity before
create. One target may fail without repeating successful targets. Receipt includes created
assignment IDs/URLs. Reversal is unsupported unless delete/unpublish is proven and tested.

Do not change standalone `/push/quick` compatibility in this commit; migrate it in a later
explicit parity check or leave it on the legacy route until cleanup.

```powershell
node --check api/webui/static/course_expert/quick_assignment.js
py -m pytest api/tests/test_quick_assignment_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py
git diff --check
```

Runtime prepare/review/partial/retry with fakes; live-fire only by explicit authorization.

## Stop conditions and required reply

Stop on ambiguous duplicate detection, implicit target expansion, or missing reversal
truth. One commit; report hash/files, command/pass results, partial/retry/repeat evidence,
receipt projection, rendered review, console count, and live-fire authorization state.

Both the CourseExpert Quick tab and standalone Quick route use this adapter; neither may
retain a direct write. Persist before POST and record returned assignment ID. Timeout or
disconnect is `sent_unknown` Attention; same-title matching never proves success, and
retry requires exact reconciliation proving absence.
