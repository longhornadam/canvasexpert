# Execution brief: Complete attachment-safe PowerGrader scoring and course-first storage

Status: **completed and accepted — archived during closure**

Risk: **high**

Executor: **Luna (same working context)**

## Outcome

Teachers can start an ordinary-assignment or New Quiz PowerGrader session without any
student upload being silently omitted, attached to an ambiguous attempt, or bypassing
the shared evidence-eligibility gate. Mixed classes keep text-only students in the
normal batch while media-bearing students are scored in isolated requests; one media
request failure leaves successful drafts intact and clearly returns the affected student
to manual review.

This is an acceptance repair of the implementation recorded in
`docs/handoffs/archive/course-first-workspace-and-new-quiz-files.md`. The existing dirty
working tree remains the starting point. Preserve it, correct the defects listed here,
and do not reopen the completed workspace migration or New Quiz transport design.

The rejected implementation stays **YELLOW** until every code defect below is corrected.
Rendered verification is a separate mandatory gate; a browser-tool failure does not
convert an implementation defect into a verification-only limitation.

## Locked decisions

### Execution and acceptance

- Continue with the same Luna executor and current working tree. Do not reset, revert,
  or reconstruct the prior implementation.
- This brief is the only active execution brief. The rejected parent brief is historical
  context under `docs/handoffs/archive/`; do not reactivate it.
- Do not create a branch or commit unless the user separately requests one. Preserve all
  unrelated changes.
- GREEN requires the focused regressions, full API suite, static checks, and rendered
  route verification in this brief. If code/tests pass but the browser runtime fails
  before page connection, return YELLOW with the exact error.

### One evidence model, two transport boundaries

- `api/powergrader/student_attachments.py` remains the one shared **post-download content
  router** for ordinary-assignment and New Quiz uploads. It owns content validation,
  text/DOCX/raster routing, extracted-text sidecars, metadata-stripped media derivatives,
  and fail-closed eligibility.
- Do not force ordinary Canvas attachments and New Quiz signed-storage URLs through one
  network helper. Ordinary attachments use Canvas-authenticated requests; New Quiz signed
  storage uses the existing clean client with no Canvas/New Quiz authorization headers.
- Neither transport may persist a source/redirect URL, authorization header, cookie,
  token, JWT, signature, or capability value in submissions, sessions, errors, fixtures,
  logs, debug receipts, or workspace artifacts.
- Every upload observed in Canvas/Student Analysis produces exactly one top-level
  attachment evidence record for eligibility, whether it succeeds or fails. A failure
  record is expected evidence that was unavailable; it must not disappear.
- Matching `new_quiz_items[].files` and top-level `attachments[]` records agree on status
  and local metadata. A file must never exist only in the item-local list.
- Record the expected attachment count before download work. Eligibility compares it to
  normalized evidence and fails closed on missing, extra, pending, failed, local-only,
  corrupt, or over-budget evidence.
- Typed-response-only work with an expected count of zero remains eligible. A no-file
  response is not held merely because the optional native file service is unavailable.

### Ordinary assignment uploads

- Retire production use of `canvas_fetch.enrich_with_code_files`. Replace all live callers
  with one attachment-ingestion entry point that receives enough context to resolve the
  canonical course/assignment/student/attempt destination.
- Download **all** ordinary Canvas attachments for local teacher access, not only code
  extensions. TXT/MD/code, DOCX, supported raster, PDF, legacy Office, and unknown formats
  all receive a canonical original path and normalized metadata; the shared router alone
  decides AI eligibility.
- New ordinary writes use:

  ```text
  Courses/<course name or nickname> — <course id>/
    Assignments/<assignment name> — <assignment id>/
      Student Work/<student display name> — <Canvas user id>/
        Attempt <n>/<original filename>
  ```

- Use the positive Canvas submission attempt when present, otherwise attempt `1`. Preserve
  the original filename only in this PRIVATE tree, using existing sanitizing/collision
  behavior.
- Stream ordinary downloads to atomic partial files, enforce timeouts, verify declared
  size when supplied, clean partials on failure, and avoid buffering arbitrary originals
  in the downloader. Extraction may read the completed file under router limits.
- Normalize at least: filename, local path when preserved, declared/actual size, download
  status, detected type, extraction status/path, attempt, assignment/item link,
  `ai_eligible`, `local_only`, warnings, and a non-sensitive failure code/message.
- `code_files` may remain readable for old sessions, but no new start, late catch-up, or
  scheduled autoscore path may populate or depend on the legacy downloader. Do not add
  extracted attachment text twice to an AI response.

