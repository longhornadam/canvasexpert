# CanvasMirror v2 — New Quizzes read representation

Status: active execution brief  
Risk: high — New Quizzes response data, student evidence, and credential-safe
native transport boundaries  
Owner: senior/orchestrator  
Executor: one implementation worker

## Objective

Extend CanvasMirror with a complete, read-only New Quizzes representation while
preserving the existing generic Mirror v1 contract. New Quiz metadata is kept
fresh by the normal mirror cadence. Full student response snapshots are acquired
on demand when a consumer requests a quiz, then retained in the disposable mirror
for later local reads.

The first consumer is the existing PowerGrader/New Quiz read path: a successful
focused fetch must populate the mirror, and a later local read may use a fresh
cached snapshot. Any item grading or feedback write still performs the existing
live/native preflight and verification; the mirror is never a write preflight.

The repository's referenced `docs/handoffs/HANDOFF_TEMPLATE.md` is absent, so
this brief uses the required equivalent sections directly.

## Locked decisions

1. **Metadata is continuous; responses are on demand.** The heartbeat may refresh
   New Quiz assignment/quiz/item metadata, but it must not generate Student
   Analysis reports for every quiz on every tick.
2. **Generic v1 remains stable.** Do not widen `roster.v1.json`,
   `assignments.v1.json`, or generic submission files to carry New Quiz item
   payloads. Add a versioned `new_quizzes/` collection under each course mirror.
3. **Reuse the existing transport.** Use `api/powergrader/new_quiz_fetch.py`
   and its tested report/item normalization instead of creating a second report
   poller or native-launch implementation.
4. **Persist complete read data, never credentials.** Student IDs, item response
   content, scores, result identities, and safe evidence metadata may live in the
   teacher-controlled workspace. Never persist or log cookies, PATs, signed launch
   fields, workflow JWTs, native/result tokens, signed URLs, or raw authorization
   headers. Persist only URL-free local relative evidence paths when files have
   already been materialized by the existing evidence owner.
5. **Attempt and result identity are mandatory.** A response snapshot must retain
   the student, attempt, submitted/report timestamps, quiz session identity when
   available, authoritative result ID/version when available, and an explicit
   incomplete/unknown state when those joins cannot be proven.
6. **Freshness is per New Quiz collection.** A fresh ordinary Canvas pass must
   not make New Quiz item responses appear fresh. Metadata and response snapshots
   each carry their own envelope and source timestamp.
7. **No item-level write-back in this slice.** Existing comment-only New Quiz
   behavior and future `new_quiz_grader.py` safety gates remain unchanged.

## Authorized scope

### Mirror storage and read API

- Add versioned New Quiz paths beneath `api/mirror/` and the per-course mirror:

  ```text
  <course>/new_quizzes/_sync.v2.json
  <course>/new_quizzes/<assignment_id>/quiz.v2.json
  <course>/new_quizzes/<assignment_id>/students/<user_id>.v2.json
  ```

- `quiz.v2.json` contains the assignment-to-quiz identity, quiz metadata, item
  catalog, item identity/type/points/prompt fields needed by existing response
  normalization, and metadata freshness/error state.
- Student files retain every report attempt that was successfully joined, a
  current/latest pointer, item responses, earned/status values, overall result
  facts, authoritative result identity when acquired, and URL-free evidence
  records. Do not silently discard a response because the item catalog is stale;
  represent the unresolved join explicitly.
- Add read helpers with a freshness gate and `(data, error)` behavior consistent
  with `api/mirror/queries.py`. Readers must be able to distinguish `mirror`,
  `canvas`, `stale`, `incomplete`, and `unavailable`.

### Acquisition and scheduling

- Add a metadata acquisition path to `api/mirror/sync.py` using the existing
  Canvas/New Quiz client conventions and the proven item shape handling in
  `new_quiz_fetch.py`.
- Add an on-demand response-refresh function used by PowerGrader/New Quiz, with
  bounded report polling and clear handling for 401/403, failed reports, stale
  reports, malformed items, and unmatched attempts.
- Make successful `new_quiz_fetch.fetch(...)` results write through to the v2
  mirror without copying signed transport fields.
- Expose status/refresh through the existing mirror service only if it is needed
  by the consumer; keep routes thin and local-only.

### Consumer integration

- Let the New Quiz PowerGrader read path use a fresh cached response snapshot when
  available, while preserving focused live/native refresh for evidence and all
  grading/write decisions.
- Do not change ordinary PowerGrader attachment behavior, the New Quiz comment
  lane, or the item-grader adapter's live preflight contract.

## References and insertion points

- `docs/mirror.md` — current Mirror v1 laws, layout, freshness, and non-goals.
- `docs/reference/new-quizzes-grading-transport.md` — verified report/native
  response and result identity boundaries.
