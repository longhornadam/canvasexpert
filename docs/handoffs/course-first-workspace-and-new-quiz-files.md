# Execution brief: Course-first student work and inspectable New Quiz uploads

Status: **design complete — held for later approval; do not execute yet**

Risk: **high**

Executor: **unassigned — Terra recommended when the senior explicitly releases this brief**

## Outcome

Teachers find downloaded work under an intuitive course -> assignment -> student tree,
while pseudonymized AI artifacts and machine-owned state have clearly named, separate
homes. New Quiz file-upload responses download immediately without retaining capability
URLs; trusted text and document content is locally extracted and scrubbed, supported
images are inspected by a teacher-selected vision model, and untrusted formats remain
available locally without being transmitted.

This is one ordered body of work. Establish the canonical workspace/path ownership
first, then build attachment ingestion on that foundation; do not create files in the
legacy `FeedbackExpert/PRIVATE/PowerGrader` shape and migrate them again afterward.

## Locked decisions

- The synced workspace remains named `CanvasExpert`.
- Human-facing student work is canonical in **course-first, assignment-first** order.
  Do not store a second copy under a parallel by-student tree. Student-first navigation
  belongs in derived `Student Reports`, indexes, or the app UI.
- Canonical human-facing roots are:
  - `Courses/` — real-name/original student work; always PRIVATE.
  - `AI Packets (Pseudonymized)/` — pseudonymized artifacts teachers must still review
    before sharing; do not describe this as anonymous or guaranteed safe.
  - `Student Reports/` — derived longitudinal/student-first output.
  - `_System/` — vault, PowerGrader session/job state, audit, and other machine-owned
    files not intended for routine browsing.
- `FeedbackExpert` still has code consumers today, but its name is an implementation
  artifact and is not part of the new human workspace. Route/service compatibility does
  not justify new writes under a `FeedbackExpert/` directory.
- Within a course, raw work is assignment-first:

  ```text
  CanvasExpert/
  +-- Courses/
  |   +-- <Course name or teacher nickname> — <course id>/
  |       +-- Course Information.txt
  |       +-- Assignments/
  |           +-- <Assignment name> — <assignment id>/
  |               +-- Assignment Information.txt
  |               +-- Student Work/
  |                   +-- <Last, First> — <Canvas user id>/
  |                       +-- Attempt <n>/
  |                           +-- Written Response.txt
  |                           +-- <original upload filename>
  |                           +-- Extracted Text/
  +-- AI Packets (Pseudonymized)/
  |   +-- <Course folder>/
  |       +-- <Assignment folder>/
  |           +-- <timestamp> — <PowerGrader mode>/
  |               +-- Assignment and Rubric.txt
  |               +-- Students/<pseudonym>/
  +-- Student Reports/
  +-- _System/
      +-- Identity Vault/
      +-- PowerGrader/Sessions/
      +-- PowerGrader/Jobs/
      +-- Audits/
      +-- Archive/
  ```

- Filesystem display names are sanitized, readable names with the stable Canvas ID as a
  quiet suffix. IDs are PRIVATE. Once created, a folder is not automatically renamed
  when Canvas display text changes; current names/dates live in the information file.
- Do not put due dates in canonical folder names. Due dates change.
- Preserve the student's original upload filename only in the PRIVATE course tree.
  Pseudonymized artifacts use synthetic filenames.
- Existing user data is never destructively reorganized automatically. New writes use
  the new roots. A compatibility migration may copy machine-owned files only when the
  destination is absent, must never overwrite, must verify the copy, and must leave the
  legacy source intact. Legacy human SAFE/PRIVATE artifacts remain in place because the
  app cannot reliably infer their course and assignment.
- Existing PowerGrader sessions/jobs remain discoverable during the compatibility
  period. Read new state first, then legacy state, and deduplicate by stable ID. All new
  writes go to `_System/PowerGrader/...`.
- The operation ledger remains machine-local as required by its contract. Do not move it
  into OneDrive merely for layout symmetry.
- New Quiz file transport follows the live-proven native session chain documented below.
  The official sessionless launch is the entry point; all later result/session endpoints
  are undocumented internal APIs and must fail soft.
