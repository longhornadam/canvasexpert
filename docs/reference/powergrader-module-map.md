# PowerGrader Module Map

Purpose: give future debugging sessions a low-token routing map so they can jump
straight to the owning file instead of re-mapping PowerGrader from scratch.

As of 2026-07-15, the old browser entry files are thin shims. PowerGrader setup now opens
course assignment/module choices from Course Catalog v1 before refreshing the selected
Current course in the background. Use this file as the first stop before reading code.

## Page / route ownership

- Route owner: `api/webui/routes/powergrader.py`
- Setup page template: `api/webui/templates/powergrader_setup.html` (extends
  `layouts/workspace.html` with the `full` variant and composes session triage plus
  the start form)
- Queue page template: `api/webui/templates/powergrader_queue.html` (extends
  `layouts/workspace.html` with the `full` variant and composes the grading queue as
  a responsive Instrument)
- Backend workflow package: `api/powergrader/`

`powergrader.py` remains the APIRouter owner only. Route-local support should move
into nearby helper modules or the backend package when it becomes reusable.

## Key files

For current source sizes, use [`tools/size_report.py`](../../tools/size_report.py).

- `api/webui/routes/powergrader.py` - route orchestration owner
- `api/course_catalog.py` - Course Catalog v1 validation, acquisition, and storage owner
- `api/webui/routes/course_catalog.py` - Current-course-gated disk-read/refresh routes
- `api/webui/static/powergrader/setup_core.js` - local-first setup/catalog consumer
- `api/webui/static/powergrader/setup_sessions.js`
- `api/webui/static/powergrader/setup_autoscore.js`
- `api/webui/static/powergrader_setup.css`
- `api/webui/static/powergrader_queue.css`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/templates/powergrader_queue.html`
- `api/webui/static/powergrader/queue_core.js`
- `api/webui/static/powergrader/queue_review.js`
- `api/webui/static/powergrader/queue_import.js`
- `api/webui/static/powergrader/queue_late_catchup.js`
- `api/webui/static/powergrader/queue_privacy.js`
- `api/webui/static/powergrader_setup.js`
- `api/webui/static/powergrader_queue.js`
- `api/powergrader/start_workflow.py`
- `api/powergrader/ai_workflow.py`
- `api/powergrader/ai_workflow_support.py`
- `api/powergrader/autoscore_queue.py`
- `api/powergrader/autoscore_claims.py`
- `api/powergrader/autopush_policy.py`
- `api/powergrader/autopush_policy_result.py`
- `api/powergrader/push_context.py` - scheduled and interactive authorization-context builders
- `api/powergrader/interactive_autopush.py` - guarded fresh-state runner for one interactive trigger
- `api/powergrader/copilot_packet.py`
- `api/powergrader/copilot_packet_support.py`
- `api/webui/routes/routines_powergrader.py`
- `api/powergrader/scheduled_autoscore_support.py`

## Source-material routing

- `api/webui/source_materials.py` — workspace paths, source-material
  listing, context assembly, token estimation, warnings, response presets
- `api/webui/source_material_extractors.py` — file-format decoding and
  normalization (PDF, DOCX, PPTX, XLSX, ODT, HTML, RTF, plain text)

## Setup screen routing

Template load order:

1. `api/webui/static/powergrader_setup.js` - thin namespace shim only
2. `api/webui/static/powergrader/setup_sessions.js` - session fetch, filtering,
   lane classification, counts, cards, and empty/error states
3. `api/webui/static/powergrader/setup_core.js` - shared setup flow
4. `api/webui/static/powergrader/setup_autoscore.js` - autoscore/model/estimate features

Ownership:

- `setup_core.js`
  - mode switching
  - local Course Catalog read followed by one background selected-course refresh per page
    session
  - module picker defaults to the last three modules in Canvas course order
  - assignment search spans the full local course catalog by assignment name, normalized
    description text, and associated module name without a Canvas request
  - explicit course-level **Sync course list** kept separate from assignment-evidence
    **Refresh from Canvas**
  - rubric picker sync
  - session start submit flow
  - shared `window.CE_POWERGRADER_SETUP` namespace
- `setup_sessions.js`
  - session summary fetch and course filtering
  - exclusive Attention, Continue, and Completed classification
  - responsive session cards, rail counts, and empty/error states
- `setup_autoscore.js`
  - model picker
  - live OpenRouter model list loading
  - estimate request/rendering
  - source-files JSON sync
  - privacy pipeline strip rendering
- `powergrader_setup.html` + `powergrader_setup.css`
  - responsive setup layout (1180px max, sectioned workspace)
  - action footer with AI acknowledgment and start button

## Queue screen routing

Template load order:

1. `api/webui/static/powergrader_queue.js` - thin namespace shim only
2. `api/webui/static/powergrader/queue_core.js` - shared queue flow
3. `api/webui/static/powergrader/queue_review.js` - teacher grading actions
4. `api/webui/static/powergrader/queue_privacy.js` - privacy strip
5. `api/webui/static/powergrader/queue_late_catchup.js` - late watch/late scoring
6. `api/webui/static/powergrader/queue_import.js` - Safe AI Packet / Copilot import flow

Ownership:

- `queue_core.js`
  - session bootstrap/load
  - shared queue state getters/setters
  - `reloadSession()` and shared escaping helpers
  - student rendering
  - AI draft formatting
  - progress/status rendering
  - latest automatic-post summary/history banner, disable control, and auto-posted row badge/hint
- `queue_review.js`
  - approve/skip/save
  - push-one and bulk push
  - AI score/apply actions
  - emoji insertion
  - queue navigation buttons + keyboard shortcuts
- `queue_privacy.js`
  - privacy audit strip summary and actions
- `queue_late_catchup.js`
  - assisted late scoring and packet **Generate Late Copilot Batch** controls
  - late-watch strip rendering
- `queue_import.js`
  - packet strip rendering
  - legacy JSON import
  - Copilot batch import, including Late labels and full-session refresh after import
  - packet folder / prompt actions

## Backend package routing

- `api/powergrader/ai_workflow.py`
  - Safe AI Packet creation
  - pseudonymization/safety gate
  - OpenRouter scoring path
  - Copilot packet batching
- `api/powergrader/ai_workflow_support.py`
  - shared workflow result shaping
  - privacy artifact dict shaping
  - source-context privacy-step shaping
- `api/powergrader/start_workflow.py`
  - reusable start-session support
  - extra-time map assembly
  - privacy-audit append
  - final session-object assembly
- `api/powergrader/autoscore_queue.py`
  - scheduled auto-score queue persistence
  - assignment eligibility classification
  - due-job selection and queue mutation
- `api/powergrader/autoscore_claims.py`
  - claim/lease lifecycle for scheduled auto-score jobs
  - worker identity resolution
  - lease refresh/release rules
- `api/powergrader/autopush_policy.py`
  - teacher opt-in and assignment eligibility checks
  - score/feedback/idempotency/canvas-state evaluation
  - final auto-push decision for one student
- `api/powergrader/autopush_policy_result.py`
  - canonical decision payload builders for blocked/review/allowed outcomes
- `api/powergrader/push_context.py`
  - immutable scheduled-job and interactive-session authorization contexts
  - policy-v2 grade/comment permission flags consumed by the shared evaluator/executor
- `api/powergrader/interactive_autopush.py`
  - interactive-session guards and exact trigger scoping
  - fresh paginated Canvas submission/assignment projection with fail-closed fallback
  - receipt-directory resolution and sanitized latest-run summary/log shaping
- `api/powergrader/session_builder.py`
  - queue student list construction
  - final session dict layout
- `api/powergrader/session_actions.py`
  - save-grade mutation
  - Canvas push mutation
- `api/powergrader/import_results.py`
  - Copilot / legacy import validation and merge
  - exact updated-user IDs and batch-owned SAFE-bundle selection; legacy fallback only when
    the batch has no bundle field
- `api/powergrader/copilot_packet.py`
  - fresh-chat Copilot batch construction
  - token-budget-based batch splitting
  - batch metadata and folder/file manifest assembly
- `api/powergrader/copilot_packet_support.py`
  - Copilot file 01/02/03 text shaping
  - batch prompt text
  - README and markdown file writing helpers
- `api/powergrader/late_catchup.py`
  - late submission detection and watch bookkeeping
- `api/powergrader/assignment_refresh.py`
  - focused assignment refresh and the private, URL-free evidence-manifest input for new sessions
  - 10 MiB aggregate binary budget, managed-evidence reuse, and incomplete-scope signaling
  - explicit setup refresh/folder actions use this same owner
- `api/powergrader/session_store.py`
  - session persistence on disk under `_System/PowerGrader/Sessions/`, with new-first legacy reads
  - process-local per-session `RLock`; interactive trigger routes hold it from authoritative
    load through fresh-state evaluation, any Canvas PUT, and final save
- `api/powergrader/canvas_fetch.py`
  - submission fetch plus authenticated ordinary-upload streaming, atomic preservation, and shared attachment routing
- `api/powergrader/new_quiz_fetch.py`
  - read-only Student Analysis snapshot, URL-free expected evidence, unambiguous native attempt joins, and clean signed-file download
- `api/powergrader/student_attachments.py`
  - local text/DOCX/raster routing, extraction sidecars, eligibility gates, and metadata-stripped AI derivatives
- `api/webui/workspace.py`
  - canonical Course Catalog and course/assignment/student/attempt path ownership plus legacy compatibility helpers
- `api/course_catalog.py`
  - strict URL-free Course Catalog v1 allowlists and validator
  - parallel assignment/module acquisition with bounded missing-item fallback
  - independent scope merge, canonical/previous/quarantine storage, and conflict warnings
- `api/webui/routes/course_catalog.py`
  - disk-only local catalog GET and read-only Canvas refresh POST, both gated to Current courses
- `api/webui/config/courses.py`
  - saved-course lookup for nickname/name/ID display ownership
- `api/powergrader/scheduled_autoscore_support.py`
  - scheduled autoscore label/status helpers
  - existing Canvas-state extraction
  - autopush summary/decision payload shaping

## Route-adjacent helper routing

- `api/webui/routes/powergrader_late.py`
  - late-catchup route support and compatibility bridge
- `api/webui/routes/powergrader.py`
  - session-scoped automatic-post authorization at start
  - locked `packet_import` and `assisted_late` triggers plus the locked disable endpoint
  - packet late generation remains write-free until a valid batch import
- `api/webui/routes/powergrader_helpers.py`
  - pure response/payload helpers
- `api/webui/routes/powergrader_setup_support.py`
  - setup page context, queue page context, estimate payload shaping
  - course-module picker loading and module-item reference shaping
- `api/webui/routes/routines_powergrader.py`
  - scheduled autoscore and late-catchup routine runners
  - execution-time Current-course gates before queue claims, Canvas reads, AI calls,
    session mutation, or Canvas writes; Previous-course work remains queued for
    automatic resumption when made Current
  - imports pure autoscore helper logic from the backend package

## First places to look by symptom

- Setup page fails before session creation:
  - `setup_core.js`
  - `api/webui/routes/course_catalog.py`
  - `api/course_catalog.py`
  - `setup_autoscore.js`
  - `powergrader.py::pg_estimate`
  - `powergrader.py::pg_start`
- Queue loads but rendering is wrong:
  - `queue_core.js`
  - `session_builder.py`
- Save/push behavior is wrong:
  - `queue_review.js`
  - `session_actions.py`
- AI import behavior is wrong:
  - `queue_import.js`
  - `import_results.py`
  - `copilot_packet.py`
  - `copilot_packet_support.py`
- Late catch-up behavior is wrong:
  - `queue_late_catchup.js`
  - `powergrader_late.py`
  - `late_catchup.py`
- Privacy strip or packet artifacts are wrong:
  - `queue_privacy.js`
  - `ai_workflow.py`
  - `ai_workflow_support.py`
  - `start_workflow.py`
- Auto-push eligibility or idempotency behavior is wrong:
  - `autopush_policy.py`
  - `autopush_policy_result.py`
  - `push_context.py`
  - `interactive_autopush.py`
  - `powergrader.py::{pg_start,pg_import_results,pg_late_score,pg_auto_post_disable}`
  - `autoscore_claims.py`
- Scheduled autoscore routine behavior is wrong:
  - `routines_powergrader.py`
  - `scheduled_autoscore_support.py`
  - `autoscore_queue.py`

## Rule of thumb for changes

- Keep route files as orchestration owners.
- Put reusable workflow logic in `api/powergrader/`.
- Keep browser entry files as thin shims plus feature files loaded in template order.
- Prefer adding one small namespace seam over duplicating fetch/reload/render helpers.