### New Quiz expected evidence and failure propagation

- Student Analysis remains authoritative for the selected latest written-response attempt
  and expected file-bearing items. Native results supply bytes only after an unambiguous
  same-attempt join.
- Create URL-free expected placeholders before native retrieval. Represent each expected
  file once in its item and once in top-level eligibility by completion; update/replace
  placeholders instead of appending duplicate success records.
- `new_quiz_files_error` may remain a UI summary, but it is never the sole representation
  of unavailable evidence. Corresponding top-level records must be failed/ineligible.
- Propagate failures for missing session/destination context; launch/ENV/CSRF/JWT/native
  stages; participant/result/quiz-session stages; zero or multiple same-attempt matches;
  malformed/mismatched item results; signed download/redirect/HTTP/storage/size/finalize
  errors; and local extraction/validation errors.
- A global launch failure marks all expected files for affected file-bearing students
  failed. A failure after global context exists marks only that student and continues
  unaffected students.
- Written responses remain visible on retrieval failure, but the affected student is held
  from automated scoring. UI copy states both facts.

### Unambiguous participant-session join

- Collect candidate participant sessions across every participant row for a Canvas user.
  Resolve candidates only far enough to get authoritative result ID and attempt.
- Do not request item results or download files until candidate collection is complete.
- Require exactly one candidate matching `new_quiz_attempt`:
  - zero: mark that student's expected evidence unavailable;
  - one: fetch item results and continue;
  - multiple: set a non-sensitive `ambiguous_attempt_join`-style error, select neither,
    fetch no item results, and download nothing.
- Duplicate participant rows for one user participate in the same ambiguity check. A
  loop-local `break` is not sufficient.
- Reconcile native results to Student Analysis item IDs. Count/item mismatch holds the
  student; never choose a partial subset for AI. Unambiguously joined originals may still
  be preserved locally when safe, but eligibility remains false.

### Readable course folder ownership

- Course display text comes from saved Canvas Expert configuration: `nickname`, then
  Canvas course `name`, then course ID only as fallback.
- Resolve it server-side by course ID. Do not trust a client path label or expect the
  assignment response to contain `course_name`.
- Add/reuse one narrow saved-course lookup helper and thread the display name through
  initial start, ordinary ingestion, New Quiz retrieval, AI artifact paths, late catch-up,
  and scheduled autoscore session creation.
- The ID remains the suffix. Test `Fictional Biology — course-1`, not
  `course-1 — course-1`, when saved configuration exists.

### Mixed text/media OpenRouter scoring

- Partition scrubbed `llm_bundle.students` into text-only students (no response media) and
  media-bearing students (at least one response with media).
- Score the entire text group once with the existing contract, then every media student in
  a separate one-student request. Media presence must never remove text students.
- Preserve shared directions, source context, rubric, persona, prompts, and feedback
  pattern in both lanes; only the `students` list changes.
- Catch exceptions around each media call, continue later students, and retain prior
  successes. Never place one student's media/result into another request/result.
- Re-identify all successful results together. A failed media student gets no AI draft.
- Return a bounded internal failure map keyed by Canvas user ID after vault lookup. Persist
  an optional backward-compatible `ai_scoring_error`-style queue field with generic copy;
  never persist keys, bodies, paths, other pseudonyms, or raw exceptions there.
- The queue says no AI draft was produced and manual grading is needed. Privacy/audit copy
  reports requested, successful, and failed counts truthfully.
- Existing text-batch failure may remain batch-level. Mixed/media runs preserve partial
  success and never return early on one media exception. If every provider request fails
  and no result exists, overall assisted failure may remain, but only after every isolated
  media request was attempted and private failure evidence recorded.
- Do not change the Feedback Scoring Contract. Failure/session metadata is local.

### Safety and privacy

- Originals/real-name paths remain PRIVATE. Only scrubbed text and validated,
  metadata-stripped derivatives may enter AI packets or OpenRouter.
- Use unmistakably synthetic fixtures. Never print or fixture real student/course data,
  district URLs, Canvas tokens, signed URLs, JWTs, cookies, or native/result tokens.
- Preserve the teacher acknowledgement and honest pseudonymization wording.
- Do not add/broaden Canvas grade/comment writes, New Quiz write-back, scheduled auto-push
  eligibility, or New Quiz late-watch.

## Scope

### Required production seams

- `api/powergrader/canvas_fetch.py`: replace extension-only enrichment; normalize all
  ordinary success/failure evidence; keep authenticated transport separate.
