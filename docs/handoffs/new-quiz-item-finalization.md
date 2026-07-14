# Execution brief: reviewed New Quiz item finalization in PowerGrader

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

For a New Quiz with text-renderable manual items, PowerGrader shows auto-graded items as
read-only, displays each Teaching Assistant proposal as read-only, and gives the teacher a
blank official item score plus optional **My feedback**.  One deliberate **Finalize student**
action applies only the teacher's item decisions through Canvas's first-party grader transport,
then reconciles the newly authoritative result version.  Any native-renderer requirement or
capability uncertainty routes that student's entire finalization to the exact SpeedGrader
target.

## Locked decisions

- This is a teacher-reviewed item-grading feature, not AI auto-push.  An AI/TA score is never
  written as an official Canvas score; the official input begins blank and must be deliberately
  typed by the teacher.  No scheduled New Quiz scoring/finalization, bulk finalization,
  per-keystroke write, or ordinary Submissions API total-grade workaround is allowed.
- If one manual item for a student requires Canvas's trusted native renderer (file, image,
  audio, video, ambiguous/failed evidence, or unsupported item/result shape), route that
  student's **entire** finalization to SpeedGrader.  Preserve the local review; do not finalize
  a supported subset or create two competing grading authorities.
- Add one narrow internal adapter under `api/powergrader/` for the signed first-party grader
  chain in `docs/reference/new-quizzes-grading-transport.md`.  Reuse parsing/launch seams in
  `new_quiz_fetch.py` where they match.  All Canvas web sessions, cookies, signed launch
  fields/URLs, launch/JWT/native/result credentials, and response content stay in memory only
  and are absent from session files, manifests, receipts, exceptions, logs, and browser JSON.
- Normalize both `quiz_api_quiz_session_id` (verified live shape) and existing supported
  `quiz_session_id` / synthetic forms into one internal value.  Unknown launch, participant,
  result, or item shapes fail closed with a generic error and exact SpeedGrader fallback.
- Immediately before finalization, obtain and freeze the complete current authoritative result
  set for exactly one student.  Bind the review to stable item IDs and the pre-write
  authoritative result ID; preserve all untouched and auto-graded item state exactly.  The
  adapter posts the complete item collection and current fudge points once, then re-fetches the
  quiz session, follows the **new** authoritative result ID, and verifies reviewed scores,
  feedback, and derived total there.
- A timeout, transport ambiguity, non-success response, new-result mismatch, or verification
  failure is unknown/review-needed—not success and not a retry loop.  Retain the local review,
  write a private content-minimized receipt without credentials/content, and link SpeedGrader.
  A repeat finalization only proceeds after a fresh reconciliation proves the prior write did
  not apply; a verified prior receipt/result is idempotently reported rather than written again.
- Canvas has one grader-feedback value per item.  Compose it only at finalization:

  ```text
  MY FEEDBACK

  <optional teacher feedback>

  -------

  TA SCORE + FEEDBACK

  <read-only TA block beginning with score earned/score available>
  ```

  If the teacher feedback is empty, omit `MY FEEDBACK` and the separator.  The TA block must
  remain visibly read-only in PowerGrader and self-identify as Teaching Assistant content.
- Extend the existing item-aware PowerGrader session/import shape and private receipt/audit
  patterns; do not introduce a second scoring contract, new provider abstraction, or persistent
  credential store.  Ordinary-assignment push review/apply behavior remains unchanged.

## Scope

- Add the narrow New Quiz grader transport, result normalization/freeze/verification, and
  content-minimized private receipt helpers under `api/powergrader/`; keep route orchestration
  in `api/webui/routes/powergrader.py` and ordinary push behavior in `session_actions.py`.
- Extend `new_quiz_fetch.py` / `session_builder.py` only as needed to retain safe stable item
  IDs, current-attempt/result context, supported text/manual classification, and exact
  SpeedGrader links without persisting credentials or signed URLs.
- Add one student-level New Quiz finalize route and bind it in the existing queue feature files
  (`queue_core.js`, `queue_review.js`, and queue template/CSS only if needed).  Render the
  read-only item/TA blocks, blank teacher score controls, optional teacher feedback, explicit
  finalization control, review-needed state, and SpeedGrader fallback.
- Update the PowerGrader module map and New Quiz-facing teacher documentation only to reflect
  implemented behavior truthfully.

## Out of scope

- No live dummy write, real course/student access, or browser finalization test unless the user
  explicitly authorizes it in this execution brief after implementation is otherwise ready.
- No scheduled scoring/auto-push, AI official score, assignment-total PUT, bulk New Quiz push,
  item media/file grading outside Canvas, or partial student finalization.
- No FeedbackExpert consolidation, scoring-contract change, workspace migration/deletion,
  generic transport framework, or change to normal Canvas assignment grade/comment pushes.

