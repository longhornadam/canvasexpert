# Execution brief: make Course Expert quiz pushes crash-safe and reviewable

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Teachers can push both whole-class and differentiated QuizForge quizzes from Course
Expert through the released operation ledger: prepare, frozen teacher review, apply,
visible polling progress, and safe retry. Quiz validation, dry-run preview, delivery
settings, target-course selection, and optional physical-copy generation keep their
current teacher-facing behavior.

This closes the last conspicuous mismatch between Course Expert's browser and the
released crash-safe content backend. Assignment, Page, Rubric, and Quick Assignment
already use the ledger path; Quiz should no longer rely on streaming writes.

## Locked decisions

- Both quiz modes move together in this brief. Whole-class and differentiated pushes
  use the registered `content.quiz` operation kind.
- The browser sends only the adapter's typed preparation inputs. Whole mode sends
  `{mode: "whole", path, settings}`. Differentiated mode sends
  `{mode: "differentiated", variants: [{path, group_name}], settings}`.
- Differentiated payloads do **not** send `student_ids`, group IDs, Canvas endpoints,
  or Canvas methods. The released adapter resolves and freezes group membership from
  server-owned Canvas state.
- `collectSettings()` remains the source of QuizForge delivery settings. Parse its
  JSON string once into an object; do not create a second settings collector or alter
  the authoring contract.
- The server-frozen review is the only write confirmation. Remove the browser's
  pre-ledger quiz confirmation rather than asking the teacher to confirm twice.
- Reuse the existing `CE_PUSH` prepare/review/apply path. Add `qf: "content.quiz"` to
  the existing operation-kind mapping and make the shared path return its apply result;
  do not create a parallel quiz-only operation client.
- Extend the existing frozen-review presentation for quiz fields and differentiated
  variants. Review copy must be teacher-readable and must come only from the frozen
  server response, never from an editable browser payload after review.
- Use `GET /api/operations/{operation_id}/status` for bounded polling while apply or
  retry is active. The Summary rail shows operation, target, and step states using
  ordinal target labels only; it must not display target keys, course IDs, object IDs,
  URLs, payloads, or diagnostics.
- Polling is ordinary timed GET polling, not SSE, WebSockets, an event log, or new
  persistence. Prevent duplicate pollers per operation and stop polling at terminal
  state, on failure, and when the page is discarded.
- The Summary rail remains the recovery surface. Prepared/reviewed operations remain
  reviewable after refresh; attention/partial/failed operations remain retryable; an
  active operation loaded from the PII-minimized list may resume status polling.
- Whole-class physical-copy generation runs only after the Canvas operation returns a
  fully `applied` result. Cancellation, partial, attention, or failure does not launch
  it. Differentiated mode does not gain a new physical-output workflow.
- Keep the legacy streaming backend routes for compatibility, but Course Expert's quiz
  buttons must no longer call them or `streamSSE`.
- Do not change the released quiz adapter, ledger contract, storage, Canvas write
  semantics, Forge contracts, or standalone compatibility globals unless a concrete
  contradiction forces a RED handback.

## Scope

- `api/webui/static/push/core.js`
  - register the quiz operation kind;
  - return prepare/review/apply results from the shared content-operation path;
  - render frozen whole/differentiated quiz review details;
  - add bounded PII-minimized polling and Summary progress/retry behavior.
- `api/webui/static/push/quiz.js`
  - replace whole and differentiated streaming calls with the shared ledger path;
  - construct the exact typed payloads above;
  - preserve validation, preview, group loading, delivery controls, busy state,
    banners/logs, and whole-mode physical generation.
- `api/tests/test_webui_template_contracts.py` and/or a narrowly named browser-contract
  test file for useful static regression boundaries. Do not duplicate backend adapter
  lifecycle coverage.
- Update `docs/reference/course-expert-module-map.md` so it accurately routes the new
  quiz and polling ownership.
- Update `docs/reference/operation-ledger-release-status.md` at closure and archive this
  handoff in the same implementation commit.

## Out of scope

- Removing `api/webui/routes/push_streaming.py`, old CLI paths, `streamSSE`, EventSource
  support used by other features, or standalone compatibility pages.
- Backend adapter changes, new routes, schema/persistence changes, migrations, or live
  Canvas probing.
