# Execution brief: New Quiz per-item review and teacher finalization (v2)

Status: **completed**

Risk: **high** — official item scores/comments, short-lived credentials, undocumented
first-party transport, FERPA.

Executor: **senior-tier implementation agent (Codex, Terra/Sol class).** The senior dev
(Claude, this repo's orchestrator role) wrote this brief and accepts the result. The
executor tier does not relax any locked decision, stop condition, or guardrail in this
brief or in `AGENTS.md`; a stronger executor is expected to *hold* these constraints under
pressure, not renegotiate them mid-implementation.

## Why v2

The v1 finalization brief and the transport-capture brief (both in `docs/handoffs/archive/`)
stopped RED because no executable launch/write contract existed. That evidence is stale.
Live work on 2026-07-14 (dummy course, commit `7fb63b9`) established:

- The **sessionless native launch read chain works end to end** with the teacher's PAT:
  `sessionless_launch` → launch-page ENV → workflow JWT → `/api/native/launch` →
  participants → `/api/participant_sessions/:id/results` → quiz session →
  `session_item_results`. Live result payloads use `host` / `token` /
  `quiz_api_quiz_session_id` (normalized in `new_quiz_fetch._resolve_native_candidate`),
  and the attempt lives on the quiz session object, not inside `authoritative_result`.
- The write itself was previously verified with user authorization (201, new authoritative
  result): see "Verified first-party item-grading chain" in
  `docs/reference/new-quizzes-grading-transport.md`.
- Interim lanes shipped and live-verified: AI drafts per item (merged per student),
  comment-only manual push of whole-assignment feedback, upload text extraction policy.

## Outcome (teacher-visible)

> For a New Quiz, PowerGrader shows each supported manual text item with a read-only
> Teaching Assistant proposal, an optional **My feedback** field, and a blank teacher score.
> One deliberate **Finalize student** action writes the teacher's per-item scores and
> per-item "Additional Comments" through Canvas's first-party grader transport, verifies the
> new authoritative result, and reports exactly what was written. Auto-graded items are
> read-only. Students whose evidence requires Canvas's renderer (images, PDFs) route wholly
> to SpeedGrader via an exact deep link.

## Phase A — close the one open transport question (do this first)

The remaining unknown: **does the sessionless-launch result credential authorize the write
POST** (`POST /api/quiz_sessions/:quiz_session_id/results` with the complete item collection
plus current fudge), or does the write require the heavier web-session/GraphQL grader launch
described in the reference doc?

Run Phase A under the archived capture brief's safety rules, restated as binding here:

1. Dummy course/assignment identifiers come from the operator in chat only; they never enter
   the repo, commits, logs, or this file. No tokens, cookies, signed URLs, or raw payloads
   anywhere but memory.
2. Validate every read stage first. If a complete item-results-plus-fudge payload cannot be
   derived from observed shapes without guessing, do not POST — record RED here and stop.
3. At most **one** temporary write (a completed dummy Essay item only; preserve every other
   item and fudge exactly; no automatic retry). Re-fetch the quiz session, follow the new
   authoritative result ID, verify in memory, and leave the temporary value for operator
   inspection (YELLOW) unless the operator directs cleanup.
4. The operator must explicitly authorize the write in chat before it is issued.

If the sessionless credential is rejected for the write, fall back to implementing the
documented web-session (`GET /login/session_token`) → GraphQL preview → signed launch chain
for the write path only; the read side stays on the proven sessionless chain.

## Phase B — production implementation

Build only after Phase A yields a verified write contract.

Required scope (unchanged from the roadmap's Luna 3, updated for current code):

- One narrow adapter module for the grader write chain (suggested:
  `api/powergrader/new_quiz_grader.py`), behind a runtime capability check. Credentials and
  signed URLs are memory-only and never appear in errors, logs, receipts, or session files.
- **Per-item AI drafts:** `feedback_results.merge_rows_by_uid` currently merges item rows
  into one blob for the queue. Additionally persist the per-item rows on each session
  student (e.g. `ai_item_results: [{item_id, score, feedback}]`) at import time in
  `ai_workflow.py` and `import_results.py`, so the finalization UI renders one TA proposal
  per item. Do not create a second scoring contract; this is the same validated rows.
- Queue UI: per manual text item — read-only TA block, optional teacher feedback field,
  blank teacher score bound to the item's real `possible` (now correctly mapped from the
  outer catalog record). Auto-graded items render read-only with their earned scores.
- Feedback composition per the locked product decision in
  `new-quizzes-grading-transport.md`: teacher feedback, separator, TA score/feedback block;
  omit the empty teacher section. AI text never becomes an official score.
- Finalization write safety (all mandatory): freeze the complete current item-result set at
  review; bind edits to stable item IDs and the preflight authoritative result ID; preserve
  untouched/auto-graded items and fudge exactly; write once per student finalization; after
  every accepted or ambiguous write re-fetch, follow the new authoritative result ID, verify
  each reviewed item and the derived total; capture a content-minimized private receipt
  under the session; treat timeout/ambiguity as unknown until reconciled.
- Mixed-evidence routing (locked decision, resolved 2026-07-14): a student with any manual
  item whose evidence requires SpeedGrader (image/PDF/unreadable upload) has their **whole**
  finalization routed to SpeedGrader with an exact link. No partial two-authority flow.
  Note: uploads with locally-extracted text are AI-*draftable* under the shipped payload
  policy, but their official grading still follows this routing rule unless the operator
  relaxes it explicitly.
- Keep the shipped comment-only assignment-level push working and clearly labeled as the
  whole-assignment lane; per-item feedback goes through the new adapter. Do not remove or
  repurpose `comment_writeback_supported` sessions.

## Out of scope

- No AI-written official score. No per-keystroke writes. No scheduled/bulk/auto-push for
  New Quizzes. No total-grade write through the ordinary Submissions API. No file/media
  grading outside Canvas's renderer. No FeedbackExpert consolidation (later batch).

## References (read in this order)

1. `AGENTS.md` — guardrails and execution model.
2. `docs/reference/new-quizzes-grading-transport.md` — canonical capability truth, verified
   chain, write-safety rules, feedback composition decision.
3. `api/powergrader/new_quiz_fetch.py` — proven read chain (`_native_file_transport`,
   `_resolve_native_candidate`), live shapes.
4. `api/powergrader/session_actions.py` — frozen review/apply pattern to mirror
   (`_writeback_mode`, review token, drift, idempotency).
5. `api/tests/test_powergrader_new_quizzes.py`, `api/tests/test_powergrader_manual_push.py`
   — synthetic fixture patterns that mirror captured live shapes.

## Verification

- Focused: `py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_manual_push.py api/tests/test_powergrader_import_results.py`
- Subsystem: `py -m pytest api/tests -k "powergrader or feedback"`
- New tests: happy path, item mismatch, result-version drift, ambiguous write
  reconciliation, idempotent re-finalize, credential-hygiene (no token/URL in session JSON
  or receipts) — synthetic IDs only.
- Rendered `/powergrader` setup and queue flows for a mixed New Quiz (per-item UI,
  SpeedGrader routing, comment-only lane still working) with zero new console errors.
  Backend pytest does not substitute for the rendered check (AGENTS testing policy).
- Live dummy finalization only with explicit operator authorization in that session.

## Stop conditions (RED — stop, record here, return to senior)

- Any unrecognized launch/result/item shape, or the write requires a guessed field,
  credential, or endpoint.
- A credential would need to be persisted or would appear in any error/log/artifact.
- Post-write verification cannot prove which result version is authoritative.
- The change would touch the ordinary Submissions API grade path, scheduled jobs, or any
  public contract.
- A regression is discovered outside this scope.

## Execution result

- Traffic light: **GREEN — Phase A and Phase B complete; New Quiz finalization is implemented with fail-closed web-session transport, frozen review, and SpeedGrader routing.**
- Commit hash: none
- Files changed: `api/powergrader/new_quiz_grader.py`, `api/powergrader/session_actions.py`, `api/powergrader/session_builder.py`, `api/powergrader/ai_workflow.py`, `api/powergrader/ai_workflow_support.py`, `api/powergrader/import_results.py`, `api/powergrader/start_workflow.py`, `api/feedback_results.py`, `api/feedback_pipeline.py`, `api/webui/routes/powergrader.py`, `api/webui/static/powergrader/queue_core.js`, `api/webui/static/powergrader/queue_new_quiz.js`, `api/webui/templates/powergrader_queue.html`, `api/tests/test_powergrader_new_quizzes.py`, `docs/reference/new-quizzes-grading-transport.md`, and this handoff.
- Verification commands and counts: focused `py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_manual_push.py api/tests/test_powergrader_import_results.py` — 31 passed; subsystem `py -m pytest api/tests -k "powergrader or feedback"` — 164 passed; `py -m py_compile api/powergrader/new_quiz_grader.py api/powergrader/session_actions.py api/webui/routes/powergrader.py` — passed; `git diff --check` — passed. Rendered local PowerGrader manual-item and whole-student SpeedGrader states with a short-lived synthetic local session; one editable item, read-only TA and auto-score displays, exact SpeedGrader link shape, and zero new browser-console errors verified.
- Deviations: the sessionless credential's one authorized Phase A POST returned `401`, made no change, and was reconciled read-only. The implementation therefore uses the locked web-session/GraphQL/signed-launch fallback. No live production finalization was issued: the supplied controlled target contains upload evidence and is correctly routed wholly to SpeedGrader under the locked policy.
- Remaining blocker / cleanup decision: none. The synthetic local session and local verification server were removed. No credential, signed URL, raw item payload, student record, or Canvas result content was stored in the repository or handoff.
