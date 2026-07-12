# Toyota handoff 11r: operation integration and acceptance repair

## Objective and commit boundary

Repair slices 11a-11c1 so Quick Assignment, AssignmentForge, PageForge, and
RubricForge use the accepted operation-ledger prepare -> review -> apply path from
both Course Expert and their standalone routes. Repair explicit target ownership,
HTTP JSON parsing, scheduled Auto-Score ledger truth, and test isolation.

This is one bounded repair commit on `dev`. Do not implement QuizForge (11d),
AssignmentForge differentiation/tiers, assignment-rubric association, reversal,
multi-operation batch apply, or any new Canvas endpoint.

## Ferrari decisions and invariants

1. `window.CE_PUSH.pushContent(...)` is the single browser gateway for the four
   existing aliases `quick`, `af`, `pf`, and `rf`. Map them in shared browser code
   to `content.quick_assignment`, `content.assignment`, `content.page`, and
   `content.rubric`. It must prepare, freeze one-operation review, show the existing
   write-review dialog from the server-frozen review, and apply only after explicit
   confirmation. It must never POST these aliases to `/api/content/push`.
2. Page's separate `#btn-pf-prepare` remains prepare-only. Move/reuse shared operation
   helpers; do not leave a second private implementation in `page.js`.
3. The prepare JSON schema is exactly:

   ```json
   {
     "payload": {"kind-specific": "fields"},
     "targets": [{"course_id": "123"}]
   }
   ```

   The server rejects a missing/non-object payload, a missing/non-list/empty targets
   value, non-object target entries, blank IDs, duplicate IDs, and inactive IDs with
   HTTP 400. Preserve target order. Client-supplied names and Canvas paths are never
   accepted. The adapter validates each ID against `config.active_courses()`.
4. All operation mutation handlers parse JSON through supported FastAPI/Starlette
   APIs (`async def` + `await request.json()` or an equivalent public API). Never read
   `Request._body`. Malformed JSON returns the existing PII-safe HTTP 400 response.
5. Standalone push pages and Course Expert must receive a non-empty CSRF token in a
   meta tag before shared push scripts run. Use one base/template mechanism, not four
   divergent hard-coded tokens. Do not weaken loopback, Origin, Host, or CSRF checks.
6. Browser review content comes from `review_batch`'s frozen reviews. It must show
   every selected server-resolved course name and kind-relevant effects:
   assignment/quick name, points/date/publish/SIS as present; page title/publish/module;
   rubric title/criteria/points/student page; Assignment Auto-Score and per-job
   auto-push opt-in. Raw normalized payloads, course IDs, and private diagnostics are
   not rendered.
7. Cancellation performs no Canvas or queue write. The reviewed operation may remain
   visible in the Course Expert operation list for later review/apply.
8. Scheduled Auto-Score is a durable `schedule_autoscore` step after the assignment
   ID is confirmed. Its payload digest includes the assignment ID, due date, settings,
   explicit auto-push choice, and policy. Before `upsert_job`, persist the step marker.
   On success checkpoint `state=applied` and `returned_object_id=<deterministic job_id>`.
   A repeated/retried call uses `autoscore_queue.upsert_job` and the same
   `autoscore_queue.make_job_id(course_id, assignment_id)`; it must not duplicate jobs.
9. If queue creation raises after assignment creation, checkpoint the schedule step as
   `failed`, retain the Canvas assignment ID/URL, return target state `partial`, and
   set a PII-safe error code such as `autoscore_queue_failed`. Extend the shared target
   model so `partial` is a valid unresolved target state, `claimed -> partial` is valid,
   a sole partial target yields operation `partial`, and retry selects it. Retry must
   verify/reuse the exact assignment ID and execute only unfinished dependencies.
10. If `autoscore_schedule` is requested without a due date, preparation fails with
    HTTP 400 before an operation or write is created. Global/default auto-push remains
    forbidden; only the request's explicit per-assignment opt-in is frozen.
11. Resolve the Auto-Score course name from server-owned active-course configuration,
    never from the client target object.
12. Tests may not access the configured synced workspace. Patch the exact workspace
    module used by `autoscore_queue`, or patch the queue boundary. No test may leave a
    `Found Poetry`, `42_24680`, or other synthetic job outside `tmp_path`.

## Exact files and ownership

- `api/webui/routes/operations.py`
  - public JSON parsing for prepare/review/apply;
  - exact prepare envelope validation and selected-target forwarding.
- `api/webui/static/push/core.js`
  - own CSRF JSON POST, alias-to-kind mapping, prepare-only helper,
    prepare/review/apply workflow, frozen-review rendering, operation-list refresh and
    later review/retry handlers;
  - retain legacy `pushContent` signature so existing callers need no parallel API.
- `api/webui/static/push/page.js`
  - remove the duplicate operation implementation;
  - call the shared prepare-only helper for `#btn-pf-prepare`.
- `api/webui/static/push/assignment.js`, `api/webui/static/push/rubric.js`,
  `api/webui/static/course_expert/quick_assignment.js`, and
  `api/webui/templates/push_quick.html`
  - only mechanical call-site/load cleanup if required; preserve current field payloads
    and globals. Both Quick implementations must reach shared `pushContent`.
- `api/webui/templates/base.html`, `api/webui/templates/workbench_base.html`,
  `api/webui/routes/pages.py`
  - one CSRF-meta/context mechanism for Course Expert and all standalone push pages.
- `api/operation_ledger/adapters/assignment.py`
  - durable schedule step, server-owned course name, due-date validation, retry truth.
