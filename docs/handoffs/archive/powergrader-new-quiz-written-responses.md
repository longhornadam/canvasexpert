# Senior handoff: PowerGrader support for New Quiz written responses

Status: **ready for senior design and executor briefing**

Risk: **high**

Senior owner: **Terra**

Expected executor: **Luna or an external VS Code agent, after Terra writes the implementation brief**

## Outcome

Make a Canvas New Quiz with constructed responses selectable in PowerGrader and load
each student's latest submitted attempt into the normal review queue. Grade Myself,
Use My AI Chat, and interactive Auto-Score should receive the written question prompts
and responses through the existing PRIVATE/SAFE workflow; the teacher remains the
reviewer.

This is the decisive product improvement: live testing proved that a normal teacher PAT
can retrieve complete New Quiz essay responses through the official Student Analysis
JSON report API. Terra should lead this to implementation, not repeat feasibility
research.

## Locked decisions

- **Latest attempt is canonical.** Group report rows by Canvas student ID and select the
  greatest numeric attempt. Never prefer an earlier on-time attempt over a later attempt.
- The canonical attempt can be late even when an earlier attempt was on time. Preserve
  Canvas's current submission `late`/`seconds_late` state for the selected student; do
  not recompute lateness from the assignment's base due date because overrides may exist.
- Add a freshness guard: compare the selected report attempt/timestamp with the current
  Core Submission row. If Core Canvas shows a newer submission than the freshly generated
  report, regenerate/retry once and then fail clearly rather than grading stale work.
- Use the **official Student Analysis JSON report** as the response source. Do not build
  the feature on the variable-width CSV, browser automation, SpeedGrader scraping, or
  Core Submission `body`/`attachments`.
- Use the official New Quiz Items API for question prompts and points. Join report
  `item_id` to the item's nested `entry.id`; it does **not** join to the outer item ID.
- For this first implementation, file-upload answers may appear as filename-only
  attachments. Actual file download is a nice-to-have and is deliberately excluded.
- Normalize the selected attempt into PowerGrader's existing submission/session flow.
  Preserve structured New Quiz item metadata internally, but score and post at the
  **assignment total** level; do not invent New Quiz item-level write-back.
- Classic Quizzes remain unsupported and disabled in the setup picker.
- New Quiz late-watch/catch-up and scheduled auto-score/auto-push remain unsupported in
  this first implementation. A session is an explicit snapshot; if a later attempt is
  submitted after session creation, the teacher creates a fresh session. Do not silently
  append or retain the superseded attempt.
- Do not enable interactive Canvas grade/comment push for New Quiz sessions until a
  separately authorized live-write test proves the existing assignment-level PUT is safe
  and defines its effect on New Quiz grades. Local review and AI drafts may ship first.
- No live course IDs, student data, response text, launch tokens, report URLs, or storage
  URLs may be committed or logged. Live IDs must be supplied through machine-local
  environment variables.

## Proven live contract

These facts were established on an active two-student practice course with the saved
teacher PAT. No student content was retained in the repository.

1. Create a fresh report:

   `POST /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/reports`

   Form data:

   - `quiz_report[report_type]=student_analysis`
   - `quiz_report[format]=json`

   The live tenant returned HTTP 201. The newer public-doc example using JSON body
   `{"report":{"type":"student_analysis"}}` returned HTTP 400, so the form contract
   above is primary. Keep request/response parsing tolerant rather than binding to one
   wrapper shape.

2. The create response was `{ "progress": { ... } }`, although Canvas documentation
   describes a bare Progress object. Poll the progress `url` until `workflow_state` is
   `completed`; then fetch `results.url`. Handle failed jobs, bounded timeout, and HTTP
   409 (another report is generating) with a bounded wait/retry. Do not spin forever.

3. The downloaded JSON root was a list with one row per student attempt. Relevant shape:

   - `student_data.id`, `student_data.name`, `student_data.sis_id`
   - `student_data.submitted`, `student_data.elapsed`, `student_data.attempt`
   - `item_responses[]`
   - each item response: `item_id`, `item_type`, `answer`, `score`

   Essay `answer` values contained the complete HTML response. File-upload `answer`
   values contained the original filename only.

4. Fetch quiz metadata from:

   `GET /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/items`

   Join report `item_id` to nested `entry.id`. Use `entry.item_body` as the prompt and
   the API's exact point value when present. Preserve quiz order.

