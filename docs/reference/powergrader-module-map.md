# PowerGrader Module Map

Purpose: give future debugging sessions a low-token routing map so they can jump
straight to the owning file instead of re-mapping PowerGrader from scratch.

As of 2026-07-13, the old browser entry files are thin shims. The route owner remains
a 513-line orchestration file; the source-material facade and format readers are now
split for lower-cost debugging. Use this file as the first stop before reading code.

## Page / route ownership

- Route owner: `api/webui/routes/powergrader.py`
- Setup page template: `api/webui/templates/powergrader_setup.html` (extends
  `workbench_base.html` and composes session triage plus the start form)
- Queue page template: `api/webui/templates/powergrader_queue.html` (extends
  `workbench_base.html` and composes the grading queue as a responsive Instrument)
- Backend workflow package: `api/powergrader/`

`powergrader.py` remains the APIRouter owner only. Route-local support should move
into nearby helper modules or the backend package when it becomes reusable.

## Current size snapshot

- `api/webui/routes/powergrader.py` - 513 lines
- `api/webui/static/powergrader/setup_core.js` - 381 lines
- `api/webui/static/powergrader/setup_sessions.js` - 115 lines
- `api/webui/static/powergrader/setup_autoscore.js` - 390 lines
- `api/webui/static/powergrader_setup.css` - 527 lines
- `api/webui/static/powergrader_queue.css` - 230 lines
- `api/webui/templates/powergrader_setup.html` - 304 lines
- `api/webui/templates/powergrader_queue.html` - 163 lines
- `api/webui/static/powergrader/queue_core.js` - 332 lines
- `api/webui/static/powergrader/queue_review.js` - 173 lines
- `api/webui/static/powergrader/queue_import.js` - 261 lines
- `api/webui/static/powergrader/queue_late_catchup.js` - 159 lines
- `api/webui/static/powergrader/queue_privacy.js` - 63 lines
- `api/webui/static/powergrader_setup.js` - 4 lines
- `api/webui/static/powergrader_queue.js` - 4 lines
- `api/powergrader/start_workflow.py` - 88 lines
- `api/powergrader/ai_workflow.py` - 394 lines
- `api/powergrader/ai_workflow_support.py` - 61 lines
- `api/powergrader/autoscore_queue.py` - 427 lines
- `api/powergrader/autoscore_claims.py` - 202 lines
- `api/powergrader/autopush_policy.py` - 308 lines
- `api/powergrader/autopush_policy_result.py` - 63 lines
- `api/powergrader/copilot_packet.py` - 222 lines
- `api/powergrader/copilot_packet_support.py` - 137 lines
- `api/webui/routes/routines_powergrader.py` - 361 lines
- `api/powergrader/scheduled_autoscore_support.py` - 127 lines

## Source-material routing

- `api/webui/source_materials.py` — 216 lines — workspace paths, source-material
  listing, context assembly, token estimation, warnings, response presets
- `api/webui/source_material_extractors.py` — 244 lines — file-format decoding and
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
  - course -> module -> assignment loading
  - module picker defaults to the last three modules in Canvas course order
  - assignment search spans the full course regardless of the active module selection
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
- `queue_review.js`
  - approve/skip/save
  - push-one and bulk push
  - AI score/apply actions
  - emoji insertion
  - queue navigation buttons + keyboard shortcuts
- `queue_privacy.js`
  - privacy audit strip summary and actions
- `queue_late_catchup.js`
  - late preview and late scoring controls
  - late-watch strip rendering
- `queue_import.js`
  - packet strip rendering
  - legacy JSON import
  - Copilot batch import
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
- `api/powergrader/session_builder.py`
  - queue student list construction
  - final session dict layout
- `api/powergrader/session_actions.py`
  - save-grade mutation
  - Canvas push mutation
- `api/powergrader/import_results.py`
  - Copilot / legacy import validation and merge
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
- `api/powergrader/canvas_fetch.py`
  - submission fetch plus authenticated ordinary-upload streaming, atomic preservation, and shared attachment routing
- `api/powergrader/new_quiz_fetch.py`
  - read-only Student Analysis snapshot, URL-free expected evidence, unambiguous native attempt joins, and clean signed-file download
- `api/powergrader/student_attachments.py`
  - local text/DOCX/raster routing, extraction sidecars, eligibility gates, and metadata-stripped AI derivatives
- `api/webui/workspace.py`
  - canonical course/assignment/student/attempt and AI-run path ownership plus legacy compatibility helpers
- `api/webui/config/courses.py`
  - saved-course lookup for nickname/name/ID display ownership
- `api/powergrader/scheduled_autoscore_support.py`
  - scheduled autoscore label/status helpers
  - existing Canvas-state extraction
  - autopush summary/decision payload shaping

## Route-adjacent helper routing

- `api/webui/routes/powergrader_late.py`
  - late-catchup route support and compatibility bridge
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