- Launch URLs, Canvas session cookies, CSRF values, JWTs, native access tokens, quiz
  result tokens, and signed storage URLs are memory-only. They must never appear in a
  log, exception, session JSON, fixture, audit file, or workspace artifact.
- Download signed storage URLs immediately with a clean HTTP client carrying no Canvas
  or New Quiz authorization headers. Require HTTPS, stream to an atomic partial file,
  compare the final byte count with Canvas's declared size when present, and discard the
  URL after the request.
- Download originals for local teacher access regardless of whether their content is
  trusted for AI transmission. Use streaming/free-space checks for storage; AI
  extraction limits are separate and must not prevent preservation of the original.
- Content routing, not extension symmetry, determines Auto-Score behavior:
  - Canvas typed responses and trusted plain-text uploads (`.txt`, `.md`, `.csv`,
    `.json`, `.py`, `.html`, `.htm`, `.css`, `.js`) are decoded locally, structurally
    labeled, scrubbed, and sent as text. A vision model is not required.
  - `.docx` is parsed locally. Preserve visible paragraphs/headings, tables, and inline
    image placement in document order. Send extracted text only after the normal scrub.
    Extract inline raster images as pseudonymized, metadata-stripped image parts.
    Document properties, author metadata, comments, revision history, macros, and the
    original filename are not transmitted. Legacy `.doc` and macro-enabled document
    formats are local-only.
  - Direct PNG, JPEG, WebP, and GIF uploads are validated by content, converted to
    metadata-stripped pseudonymized derivatives, and sent as image parts.
  - PDF and every other not-yet-trusted format are downloaded for local access but are
    not sent to OpenRouter in this brief.
- Never silently truncate student evidence and then score it. If a required attachment
  is corrupt, extraction exceeds the allowed AI budget, a DOCX contains unsupported
  evidence, or one attachment is local-only, hold that student for teacher review rather
  than score from a partial submission. Continue with unaffected students.
- A response containing images may be sent only when the exact selected OpenRouter model
  advertises `image` in `architecture.input_modalities`. The server enforces this even
  if the browser is bypassed. The current DeepSeek V4 defaults are text-only.
- Media-bearing students are scored in isolated per-student requests so files cannot be
  associated with the wrong pseudonym and one provider failure does not discard the
  class. Existing text-only batch scoring may remain batched.
- The multimodal request includes the existing assignment directions, source context,
  rubric, item prompt, typed/extracted response, and labeled media. Do not invent a
  second grading contract.
- Image/request price fields and actual media counts are included in the post-download
  budget receipt. Copy must state when the displayed estimate is a floor because a
  provider tokenizes images rather than charging a fixed image price.
- Originals stay PRIVATE. Only scrubbed text and pseudonymized, metadata-stripped media
  derivatives may enter `AI Packets (Pseudonymized)` or an OpenRouter request. Visible
  pixels may still contain identifying context; preserve the existing teacher
  acknowledgement and make the pipeline wording honest.
- New Quiz sessions remain read-only Canvas snapshots. This work does not add New Quiz
  grade/comment write-back, scheduled scoring, or late-watch.

## Scope

- Replace legacy workspace path ownership with centralized resolvers in
  `api/webui/workspace.py`; update direct path consumers rather than scattering string
  joins.
- Route PowerGrader sessions/jobs/audits/vault and Feedback Tools compatibility through
  the new `_System`/AI-packet resolvers:
  - `api/powergrader/session_store.py`
  - `api/powergrader/autoscore_queue.py`
  - `api/powergrader/privacy.py`
  - `api/powergrader/context.py`
  - `api/feedback_vault.py`
  - `api/feedback_artifacts.py`
  - `api/webui/readiness.py`
  - narrow `api/webui/routes/feedback_*.py`, `routes/names.py`, and `routes/pages.py`
    call sites that currently request `workspace.feedback_folder(...)`.
- Change ordinary Download Work output in `api/downloader.py` from duplicated
  `by_assignment`/`by_student` copies to the canonical course/assignment/student tree.
  Respect an explicitly configured custom download root while preserving the same
  course-first shape beneath it.
- Add New Quiz native session/result transport and immediate file downloading in the
  `api/powergrader/new_quiz_fetch.py` ownership boundary. Thread the already-created
  PowerGrader `session_id` through `routes/powergrader.py` ->
  `powergrader/canvas_fetch.py` -> `new_quiz_fetch.fetch(...)` so files have a stable
  destination before AI processing.
