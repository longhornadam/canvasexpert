# Execution brief: retire obsolete QuizForge streaming HTTP writes

Status: **ready for implementation**

Risk: **medium**

Executor: **external VS Code agent**

## Outcome

Course Expert has one browser live-write path for quizzes: typed operation-ledger
prepare/review/apply with polling status. The four obsolete SSE HTTP wrappers around
the manual QuizForge CLI are deleted, so they can no longer offer an uncheckpointed
Canvas-write path from the local browser server.

The direct CLI commands `qf_pusher.py` and `push_tiers.py` remain supported manual
teacher tools. Quiz dry-run preview and Download Work streaming also remain available.
This removes a parallel write surface and its related documentation without changing
the canonical Workbench flow.

## Locked decisions

- Delete these four local HTTP routes and their handlers:
  - `GET /api/push/stream`
  - `GET /api/push-multi-whole/stream`
  - `GET /api/push-variants/stream`
  - `GET /api/push-multi/stream`
- The routes have no current browser, template, CLI, routine, or repository-doc caller.
  They are not a supported external API contract: Canvas Expert is local-only and the
  supported CLI invokes `qf_pusher.py` / `push_tiers.py` directly rather than through
  the local HTTP server.
- Retain the direct manual CLIs unchanged. Do not modify `api/qf_pusher.py`,
  `api/push_tiers.py`, `api/webui/runner.py`, their credentials, or their CLI behavior.
- Retain `POST /api/push/preview` as a local dry-run planner. Move its small handler
  into `push_validation.py`, which owns the adjacent validation/preview path; do not
  create a replacement `push_preview.py` module.
- Delete `push_streaming.py` after moving preview. Its only remaining purpose would be
  the removed endpoints, so preserving the file would retain a misleading ownership
  boundary.
- Retain `push/core.js::streamSSE`; Download Work uses it for
  `/api/submissions/download/stream`. Do not modify browser assets in this batch.
- Preserve the existing Quiz browser contract test's meaningful assertions that Quiz
  uses typed operation preparation and does not call `streamSSE`, direct write review,
  or send browser-observed student IDs. Remove only its now-pointless assertions for
  the four deleted literal route strings.

## Scope

- Move `api_push_preview` from `api/webui/routes/push_streaming.py` to
  `api/webui/routes/push_validation.py`, preserving request fields, `resolve_env`,
  `QF_PUSH_SETTINGS`, `qf_pusher.py <path> --dry-run`, and the JSON response shape.
- Delete `api/webui/routes/push_streaming.py`.
- In `api/webui/routes/push.py`, remove the streaming-route import and registration;
  keep validation-route registration and module/assignment-group routes intact.
- Remove the four route entries from `api/tests/test_route_contract.py::EXPECTED`.
- In `api/tests/test_webui_template_contracts.py`, remove only the loop that asserts
  those four literal routes are absent from `quiz.js`; retain the rest of
  `test_quiz_push_uses_typed_operation_payloads_not_streaming_writes`.
- Update only the current ownership/reference statements in:
  - `docs/reference/course-expert-module-map.md`
  - `docs/reference/workbench-canonical-flow-map.md`
  - `docs/reference/operation-ledger-release-status.md`
  - `docs/reference/quiz-operation-design.md`
  - `api/webui/README.md`
  They must identify typed operations as the sole browser live-write path, direct CLI
  as an explicit manual path, and `push_validation.py` as the preview owner. Remove
  statements that legacy browser streaming remains active or that either Quiz UI uses
  it.
- Record the completed batch in the Workbench canonical-flow map, then archive this
  handoff to `docs/handoffs/archive/` after its execution result is complete.

## Out of scope

- Do not change operation-ledger adapters, operation contracts, persistence records,
  retry/reconciliation, polling behavior, Canvas request sequencing, or review UI.
- Do not modify `streamSSE`, Download Work routes, Feedback streaming, student report
  streaming, or any other SSE endpoint.
- Do not add fail-closed/410 replacement routes, redirects, endpoint aliases, or
  compatibility wrappers. The retired endpoints may return 404.
- Do not alter QuizForge parse/validate/physical-render behavior or authoring contracts.
- Do not make Canvas or OpenRouter requests, run live CLI pushes, start routines, or
  inspect private workspace data.
- Do not run a full API suite solely because this changes four retired local routes.

## Reference pattern and routing

- Browser canonical path: `api/webui/static/push/quiz.js::pushQuiz`
- Shared operation gateway: `api/webui/static/push/core.js::pushContent`
- Retained dry-run behavior:
  `api/webui/routes/push_streaming.py::api_push_preview` (move without redesign)
- New destination owner: `api/webui/routes/push_validation.py::register_validation_routes`
- Retained direct CLI owners: `api/qf_pusher.py::main`, `api/push_tiers.py::main`
- HTTP surface contract: `api/tests/test_route_contract.py::EXPECTED`
- Quiz browser safety boundary:
  `api/tests/test_webui_template_contracts.py::test_quiz_push_uses_typed_operation_payloads_not_streaming_writes`
- Current routing map: `docs/reference/course-expert-module-map.md`
- Read project-local `TOOLS.md` before broad inspection. Use `rg` to prove that no
  source registration or caller for a deleted route remains.

## Implementation requirements

