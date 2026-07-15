# FeedbackExpert Compatibility Module Map

FeedbackExpert is retired as a teacher-facing page. `/feedback-expert` returns a
307 redirect to `/powergrader?advanced=import`; existing `FeedbackExpert/` workspace
artifacts remain compatibility-read data and are never automatically copied or deleted.

## Active ownership

- **Teacher flow:** `api/webui/templates/powergrader_setup.html` and
  `powergrader_queue.html`, with `static/powergrader/setup_advanced.js`,
  `queue_import.js`, and `queue_new_quiz.js`.
- **Session/review/write owner:** `api/webui/routes/powergrader.py` and
  `api/powergrader/`. Legacy result JSON must validate against the selected session's
  SAFE bundle before it affects a suggestion; Canvas writes use the existing
  PowerGrader review/preflight/receipt path.
- **New Quiz CSV fallback:** `api/powergrader/new_quiz_csv.py` creates a private,
  review-only session. `new_quiz_grader.py` resolves current authoritative identity;
  missing, stale, ambiguous, or mismatched identity leaves the full student in
  SpeedGrader.
- **Persona/pattern library:** `api/webui/routes/feedback_library.py` and
  `api/webui/config/feedback.py`. PowerGrader's advanced controls use these routes;
  no second registry or config format exists.
- **Redirect owner:** `api/webui/routes/pages.py::feedback_expert_page`.

## Retired presentation and direct-write surface

The old `feedback_expert.html` page, `static/feedback/` scripts, and the registered
manual/run/direct-push FeedbackExpert HTTP routes are removed. The implementation
modules are retained where they provide compatibility helpers or shared engines; they
are not a teacher-facing alternate Canvas write path.

## Shared privacy and contract engines

- `api/feedback_pipeline.py` — compatibility facade
- `api/feedback_artifacts.py` — SAFE/PRIVATE artifact helpers
- `api/feedback_contract.py` — scoring prompt/contract text
- `api/feedback_results.py` — parse, validate, normalize, re-identify, CSV
- `api/feedback_safety.py` / `api/feedback_scrub.py` — safety scanning/scrubbing
- `api/feedback_vault.py` — local private vault
- `docs/contracts/feedback-scoring-contract.md` — scoring contract

## Guardrails

- SAFE files are pseudonymized, not guaranteed anonymous; teachers review them before
  external upload.
- CSV bytes, legacy result-folder paths, names, IDs, grades, comments, and submission
  content remain private and never enter catalogs, generic receipts, or test fixtures.
- Imported AI results are drafts until reviewed in PowerGrader. No FeedbackExpert route
  bypasses PowerGrader's current-state, idempotency, or post-write verification.