- Redesigning Course Expert layout, navigation, course selection, validation, preview,
  file staging, physical rendering, or other content-type cards.
- Migrating Student Reports, portfolios, downloads, FeedbackExpert, or any scheduled
  workflow to the operation ledger.
- Settings polish or generic refactoring of the large shared browser scripts.

## Reference pattern and routing

- Existing shared operation path:
  `api/webui/static/push/core.js::pushContent`, `prepareOperation`,
  `reviewAndApply`, and `renderOperationsList`
- Current quiz insertion points:
  `api/webui/static/push/quiz.js` handlers for `btn-push` and `btn-push-variants`
- Typed backend boundary:
  `api/operation_ledger/adapters/quiz.py::QuizAdapter.build_payload`
- Polling response:
  `api/webui/routes/operations.py::operation_status_route`
- Backend lifecycle tests:
  `api/tests/test_quiz_operation.py`, `api/tests/test_quiz_tier_operation.py`, and
  `api/tests/test_operation_routes.py`
- Required durable contract/reference:
  `docs/contracts/operation-ledger-contract.md` and
  `docs/reference/course-expert-module-map.md`
- Read project-local `TOOLS.md` before using broad manual inspection.

## Implementation requirements

1. Adapt the shared operation UI without forking it. Keep existing Assignment, Page,
   Rubric, and Quick Assignment behavior compatible while adding result return values,
   quiz review fields, and polling.
2. Replace both live quiz button handlers with typed `content.quiz` preparation through
   the shared path. Reject missing paths, fewer than two differentiated variants, or
   missing group names before preparation. Do not include browser-observed membership
   lists in the preparation request.
3. Present the frozen whole-class review with title, item/point totals, dates, publish,
   module/assignment group, attempts, timing, shuffle/result restrictions, and relevant
   warnings when supplied. Present differentiated review with each frozen variant's
   title/group/student count plus the server's tier warning. Omit absent fields cleanly.
4. Poll the PII-minimized status endpoint during apply/retry and reflect changes in the
   existing Summary rail. Polling failure must stop cleanly and surface a useful local
   message without causing a retry or another Canvas write.
5. Preserve safe cancellation, busy-state restoration, banner/log behavior, and Summary
   refresh. A teacher can cancel frozen review and later apply the prepared operation
   from Summary without re-preparing it.
6. Keep script order, legacy globals, deep links, keyboard tab behavior, and all
   non-quiz Course Expert workflows intact.

## Verification

Run the released quiz and route boundaries plus the affected browser contracts; do not
run the full API or engine suites unless focused failures reveal unexpected coupling.

```powershell
py -m pytest api/tests/test_quiz_operation.py api/tests/test_quiz_tier_operation.py api/tests/test_operation_routes.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
node --check api/webui/static/push/core.js
node --check api/webui/static/push/quiz.js
git diff --check
```

Rendered verification uses a lifespan-disabled local server and performs no preparation,
review, apply, retry, Canvas write, or local operation creation:

- `/course-expert?tab=quiz` at approximately 1366x768 light and 760x900 dark.
- Confirm the Quiz tab/deep link, whole/differentiated mode controls, delivery controls,
  target-course surface, and Summary rail render without page overflow.
- Confirm required globals exist, shared scripts occur once in dependency order, and the
  table/panel layout owns any narrow overflow.
- Confirm the Summary surface can render existing PII-minimized operation states without
  exposing private target data in structural evidence.
- Confirm zero new CanvasExpert browser-console warnings/errors.

## Stop conditions

Stop with RED rather than guessing if:

- `QuizAdapter.build_payload` does not accept the locked whole/differentiated shapes.
- The shared `pushContent` seam cannot return an apply result without changing another
  content type's public behavior.
- Polling requires a new server route, background job system, persistence format, or
  client-defined Canvas instruction.
- Preserving physical generation would require running it before a fully applied result.
- A credential, FERPA, target-resolution, duplicate-write, or ambiguous-retry question is
  not already answered by the released contract and adapter.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **not started**
- Changes are uncommitted
- Files changed: none
- Verification commands and pass/fail/skip counts: not run
- Rendered routes checked: not run
- Deviations from the brief: none
- Remaining blocker or decision: none