- Normalize downloaded files into their matching `new_quiz_items[].files` and top-level
  submission attachments without retaining URLs. Include local path, original filename,
  declared/actual size, detected media type, extraction status, attempt, and item link.
- Add one shared student-attachment content router under `api/powergrader/` and reuse the
  extraction primitives in `api/webui/source_material_extractors.py` where their behavior
  is appropriate. Do not duplicate the ordinary-assignment and New Quiz extractors.
- Extend `api/feedback_artifacts.py`, `api/powergrader/ai_workflow.py`, and
  `api/openrouter_client.py` so scrubbed text and safe media derivatives remain linked to
  pseudonym/item IDs and form valid multimodal chat-completions requests.
- Extend OpenRouter model metadata through `api/webui/routes/settings.py` and the
  PowerGrader model picker so teachers can identify image-capable models.
- Persist local attachment metadata in `api/powergrader/session_builder.py` and render
  useful status/open-file controls in `api/webui/static/powergrader/queue_core.js` using
  the existing guarded local open-path behavior.
- Update teacher-facing workspace/privacy wording in the affected Settings,
  PowerGrader, Feedback Tools, README, and module-map locations. Preserve the semantic
  SAFE/PRIVATE safety contract while using the new human labels.
- Add synthetic tests/fixtures only. No district URL, live ID, student name, signed URL,
  token, or downloaded probe byte may enter the repository.

## Out of scope

- No executor assignment or implementation until a senior explicitly releases this
  held brief.
- No automatic deletion, move, or cleanup of `FeedbackExpert/`, `PowerGrader/`,
  `Exports/`, or any other existing synced folder.
- No duplicate by-student copy of raw submissions and no OneDrive hardlinks, junctions,
  or shortcuts as canonical storage.
- No PDF extraction, OCR, page rendering, or PDF transmission to OpenRouter.
- No generic DOC/DOCM/XLSX/PPTX/ZIP/media/audio/video transmission.
- No attempt to redact identifiers visible in image pixels or promise anonymity.
- No change to the Feedback Scoring Contract result schema unless the existing schema
  genuinely cannot represent one student's media-linked response; stop rather than
  versioning it speculatively.
- No Canvas write, New Quiz write-back, grade/comment auto-push expansion, scheduled New
  Quiz workflow, or live production probe.
- Do not rerun the sandbox probe unless the user separately authorizes live access at
  execution time.

## Reference pattern and routing

- Workspace ownership and legacy migration: `api/webui/workspace.py`
- Existing course/assignment/student download behavior: `api/downloader.py`
- Existing student-first derived output: `api/webui/config/reports.py`,
  `api/student_packet.py`, and `api/portfolio_service.py`
- New Quiz written-response owner: `api/powergrader/new_quiz_fetch.py`
- Assignment fetch insertion point: `api/powergrader/canvas_fetch.py::fetch_submissions`
- Existing format extraction: `api/webui/source_material_extractors.py`
- Pseudonymization and SAFE/PRIVATE writer: `api/feedback_artifacts.py`
- AI orchestration and request builder: `api/powergrader/ai_workflow.py`,
  `api/openrouter_client.py::build_request`
- Session persistence/UI metadata: `api/powergrader/session_store.py`,
  `api/powergrader/session_builder.py`
- Model metadata UI: `api/webui/routes/settings.py::_model_row`,
  `api/webui/static/powergrader/setup_autoscore.js`
- Queue attachment display: `api/webui/static/powergrader/queue_core.js`
- Durable scoring boundary: `docs/contracts/feedback-scoring-contract.md`
- PowerGrader ownership map: `docs/reference/powergrader-module-map.md`
- Feedback Tools ownership map: `docs/reference/feedbackexpert-module-map.md`
- Official OpenRouter references:
  - `https://openrouter.ai/docs/guides/overview/multimodal/image-understanding`
  - `https://openrouter.ai/docs/api/api-reference/models/get-models`
- Read project-local `TOOLS.md` before broad manual inspection. The Canvas doc/API helper
  manifests are currently planned, so use them if they are available by execution time.

### Sanitized live-probe transport contract