- `api/mirror/store.py` — versioned disposable storage, atomic writes, validators,
  per-course locks, and workspace-safe paths.
- `api/mirror/sync.py` — deterministic full/delta/roster pass patterns.
- `api/mirror/queries.py` — mirror freshness and gradebook-shaped reads.
- `api/webui/mirror_service.py` — heartbeat/manual synchronization service.
- `api/powergrader/new_quiz_fetch.py` — existing Student Analysis normalization,
  native file evidence resolution, and credential scrubbing boundary.
- `api/powergrader/new_quiz_grader.py` — live/native authoritative-result
  preflight; do not weaken or route writes through the mirror.
- `api/powergrader/assignment_refresh.py` and
  `api/webui/routes/powergrader.py` — focused consumer insertion points.

## Required verification

- Unit tests for metadata normalization, every-attempt retention, item-response
  joins, authoritative result identity, URL/token scrubbing, corrupt-file
  handling, stale/incomplete states, and idempotent refresh.
- Mocked report lifecycle tests for success, 401/403, report failure, report older
  than Canvas, malformed item data, duplicate/ambiguous attempt joins, and native
  evidence failures.
- Consumer tests proving a fresh mirror avoids the ordinary report/Canvas read,
  while stale or incomplete data falls back to the focused live path.
- Run the affected PowerGrader/New Quiz tests, all mirror tests, and the full API
  suite if shared PowerGrader or server wiring changes.
- Run `git diff --check`; confirm no credential-shaped values, signed URLs, or
  real student data enter tracked files or test fixtures.

## Stop conditions

Stop and return RED/YELLOW instead of guessing if:

- The existing New Quiz transport does not expose enough stable fields to prove a
  student/attempt/result join.
- Implementing metadata or response acquisition requires a new authentication
  flow beyond the existing tested report/native paths.
- A proposed cache path would persist a credential, signed URL, raw response
  token, or private evidence outside the existing workspace boundary.
- The consumer would use a mirror snapshot as the preflight for an item score or
  feedback write.
- The current code contradicts these boundaries or requires expanding the public
  write contract.

## Execution result

Traffic light: GREEN  
Commit: `d6840c6 feat: add CanvasMirror New Quizzes v2`; correction:
`03e7d02 fix: preserve rich New Quiz mirror metadata` (local only; not pushed)
Files changed:  
- `api/mirror/new_quizzes.py` — versioned v2 metadata/response storage, validators,
  freshness reads, metadata sync, attempt/evidence normalization, and cache adapter.  
- `api/mirror/sync.py` — continuous New Quiz metadata refresh from full/delta passes.  
- `api/powergrader/new_quiz_fetch.py` — reusable all-attempt normalization, safe
  result identity capture, snapshot callback, and fresh-cache mode.  
- `api/powergrader/canvas_fetch.py` — New Quiz snapshot write-through and cached
  read routing; native evidence path remains unchanged.  
- `api/powergrader/assignment_refresh.py` — fresh v2 snapshot consumer with
  stale/incomplete fallback to focused acquisition.  
- `api/tests/test_mirror_new_quizzes.py` — v2 storage, sync, scrubbing, state,
  idempotency, and consumer regression tests.  
- `docs/mirror.md` — v2 layout, cadence, read, and write-safety documentation.  
- `docs/handoffs/canvasmirror-new-quizzes-v2.md` — this execution result.  
Verification:  
- `py -m pytest api/tests/test_mirror_new_quizzes.py api/tests/test_mirror_store.py
  api/tests/test_mirror_sync.py api/tests/test_mirror_queries.py
  api/tests/test_mirror_service.py api/tests/test_powergrader_new_quizzes.py
  api/tests/test_powergrader_attachment_workflow.py api/tests/test_route_contract.py`
  — **98 passed**.  
- `py -m pytest api/tests` — **826 passed, 1 skipped** (827 collected).  
- `py -m compileall -q api/mirror api/powergrader
  api/tests/test_mirror_new_quizzes.py` — passed.  
- `git diff --check` — passed.  
- Self-review confirmed no changes to `new_quiz_grader.py`, no mirror write path,
  no generic v1 New Quiz payload widening, and no credential/signed-URL persistence
  in the new v2 cache.  
- Correction rerun: `py -m pytest api/tests/test_mirror_new_quizzes.py
  api/tests/test_mirror_store.py api/tests/test_mirror_sync.py
  api/tests/test_mirror_queries.py api/tests/test_mirror_service.py
  api/tests/test_powergrader_new_quizzes.py` — **82 passed**.
- Correction `git diff --check` — passed.
- The previously recorded full API result (**826 passed, 1 skipped**) predates
  this bounded mirror-only correction and was not rerun.
Deviations: none recorded.  
Unresolved decision: none — metadata-continuous/on-demand-response policy is locked.