5. Report `student_data.id` matched Core Submission `user_id` exactly. The current Core
   Submission is still needed for user metadata, current score, submitted timestamp,
   workflow state, and Canvas-calculated lateness. For New Quizzes its submission type is
   `basic_lti_launch`; its `body` and `attachments` are empty and are not response sources.

6. PAT access is enrollment-sensitive. The report API worked for an active enrollment;
   known concluded-course behavior can be HTTP 403. Return an actionable teacher-facing
   error and leave the manual Student Analysis CSV workflow available as fallback. Do not
   claim universal New Quiz access.

Official references:

- `https://developerdocs.instructure.com/services/canvas/resources/new_quizzes_reports`
- `https://developerdocs.instructure.com/services/canvas/resources/new_quiz_items`
- `https://community.instructure.com/en/kb/articles/661090-how-do-i-view-reports-for-a-quiz-in-new-quizzes`

## Scope for Terra's implementation brief

- Add one focused backend owner under `api/powergrader/` for report creation, progress
  polling, JSON validation, item metadata retrieval, latest-attempt selection, freshness
  checking, and normalization. Keep `api/webui/routes/powergrader.py` orchestration-only.
- Branch in `api/powergrader/canvas_fetch.py::fetch_submissions` or a nearby dispatcher
  after the assignment object confirms `is_quiz_lti_assignment`. Server-side validation
  must not trust only the browser's quiz classification.
- Produce one normalized submission per student with the same identity/current-score
  fields consumed today plus:

  - a deterministic body containing each written question prompt and latest response;
  - canonical attempt number and submitted timestamp;
  - Canvas lateness metadata from the current Core Submission;
  - structured New Quiz item records for diagnostics/future use;
  - filename-only attachment metadata for file-upload responses.

- Keep raw response HTML for the sandboxed local queue display. Use the existing
  `api/nq_report.py::html_to_text` boundary when text enters an AI bundle. Do not extend
  the positional CSV parser to parse JSON.
- Reuse the current PRIVATE vault and SAFE packet machinery. Terra must decide the
  narrowest change that lets `api/powergrader/ai_workflow.py` produce an overall
  assignment-scoring bundle from the normalized latest attempt without losing question
  prompts. Do not create a second AI contract.
- Update `api/powergrader/session_builder.py::build_students` and
  `api/webui/static/powergrader/queue_core.js::renderStudent` only as needed to display
  canonical attempt and late status. The teacher must be able to see which attempt is
  being graded.
- In `api/webui/static/powergrader/setup_core.js`, make New Quizzes startable while
  leaving Classic Quizzes disabled. Replace the blanket unsupported hint in
  `api/webui/templates/powergrader_setup.html` with accurate per-kind guidance.
- Gate New Quiz push controls, late-watch controls, and scheduled paths explicitly; do
  not rely on the current UI merely hiding them by accident.
- Update durable docs after implementation:

  - `docs/reference/powergrader-module-map.md`
  - `docs/reference/new-quizzes-student-analysis-csv.md` (API JSON verified, CSV leading
    columns vary, all attempts are rows, report item ID joins to `entry.id`)
  - `api/README.md` and teacher-facing unsupported wording that the implementation makes
    false

## Out of scope

- Undocumented native New Quizzes launch/session APIs.
- Downloading uploaded photos or other file-upload bytes.
- Browser automation or signed-in SpeedGrader scraping.
- New Quiz item-level score or feedback write-back.
- Proving or enabling assignment-level Canvas writes.
- New Quiz late catch-up, scheduled auto-score, or auto-push.
- Replacing the manual CSV workflow used by FeedbackExpert/portfolio features.
- Broad refactors of `nq_report.py`, the scoring contract, or PowerGrader session storage.

## Reference pattern and routing

- Route orchestration: `api/webui/routes/powergrader.py::pg_start`
- Submission fetch seam: `api/powergrader/canvas_fetch.py::fetch_submissions`
- Session shaping: `api/powergrader/session_builder.py::build_students`
- AI bundle boundary: `api/powergrader/ai_workflow.py::run_ai_workflow`
- Existing constructed-response bundle shape:
  `api/feedback_artifacts.py::pseudonymize`
- Existing assignment bundle path and latest-submission test:
  `api/feedback_artifacts.py::pseudonymize_submissions` and
  `api/tests/test_feedback_pipeline.py::test_pseudonymize_submissions_keeps_latest_attempt`
