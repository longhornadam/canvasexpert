# Execution brief: Grade New Quiz written responses in PowerGrader

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Teachers can select a Canvas **New Quiz** in PowerGrader and create a local review
session from each student's latest written-response attempt. Grade Myself, Use My AI
Chat, and interactive Auto-Score receive the written item prompts and responses through
the existing PRIVATE/SAFE workflow; teachers can review and save local drafts, but this
release never writes grades or comments to Canvas for a New Quiz.

This is a single vertical improvement: selectable New Quiz -> reliable latest attempt
snapshot -> normal review queue and AI packet. It does not broaden PowerGrader into an
item-level New Quiz grading system.

## Locked decisions

- The source of New Quiz responses is only the official Student Analysis **JSON** report:
  `POST /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/reports` with form data
  `quiz_report[report_type]=student_analysis` and `quiz_report[format]=json`.
- A report creation response may wrap the Progress object in `progress` or return it bare.
  Poll the returned progress URL until it is completed, then download `results.url`.
  HTTP 409 waits/retries within a bounded budget; failed state, timeout, malformed data,
  and 401/403 return a concise actionable error. Never expose report URLs, response URLs,
  tokens, student identities, or response text in errors/logs.
- Fetch New Quiz item metadata from
  `GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items`. Join report
  `item_responses[].item_id` to **nested** `entry.id`, not the outer item ID. Preserve
  API quiz order and use `entry.item_body` plus its exact available point value.
- Group report rows by `student_data.id` and choose the greatest numeric `attempt`.
  A later, late attempt always replaces an earlier on-time attempt.
- Join the selected report row to its Core Canvas submission by `student_data.id == user_id`.
  Preserve current Core `score`, `submitted_at`, `workflow_state`, `late`, and
  `seconds_late`; do not recompute lateness from a due date.
- Freshness is fail-closed. If Core's current submission timestamp is newer than the
  selected report timestamp, generate and read one new report once. If Core remains newer
  or the timestamps cannot be safely compared, return an error rather than grading stale
  work. Do not silently use an older attempt.
- Normalize each selected attempt into the existing submission shape with `body`,
  `attachments`, `user`, current submission fields, and an internal
  `new_quiz_items` list. `body` deterministically presents each written prompt and latest
  response for the local queue. `new_quiz_items` preserves item id, type, prompt, raw
  HTML answer, possible points, earned score, and filename-only file-upload data.
- Retain raw answer HTML only in the local PRIVATE/session path. Convert it through
  `nq_report.html_to_text` at the existing SAFE bundle boundary. Do not make a second AI
  contract: extend `feedback_artifacts.pseudonymize_submissions` to emit one response per
  normalized `new_quiz_items` entry, falling back to its current single-assignment response
  behavior for ordinary submissions.
- New Quiz sessions are immutable snapshots: no late-watch/catch-up, scheduled auto-score,
  scheduled auto-push, interactive push review, or Canvas grade/comment PUT. Store an
  explicit session capability flag (for example `canvas_writeback_supported: false`) and
  enforce it server-side before both push-review and push; hiding buttons alone is not
  sufficient.
- New Quizzes are selectable in the setup picker; Classic Quizzes remain disabled. Server
  dispatch relies on `assignment.is_quiz_lti_assignment is True`, never on browser
  classification alone.
- File-upload answers list only a filename. Do not fetch a file URL or bytes.

## Scope

- Add `api/powergrader/new_quiz_fetch.py` as the focused backend owner for report request,
  progress polling, download/validation, item metadata retrieval, latest-attempt selection,
  freshness retry, and normalization. Use `webui.canvas_client._canvas_headers` for the
  token/base boundary; keep raw request handling and report-specific response tolerance in
  this module rather than modifying the general Canvas client.
- Update `api/powergrader/canvas_fetch.py::fetch_submissions` to retrieve the assignment
  and dispatch to the new module only for `is_quiz_lti_assignment is True`. Its return
  contract remains `(subs, assignment_obj, error)`. Classic Quiz detection returns a clear
  unsupported error if it reaches this server seam.
- Update `api/webui/routes/powergrader.py::pg_start` only to use the normalized fetch
  output and set New Quiz session capabilities/late-watch state. Keep route orchestration
  thin. Do not code-file-enrich normalized New Quiz answers.
- Update `api/feedback_artifacts.py::pseudonymize_submissions` narrowly so normalized
  `new_quiz_items` become the existing multi-response SAFE bundle; ordinary Assignment
  behavior and its latest-submission rule must remain unchanged.
