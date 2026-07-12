# Toyota handoff 11b1: core AssignmentForge operation

## Objective

Migrate only core assignment creation to `content.assignment`: parsed canonical source,
course targets, core Canvas assignment fields, review, create, receipt. Exclude files,
printables, modules, rubrics, differentiation, and scheduled scoring.

Use new `operation_ledger/adapters/assignment.py`, the adapter registry,
`push_service.py` pure parse/normalize helpers, `static/push/assignment.js`, and focused
tests. Both the CourseExpert tab and standalone Assignment route must call the same ledger
path; neither may retain a direct write. Preserve route/global/deep-link behavior.

Persist write-ahead before POST; record returned assignment ID. Timeout/disconnect is
`sent_unknown` and Attention, never an automatic retry or same-title success. Retry only
after reconciliation proves absence. Test multi-course partial, drift, repeat, ambiguous
result, reconciliation, cancel/no-write, redaction, and exact postcondition.

```powershell
node --check api/webui/static/push/assignment.js
py -m pytest api/tests/test_assignment_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py
git diff --check
```

Stop if core fields cannot be separated from dependencies. One commit; reply with hash,
surface parity, target result matrix, receipt evidence, and no-live-write statement.

Accepted by Ferrari on 2026-07-11 after integration repair `a2d6617`; explicit-target
prepare/review/apply, exact-ID recovery, full tests, and rendered parity checks passed.
Tiered content remains excluded under deferred slice 11b4.
