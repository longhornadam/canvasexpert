# Bounded CanvasMirror coordinator and release telemetry

Status: **READY**

Risk: **high** - shared Canvas GET scheduling, request retry, local route middleware, and
privacy-minimized diagnostics sit beside live write preflight and private projections.

Depends on: `dev` / `origin/dev` at `1ba9f93`; preserve the senior-owned dirty changes to
`docs/handoffs/CURRENT.md` and `docs/handoffs/NEXT_BATCH.md`.

## Teacher-visible result

Manual Sync returns immediately and shows observable progress; background CanvasMirror
work yields to any active teacher request, duplicate refreshes coalesce, Canvas 429 reads
retry safely, and a read-only release harness can measure cold/warm behavior without
touching the teacher's current mirror or leaking course/student identity.

## Acceptance criteria

- [ ] An in-memory, fixed-two-worker coordinator enforces `preflight > post_write > focus
  > manual > background > concluded`, dependency order, duplicate `(course, scope)`
  coalescing/promotion, cancellation, and failure isolation with sanitized job/plan state.
- [ ] Every local HTTP request is a foreground interval; queued/running low-priority GET
  work waits cooperatively before each physical request, while cancellation/failure never
  advances a successful mirror watermark.
- [ ] `POST /api/mirror/sync-now` returns `202` with an opaque plan ID; a GET status route
  exposes progress, and Home polls it before rescanning Work. One course and the locked
  named scopes can be requested without opening a second long HTTP request.
- [ ] Core GETs retry only `429` at most twice, honor numeric `Retry-After` capped at 30s,
  and record logical/physical requests, bytes, retries, status/error class, transport time,
  queue wait, priority, scope, and yield/cancel counts without URLs, IDs, or response text.
- [ ] A read-only CLI validates the 1-current/2-concluded profile and measures three-run
  cold/warm plus optional focused reads in a temporary disposable root. It refuses output
  under the repo or configured workspace and emits aggregate JSON only.
- [ ] Current docs describe shipped behavior; the named gate passes.

## Explicit non-goals

- Do not run the live benchmark, select courses, mutate Canvas, bump the app version, write
  release notes, change projection schemas, or implement new read-service intents.
- Do not persist coordinator jobs, build a generalized scheduler, add public routes, retry
  mutations/5xx/connection failures, or move specialized New Quiz/file transports.
- Do not change engine behavior or the deliberately deferred per-student override unit.

## Locked decisions

- Add `docs/contracts/canvasmirror-coordinator-contract.md`. Production scope names are
  `course.refresh`, `course_context`, `course_structure`, `roster`, `groups`,
  `submissions.course_delta`, and `new_quizzes.metadata`; `course.refresh` is a compatibility
  orchestration unit, never a claim that pass and scope are synonyms.
- Job states are `queued/running/succeeded/failed/cancelled`; plans aggregate jobs. State is
  process-local and bounded; status may contain local course ID, but logs/benchmark output may not.
- Production runners are an explicit read-only registry in `mirror_service`; coordinator
  code imports no Canvas send/mutation owner. `sync_now()` remains a direct compatibility
  function for internal callers/tests, while the HTTP route uses the coordinator.
- Server middleware marks the full lifetime of every HTTP request as foreground.
  Coordinator worker context makes the core Canvas GET client yield before each physical GET.
- GET telemetry is captured by a nestable context in `canvas_client` and emitted through
  the expanded strict `operational_log` allowlist; raw URL/path/params/body never enter it.
- The benchmark CLI lives at `tools/canvasmirror_release_benchmark.py`, requires explicit
  output, uses a temporary root passed to existing projection owners, cleans only that
  verified temp root, and never deletes or rewrites the configured workspace.

## Scope

- Add: `api/mirror/coordinator.py`, `api/tests/test_mirror_coordinator.py`,
  `tools/canvasmirror_release_benchmark.py`, `api/tests/test_canvasmirror_release_benchmark.py`,
  `docs/contracts/canvasmirror-coordinator-contract.md`.
- Modify only as needed: `api/webui/{server.py,mirror_service.py,canvas_client.py}`,
  `api/webui/routes/mirror.py`, `api/webui/static/desk.js`, `api/operational_log.py`,
  affected tests in `api/tests/`, `docs/mirror.md`, `api/webui/README.md`, and this brief.

## Read only these references

- `AGENTS.md`; this brief
- Vision §§5.8, 6.1, 9, 16, 19.2, 19.5, and 20 Performance/Maintainability
- `docs/contracts/canvas-read-spine-contract.md`
- `docs/mirror.md` sections `Design laws`, `Scheduling`, `v1 non-goals`
- `api/webui/README.md` `Page map`; exact scope files above

Do not read archived handoffs, unrelated module maps, or the whole vision document.

## Preflight - stop if these facts are false

```powershell
git branch --show-current
git rev-parse HEAD; git rev-parse origin/dev
git status --short
Test-Path api/mirror/coordinator.py
rg -n "sync-now.*runs synchronously|def mirror_sync_now" api/webui/routes/mirror.py
rg -n "physical_count|byte_count|retry_count|queue_wait_ms" api/operational_log.py
```