The July 2026 dummy-course probe established this read-only chain. Treat field names as
evidence, not the internal endpoints as a stable public contract:

1. `GET /api/v1/courses/:course_id/external_tools/sessionless_launch` with
   `launch_type=assessment` and `assignment_id` returns the native launch URL.
2. Following that URL establishes a Canvas web session and yields `ENV.NEW_QUIZZES`
   (`params`, `signature`, `basename`, `launchType`) plus `ENV.ACCOUNT_ID`.
3. Canvas requests a workflow JWT with
   `POST /api/v1/jwts?canvas_audience=false&workflows[]=new_quizzes_native_launch&context_id=:account_id&context_type=account`
   using the session CSRF header.
4. `POST :backend_url/api/native/launch` uses `Authorization: Bearer <workflow JWT>`,
   JSON `{params, signature}`, and the launch-derived `X-Domain`. Its response supplies
   `access_token` and `entry_path.resourceId`.
5. `GET :backend_url/api/assignments/:resourceId/participants?no_pagination=true` uses
   the native bearer token and returns `canvas_user_id` plus `participant_sessions[]`.
6. `GET :backend_url/api/participant_sessions/:id/results` supplies the quiz API host,
   a result-service token, and the quiz-session ID.
7. `GET :quiz_host/api/quiz_sessions/:quiz_session_id` uses the result token verbatim in
   `Authorization` with `AuthType: Signature`; it returns
   `authoritative_result.id` and the attempt number.
8. `GET :quiz_host/api/quiz_sessions/:quiz_session_id/results/:authoritative_result_id/session_item_results`
   returns item results. File-upload answers appear at
   `scored_data.value[]` with exactly `id`, `name`, `size`, and `url` in the observed
   contract.
9. Join `participant.canvas_user_id` to the Core submission and result `item_id` to the
   Student Analysis item. Select the completed quiz session whose attempt equals the
   already-selected latest Student Analysis attempt. If the join is ambiguous, do not
   attach files from a possibly wrong attempt.

The probe downloaded one PNG and one JPEG from two dummy students; actual bytes matched
the declared sizes. The probe artifacts are external PRIVATE data and are not fixtures.

## Implementation requirements

1. Centralize the new workspace tree and compatibility reads. Seed a concise root readme
   explaining that `Courses` and `_System` are PRIVATE and `AI Packets
   (Pseudonymized)` must be reviewed before sharing. Prove that legacy data is neither
   overwritten nor deleted.
2. Convert Download Work and PowerGrader artifact/session ownership to the centralized
   paths. Use one resolver for course, assignment, student, attempt, and AI-run folders;
   include collision and Windows path-length handling.
3. Implement the native New Quiz session transport behind private helpers. Redact
   exceptions at the boundary, use timeouts on every request, and return per-stage
   non-sensitive error codes/messages. Written-response snapshots must still succeed
   when the internal file path is unavailable.
4. Download every observed upload immediately into the correct PRIVATE attempt folder.
   Use clean-session HTTPS streaming, atomic finalize, size verification, filename
   sanitization/collision handling, and filesystem free-space checks. Never place a
   signed URL in normalized data.
5. Route content locally. Produce human-readable extracted-text files in the PRIVATE
   student folder, then scrub separate pseudonymized text for AI. Preserve DOCX body
   order and link extracted inline images to their position. Validate raster bytes with
   Pillow and strip metadata when creating pseudonymized derivatives.
6. Build a per-student eligibility decision before any external call. The decision must
   enumerate all expected evidence and block partial scoring if any attachment is
   unsupported, failed, or omitted. Show the teacher which students were held and why
   without leaking another student's data.
7. Fetch exact OpenRouter model metadata during the existing pricing gate. Expose image
   capability in the picker, enforce it server-side, include media/request pricing where
   published, and retain the current prohibition on unverifiable/Auto Router pricing.
8. Build multimodal requests from the same scrubbed scoring bundle and safe derivatives.
   Put explanatory text before image parts as OpenRouter recommends, explicitly label
   pseudonym and item association, and aggregate per-student responses back through the
   existing result parser/re-identification path.
9. Persist only local paths/statuses needed for teacher review. Make downloaded originals
   openable from the queue and make privacy/audit receipts distinguish downloaded,
   extracted, transmitted, held-local, and failed counts.