- HTML-to-text boundary: `api/nq_report.py::html_to_text`
- Setup classification: `api/webui/static/powergrader/setup_core.js`
- Queue rendering: `api/webui/static/powergrader/queue_core.js::renderStudent`
- Module ownership map: `docs/reference/powergrader-module-map.md`
- Safety contract: `docs/contracts/feedback-scoring-contract.md`
- Read `TOOLS.md` before broad inspection.

At handoff creation the worktree already contained substantial unrelated user changes,
including modifications to `docs/reference/powergrader-module-map.md`. Preserve them and
merge narrowly; never reset or overwrite them.

## Required verification in Terra's executor brief

Create a fully synthetic JSON fixture—never copy the live report. It must cover two
students and at least one student with attempt 1 on time and attempt 2 late, with different
essay text in each attempt.

Required focused evidence:

- HTTP 201 report creation, wrapped and bare Progress parsing, polling, completed download.
- HTTP 409 bounded retry; failed job; timeout; 401/403 actionable error; malformed JSON.
- Latest numeric attempt wins even when the prior attempt was on time.
- Freshness mismatch never falls back to the older report attempt.
- Report student ID joins Core Submission user ID.
- Report item ID joins nested `entry.id`, not the outer item ID.
- Essay HTML is preserved locally and converted to readable text in SAFE AI artifacts.
- AI packet and debug artifacts contain only the latest attempt and no real names, IDs,
  tokens, report URLs, or response URLs.
- File-upload filename is shown without attempting a download.
- New Quiz is selectable; Classic Quiz remains disabled.
- New Quiz queue shows attempt and late state; push, late-watch, and scheduled controls
  remain unavailable.
- Existing Assignment PowerGrader behavior remains unchanged.

Suggested affected test matrix, adjusted by the executor to the actual diff:

```powershell
py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_feedback_pipeline.py api/tests/test_route_contract.py
```

Because shared setup and queue browser code changes, render `/powergrader` and one
synthetic/local New Quiz session route. Verify New Quiz selection, session creation,
latest-attempt/late badges, disabled write/watch controls, and zero new browser-console
errors. Source-text tests do not substitute for this check.

One final read-only live verification may use machine-local environment variables such as
`CE_LIVE_NQ_COURSE` and `CE_LIVE_NQ_ASSIGNMENT`, with explicit user authorization. It may
generate/download a report but must print only counts, item types, join booleans, and
attempt numbers—never identities or responses. No live grade/comment PUT is authorized by
this handoff.

## Stop conditions

Stop with RED rather than guessing if:

- The live JSON report no longer contains complete essay answers or per-attempt rows.
- Core Submission and report freshness cannot be reconciled without choosing stale work.
- Supporting New Quiz AI modes requires a second scoring contract or leaks identity into
  SAFE artifacts.
- Assignment-level grade/comment writes are required to satisfy acceptance.
- The implementation requires undocumented native APIs, live file URLs, or student files.
- Existing behavior contradicts the latest-attempt or Canvas-lateness decisions.
- Unrelated worktree changes overlap a required seam and cannot be preserved safely.

## Terra lead sequence

1. Read this handoff, `AGENTS.md`, `TOOLS.md`, and the routed reference files only.
2. Inspect the current diff at the named seams and resolve any overlap without discarding
   user work.
3. Convert this senior handoff into one executable implementation brief using
   `docs/handoffs/HANDOFF_TEMPLATE.md`; assign Luna or the user's external VS Code agent.
4. Keep one executor active, return yellow corrections to that same executor, and accept
   based on the required evidence rather than commissioning an automatic reviewer.
5. After GREEN, bring the user a separate proposal for an authorized assignment-level
   New Quiz grade/comment write test. Do not fold that live-write experiment into response
   ingestion.

## Return report

Terra should record the implementation handoff path and the executor's final traffic-light
result here when this senior handoff has been fulfilled.

### Execution result

- Traffic light: **not started**
- Implementation handoff: `docs/handoffs/powergrader-new-quiz-written-responses-luna.md` (ready for Luna)
- Commit hash: **none**
- Files changed: **senior and Luna handoffs only**
- Verification: **live read-only feasibility already established; implementation not started**
- Deviations: **none**
- Remaining decision: **assignment-level New Quiz write behavior requires a later, separately authorized live test**
