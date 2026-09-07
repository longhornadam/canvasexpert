# PowerGrader scoring and privacy engine map

Routing scope: open this map only when the active handoff touches PowerGrader scoring,
result imports, or the shared scoring/privacy engines. It is not global executor context.

This map owns the scoring and privacy engines, pipelines, artifact routing, and every
scoring entry point, whatever route delivers it, including the web UI import, Copilot batch,
and MCP `stage_scores` path. A new way for scores to enter a session gets documented here,
not in the module map. For routes, scripts, templates, browser load order, and backend
package routing, see `docs/reference/powergrader-module-map.md`.

PowerGrader is the single teacher-facing owner of scoring student work and AI feedback.
The legacy grading page is retired: `/feedback-expert` returns a 307 redirect to
`/powergrader?advanced=import`. The legacy compatibility layer for the historical
`FeedbackExpert/` workspace folder (`workspace.LEGACY_FEEDBACK_NAME`, `FEEDBACK_NAME`,
`FEEDBACK_SUBFOLDERS`, `legacy_feedback_root`, `feedback_folder`, etc.) has been removed
entirely; it is a clean break with no migration path, and no code reads that old folder
anymore.

## Active ownership

- **Teacher flow:** `api/webui/templates/powergrader_setup.html` and
  `powergrader_queue.html`, with `static/powergrader/setup_advanced.js`,
  `queue_import.js`, and `queue_new_quiz.js`.
- **Session/review/write owner:** `api/webui/routes/powergrader.py` and
  `api/powergrader/`. Imported result JSON must validate against the selected session's
  SAFE bundle before it affects a suggestion; Canvas writes use the existing
  PowerGrader review/preflight/receipt path.
- **New Quiz CSV fallback:** `api/powergrader/new_quiz_csv.py` creates a private,
  review-only session. `new_quiz_grader.py` resolves current authoritative identity;
  missing, stale, ambiguous, or mismatched identity leaves the full student in
  SpeedGrader.
- **MCP scoring surface:** `api/powergrader/scoring_packet.py` plus the three tools in
  `api/mcp_server/tools.py`. An assistant connected over MCP can call
  `list_scoring_sessions`, pull a paged SAFE bundle with `get_scoring_packet`, and return
  scores with `stage_scores`. This is a third import route onto the existing one, not a
  parallel one: staging runs `import_results` under the same `session_store.session_lock`
  the web UI's import route takes, so a teacher working the queue and an assistant staging
  cannot interleave a read-modify-write on one session file. It is course-gated on the
  session's own `course_id`, refuses on a `packet_digest` mismatch after a session re-run,
  and stages partially rather than all-or-nothing. Staged scores are suggestions awaiting
  teacher review; nothing reaches Canvas on this path even when auto-post is enabled.
- **Persona/pattern library:** `api/webui/routes/feedback_library.py` and
  `api/platform_services/config/feedback.py`. PowerGrader's advanced controls use these routes;
  no second registry or config format exists. (These modules keep the `feedback_`
  name until the optional engine-rename phase.)
- **Legacy redirect owner:** `api/webui/routes/pages.py::feedback_expert_page`.

## Retired presentation and direct-write surface

The old grading page, its `static/feedback/` scripts, and the registered
manual/run/direct-push HTTP routes are removed. The implementation modules are retained
only where they provide compatibility helpers or shared engines; they are not a
teacher-facing alternate Canvas write path.

## Shared privacy and scoring engines

These modules are shared, load-bearing engines that PowerGrader imports. They keep the
`feedback_` prefix for now; an optional later phase may rename them to neutral,
engine-accurate names.

- `api/feedback_pipeline.py` — compatibility facade
- `api/feedback_artifacts.py` — SAFE/PRIVATE artifact helpers
- `api/feedback_contract.py` — scoring prompt/contract text
- `api/feedback_results.py` — parse, validate, normalize, re-identify, CSV
- `api/feedback_safety.py` / `api/feedback_scrub.py` — safety scanning/scrubbing
- `api/feedback_vault.py` — local private vault
- `api/powergrader/writing_timeline.py` — local OOXML revision parsing, author-match
  categorization, the whitelist-rebuilt SAFE projection, and the teacher-only
  observation guard. `feedback_results.reidentify` and `feedback_artifacts` both
  depend on it; it imports nothing from `api/` in return.
- `api/powergrader/oral_reading.py` — local-only media transcript/alignment evidence;
  it imports neither Canvas nor LLM clients. `feedback_artifacts` may rebuild a
  scrubbed transcript-first allowlist for SAFE scoring; audio, paths, media IDs,
  filenames, word events, and model-cache values remain private.
