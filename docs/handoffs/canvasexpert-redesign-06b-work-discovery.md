# Toyota handoff 06b: bounded cross-course work discovery

## Objective and exact modules

Add read-only cached discovery without scanning on Desk GET.

- New `api/work_registry/discovery.py`.
- New `api/work_registry/providers/powergrader.py`, `grading_debt.py`,
  `late_work.py`, and `roster_warnings.py`.
- `api/webui/routes/work.py`; focused tests in `test_work_discovery.py` and
  `test_work_routes.py`.

`POST /api/work/scan` scans active bookmarked courses with at most three concurrent
courses, ten seconds per Canvas request, thirty seconds overall, and a five-minute cache
TTL. Pagination is mandatory. One course/provider failure preserves all other results
and its last good cache with stale/error metadata. `GET /api/work` reads local state only.

## Grading-debt semantics

A submission is eligible when workflow state is `submitted` or `pending_review` and
`submitted_at` exists. A score `is not None` counts as graded, including zero. Fetch
`include[]=submission_comments`; a teacher/non-student comment means touched even with
no score. PowerGrader evidence is keyed by course+assignment+user and counts only a
teacher score/comment or the terminal states approved, skipped, or posted. Merely
creating or leaving a pending session does not count.

A submission after `graded_at` or after the stored PowerGrader baseline resurfaces as
`resubmitted`, not untouched. Persist only aggregate counts/stable object IDs. Student
IDs are transient in memory and never enter registry/cache/response/log evidence.

`material_version` is SHA-256 over normalized kind, course ID, assignment ID, aggregate
counts, latest submitted timestamp, latest attempt number, and due timestamp—never
identity. Display titles use a deterministic protected-name sanitizer; on uncertainty,
use a generic course/type/count label.

Late-work and roster providers reuse existing pure school-day/extra-time and warning
category calculations. Routine and operation projections use the contract's
`routine_state` and `operation_receipt` source types.

## Verification

Test zero score, comment-only, pending vs terminal PG evidence, partial PG session,
resubmission, pagination, concurrency=3, both timeouts, TTL, partial course failure,
material resurfacing, no mutation methods, and a PII deny-list over disk/API/logs.

```powershell
py -m pytest api/tests/test_work_discovery.py api/tests/test_work_routes.py api/tests/test_gradebook_routes.py api/tests/test_roster_routes.py api/tests/test_route_contract.py
git diff --check
```

Stop if identity must persist or GET triggers Canvas. One commit; reply with hash,
timing/concurrency matrix, semantic case matrix, redaction result, and Canvas method audit.
