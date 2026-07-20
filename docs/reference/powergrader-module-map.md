# PowerGrader Route Card

Routing scope: open this card only when the active handoff touches PowerGrader, then read
the relevant section. It is not global executor context and does not replace a handoff's
exact file/symbol list.

## Entry points

- Route orchestration: `api/webui/routes/powergrader.py`
- Setup / queue templates: `api/webui/templates/powergrader_setup.html`,
  `api/webui/templates/powergrader_queue.html`
- Backend workflow package: `api/powergrader/`
- Setup browser shim/features: `api/webui/static/powergrader_setup.js`,
  `api/webui/static/powergrader/setup_*.js`
- Queue browser shim/features: `api/webui/static/powergrader_queue.js`,
  `api/webui/static/powergrader/queue_*.js`
- Local course navigation: `api/course_catalog.py`,
  `api/webui/routes/course_catalog.py`

Keep `powergrader.py` a route coordinator and the two top-level browser files thin
namespace shims.

## Ownership routes

| Concern | Owners |
|---|---|
| Start/session assembly | `start_workflow.py`, `session_builder.py`, `session_store.py` |
| Teacher save/push | `session_actions.py`, `queue_review.js` |
| AI workflow and SAFE artifacts | `ai_workflow.py`, `ai_workflow_support.py`, `queue_privacy.js` |
| Copilot packets/import | `copilot_packet.py`, `copilot_packet_support.py`, `import_results.py`, `queue_import.js` |
| Focused assignment evidence | `assignment_refresh.py`, `canvas_fetch.py`, `new_quiz_fetch.py`, `student_attachments.py` |
| Late catch-up | `late_catchup.py`, `routes/powergrader_late.py`, `queue_late_catchup.js` |
| Scheduled autoscore | `autoscore_queue.py`, `autoscore_claims.py`, `scheduled_autoscore_support.py`, `routes/routines_powergrader.py` |
| Automatic-post policy | `autopush_policy.py`, `autopush_policy_result.py`, `push_context.py`, `interactive_autopush.py` |
| Setup/catalog flow | `setup_core.js`, `setup_sessions.js`, `setup_autoscore.js`, `course_catalog.py`, `routes/course_catalog.py` |
| Queue state/rendering | `queue_core.js`, `queue_review.js`, `queue_import.js`, `queue_late_catchup.js`, `queue_privacy.js` |
| Source-material context | `api/webui/source_materials.py`, `api/webui/source_material_extractors.py` |

Browser load order is template-owned. Setup loads the shim before sessions, core, and
autoscore features. Queue loads the shim before core, review, privacy, late-catchup, and
import features. Preserve `window.CE_POWERGRADER_SETUP` and existing queue namespace seams.

## Privacy and write boundaries

- PowerGrader sessions/jobs under `<workspace>/_System/PowerGrader/` are PRIVATE. Names,
  submissions, grades, comments, and identity mappings never enter the repo, fixtures,
  generic receipts, catalogs, or logs.
- Course Catalog is a student-free navigation/search projection. It may select work but
  never supplies focused evidence or authorizes a Canvas write. See
  `docs/contracts/course-catalog-contract.md`.
- SAFE packets are pseudonymized, not guaranteed anonymous. Teachers review them before
  external upload. See `docs/contracts/feedback-scoring-contract.md`.
- AI scores/comments are drafts until teacher review and push except for two narrow,
  default-off, non-global opt-ins:
  - a specific scheduled job/assignment, after eligibility, fresh-state, policy,
    idempotency, and receipt checks;
  - one newly created assisted/packet interactive session, under the per-session lock from
    authoritative reload through final save.
- Interactive auto-post is unavailable to Grade Myself, Classic Quiz, and New Quiz.
  Packet late generation never writes; only a valid import against that late batch's SAFE
  bundle may trigger the scoped path. Uncertain results remain drafts.
- New Quiz sessions have a separate teacher-reviewed item-finalization lane for item scores
  and per-item feedback. In a live course with active/current instructor enrollment, it uses
  Canvas's first-party, short-lived signed grader transport rather than the ordinary
  assignment-total `PUT`; concluded, closed, past-enrollment, or otherwise restricted courses
  may return `403`. The lane preserves preflight freeze, result-version drift detection,
  idempotency, post-write verification, content-minimized receipts, and fail-closed
  SpeedGrader fallback. New Quiz scheduled, late-catch-up, and interactive automatic posting
  remain unavailable. See `docs/reference/new-quizzes-grading-transport.md`.

## Symptom routing

| Symptom | Start with |
|---|---|
| Setup/course/module/assignment selection | `setup_core.js`, `routes/course_catalog.py`, `course_catalog.py` |
| Session start or assembly | `powergrader.py::pg_start`, `start_workflow.py`, `session_builder.py` |
| Queue rendering/navigation | `queue_core.js`, `queue_review.js` |
| Save or reviewed push | `queue_review.js`, `session_actions.py` |
| Packet/import mismatch | `queue_import.js`, `import_results.py`, `copilot_packet.py` |
| Evidence/attachments | `assignment_refresh.py`, `canvas_fetch.py`, `new_quiz_fetch.py`, `student_attachments.py` |
| Late submission flow | `queue_late_catchup.js`, `powergrader_late.py`, `late_catchup.py` |
| Auto-post eligibility/idempotency | `autopush_policy.py`, `push_context.py`, `interactive_autopush.py`, `autoscore_claims.py` |
| Scheduled routine | `routines_powergrader.py`, `scheduled_autoscore_support.py`, `autoscore_queue.py` |
| Privacy/SAFE artifacts | `queue_privacy.js`, `ai_workflow.py`, `ai_workflow_support.py` |

## Test routing

Core focused regressions:

- `api/tests/test_powergrader_packet.py`
- `api/tests/test_powergrader_copilot_packet.py`
- `api/tests/test_powergrader_import_results.py`
- `api/tests/test_powergrader_late_catchup.py`
- `api/tests/test_route_contract.py`

The handoff must add the focused policy/idempotency tests owned by any changed high-risk
path. Browser changes require rendered checks of `/powergrader` and/or the affected queue
route with zero new console errors. Use `tools/size_report.py` only when file size is the
question; this card does not carry line-count snapshots.