- `api/powergrader/student_attachments.py`: include expected count and download/extraction
  states in eligibility; retain shared routing ownership.
- `api/powergrader/new_quiz_fetch.py`: thread course display text; create/update expected
  evidence; collect candidates before download; propagate global/per-student failures.
- `api/feedback_artifacts.py`: carry expected/failure metadata into packet eligibility and
  route ordinary extracted text/media exactly once.
- `api/powergrader/ai_workflow.py`: split lanes, isolate media failures, preserve/reidentify
  partial results, and shape bounded failure metadata.
- `api/powergrader/ai_workflow_support.py`: extend the internal result only as needed for
  per-student failure handoff.
- `api/powergrader/session_builder.py`: persist expected-count eligibility and generic
  optional AI failure state.
- `api/webui/routes/powergrader.py`: resolve course display once and pass full ingestion/
  failure context through initial session creation.
- `api/webui/routes/powergrader_late.py`: cut late catch-up over from the code-only path and
  preserve AI failure state.
- `api/webui/routes/routines_powergrader.py`: cut scheduled autoscore over to the shared
  path without changing auto-push policy/claims/writes.
- `api/webui/config/courses.py` and `api/webui/config/__init__.py`: add/export the narrow
  server-side course display resolver if no equivalent exists.
- `api/webui/static/powergrader/queue_core.js`: render held/failure states generically and
  safely.

### Required tests

- Extend `api/tests/test_powergrader_new_quizzes.py` for failure propagation, ambiguity,
  and readable path ownership.
- Extend `api/tests/test_student_attachments.py` for download-status and expected-count
  eligibility.
- Add `api/tests/test_powergrader_attachment_workflow.py` if existing modules cannot
  cleanly hold ordinary routing and mixed scoring cases.
- Update `api/tests/test_powergrader_late_catchup.py` and
  `api/tests/test_powergrader_scheduled_autoscore.py` for the replacement seam/failure map.
- Extend route/session tests only as needed for backward-compatible optional fields.

### Documentation and durable state

- Update `docs/reference/powergrader-module-map.md` when symbol ownership changes.
- Update this handoff's `Execution result` before return; distinguish browser-runtime
  failure from implementation/test state.
- Do not create another active correction handoff. Return corrections to the same Luna
  context and record them here.

## Out of scope

- Reworking completed workspace/downloader/vault/Feedback Tools/model-picker work.
- Live Canvas, New Quiz, or OpenRouter probes.
- PDF OCR/extraction, legacy Office extraction, audio/video, or new AI formats.
- Changing Feedback Scoring/OpenRouter public contracts or Canvas client architecture.
- Moving/deleting legacy data or renaming existing canonical folders.
- Redesigning PowerGrader UI, scheduled jobs, late-watch, or auto-push policy.
- New download frameworks, workers, databases, registries, or migration infrastructure.
- Broad unrelated cleanup.

## Reference pattern and routing

- Rejected implementation: `docs/handoffs/archive/course-first-workspace-and-new-quiz-files.md`
- Workspace paths: `api/webui/workspace.py::attempt_folder`,
  `api/webui/workspace.py::named_id_folder`
- Course source: `api/webui/config/courses.py::saved_courses`
- Initial orchestration: `api/webui/routes/powergrader.py::pg_start`
- Late orchestration: `api/webui/routes/powergrader_late.py::_run_late_catchup_score`
- Scheduled orchestration:
  `api/webui/routes/routines_powergrader.py::run_powergrader_autoscore_routine`
- Ordinary defect: `api/powergrader/canvas_fetch.py::enrich_with_code_files`
- New Quiz seams: `api/powergrader/new_quiz_fetch.py::_native_file_transport`,
  `api/powergrader/new_quiz_fetch.py::_download_item_files`,
  `api/powergrader/new_quiz_fetch.py::fetch`
- Shared router/gate: `api/powergrader/student_attachments.py::ingest_local_file`,
  `api/powergrader/student_attachments.py::eligibility_decision`
- Packet preparation: `api/feedback_artifacts.py::pseudonymize_submissions`,
  `api/feedback_artifacts.py::_prepare_attachment_safe_bundle`
- Mixed scoring: `api/powergrader/ai_workflow.py::run_ai_workflow`
- Request seam: `api/openrouter_client.py::score`
- Session/UI: `api/powergrader/session_builder.py::build_students`,
  `api/webui/static/powergrader/queue_core.js`
