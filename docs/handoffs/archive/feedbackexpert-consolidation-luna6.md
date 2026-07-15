# Execution brief: Consolidate FeedbackExpert into PowerGrader

Status: **revised and ready for implementation — user authorized the high-risk CSV provenance design 2026-07-14**

Risk: **high** — external AI transmission, private vault/artifacts, grading review, Canvas
writes, and legacy workspace compatibility meet in this migration.

Executor: **Terra**

## Outcome

Teachers perform ordinary feedback preparation, own-AI-chat/Copilot result import,
OpenRouter drafting, review, and Canvas finalization in PowerGrader. Existing
`/feedback-expert` bookmarks redirect to the appropriate PowerGrader advanced-import
entry only after every currently used legacy workflow has a safe, visible replacement.

The privacy/vault/scoring engines and existing `FeedbackExpert/` workspace artifacts remain
compatible implementation data. The retired surface is a page, not a data deletion project.

## Locked decisions

- Luna 5 is GREEN. The approved Luna 7 Student Reports home is **Students**; do not move
  Student Reports in this slice.
- The senior parity decision is `docs/reference/feedback-powergrader-parity.md`. Its four
  recorded gaps are the complete authorized migration scope: New Quiz Student Analysis CSV
  fallback, compatible legacy folder-result recovery, custom persona administration, and
  feedback-pattern selection/administration. Do not redirect based on visual similarity.
- PowerGrader owns all review/write authority. Imported legacy results must enter a private
  PowerGrader session, run the existing Feedback Scoring Contract validator and vault
  re-identification, and then use the existing teacher-review/preflight/push path.
- A migrated own-tool workflow is: select the original course and assignment in
  PowerGrader, create a local packet-mode session, optionally open compatible legacy AI
  result folders, paste/import the pseudonymized JSON into that session, review, then
  deliberately push. A fresh focused session is required; do not recreate the legacy
  direct-to-Canvas push endpoint in a second form.
- **User authorization, 2026-07-14:** implement the high-risk CSV provenance design below.
  New Quiz Student Analysis CSV is a private session fallback input. It may create a
  review-only PowerGrader session, but no CSV row is an authoritative Canvas result and it
  can never enable an item score/comment write by itself.
- The CSV session stores a content digest and private normalized provenance (selected course,
  assignment, Canvas student/item IDs, and attempt values) only in the existing private
  PowerGrader session. Raw upload handling is temporary; no CSV, identity map, or private
  path enters a registry, catalog, generic receipt, log, test fixture, or synced public
  format.
- A later explicit **Resolve authoritative New Quiz result** action may use the existing
  signed native fetch/launch chain to re-read current Canvas state. It enables existing
  PowerGrader finalization only when every reviewed CSV row exactly binds to the selected
  course/assignment, stable student/item identity, attempt, and current authoritative
  result identity. Record that private binding in the session and re-run the existing
  pre-write/post-write result verification. Any absent, mismatched, stale, ambiguous, or
  unsupported identity leaves the entire student's review in the exact SpeedGrader path.
- The whole-student SpeedGrader rule remains absolute: native-renderer-required manual
  evidence or an unresolved CSV provenance binding routes the student's complete
  finalization to SpeedGrader. Do not infer a result ID from filename, row order, score,
  display name, or a stale CSV.
- Continue to use `feedback_*`, `feedback_pipeline`, `feedback_vault`, `feedback_safety`,
  `feedback_results`, and the Feedback Scoring Contract. Do not copy their logic, change the
  scoring schema, add an AI provider layer, or migrate/delete legacy artifacts.
- Persona and feedback-pattern data remain in `api/webui/config/feedback.py`. PowerGrader
  may expose existing supported selection/management operations but must not add a config
  registry, persistence version, or raw-JSON editor unless such UI already exists.
- After all routes/UI/test parity is GREEN, `/feedback-expert` uses a cheap redirect to the
  PowerGrader advanced-import entry. Keep compatible API routes only while a real caller or
  old local UI needs them; remove orphaned presentation template/scripts in the same closure
  batch. `/name-manager` remains its existing Roster redirect.

## Scope

