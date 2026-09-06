# New Quizzes response and grading capability

Last verified: **2026-07-14**

This is the canonical Canvas Expert reference for New Quizzes authentication, response
acquisition, and item-level manual grading. It separates Canvas capability from features
that Canvas Expert currently exposes. Do not revive the older blanket claim that New
Quizzes item write-back is blocked by personal access tokens.

## Capability summary

| Capability | Canvas behavior | Canvas Expert status |
|---|---|---|
| New Quiz list and report APIs | An actively enrolled teacher's PAT can reach `/api/quiz/v1/...`; concluded enrollment may return `403` | Diagnostic and Student Analysis report paths exist |
| Constructed responses | Student Analysis JSON/CSV exposes item responses; the UI CSV remains a fallback | PowerGrader uses JSON snapshots; CSV remains a manual fallback |
| Native file evidence | Canvas's signed native/LTI result path exposes current attempt item evidence | PowerGrader has a focused signed-file acquisition path; unsupported or failed evidence remains teacher-review-only |
| Per-item manual score | Canvas's first-party grader accepts an independent score for each manual item | Exposed: New Quiz sessions post teacher-reviewed item scores and per-item feedback through a reviewed, receipt-backed finalization lane (preflight freeze, result-version drift detection, idempotency, post-write verification; concluded enrollment may return `403`) |
| Per-item grader feedback | The same result update accepts one grader-feedback value per item ("Additional Comments") | Exposed through the same finalization lane |
| Assignment-level submission comments | The ordinary Submissions API accepts comment writes on a New Quiz submission without touching the quiz-engine score (write + delete verified live 2026-07-14) | Exposed: New Quiz sessions post teacher-reviewed feedback as assignment comments through the frozen manual push review (comment-only; never a score) |
| Assignment total | Canvas derives the New Quiz result total from item scores and fudge points | Do not replace item grading with a forced ordinary-assignment total write |

## Authentication boundaries

“PAT works” does not mean the PAT is sent directly to every quiz-LTI or quiz API endpoint.
There are two different paths:

1. Public New Quiz list/report endpoints accept the teacher's normal Canvas bearer token
   when enrollment and scope permit.
2. Manual item grading follows Canvas's own web/LTI grader launch. A PAT obtains a
   time-limited Canvas web session through `GET /login/session_token`; Canvas GraphQL
   supplies the submission preview launch; the signed LTI flow issues short-lived
   participant and result credentials for the quiz services.
   The separate sessionless native-launch credential supports the focused result-read
   chain, but a user-authorized Phase A probe on 2026-07-14 received `401` when it
   submitted a complete item-result collection plus current fudge to the write endpoint.
   Treat it as read-only; the web-session/signed-launch credential is required for writes.

Never persist or log the session URL, signed LTI fields, cookies, launch token, participant
credential, result token, or signed file URL. A direct PAT bearer request is not a substitute
for the first-party grader launch.

Official documentation:

- Canvas documents `/login/session_token` specifically for starting a normal web session
  when a feature is not supported through an ordinary API:
  https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth_endpoints
- Canvas GraphQL uses `POST /api/graphql` and mirrors the requesting user's permissions:
  https://developerdocs.instructure.com/services/canvas/basics/file.graphql
- Public New Quiz item documentation covers quiz authoring, not student item-result grading:
  https://developerdocs.instructure.com/services/canvas/resources/new_quiz_items

## Verified first-party item-grading chain

With explicit user authorization, the following was verified against dummy course data:

1. Establish a short-lived Canvas web session and open the submission's signed New Quiz
   grading launch.
2. Resolve the participant grading context, quiz API host, quiz session, and short-lived
   result credential.
3. Read the quiz session's current `authoritative_result` and its complete
   `session_item_results` collection.
4. Submit the complete item-result collection plus current fudge points to
   `POST /api/quiz_sessions/:quiz_session_id/results` using the result credential.
5. Re-fetch the quiz session, follow its new authoritative result ID, and verify the item
   scores, grader feedback, and derived total there.

A temporary dummy item score and temporary grader feedback were each accepted with `201`,
verified on the newly authoritative result, and cleared afterward. No live identifiers,
credentials, responses, or grades were stored in the repository.

