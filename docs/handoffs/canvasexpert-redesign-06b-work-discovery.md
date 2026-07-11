# Toyota handoff 06b: bounded cross-course work discovery

## Prerequisite and objective

06a must be accepted first. Add explicit, bounded, read-only discovery behind
`POST /api/work/scan`; Desk `GET /api/work` remains local-only and must never scan
Canvas. Discovery enriches the accepted Work Registry with aggregate findings and
stable object references. It never becomes an authority and never stores identity.

## Authorized files and interfaces

- New `api/work_registry/discovery.py`
  - Expose `scan_active_courses(now=None)`, `load_discovery_cache()`, and
    `save_discovery_cache(document)`.
  - Use at most three worker threads across active bookmarked courses, a monotonic
    30-second overall deadline, and a 10-second timeout for every Canvas request.
  - A provider must check the deadline before each request and return a fixed error
    code when the course deadline expires; do not extend the overall deadline by
    starting new work after it expires.
- New `api/work_registry/providers/powergrader.py`, `grading_debt.py`,
  `late_work.py`, and `roster_warnings.py`
  - Each provider exposes `scan_course(course_id, *, now, deadline, canvas_get_all)`
    for Canvas-backed work, or a clearly named local projection for PowerGrader.
  - Providers may inspect private authorities transiently in memory when necessary
    to match evidence, but must return only aggregate counts, stable object IDs,
    material facts, and PII-free job projections.
- `api/work_registry/storage.py`
  - Add cache helpers using the existing workspace `_system/workbench/` root,
    versioned file `discovery-cache.v1.json`, same-directory fsync/atomic replace,
    and quarantine. Preserve 06a registry/suppression behavior.
- `api/webui/routes/work.py`
  - Add the scan route and merge its results into the registry/cache without changing
    the 06a route shapes.
- New `api/tests/test_work_discovery.py`; extend `api/tests/test_work_routes.py`.

## Scan route and cache contract

`POST /api/work/scan` takes no client-selected course IDs and no provider options.
Run `require_local_mutation(request)` before reading config or making Canvas calls.
Scan exactly `config.active_courses()`, with maximum concurrency three. Return:

```json
{
  "ok": true,
  "partial": false,
  "courses_scanned": 0,
  "findings": 0,
  "stale_course_ids": [],
  "error_codes": []
}
```

`partial` is true when any course/provider failed; `error_codes` contains only fixed
codes such as `course_timeout`, `course_unavailable`, or `provider_failed`, never
Canvas response text, URLs, paths, names, or exception text. A scan with zero active
courses is a successful empty result. GET reads the most recent local cache and
registry projections only.

The cache document is exactly versioned and PII-minimized:

```json
{
  "version": 1,
  "updated_at": "ISO-8601",
  "courses": {
    "opaque-course-id": {
      "checked_at": "ISO-8601",
      "findings": [],
      "stale": false,
      "error_code": ""
    }
  }
}
```

Each course keeps its last good findings when a later scan fails, marks that course
stale, and records only a fixed error code. Cache TTL is five minutes for display;
an explicit scan still refreshes it. Never discard good courses because one course
failed. Never persist student IDs, names, submission content, grades, comments,
monitored notes, absolute paths, raw Canvas errors, or request URLs.

## Provider semantics

### Grading debt

Fetch paginated assignments and paginated submissions with
`include[]=submission_comments`; pass `timeout=10` to every request. An item is
eligible only when workflow state is `submitted` or `pending_review` and
`submitted_at` exists. A score where `score is not None` is graded, including zero.
A teacher/non-student comment means touched even when no score exists. Student IDs
and comment authors may be held transiently to classify the item, then discarded.

PowerGrader evidence is transiently keyed by course/assignment/user and counts only
a teacher score/comment or terminal states `approved`, `skipped`, or `posted`.
Creating or leaving a pending session does not count. A submission after `graded_at`
or the stored PowerGrader baseline is `resubmitted`, not untouched.

### Late work

Reuse the existing pure school-day and extra-time calculations. Fetch only the
assignment/submission facts required to aggregate late counts. Do not persist or
return the student ID that produced a count. Titles fall back to generic
`Late work · <count>` labels when any course/assignment label is uncertain.

### Roster warnings

Reuse existing pure warning categories (`missing_pseudonym`, `extra_time_without_days`,
`group_unset`, `multiple_groups_in_selected_set`, `nickname_collision`, and
`protected_name_collision`) over transient fetched/configured data. Aggregate by
warning code and course. Do not call the roster route, upsert the vault, or persist
student rows. A provider failure is stale/error metadata, not an empty healthy result.

### PowerGrader/local sources

Project existing session summaries, autoscore queue, routine state, and receipts
without Canvas calls. If per-student terminal evidence is needed, load it transiently
from the existing PRIVATE authority and immediately reduce it to aggregate counts and
stable course/assignment object IDs. The registry/cache never receives that payload.

For every finding, compute `material_version` exactly as specified by the accepted
Work Registry contract: SHA-256 over normalized kind, course ID, assignment ID,
aggregate counts, latest submitted timestamp, latest attempt number, and due timestamp.
Never include identity in the digest input.

## Required tests

Test zero-score grading, comment-only grading, pending versus terminal PowerGrader
evidence, partial sessions, resubmission, mandatory pagination, concurrency capped at
three, per-request timeout, overall timeout, five-minute TTL, partial course failure
with last-good retention, material-version resurfacing, roster warning aggregation,
no mutation methods, no Canvas calls on GET, local mutation guard rejection, and a
PII/absolute-path deny-list over cache, registry, API, and log output.

```powershell
py -m pytest api/tests/test_work_discovery.py api/tests/test_work_routes.py api/tests/test_gradebook_routes.py api/tests/test_roster_routes.py api/tests/test_route_contract.py
git diff --check
```

One commit. Report the hash, timing/concurrency matrix, semantic case matrix,
last-good/stale cache evidence, redaction result, and Canvas method audit. Do not
archive this handoff.

## Forbidden changes / escalation

- Do not make `GET /api/work` call Canvas.
- Do not accept client course/provider scope, add arbitrary Canvas paths/methods, or
  add a second CSRF/origin implementation.
- Do not persist identity, raw Canvas responses, or source payloads.
- Do not add Desk/Workbench markup or operation-ledger routes.
- Stop if an existing provider cannot be made aggregate-only, if the deadline cannot
  be enforced, or if a failure would replace a last-good cache with an empty healthy
  result.