- `api/operation_ledger/models.py`
  - target `partial` state/transitions/status computation/unresolved predicate.
- `api/operation_ledger/executor.py`
  - when persisting a final adapter result, overwrite `error_code` and
    `private_diagnostic` even when the final values are `None`; a successful retry
    must clear stale failure metadata before receipt projection.
- `api/tests/test_operation_routes.py` (new)
  - real TestClient coverage through the registered routes with temp ledger and fake
    Canvas only.
- `api/tests/test_assignment_operation.py`
  - isolated successful schedule, failure -> partial, deterministic job ID, retry/no
    duplicate, and missing-due preparation tests.
- `api/tests/test_webui_template_contracts.py`
  - script order, CSRF meta, no legacy route for the four aliases, standalone/Course
    Expert wiring.
- Update `api/README.md`, `api/webui/README.md`, and rubric teacher-facing text only to
  remove statements made false by the accepted wiring. Do not claim FERPA safety,
  anonymity guarantees, reversal, tiers, rubric association, or live-fire evidence.
- Remove trailing whitespace in `docs/reference/rubric-live-path.md`.

If a necessary edit falls outside this list, stop and report it unless it is a direct
test fixture/import required by the specified behavior.

## HTTP and browser behavior

- Prepare response remains `{ok, operation_id, review_summary}`.
- Review and apply remain one operation per browser batch in this slice. Do not broaden
  or redesign multi-operation batch semantics.
- Non-2xx JSON responses must be surfaced in the relevant log/banner; buttons are
  re-enabled after success, cancellation, or failure.
- Course Expert's operation list must render on load and refresh after prepare, apply,
  and retry. Standalone pages need no list container and must not throw when it is absent.
- Existing validation buttons remain validation-only.
- `/api/content/push` remains for explicitly out-of-scope legacy kinds, including Quiz;
  do not delete the compatibility route or push-service functions in this repair.

## Required tests

Positive tests:

- valid CSRF + one selected active target prepares exactly that target;
- two selected targets preserve order and no third active course is included;
- prepare -> review -> apply creates only the selected fake Canvas objects;
- each alias maps to its registered `content.*` kind;
- standalone and Course Expert templates load CSRF before shared push code;
- scheduled job success records `schedule_autoscore` with deterministic job ID;
- retry/upsert does not duplicate a job;
- successful retry clears the prior queue-failure error and private diagnostic from
  the target and receipt;
- assignment success plus queue failure retains assignment ID and yields target and
  operation `partial`.

Negative tests:

- malformed JSON; missing/wrong payload; missing/empty/wrong targets; blank,
  duplicate, or inactive target IDs all return 400 and create no operation/write;
- invalid/missing CSRF remains 403;
- cancellation causes no Canvas/queue write;
- schedule without due date creates no operation/job;
- no Quick/Assignment/Page/Rubric browser call reaches `/api/content/push`;
- test run leaves configured workspace untouched.

## Verification commands

```powershell
node --check api/webui/static/push/core.js
node --check api/webui/static/push/page.js
node --check api/webui/static/push/assignment.js
node --check api/webui/static/push/rubric.js
node --check api/webui/static/course_expert/quick_assignment.js
py -m pytest api/tests/test_operation_routes.py api/tests/test_assignment_operation.py api/tests/test_quick_assignment_operation.py api/tests/test_page_operation.py api/tests/test_rubric_operation.py api/tests/test_operation_ledger.py api/tests/test_push_service.py api/tests/test_powergrader_autoscore_queue.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_powergrader_autopush_policy.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
py -m pytest api/tests
git diff --check
```

Rendered runtime acceptance is mandatory on `/course-expert`, `/push/quick`,
`/push/assignment`, `/push/page`, and `/push/rubric`: confirm required globals/functions,
selected-target request shape, no direct legacy call for the four kinds, and zero new
console errors. Use fakes or interception only; no live Canvas write is authorized.

## Forbidden changes

- No live Canvas calls in tests or runtime verification.
- No secrets, student/course-derived fixtures, configured-workspace writes, or raw
  private diagnostics in browser/API projections.
- No weakening local-only or mutation guards.
- No QuizForge migration, tier/differentiation enablement, rubric association,
  scheduled global/default auto-push, deletion/reversal, or navigation redesign.
- Do not archive this handoff. Ferrari performs acceptance and archival.

## Toyota stop conditions and required reply

Stop instead of guessing if the shared `pushContent` callers require materially
different user-visible sequencing, the queue cannot return a deterministic job ID,
`partial` cannot be added without breaking recovery semantics, a named route/template
is absent, or runtime verification would require live Canvas access.

Reply with the one commit hash, exact files, focused/full test counts, HTTP target matrix,
Auto-Score success/failure/retry evidence, standalone/Course Expert runtime results,
console-error count, configured-workspace non-mutation evidence, and explicit
no-live-write confirmation.

## Ferrari acceptance

Accepted 2026-07-11 after independent review of commit `a2d6617`.

- Five JavaScript syntax checks passed.
- Focused acceptance suite: 229 passed.
- Full API suite: 474 passed, 1 skipped.
- Explicit-target HTTP prepare/review/apply matrix passed with fake Canvas only.
- Scheduled Auto-Score success, partial failure, deterministic retry, stale-diagnostic
  clearing, and configured-workspace isolation passed.
- `/course-expert`, `/push/quick`, `/push/assignment`, `/push/page`, and `/push/rubric`
  rendered with one non-empty CSRF token and the shared operation script; Course Expert
  tab behavior executed and all five routes produced zero browser-console errors.
- `git diff --check` passed. No live Canvas write was performed.