1. **Retire the wrappers, not the CLI.** Delete the four route handlers in full. Their
   subprocess invocation, temporary manifests, SSE formatting, multi-course fan-out,
   and browser request shapes must not be relocated into another HTTP module.

2. **Keep preview small and honest.** Transfer the existing preview handler mechanically
   to `push_validation.py`. Its dry-run command must remain `qf_pusher.py`, the selected
   path, and `--dry-run`; it must not call the operation apply endpoint or any Canvas
   write route.

3. **Remove dead dependencies with the dead module.** After deletion, remove only
   imports that became unused because of `push_streaming.py` (for example its router
   registration). Do not consolidate unrelated push modules or browser utilities.

4. **Prune only superseded tests.** Delete the four HTTP snapshot entries and the four
   literal-string assertions. Keep the typed-operation, no-`streamSSE`, no-direct-write,
   and no-student-ID assertions because they still protect the teacher-visible safety
   boundary independently of the removed route names.

5. **Correct current docs, not history.** The module maps and live-path references must
   no longer route a debugging session to a deleted file. Historical archived handoffs
   remain unchanged. The durable operation design must not claim a browser uses legacy
   streaming or that an active compatibility response remains.

6. **Self-audit the boundary.** It is acceptable for `qf_pusher.py`, `push_tiers.py`,
   and `streamSSE` to remain. It is not acceptable for the four removed paths,
   `register_streaming_routes`, `push_streaming.py`, or a browser live-write use of the
   manual CLI wrappers to remain outside historical archive documents.

## Verification

```powershell
py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
rg -n '/api/push/stream|/api/push-multi-whole/stream|/api/push-variants/stream|/api/push-multi/stream|register_streaming_routes|push_streaming' api docs/reference --glob '!docs/handoffs/archive/**'
git diff --check
```

The caller search must return no live source or current-reference documentation for the
deleted HTTP wrappers. It may return the Workbench map only if it clearly records that
the routes were removed; it must not present them as active.

No browser rendering check is required: the Course Expert browser assets and canonical
typed-operation flow are unchanged. Do not replace the focused command with a full-suite
pass count.

## Stop conditions

Stop with RED rather than guessing if:

- A live browser, template, CLI, routine, or supported local client calls any deleted
  streaming route.
- Moving preview would change its dry-run command, make it perform a Canvas write, or
  require a new request/response contract.
- Removing the wrappers requires a change to CLI credentials, operation-ledger behavior,
  Canvas write safety, or private workspace storage.
- The focused tests reveal a regression outside this retired HTTP boundary.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: uncommitted
- Files changed, deleted, and moved:
  - **Deleted:** `api/webui/routes/push_streaming.py` (147 lines, 4 streaming handlers + preview)
  - **Moved (preview):** `api_push_preview` handler relocated to `api/webui/routes/push_validation.py` (added `config`, `runner` imports; preview route registered alongside validation routes)
  - **Updated:** `api/webui/routes/push.py` — removed `register_streaming_routes` import and call; updated docstring
  - **Updated:** `api/tests/test_route_contract.py` — removed 4 `EXPECTED` entries (`/api/push/stream`, `/api/push-multi-whole/stream`, `/api/push-variants/stream`, `/api/push-multi/stream`)
  - **Updated:** `api/tests/test_webui_template_contracts.py` — removed 4 literal-string assertions for deleted routes; retained typed-operation, no-`streamSSE`, no-direct-write, and no-student-ID assertions
  - **Updated:** `docs/reference/course-expert-module-map.md` — removed `push_streaming.py` ownership; added preview to `push_validation.py`; updated symptom routing
  - **Updated:** `docs/reference/operation-ledger-release-status.md` — changed "Browser migration deferred" to "Browser migration complete"
  - **Updated:** `docs/reference/quiz-operation-design.md` — changed "Both Quiz UI surfaces call GET streaming routes" to "Course Expert Quiz UI calls typed operation-ledger prepare/review/apply"
  - **Updated:** `api/webui/README.md` — removed `push_streaming.py` from route listing; fixed stale reference
  - **Updated:** `docs/reference/workbench-canonical-flow-map.md` — moved streaming batch to "Completed retirements"; removed "Retirement candidates" section
- Verification commands and pass/fail/skip counts:
  - `py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py` — **79 passed** in 1.54s
  - `rg -n '/api/push/stream|/api/push-multi-whole/stream|/api/push-variants/stream|/api/push-multi/stream|register_streaming_routes|push_streaming' api docs/reference --glob '!docs/handoffs/archive/**'` — returned only past-tense documentation references in `workbench-canonical-flow-map.md`, `course-expert-module-map.md`, and `quiz-operation-design.md`. Zero live source code references.
  - `git diff --check` — clean
- Caller-search result: No browser, template, CLI, routine, or repository-doc caller of the deleted streaming routes was found. The `rg` caller search confirmed zero live references outside historical archive documents.
- Confirmation that direct CLI and `streamSSE` were unchanged: `git diff --stat` confirms `api/qf_pusher.py`, `api/push_tiers.py`, `api/webui/runner.py`, `api/webui/static/push/core.js`, and `api/webui/static/push/download.js` are not in the diff.
- Deviations from the brief: None.
- Remaining blocker or decision: None.