## Versioning and write safety

Every accepted result update creates a new authoritative result version. The previous result
remains readable but is superseded. Verifying against the pre-write result ID can therefore
produce a false failure even when the write succeeded.

Any Canvas Expert implementation must:

- acquire and freeze the complete current item-result set immediately before review/apply;
- bind teacher decisions to stable item IDs and the preflight authoritative result ID;
- preserve auto-graded and untouched item values exactly;
- post once per deliberate student finalization, never once per keystroke;
- re-fetch the quiz session after the write and verify the new authoritative result;
- treat a timeout or ambiguous response as unknown until reconciliation completes;
- fail closed and link to the exact SpeedGrader target when authentication, shape, item
  identity, result version, or verification differs from the expected contract;
- capture a content-minimized private receipt without credentials or student content.

This transport is used by Canvas's current first-party grader but is not documented as a
stable public item-grading API. Keep it behind one narrow adapter and a runtime capability
check so Canvas drift does not weaken review or write safety.

## Current implementation facts

- PowerGrader can select New Quizzes and build local written-response sessions.
- New Quiz sessions support two manual write lanes:
  - **Comment-only push** (2026-07-14): teacher-approved assignment-level feedback posts
    as ordinary submission comments through frozen review/drift/idempotency flow; payload
    excludes `submission`/`posted_grade`. Legacy sessions without `comment_writeback_supported` 
    stay fully blocked.
  - **Item-finalization lane** (2026-07-14): teacher-reviewed item scores and per-item
    grader feedback finalize through a gated two-phase route: `POST .../new-quiz-review`
    (preflight freeze → 15-minute review token) then `POST .../new-quiz-finalize` (verification
    and application). Sessions with `new_quiz_item_finalization_supported=true` are eligible;
    the route validates result-version stability (drift check against cached state digest),
    applies an idempotency key (keyed on user/state/decision digests), re-fetches and
    verifies the authoritative result post-write, and logs content-minimized receipts.
    Concluded enrollment may return `403`. A second caller reaches the same lane
    unchanged (2026-09-06): the MCP server's `preview_new_quiz_scores` /
    `apply_new_quiz_scores` pair calls `session_actions.review_new_quiz_finalization`
    and `finalize_new_quiz` directly, one student per loop iteration, so an assistant
    scoring a New Quiz from a conversation gets the identical freeze/drift/idempotency/
    receipt behavior as the interactive PowerGrader queue. It is not a second
    finalization path; there is exactly one, with two callers.
- `api/powergrader/new_quiz_fetch.py` uses native result acquisition; the live participant
  result key `quiz_api_quiz_session_id` is normalized alongside older/synthetic
  `quiz_session_id` shapes (fixed 2026-07-14, live-verified: file evidence downloads).
- The sessionless result credential is deliberately **not** a production write credential:
  its Phase A full-result POST was rejected without changing the authoritative result.
  The current item-finalization adapter acquires the web-session/GraphQL signed grader launch
  for each deliberate finalization, keeping all launch/session/result credentials in memory.
- Live report shape (verified 2026-07-14): upload answers arrive as filename-only strings
  with no file refs — `normalize()` seeds the expected file record from the answer so the
  native transport can materialize the upload. `item_responses[].item_type` carries the
  interaction slug; catalog points live on the OUTER `/items` record.
- AI-payload policy (2026-07-14): New Quiz uploads never enter the AI lane as files or
  filenames. Locally-extracted text (TXT/DOCX-style) is inlined as an essay-like response;
  unreadable uploads (image/PDF/failed) are excluded from the packet and stay teacher-review-only.
- Student Reports currently do not materialize New Quiz item responses. That is a missing
  consumer integration, not proof that Canvas cannot provide item responses.
- The ordinary Canvas Submissions API does not expose the complete New Quiz item-result
  collection. Use the focused report/native grader paths described above.

## Product decision for feedback composition

Canvas exposes one grader-feedback value per item. PowerGrader will keep the Teaching
Assistant block read-only and provide an optional teacher field above it. On finalization,
Canvas receives teacher feedback, a separator, and the TA score/feedback block. When the
teacher field is empty, omit the empty section and publish only the TA block.