Expect `dev`, equal `1ba9f93`, only the two senior handoff changes, no coordinator, the
synchronous route marker present, and no release telemetry fields. Otherwise return RED.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_mirror_coordinator.py api/tests/test_canvas_client.py api/tests/test_mirror_service.py api/tests/test_canvasmirror_release_benchmark.py api/tests/test_beta075_connections.py api/tests/test_desk_routes.py api/tests/test_route_contract.py api/tests/test_operation_routes.py api/tests/test_presentation_contracts.py api/tests/test_webui_template_contracts.py -q
py -m pytest api/tests -q
git diff --check
```

Also run the harness's synthetic/self-check to a temp path outside repo/workspace, and load
every Page-map route in the local app with zero new console errors. Do not click write or
live-sync controls; report route/error counts only, never rendered private content.

## Stop conditions

- **RED:** production scheduling would accept mutation runners; metrics require raw URLs,
  identifiers, bodies, or secrets; safe temp-root proof is impossible; a public contract
  beyond the new coordinator contract is required.
- **YELLOW:** an unrelated broad-suite failure, unavailable browser check, or one bounded
  compatibility decision remains after the focused gate.

## Execution result

Executor records traffic light, commit hash if any, changed files, exact gate counts,
browser route/error count, self-check output location/classification, deviations, and
unresolved decisions. Do not self-accept or edit `NEXT_BATCH.md`.

**YELLOW — 2026-07-19 executor report**

- Commit: none (browser acceptance seam unavailable; do not self-accept).
- Changed: `api/mirror/coordinator.py`, `api/webui/{server.py,mirror_service.py,canvas_client.py,routes/mirror.py,static/desk.js,README.md}`, `api/operational_log.py`, `tools/canvasmirror_release_benchmark.py`, `docs/contracts/canvasmirror-coordinator-contract.md`, `docs/mirror.md`, and focused affected tests (`test_mirror_coordinator.py`, `test_canvasmirror_release_benchmark.py`, `test_canvas_client.py`, `test_mirror_service.py`). `docs/handoffs/NEXT_BATCH.md` remains senior-owned and unmodified by executor work.
- Focused acceptance command: **102 passed** in 3.95s.
- Full API command: **1117 passed, 1 skipped** in 34.63s.
- `git diff --check`: passed.
- Synthetic harness self-check: passed; aggregate-only JSON at `C:\Users\adamb\AppData\Local\Temp\canvasmirror-release-self-check-20260719-019f7d5d.json`, classification `synthetic_self_check`, verified disposable root, 1-current/2-concluded profile, no Canvas calls.
- Browser Page-map matrix: **0 routes / 0 console errors observed**. Local app was started without invoking sync/write controls, but the required in-app browser connection returned exact failure text: `No browser is available`; all Page-map routes therefore remain unverified. This is the sole YELLOW condition.
- Deviations: none from locked implementation decisions. `course.refresh` is implemented as compatibility orchestration over dependent scope jobs, not a physical pass/scope synonym; legacy direct `sync_now()` remains for internal callers/tests.
- Unresolved decision: senior lane must provide/restore a real browser surface and run the required Page-map route matrix before GREEN acceptance.

**YELLOW — correction evidence**

- Repaired coordinator seams: heartbeat now queues one `course.refresh` compatibility job per course at `background`/`concluded` priority and waits before `refresh_work_findings`; post-write timers queue/coalesce `submissions.course_delta` at `post_write`; `course.refresh` no longer fans out, while explicit named scopes retain dependency planning; structure and New Quiz metadata runners are narrow/direct; result states, failed dependencies, queue wait/context telemetry, and bounded job/key cleanup are enforced.
- Added focused assertions for background/concluded foreground yield, heartbeat priority/order, post-write queueing, no legacy full/delta from named runners, failed-result/dependency isolation, queue telemetry, and deterministic plan/job/key bounds.
- Corrected focused command: **109 passed** in 4.04s. Corrected full API command: **1124 passed, 1 skipped** in 35.08s. `git diff --check`: passed.
- Corrected synthetic self-check: passed; aggregate-only JSON at `C:\Users\adamb\AppData\Local\Temp\canvasmirror-release-self-check-20260719-correction.json`, classification `synthetic_self_check`.
- The original browser matrix remains unavailable (`No browser is available`); this is still the sole YELLOW condition. No commit was created.

**YELLOW — live-readonly harness correction evidence**

- Corrected `new_quizzes.metadata` to pass normalized values from the local assignment map, rather than map keys. Context and group runners now return explicit `ok: false` for stale/unavailable outcomes, so coordinator plan state cannot claim success after an unsuccessful acquisition.
- Added `--live-readonly` to the release harness. It validates the configured 1-current/2-concluded lifecycle profile through core GET-backed course-context reads, runs three fresh disposable-root cold/full + current-only warm/delta pairs, optionally executes membership-checked focused reads from a private environment ID, cleans every verified root, and writes/prints aggregate-only sanitized results. The executor did **not** run this live mode.
- Added injected synthetic orchestration coverage for fresh-root-per-pair cleanup, current/concluded cadence, focused membership, aggregate-only output, profile refusal, runner failure normalization, and internal core-GET status-class counters without new persisted operational-log fields.
- Final focused command: **112 passed** in 3.75s. Final full API command: **1127 passed, 1 skipped** in 32.27s. `git diff --check`: passed.
- Final synthetic self-check: passed; classification `synthetic_self_check`; aggregate-only JSON at `C:\Users\adamb\AppData\Local\Temp\canvasmirror-release-self-check-20260719-live-readonly.json`.
- Browser remains unattempted in this correction pass and unavailable from the prior executor check (`No browser is available`): sole YELLOW condition. No commit was created.

**YELLOW — benchmark helper cleanup evidence**

- Removed obsolete `measure_three_runs` and its one-root test. The only multi-run measurement path is now `--live-readonly`'s three paired, fresh-root cold/warm runs. Updated the harness module docstring to distinguish configured read-only measurement from synthetic `--self-check`.
- Focused named gate: **111 passed** in 4.33s. `git diff --check`: passed. No production coordinator/service code changed; no commit was created. Browser remains the sole YELLOW condition.
