# FeedbackExpert → PowerGrader parity matrix

Status: **Luna 6 implementation complete**, 2026-07-14. This is a source-level routing
inventory; it contains no workspace artifacts, Canvas data, or credentials.

## Decision

PowerGrader is the single teacher-facing owner for ordinary assignment grading and reviewed
AI-assisted scoring. It already has the stronger session/frozen-review/Canvas-write path.
`feedback_*` modules remain the shared privacy, vault, validation, packet, persona, and
pattern engines; Luna 6 must not copy or delete them.

The legacy FeedbackExpert page cannot truthfully redirect until its three migration seams
have a concrete PowerGrader replacement: manual Student Analysis CSV fallback, legacy
folder-result recovery, and persona/pattern administration. A link alone is not parity.

## Current capability inventory

| Workflow | Current FeedbackExpert owner | Current PowerGrader owner | Parity / Luna 6 action |
|---|---|---|---|
| Assignment-scoped preparation | `/api/feedback/run/prepare` fetches/pseudonymizes one assignment | `routes/powergrader.py::pg_start` plus `powergrader/ai_workflow.py` | **Parity.** PG is canonical; it preserves a private session and focused evidence. |
| SAFE/PRIVATE artifact creation and safety scan | `feedback_run.py`, `feedback_artifacts.py`, `feedback_safety.py` | `powergrader/ai_workflow.py` reuses the same engines | **Parity.** Preserve honest pseudonymization wording and compatibility reads. |
| Own-AI-chat packet and pasted JSON | folder packet + `/api/feedback/push/preview` | `packet.py`, `copilot_packet.py`, `import_results.py`, queue import UI | **Parity.** PG adds session/batch binding; it is the replacement. |
| Contract parsing, validation, and re-identification | `feedback_pipeline.parse_results/validate_results/reidentify` | `powergrader/import_results.py` calls those same helpers | **Parity.** Do not add a second scoring schema. |
| OpenRouter drafting | `/api/feedback/run/stream` and `feedback_manual.py::score_openrouter` | `powergrader/ai_workflow.py` assisted mode after budget and safety gates | **Parity for ordinary assignment scoring.** PG is canonical; no provider abstraction change. |
| Teacher review and Assignment grade/comment push | `feedback_push.py` direct preview/apply | PowerGrader review, preflight, push review/push, receipts | **Parity, stronger in PG.** Never weaken review, drift, or idempotency safeguards to imitate legacy routes. |
| New Quiz direct response review/finalization | manual CSV/import is read-only; no item write | `new_quiz_fetch.py`, `new_quiz_grader.py`, session review/finalize | **Parity and expanded capability.** PG is the only finalization owner. |
| New Quiz Student Analysis CSV fallback | Retired Inbox/manual CSV presentation | `new_quiz_csv.py`, resolver, and queue New Quiz controls | **Parity.** CSV is private review-only with digest/provenance; a signed current-result binding and matching preflight are required before finalization, otherwise whole-student SpeedGrader. |
| Folder-driven own-tool results (`FromLLM` → re-identify → `ToEnter`) | Retired folder presentation | packet session + local result-file selection + `import_results.py` | **Parity.** Teacher selects a compatible JSON file locally; its content enters only the selected session validator and SAFE-bundle/vault path. No folder path or direct push is retained. |
| Custom persona CRUD | `feedback_library.py`, retired persona script | PowerGrader advanced setup + `feedback_library.py` | **Parity.** Existing config is the only owner; controls add/remove custom personas with validation. |
| Feedback-pattern administration | `feedback_library.py::save_patterns` | PowerGrader selected pattern + advanced graphical editor | **Parity.** Existing config/library route remains the owner; no raw-JSON editor or new format. |
| Folder open actions | Retired global folder actions | queue session artifact actions and local result-file picker | **Parity.** Only current-session artifact folders are opened; compatible legacy result content is user-selected and bound to that session. |
| Name Manager/privacy administration | legacy page compatibility route only | `/name-manager` already redirects to Roster safety lens | **Parity.** No new Name Manager work. |

## Locked migration path

1. PowerGrader remains the only grading/review/write authority. The migration may create a
   session from an already prepared compatible artifact, but it must pass the same contract,
   vault, review, and current-Canvas safeguards as a newly started session.
2. New Quiz CSV is fallback input to a private PowerGrader session only. It cannot create a
   write path on its own, substitute for native evidence, or persist raw upload data outside
   the existing private session/canonical evidence boundary.
3. Persona and pattern storage stay in `api/webui/config/feedback.py`; PowerGrader gains
   the teacher-facing controls, not a new registry or config format.
4. The legacy route redirects after those flows pass focused route/template checks. Browser
   rendering remains an acceptance check when a browser is available;
   and retained cheap compatibility links for existing bookmarks. `FeedbackExpert/` workspace
   data stays read-compatible forever; no batch deletion or migration is authorized.
5. User authorized the CSV provenance + later live authoritative-binding design on
   2026-07-14. It is not a CSV-only grade transport: unresolved identity remains review-only
   and routes the entire student to SpeedGrader.

## Source and test seams

- Compatibility route: `api/webui/routes/feedback.py` (library API only) and
  `routes/pages.py::feedback_expert_page`; legacy manual/run/push routes are unregistered.
- Shared engines: `api/feedback_pipeline.py`, `api/feedback_artifacts.py`,
  `api/feedback_results.py`, `api/feedback_vault.py`, `api/feedback_safety.py`.
- PowerGrader routes/UI: `api/webui/routes/powergrader.py`,
  `api/webui/templates/powergrader_setup.html`,
  `api/webui/templates/powergrader_queue.html`, `api/webui/static/powergrader/`.
- PowerGrader engines: `api/powergrader/ai_workflow.py`, `packet.py`,
  `import_results.py`, `new_quiz_fetch.py`, `new_quiz_grader.py`, and session helpers.
- Current focused oracles: `api/tests/test_feedback_pipeline.py`, feedback route tests,
  `api/tests/test_powergrader_packet.py`, `test_powergrader_import_results.py`,
  `test_powergrader_new_quizzes.py`, and `test_powergrader_manual_push.py`.