- Contract/map: `docs/contracts/feedback-scoring-contract.md`,
  `docs/reference/powergrader-module-map.md`
- Read `TOOLS.md` before broad inspection. Local repo/diff/test summarizers remain planned
  unless their manifests become executable; do not pretend they ran.

Use only the named seams/current diff and synthetic fixtures.

## Implementation requirements

1. **Record the rejected starting state.** Mark this execution in progress and preserve
   the five reviewed defects: ordinary bypass, mixed-student loss/media failure fan-out,
   New Quiz failure eligibility bypass, ambiguous same-attempt selection, and ID-only
   course folder names.
2. **Resolve course display server-side.** Implement nickname/name/ID lookup and use it in
   initial, late, and scheduled flows. Do not add a client-trusted path name.
3. **Replace ordinary enrichment vertically.** Download every attachment to the canonical
   PRIVATE attempt folder, call `ingest_local_file`, leave one success/failure record per
   expected file, update all callers, and stop populating new `code_files` data.
4. **Strengthen eligibility.** Reject incomplete counts, non-downloaded/pending files,
   failed/unsupported extraction, missing originals, local-only formats, and over-budget
   evidence. Keep zero-file typed work eligible. Use the same decision for packets/session.
5. **Normalize New Quiz expectations first.** Create URL-free placeholders, then update
   item-local/top-level records together. Centralize metadata/failure marking in the New
   Quiz module.
6. **Fail closed on native joins.** Collect all same-attempt candidates; require one;
   mark zero/multiple/malformed cases per student; never download ambiguous evidence.
7. **Isolate mixed AI calls.** One text bundle plus one media bundle per student; catch
   media errors locally; collect/reidentify successes and failures; pass generic failure
   metadata to sessions without changing LLM schema.
8. **Surface manual review.** Persist/render attachment and AI failure state with escaped,
   generic copy. Keep raw provider detail only in existing PRIVATE debug handling.
9. **Update dependent workflows/map.** Initial, late, and scheduled callers use the new
   path. Do not alter scheduled write safety or New Quiz immutability.
10. **Self-review dangerous traces.** Follow ordinary DOCX/PNG/PDF/failure, New Quiz
    failure/ambiguity, and mixed media failure from fetch to saved session. Confirm no URL/
    token persistence and no partial-evidence AI draft.

## Required regression cases

1. Ordinary TXT/DOCX/raster uploads are preserved under a readable course-first attempt
   path and routed through `student_attachments`.
2. Ordinary PDF/unsupported files are preserved locally but hold only that student.
3. Ordinary download/size/extraction failure leaves a top-level failed record, expected
   count parity, and no draft; another student remains eligible.
4. No production caller invokes/populates the old code-only path.
5. New Quiz success creates one item-local and one matching top-level record with no URL.
6. New Quiz download/extraction failure creates matching failed records and held
   eligibility while written text remains visible.
7. Global native failure/missing session holds affected file-bearing students only.
8. Two same-attempt sessions produce ambiguity, no item-results/download call, and hold
   only that student.
9. Zero same-attempt matches holds that student while an unambiguous peer succeeds.
10. New Quiz path uses saved nickname/name plus ID, never duplicated ID when saved.
11. Two text plus two media students produce one two-student text request and two
    one-student media requests; every pseudonym appears once.
12. First media exception does not block second media or discard text results; failed user
    has no draft and generic manual-review state; successes remain correctly reidentified.
13. Pseudonym/item association stays exact after partial failure.
14. Serialized fixtures contain no URL/signed URL/bearer/cookie/JWT/native/result token or
    fictional secret value.
15. Old sessions without expected-count/AI-error fields load/render normally.

## Verification

Run focused tests during implementation, then the focused matrix and full API suite at
completion because shared eligibility, three scoring entry paths, session metadata, and
external AI-call isolation changed.

```powershell
py -m pytest api/tests/test_student_attachments.py api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_openrouter_client.py api/tests/test_workspace.py api/tests/test_readiness_routes.py api/tests/test_route_contract.py
py -m pytest api/tests
py -m compileall -q api
node --check api/webui/static/powergrader/queue_core.js
node --check api/webui/static/powergrader/setup_core.js
git diff --check
```

If an existing module is extended instead of creating
`test_powergrader_attachment_workflow.py`, replace that filename and record the exact
command. Do not create an empty test file to satisfy the path.

Rendered verification is mandatory against local synthetic state:

- `/powergrader`: confirm saved nickname/name display, model capabilities, mode switching,
  AI acknowledgement, one synthetic validation error, and zero console errors.