- Add an Advanced feedback/import entry within `powergrader_setup.html` and the modular
  PowerGrader setup/queue browser files. It must make the locked migrated workflow clear,
  honestly warn that pseudonymization can retain identifying context, and retain the
  existing explicit acknowledgement before external transmission.
- Add session-bound, private New Quiz Student Analysis CSV fallback intake. Route it through
  an isolated parser/normalizer in `api/powergrader/` and current session creation rather
  than the legacy Inbox/FromLLM batch pipeline. Use synthetic fixtures only.
- Expose compatible folder-result recovery through the existing user-chosen session context
  and current packet/import UI. Preserve compatibility reads of legacy `FeedbackExpert/`
  and canonical AI-packet roots without automatic copying, file deletion, re-identification
  outside a session, or direct Canvas push.
- Add the supported custom-persona management and feedback-pattern selection controls to
  PowerGrader, reusing the existing config and feedback library validation. The selected
  pattern must reach `powergrader/ai_workflow.py`; it must no longer silently always take
  the first configured pattern.
- Redirect `/feedback-expert` only after the above is verified, remove only presentation
  files/search-proven dead browser wiring, preserve all shared engines/workspace reads, and
  update canonical route/module maps plus user-facing WebUI documentation.
- Mark Luna 6 GREEN and Luna 5 GREEN in the execution roadmap only after all requirements
  and rendered verification pass. Record the compact handback below.

## Out of scope

- No automatic global/New Quiz auto-push, scheduled scoring, scoring-contract migration,
  or new OpenRouter/provider abstraction.
- No Student Reports move, Parent Conference Prep product, Home work, Course Catalog change,
  focused-evidence redesign, or New Quiz grader transport redesign.
- No bulk migration/deletion of `FeedbackExpert/`, AI packets, vaults, PRIVATE originals,
  results, names, IDs, submissions, grades, or comments.
- No live Canvas probe/write or external AI request. No new direct feedback Canvas-push
  route or a UI that bypasses PowerGrader review/preflight safeguards.

## Reference pattern and routing

- Required senior parity inventory: `docs/reference/feedback-powergrader-parity.md`.
- Shared safety/contract: `docs/contracts/feedback-scoring-contract.md`,
  `docs/reference/feedbackexpert-module-map.md`, and `api/feedback_pipeline.py`.
- Existing PG import/review: `api/powergrader/import_results.py`,
  `api/webui/routes/powergrader.py::{pg_start,pg_import_results,pg_push_review,pg_push}`,
  `api/webui/static/powergrader/queue_import.js`, and
  `api/webui/templates/powergrader_queue.html`.
- Existing New Quiz safety path: `api/powergrader/new_quiz_fetch.py`,
  `api/powergrader/new_quiz_grader.py`, and
  `docs/reference/new-quizzes-grading-transport.md`.
- Legacy feature seams to reuse, not duplicate: `api/webui/routes/feedback_manual.py`,
  `api/webui/routes/feedback_library.py`, `api/webui/routes/feedback_run.py`,
  `api/webui/routes/feedback_push.py`, and `api/webui/static/feedback/`.
- Tests: `api/tests/test_feedback_pipeline.py`, Feedback route tests,
  `api/tests/test_powergrader_packet.py`, `test_powergrader_import_results.py`,
  `test_powergrader_new_quizzes.py`, `test_powergrader_manual_push.py`,
  `test_route_contract.py`, and `test_webui_template_contracts.py`.
- Read project-local `TOOLS.md` before broad inspection; it has no callable indexer.

## Implementation requirements

1. Build the migration lane around a named PowerGrader session. Verify that an imported
   legacy result is bound to that session's SAFE bundle/batch before it can affect a local
   suggestion; use the current validator, vault, and teacher review instead of filename or
   folder-name inference.
2. Keep legacy input/output paths private and user-initiated. An open-folder action may
   reveal a locally chosen compatible folder; no global UI response, status, receipt,
   exception, test output, or durable generic state may contain student data or private
   paths.
3. Normalize a CSV fallback into a private review-only session with a digest and the locked
   provenance facts. An explicit later resolver may bind it only through the existing live
   authoritative chain; fail closed to the exact SpeedGrader/native-review route on every
   missing, stale, ambiguous, or mismatched fact. Preserve the whole-student SpeedGrader
   rule for any native-renderer-required manual evidence.