- Update `api/powergrader/session_builder.py::build_students` and
  `api/powergrader/session_builder.py::build_session` only for the attempt/late display
  fields and explicit session capabilities. The structured item metadata must remain local.
- Gate writes in `api/powergrader/session_actions.py::{review_push,push_grades}` from the
  persisted session capability. Gate New Quiz late-watch in
  `api/webui/routes/powergrader_helpers.py::build_late_watch_state` or the immediate start
  caller so its response says that New Quiz snapshots do not support late catch-up.
- Update `api/webui/static/powergrader/setup_core.js` to put New Quizzes in the selectable
  assignments collection while retaining Classic Quizzes as disabled options. Update
  `api/webui/templates/powergrader_setup.html` to give separate, accurate New Quiz and
  Classic Quiz guidance.
- Update `api/webui/static/powergrader/queue_core.js` and, only if necessary,
  `api/webui/static/powergrader/queue_review.js` so New Quiz sessions display canonical
  attempt number and Canvas late status and do not offer one/bulk push. The late-watch
  strip must show the disabled snapshot reason, not an actionable control.
- Add a fully synthetic fixture and focused test module
  `api/tests/test_powergrader_new_quizzes.py`. Synthetic identifiers and prose must be
  fictional; never copy a live report, names, response text, URLs, or tokens.
- Merge documentation changes narrowly into the existing in-progress
  `docs/reference/powergrader-module-map.md`, and update
  `docs/reference/new-quizzes-student-analysis-csv.md`, `api/README.md`, and false
  teacher-facing unsupported wording. Preserve unrelated worktree edits.

## Out of scope

- Any Canvas grade/comment write, item-level score/feedback write-back, or live-write test
  for New Quizzes.
- New Quiz late catch-up, scheduled auto-score/auto-push, or retaining/silently replacing
  a newer attempt in an existing session.
- Downloading file-upload response content; browser automation; SpeedGrader scraping;
  undocumented New Quiz APIs; CSV parser changes; or a scoring-contract redesign.
- Full API/engine suite, branch manipulation, commits, and a live API probe. A later
  read-only live verification needs explicit user authorization and machine-local env vars.

## Reference pattern and routing

- Existing fetch seam: `api/powergrader/canvas_fetch.py::fetch_submissions`
- Existing session/start flow: `api/webui/routes/powergrader.py::pg_start` and
  `api/powergrader/session_builder.py::{build_students,build_session}`
- Existing assignment SAFE bundle: `api/feedback_artifacts.py::pseudonymize_submissions`
- HTML conversion boundary: `api/nq_report.py::html_to_text`
- Quiz classification source: `api/webui/routes/reports.py::{_is_quiz,_quiz_kind}`
- Existing late/watch gate: `api/webui/routes/powergrader_helpers.py::build_late_watch_state`
- Existing write gate seam: `api/powergrader/session_actions.py::{review_push,push_grades}`
- Existing test patterns: `api/tests/test_powergrader_packet.py`,
  `api/tests/test_powergrader_import_results.py`, and
  `api/tests/test_feedback_pipeline.py::test_pseudonymize_submissions_keeps_latest_attempt`
- Durable safety contract: `docs/contracts/feedback-scoring-contract.md`
- Read project-local `TOOLS.md` before broad inspection.

## Implementation requirements

1. Implement the report module as a testable transport/normalization boundary. Inject or
   isolate time/request calls sufficiently for unit tests; use bounded constants for polls
   and 409 retry. Accept wrapped/bare Progress shapes and JSON roots only when they are the
   expected list/row/item structures. Error text should tell the teacher what to do (for
   example, verify active enrollment or use the existing Student Analysis CSV workflow)
   without leaking server payloads.
2. Fetch Core submissions and assignment metadata, dispatch server-side for New Quiz, then
   reconcile report records with Core records. Require usable IDs and timestamps for every
   normalized selected response. Omit unsubmitted students as the existing flow does.
3. For constructed responses, preserve essay prompt/HTML locally, use readable SAFE text,
   and preserve question order. File-upload entries must be represented as filename-only
   local metadata and must not cause network file retrieval. Ensure packet/debug artifacts
   include the selected latest attempt only and no direct student identity or URLs.
4. Build the regular PowerGrader session for all three existing modes. Add visible attempt
   and late badges based on the selected attempt and Canvas Core lateness. For a New Quiz,
   persist the no-write/no-late-watch capabilities and enforce them in every direct route
   as well as the browser UI. Local save/approve/review queue behavior remains available.