## Reference pattern and routing

- Canonical transport/safety reference: `docs/reference/new-quizzes-grading-transport.md`.
- Current read-side native transport: `api/powergrader/new_quiz_fetch.py::_native_file_transport`,
  `::_resolve_native_candidate`, and `_download_item_files`.
- Current ordinary reviewed push pattern: `api/powergrader/session_actions.py::review_push`,
  `::push_grades`, and `api/tests/test_powergrader_manual_push.py`.
- Current session/item import shape: `api/powergrader/session_builder.py`,
  `api/powergrader/import_results.py`, and `api/tests/test_powergrader_import_results.py`.
- Queue owner: `api/webui/static/powergrader/queue_core.js` and `queue_review.js`; route owner:
  `api/webui/routes/powergrader.py`.
- Required tests: `api/tests/test_powergrader_new_quizzes.py`,
  `test_powergrader_import_results.py`, `test_powergrader_manual_push.py`, and
  `test_powergrader_attachment_workflow.py`.
- Read `AGENTS.md` and `TOOLS.md`; the local Canvas/document tools are planned, so use the
  canonical reference and focused synthetic fixtures rather than a live Canvas probe.

## Implementation requirements

1. Implement a memory-only first-party grader adapter with explicit stage validation:
   session/launch, native participant resolution, current authoritative result fetch, complete
   item-results fetch, result post, and new-authoritative-result verification.  Normalize known
   identifiers; no stage may fall back to filename, position, a direct PAT result request, or an
   ordinary assignment submission write.
2. Build a single-student finalization preflight that classifies items/evidence.  It must fail
   closed and return an exact SpeedGrader link for any native-renderer/manual unsupported case,
   result/item drift, missing stable identity, credential/launch failure, or ambiguous write.
3. Extend the saved private session with only the required result/item baseline, teacher edits,
   finalize receipt reference/status, and fallback information.  Ensure all persisted data is
   URL/credential-free and content-minimized; invalidate frozen review when a teacher item edit
   changes.
4. Render the item review safely.  Auto-graded/untouched items are read-only; the TA block is
   non-editable and clearly labeled; teacher score is initially empty; teacher feedback is
   separate.  The student-level finalization action states that it writes official item
   decisions and never derives/forces an assignment total.
5. On finalization, atomically use the complete frozen result collection, merge only reviewed
   teacher decisions, compose one grader-feedback field per reviewed item, post once, then
   reconcile the newly authoritative result version.  Record success only after verification;
   otherwise store a private minimal unknown/review-needed receipt and retain edits.
6. Add synthetic happy, unsupported/native-fallback, launch/result-shape drift, item mismatch,
   timeout/ambiguous response, new-result-version verification, receipt privacy, and
   idempotency tests.  Preserve ordinary push tests and update docs/module map in the same
   change.

## Verification

```powershell
py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_manual_push.py api/tests/test_powergrader_attachment_workflow.py
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_route_contract.py
git diff --check
```

Render `/powergrader` setup and queue with synthetic/local session data only.  Confirm mixed
item review controls, read-only TA blocks, blank teacher item score, SpeedGrader fallback, and
zero new console errors.  Do not select real course work, submit a finalization, or issue a
live write.  A live dummy write requires a separate explicit user authorization.

## Stop conditions

Stop with RED rather than guessing if:

- A launch, result, or item shape is not one of the canonical/known synthetic forms; stable
  student, attempt, item, and authoritative-result identity cannot be proven; or Canvas does
  not expose the complete current result collection.
- The implementation requires persisting a credential, signed URL, cookie, student content, or
  raw provider response; uses a direct PAT item-grade request; or cannot give a precise
  SpeedGrader fallback.
- A partial student finalization, assignment-total workaround, automatic retry after ambiguity,
  or scheduled/AI official write is needed to satisfy the outcome.
- The adapter would change the Feedback Scoring Contract, the ordinary push contract, or a
  public persistence format beyond the narrow private session/receipt extension.
- A required live write/probe or unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **RED**
- Commit hash: no implementation commit
- Files changed: this handoff execution result only
- Verification: no tests or rendered routes run; implementation stopped before a high-risk transport edit.
- Rendered routes checked: none.
- Deviations: none.
- Remaining blocker: the required first-party grader launch has no executable, canonical request/response seam in the routed reference or current code. `new_quiz_fetch.py` implements a read-side sessionless/native-file path, while the verified write chain requires a web-session plus GraphQL submission-preview launch. The canonical transport reference intentionally describes that chain at a safety level but does not define the GraphQL operation, launch payload, participant/result response shapes, or synthetic fixtures needed to validate it. Implementing these credentials/result stages would require guessing a high-risk transport, which is a RED stop condition.