- `api/ai_transmission.py` — the single authorization boundary for live OpenRouter sends
- `api/operational_log.py` — sanitized local support/transport event log
- `docs/contracts/feedback-scoring-contract.md` — scoring contract

## One readable-work capability, one gate

"Can PowerGrader read this student's work?" has exactly one answer, and it lives in
`student_attachments.AI_TEXT_EXTS` — the extensions `route_bytes` turns into
AI-sendable response text (the trusted text/code set plus `.docx`). Rasters are
AI-eligible but carry no response text, so they are excluded.

`autoscore_queue.READABLE_UPLOAD_EXTS` is **derived** from that set, never
hand-maintained. The two were independent lists for a month and drifted in both
directions: the gate promised scheduled auto-score for 20 code extensions
(`.java`, `.ts`, `.sql`, `.ipynb`, …) that `route_bytes` routes to `local_only`, so
every student would be held and nothing scored while the teacher was still charged
for the run — the precise failure the original design forbade — while excluding
`.docx`, which the router extracts in full. Anything that changes what the router
can read must change this one set, and
`test_autoscore_gate_matches_what_the_attachment_router_can_read` pins the
derivation against observed `route_bytes` behavior so it cannot drift again.

## Guardrails

- **Assistant words are attributed; the teacher's are not.** Feedback reaches Canvas
  under the teacher's own name, because it is their token and their gradebook. That is
  right for words they wrote and wrong for words an assistant drafted: a student reading
  it cannot tell the difference, and neither can the teacher weeks later. Every outbound
  path that can carry assistant prose prefixes it with
  `Autofeedback from an automated assistant:` followed by a blank line.
  `api/powergrader/attribution.py` owns the wording so it cannot drift between the three
  callers, and `api/tests/powergrader/test_attribution.py` pins the rule.
  - The **reviewed assignment push** (`session_actions._payload`) has one feedback box
    holding either kind, so provenance is decided by comparing it to the assistant's
    draft. An accepted draft is marked, an accepted draft the teacher added a line to is
    marked, and feedback the teacher wrote themselves goes out unmarked.
  - **Automatic posting** (`autopush_executor`) is always marked. Nothing on that path is
    teacher-written and nothing is reviewed before it posts.
  - **New Quiz item finalization** (`new_quiz_grader.compose_feedback`) marks the
    assistant's block. Canvas exposes one grader-feedback value per item, so a teacher
    note and the assistant's block share a field under a `MY FEEDBACK` / attribution
    split.
  - Marking is idempotent, so a value that round-trips through a session file cannot
    accumulate banners, and empty feedback stays empty so callers can keep using
    falsiness to decide whether to send a comment at all.
- **Single grading surface:** PowerGrader is the only code that writes a Canvas
  submission comment (`comment[text_comment]`) as AI feedback. Gradebook may write
  `posted_grade` for post-hoc adjustment (curve, late penalty, extension, policy) but
  never writes AI feedback. This invariant is machine-enforced by
  `api/tests/test_grading_surface_invariant.py`, which fails the build if any file
  outside `api/powergrader/` writes `comment[text_comment]`.
- **Blind-first withholds unrevealed AI scores from the browser, not just from the DOM.**
  `api/powergrader/blind_first.py` owns the projection `pg_get_session` returns; a
  session with blind-first on ships `ai_score: null` for every unrevealed student. The
  teacher's blind capture (`blind_score`, `blind_feedback`, `blind_delta`) is teacher-only
  session data and never enters a Canvas payload, a push receipt, a SAFE artifact, or a
  catalog. See the Blind-first section of `docs/reference/powergrader-module-map.md`.
- SAFE files are pseudonymized, not guaranteed anonymous; teachers review them before
  external upload.
- CSV bytes, legacy result-folder paths, names, IDs, grades, comments, and submission
  content remain private and never enter catalogs, generic receipts, or test fixtures.
- Imported AI results are drafts until reviewed in PowerGrader. No import path bypasses
  PowerGrader's current-state, idempotency, or post-write verification.
- **The Writing Timeline never concludes anything.** It reports editing-process facts:
  counts, times, booleans, and author-match categories. Raw Office authors and document
  properties stay in the private session. The optional teacher-only
  `writing_process_observations` string is never an integrity conclusion, a probability,
  or a penalty recommendation — enforced by
  `writing_timeline.sanitize_process_observation` in `reidentify`, not by prompt text
  alone. It never reaches `feedback`, a score, a Canvas write, or a receipt.