10. Update durable docs and `AGENTS.md` only where the canonical workspace, safety path,
    or module ownership actually changed. Remove stale claims that new artifacts live
    under `FeedbackExpert/`, but preserve compatibility notes while legacy reads exist.

## Verification

This is high risk because it moves credential-adjacent transport through undocumented
APIs, handles FERPA data in synced storage, and adds external multimodal transmission.

Required focused coverage includes:

- path resolver sanitization, collisions, stable ID suffixes, Windows path length, and
  course -> assignment -> student -> attempt layout;
- non-destructive legacy compatibility: new-first reads, no-overwrite copy, dedupe, and
  zero deletion/move calls;
- Download Work writes one canonical assignment-first copy, not duplicate raw bytes;
- launch-page ENV parsing, CSRF/JWT/native launch headers, participant/attempt/item joins,
  raw Signature authorization, and fail-soft stage errors using synthetic responses;
- signed URL absent from every returned object, log/audit/session artifact, and raised
  error; clean download client carries no auth headers;
- atomic download success, redirect/HTTP failure, size mismatch, filename traversal,
  collision, insufficient space, and interrupted partial-file cleanup;
- TXT/MD decoding, structured DOCX paragraphs/tables/order, inline-image extraction,
  document metadata exclusion, corrupt/legacy DOC handling, and no silent truncation;
- image magic/MIME validation, metadata removal, synthetic filename, and unsupported
  media handling;
- one unsupported or failed attachment blocks only that student's automated score and
  never produces a partial AI draft;
- text-only model rejection for media, image-capable model acceptance, pricing receipt,
  multimodal request ordering/association, per-student failure isolation, parse, and
  re-identification;
- New Quiz written-response behavior remains available when file retrieval fails and
  New Quiz write-back/late-watch remain disabled.

At completion run focused tests during implementation, then the affected API suite and
full API suite because workspace, feedback, PowerGrader, downloader, and shared model
metadata are cross-cutting:

```powershell
py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_openrouter_client.py api/tests/test_source_materials.py api/tests/test_downloader.py api/tests/test_feedback_pipeline.py api/tests/test_readiness_routes.py api/tests/test_route_contract.py
py -m pytest api/tests
```

Rendered verification is mandatory because setup/model-picker, privacy controls, queue
attachments, and Settings/Feedback path buttons are browser behavior:

- `/powergrader`: load models, identify vision capability, select text-only versus
  image-capable models, acknowledge the AI route, and exercise a synthetic start error.
- `/powergrader/session/:synthetic_session_id`: view typed text, extracted DOCX text,
  local-only attachment status, transmitted image status, held-student reason, and open a
  permitted local file; confirm zero new console errors.
- `/settings`: verify workspace/download path labels and folder actions.
- `/feedback-expert`: verify compatibility folder actions if this route remains exposed.

Do not use live Canvas or OpenRouter calls as required test evidence. A separately
authorized dummy-course smoke test may supplement, never replace, the synthetic matrix.

## Stop conditions

Stop with RED rather than guessing if:

- A named launch field, participant/session/result field, or attempt/item join differs
  from the sanitized contract.
- The app cannot unambiguously associate a file with the same latest attempt selected by
  Student Analysis.
- Existing workspace data would need to be moved, overwritten, or deleted to proceed.
- A Feedback Tools consumer cannot use centralized paths without changing the public
  scoring contract or losing existing vault/session state.
- DOCX visible-body ordering or inline image association cannot be implemented without
  silently omitting evidence.
- The OpenRouter model catalog cannot verify required image input or price information.
- A signed URL/token would need to be persisted, logged, or exposed to the browser.
- Satisfying the outcome requires PDF/OCR, Canvas write-back, scheduled New Quiz work,
  or another excluded subsystem.
- Any synthetic fixture or output contains a real district URL, course/user ID, student
  name, token, or probe artifact.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **not started**
- Commit hash: **none — design brief only**
- Files changed: **none**
- Verification commands and pass/fail/skip counts: **not run**
- Rendered routes checked: **none**
- Deviations from the brief: **none**
- Remaining blocker or decision: **senior/user must explicitly release the held brief and assign one executor**