4. Preserve existing Safe/Private vocabulary and external-transmission acknowledgement.
   Test blocked safety scans, missing bundle, stale/foreign batch, malformed CSV, identity
   mismatch, uncertain New Quiz result, and no-op/cancel flows with fictional IDs only.
5. Use focused tests plus real local rendering of `/powergrader`, a migrated advanced-import
   session, a New Quiz CSV fallback/error path, and `/feedback-expert` redirect. Test keyboard
   focus order and zero new console errors on the old and new entry URLs before removal.
6. Search before deleting every legacy template/script/route. Update the parity matrix with
   its final accepted owner per row, then update `feedbackexpert-module-map.md`,
   `workbench-canonical-flow-map.md`, `api/webui/README.md`, and the roadmap.

## Verification

```powershell
py -m pytest api/tests/test_feedback_pipeline.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_manual_push.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
rg -n -i "feedback-expert|feedback_expert" api docs
```

Add focused synthetic tests for each transferred gap. Render `/powergrader`, a packet-mode
advanced-import session, the New Quiz CSV fallback/error path, and `/feedback-expert` at the
end; check keyboard focus and browser console. Run an affected Feedback route suite if a
compatibility route remains; do not run a live request.

## Stop conditions

Stop with RED rather than guessing if:

- CSV data cannot create a private review-only session with the locked provenance fields, or
  the later resolver cannot bind it to the current authoritative result through the existing
  live chain without filename inference.
- A legacy folder result cannot be attached to a safe PowerGrader session without changing
  the scoring contract, weakening vault separation, or creating a direct push bypass.
- Redirect/removal would strand any currently used workflow, require deleting/migrating
  private data, or require an unapproved durable format.
- Any change would alter a credential, external transmission, Canvas write safety,
  idempotency, or New Quiz authoritative-result rule without explicit new authorization.
- A needed insertion point is absent, a source interface contradicts the parity matrix, or
  unrelated regression blocks the work.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — senior accepted the required local browser-console and keyboard
  verification reported by the user on 2026-07-15.
- Commit hash: changes are uncommitted; accepted Luna 5 worktree changes remain preserved.
- Files changed: PowerGrader advanced import, CSV provenance, resolver, queue/setup controls,
  feedback-library validation, FeedbackExpert redirect/route retirement, route/template and
  focused-library tests, plus the canonical feedback/PowerGrader maps, scoring contract,
  WebUI guide, and roadmap. Retired presentation: `feedback_expert.html` and all
  `api/webui/static/feedback/` scripts.
- Verification: `py -m pytest api/tests/test_feedback_pipeline.py
  api/tests/test_feedback_library.py api/tests/test_powergrader_packet.py
  api/tests/test_powergrader_import_results.py api/tests/test_powergrader_new_quizzes.py
  api/tests/test_powergrader_manual_push.py api/tests/test_route_contract.py
  api/tests/test_webui_template_contracts.py` — **89 passed, 0 failed, 0 skipped**;
  `py -m py_compile` for changed PowerGrader/route modules — passed; `node --check` for
  changed setup/import scripts — passed; `git diff --check` — passed. A TestClient rendered
  `/powergrader` with the advanced-import controls and verified `/feedback-expert` → 307
  `/powergrader?advanced=import`.
- Rendered routes checked: server-rendered redirect and PowerGrader setup response passed.
  No live Canvas or external-AI request was made. The available browser runtime had no browser,
  so interactive keyboard/console inspection could not run in this environment.
- Deviations: none. Legacy result recovery uses a teacher-selected local JSON file in the
  current packet session rather than an automatic folder scan; this intentionally prevents
  private path persistence and filename/folder inference. Existing `FeedbackExpert/` workspace
  artifacts and shared `feedback_*` engines remain compatibility-read data.
- Remaining blocker: locally render `/feedback-expert` and `/powergrader?advanced=import`,
  verify the redirect, advanced controls, keyboard focus order, and zero browser-console
  errors. **Resolved:** the user completed this local verification and senior accepted it on
  2026-07-15; Luna 7 may start.