5. Keep assignments unchanged: ordinary fetch, bundle generation, queue rendering, existing
   late watch, and existing Canvas push behavior must continue to work.

## Verification

Create a synthetic JSON report fixture with two fictional students. One must have an
on-time attempt 1 and a late attempt 2 with different essay text; include a file-upload
answer. Include deliberately different outer-item and `entry.id` values.

Required focused assertions:

- Report creation handles HTTP 201, wrapped/bare Progress, polling/download, bounded 409,
  failed job, timeout, 401/403, and malformed JSON.
- Latest numeric attempt wins; core/report student IDs join; Core newer-than-report causes
  exactly one regeneration attempt and then a fail-closed error if still stale.
- Item lookup joins nested `entry.id`; raw essay HTML stays local; SAFE bundle has readable
  text and only latest-attempt prompts/responses; names, IDs, tokens, and URLs are absent.
- File-upload filename is represented without a download request.
- New Quiz picker option starts a session; Classic Quiz stays disabled; New Quiz queue shows
  attempt/late fields; New Quiz direct push-review/push and late-watch/late-preview paths
  reject; ordinary assignment push and bundle tests still pass.

```powershell
py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_feedback_pipeline.py api/tests/test_route_contract.py
```

Render the local `/powergrader` setup page and a synthetic/local New Quiz queue session.
Verify New Quiz selection/session creation, canonical attempt and late badges, disabled
write/watch controls, Classic Quiz disabled state, required globals/state, and zero new
browser-console errors. Do not call Canvas during rendered verification.

## Stop conditions

Stop with RED rather than guessing if:

- The live contract assumed by the senior handoff is contradicted by implementation-facing
  fixtures or current code: no complete essay response, no per-attempt rows, no reliable
  ID join, or no safe timestamp reconciliation.
- Supporting New Quiz in AI modes requires a second scoring contract or introduces an
  identity-bearing SAFE artifact.
- A direct Canvas grade/comment PUT, undocumented API, response-file URL, or scheduled
  path becomes necessary for the stated outcome.
- The named insertion points are missing, the existing ordinary Assignment flow regresses,
  or unrelated worktree edits overlap a required seam and cannot be preserved narrowly.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: **uncommitted**
- Files changed: **new Quiz report fetch/normalizer; PowerGrader fetch, session, route, UI, SAFE-bundle, docs, and focused synthetic test seams**
- Verification commands and pass/fail/skip counts: **`py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_feedback_pipeline.py -q` — 43 passed; `py -m py_compile api/powergrader/new_quiz_fetch.py api/tests/test_powergrader_new_quizzes.py` and `git diff --check` passed. Synthetic transport tests cover wrapped/bare Progress, 409 retry budget, failed/timeout/malformed/auth errors, and one freshness regeneration followed by fail-closed rejection. The synthetic nested `student_data.attempt` / `student_data.submitted_at` regression fixture proves latest-attempt selection and freshness behavior. No live request was made in this correction.**
- Rendered routes checked: **The local `/powergrader` setup page rendered in the in-app browser with no console errors. A senior-created temporary fictional New Quiz session rendered at `/powergrader/session/synthetic-new-quiz-browser-check-20260713`; it visibly showed `New Quiz · Attempt 2` and `Late in Canvas`, displayed the disabled late-watch reason, omitted one/bulk Canvas push controls, and had zero browser-console errors. The temporary session was removed immediately afterward. No course was selected and no Canvas request occurred.**
- Deviations from the brief: **none for this correction; nested Student Analysis fields are preferred with row-level fallbacks retained.**
- Remaining blocker or decision: **the authorized comment-only live test is complete; New Quiz score writes, item-level writes, late catch-up, and scheduled paths remain unproven and unauthorized.**

### Authorized live verification addendum

- The teacher explicitly authorized a live read of course `92308`, assignment `3530751`,
  and a comment-only New Quiz assignment-level write for its two fictional test students.
- The live report returned two Core submissions and two Student Analysis rows after the
  nested `student_data` correction. Two comment-only `PUT` requests succeeded and a
  subsequent read verified both exact comments. No posted grade, score, or other mutation
  was sent.
- This proves only comment-only assignment-level delivery for the authorized test. It does
  not authorize or prove New Quiz score writes, item-level writes, late catch-up, or any
  scheduled path.
