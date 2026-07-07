# Handoff: PowerGrader Size Follow-Up For VSCode Agent

## Goal

Continue the completed PowerGrader modularization by reducing the remaining large
route and browser files without changing the teacher workflow.

Current size report highlights:

- `api/webui/static/powergrader_queue.js` - about 493 lines after import,
  late-catchup, and privacy extraction
- `api/webui/routes/powergrader.py` - about 577 lines after late-catchup extraction
- `api/webui/static/powergrader_setup.js` - about 503 lines
- Supporting backend modules such as `api/powergrader/autoscore_queue.py` and
  `api/powergrader/autopush_policy.py` are also sizeable but less urgent than the UI
  route/script split.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- No live Canvas calls.
- Never commit student data, submission text, grades, teacher comments, names, IDs, or
  private PowerGrader session artifacts.
- Preserve all route paths, request/response shapes, DOM ids, keyboard shortcuts, and
  session storage shapes.
- AI suggestions remain drafts until teacher review, except the existing narrow
  scheduled auto-push path with policy/idempotency/audit checks.
- Do not broaden scheduled auto-push behavior.
- Do not touch `LLM_Modules/*_Base.md`.
- Do not introduce a frontend framework, bundler, ES modules, or TypeScript.
- Do not revert unrelated dirty worktree changes.

## Files To Inspect First

- `api/webui/routes/powergrader.py`
- `api/webui/static/powergrader_setup.js`
- `api/webui/static/powergrader_queue.js`
- `api/powergrader/`
- `api/tests/test_powergrader_packet.py`
- `api/tests/test_powergrader_copilot_packet.py`
- `api/tests/test_powergrader_import_results.py`
- `api/tests/test_powergrader_late_catchup.py`
- `api/tests/test_powergrader_scheduled_autoscore.py`

## Backend Slice Plan

Keep `api/webui/routes/powergrader.py` as the APIRouter owner.

### Slice 1: Move Late Catch-Up Support - implemented

Create:

- `api/webui/routes/powergrader_late.py`

Move the route-local late catch-up helpers currently clustered near the top of
`powergrader.py`:

- `_late_watch_error`
- `_build_late_catchup_students`
- `_run_late_catchup_score`

Important compatibility note:

- `api/webui/routes/routines_powergrader.py` calls `pg_routes._run_late_catchup_score`
  today. Preserve that seam with a thin alias on `powergrader.py`, or update the
  routines dependency cleanup to pass the new helper explicitly.
- Do not change the `/api/powergrader/session/{session_id}/late-preview` or
  `/late-score` route handlers in the first slice except to call the moved helper.

### Slice 2: Move Request Parsing/Response Builders

Create:

- `api/webui/routes/powergrader_helpers.py`

Move route-local pure helpers that parse forms, build common JSON response fragments,
or normalize IDs. Do not move Canvas writes or session mutation unless a helper already
encapsulates it cleanly.

### Slice 3: Move Setup-Only Route Support

If setup/start workflow helpers remain in the route file, move them to:

- `api/webui/routes/powergrader_setup_support.py`

Do not change `api/powergrader/session_builder.py` or `api/powergrader/ai_workflow.py`
unless the route helper extraction exposes a clear duplicate.

## Frontend Slice Plan

Split scripts using plain browser IIFEs and a small namespace. Suggested layout:

- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader/setup_autoscore.js`
- `api/webui/static/powergrader/queue_core.js`
- `api/webui/static/powergrader/queue_review.js`
- `api/webui/static/powergrader/queue_late_catchup.js`
- `api/webui/static/powergrader/queue_import.js`
- `api/webui/static/powergrader/queue_packet.js`

Keep the current filenames as bootstrap/shared files until each feature slice is
stable, then decide whether to leave thin shims or update template script tags.

Namespace pattern:

```js
window.CE_POWERGRADER = {
  postForm,
  esc,
  state,
  renderCurrentStudent,
};
```

Do not put student names, submission text, grades, or comments in console logging.

Completed frontend slices:

- `api/webui/static/powergrader/queue_import.js` owns Copilot/legacy import behavior.
- `api/webui/static/powergrader/queue_late_catchup.js` owns late-watch preview/score UI.
- `api/webui/static/powergrader/queue_privacy.js` owns privacy audit strip rendering.

Remaining suggested frontend slices:

1. Decide whether packet strip rendering should stay in `queue_import.js` or move to a
   later `queue_packet.js`. Do not churn it just to rename modules.
2. Leave `renderStudent`, grade save/push, keyboard handling, and emoji insertion for
   later because they share the most live state.

## Required Verification After Each Slice

```powershell
node --check api/webui/static/powergrader_setup.js
node --check api/webui/static/powergrader_queue.js
py -m py_compile api/webui/routes/powergrader.py
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py
py -m pytest api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_scheduled_autoscore.py
py -m pytest api/tests/test_route_contract.py
```

Before final handoff:

```powershell
py -m pytest api/tests
py tools/size_report.py
```

## Acceptance

- `api/webui/routes/powergrader.py` is closer to route orchestration and materially
  smaller.
- PowerGrader setup/queue JS files are split by workflow while preserving all DOM ids
  and keyboard behavior.
- Focused PowerGrader tests pass.
- Full API tests pass.
- No private PowerGrader artifacts, fixtures, or logs are added.
