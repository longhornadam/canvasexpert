# PowerGrader scoring and privacy engine map

Routing scope: open this map only when the active handoff touches PowerGrader scoring,
result imports, or the shared scoring/privacy engines. It is not global executor context.

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
- **Persona/pattern library:** `api/webui/routes/feedback_library.py` and
  `api/webui/config/feedback.py`. PowerGrader's advanced controls use these routes;
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
- `api/ai_transmission.py` — the single authorization boundary for live OpenRouter sends
- `api/operational_log.py` — sanitized local support/transport event log
- `docs/contracts/feedback-scoring-contract.md` — scoring contract

## Guardrails

- **Single grading surface:** PowerGrader is the only code that writes a Canvas
  submission comment (`comment[text_comment]`) as AI feedback. Gradebook may write
  `posted_grade` for post-hoc adjustment (curve, late penalty, extension, policy) but
  never writes AI feedback. This invariant is machine-enforced by
  `api/tests/test_grading_surface_invariant.py`, which fails the build if any file
  outside `api/powergrader/` writes `comment[text_comment]`.
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