- `/powergrader/session/:synthetic_session_id`: render text/media successes, readable
  written text with attachment hold, failed-media manual review/no draft, local-only and
  transmitted-image statuses, permitted local open action, no cross-student evidence,
  and zero console errors.
- `/settings`: confirm prior course-first labels/folder actions and zero console errors.
- `/feedback-expert`: confirm exposed compatibility folder actions and zero console errors.

Source-text/HTTP tests and `node --check` do not replace rendering. If the in-app Browser
fails with `Cannot redefine property: process`, record that exact environment failure and
remain YELLOW after other checks pass.

## Stop conditions

Stop with RED rather than guessing if:

- A named seam is absent/materially changed.
- Ordinary downloads cannot stay authenticated without forwarding credentials to an
  untrusted host.
- Student Analysis/native results cannot be reconciled without selecting among plausible
  file/attempt associations.
- Completion requires persisting a launch/signed URL, token, cookie, JWT, signature, or
  authorization value.
- Failure isolation requires changing the Feedback Scoring/public OpenRouter schema.
- Scheduled ingestion repair would broaden auto-push or bypass policy/idempotency.
- A live Canvas/New Quiz/OpenRouter probe appears necessary; none is authorized.
- Existing user data would need move/overwrite/rename/delete.
- An unrelated regression requires scope expansion.
- Synthetic work exposes real PII/secrets; stop without reproducing the value.

## Return report

Before handback, replace the placeholders here and report the same compact result. Keep
execution state/test evidence durable in this file.

### Execution result

- Traffic light: **GREEN**
- Commit hash: **not committed; preserve the existing uncommitted worktree as directed**
- Files changed by this execution: `api/powergrader/canvas_fetch.py`,
  `api/powergrader/student_attachments.py`, `api/powergrader/new_quiz_fetch.py`,
  `api/powergrader/ai_workflow.py`, `api/powergrader/ai_workflow_support.py`,
  `api/powergrader/session_builder.py`, `api/feedback_artifacts.py`,
  `api/webui/config/courses.py`, `api/webui/config/__init__.py`,
  `api/webui/routes/powergrader.py`, `api/webui/routes/powergrader_late.py`,
  `api/webui/routes/routines_powergrader.py`,
  `api/webui/static/powergrader/queue_core.js`,
  `api/tests/test_powergrader_attachment_workflow.py`,
  `api/tests/test_powergrader_new_quizzes.py`,
  `api/tests/test_powergrader_late_catchup.py`,
  `api/tests/test_powergrader_scheduled_autoscore.py`,
  `docs/reference/powergrader-module-map.md`, and this handoff.
- Verification commands and pass/fail/skip counts:
  - Follow-up focused regressions: **30 passed, 0 failed**.
  - Full API suite (`py -m pytest api/tests -q`): **643 passed, 1 skipped, 0 failed**.
  - `py -m compileall -q api`: **passed**.
  - `git diff --check`: **passed**; Git emitted only existing LF/CRLF normalization warnings.
- Rendered routes checked once against local synthetic/runtime state: `/powergrader`,
  `/powergrader/session/synthetic-session-acceptance`, `/settings`, and
  `/feedback-expert`; all loaded with **zero browser console errors**. The synthetic
  queue showed the written response, attachment hold, and generic manual-review state;
  the temporary session was removed after verification. Browser checks were not repeated
  because this repair changed backend code only.
- Follow-up defects corrected: native candidate-resolution and item-result request
  failures now hold only the affected student after launch; Canvas attachment downloads
  follow same-host redirects with Canvas credentials, permit HTTPS CDN redirects only
  after removing credential-bearing headers, and clean partial files on mismatch; and
  scheduled autoscore loads an existing session before ordinary ingestion, preventing
  attachment redownload on rerun.
- Earlier defects remain corrected: ordinary attachments now use authenticated, host-checked,
  atomic course-first ingestion for every file; New Quiz expected evidence is
  placeholder-backed and failure-complete, with ambiguous/zero-attempt joins held
  per student; shared eligibility requires count/transport/path/size/extraction
  evidence; saved course nickname/name plus ID is used once for readable ownership;
  mixed text/media scoring preserves the text batch, isolates media failures, and
  records generic manual-review state without leaking provider details.
- Deviations from the brief: no live Canvas, New Quiz, or OpenRouter probes; no commit
  was created. The legacy `enrich_with_code_files` reader remains only for compatibility
  with old sessions and is not used by the production PowerGrader ingestion paths.
- Remaining blocker or decision: **none**.
