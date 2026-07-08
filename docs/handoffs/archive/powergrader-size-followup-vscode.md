# Handoff: PowerGrader Size Follow-Up For VSCode Agent

## Goal

Continue the completed PowerGrader modularization by reducing the remaining large
route and browser files without changing the teacher workflow.

Current size snapshot after the implemented splits:

- `api/webui/routes/powergrader.py` - 479 lines
- `api/webui/static/powergrader_setup.js` - 4 lines (thin shim)
- `api/webui/static/powergrader_queue.js` - 4 lines (thin shim)
- `api/webui/static/powergrader/setup_core.js` - 184 lines
- `api/webui/static/powergrader/setup_autoscore.js` - 390 lines
- `api/webui/static/powergrader/queue_core.js` - 332 lines
- `api/webui/static/powergrader/queue_review.js` - 173 lines
- `api/webui/static/powergrader/queue_import.js` - 262 lines
- `api/webui/static/powergrader/queue_late_catchup.js` - 160 lines
- `api/webui/static/powergrader/queue_privacy.js` - 64 lines
- `api/powergrader/ai_workflow.py` - 395 lines
- `api/powergrader/ai_workflow_support.py` - 61 lines
- `api/powergrader/autoscore_queue.py` - 428 lines
- `api/powergrader/autoscore_claims.py` - 202 lines
- `api/powergrader/autopush_policy.py` - 309 lines
- `api/powergrader/autopush_policy_result.py` - 63 lines
- `api/powergrader/start_workflow.py` - 88 lines
- `api/powergrader/copilot_packet.py` - 222 lines
- `api/powergrader/copilot_packet_support.py` - 137 lines
- `api/webui/routes/routines_powergrader.py` - 362 lines
- `api/powergrader/scheduled_autoscore_support.py` - 127 lines

There are no remaining PowerGrader Python or browser files above the 500-line
threshold in this slice.

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
- `api/webui/static/powergrader/queue_review.js` owns save/push/AI-apply/keyboard behavior.
- `api/webui/static/powergrader/queue_core.js` owns queue bootstrap, student rendering,
  shared state, progress/status helpers, and session reload.
- `api/webui/static/powergrader/setup_core.js` owns shared setup flow.
- `api/webui/static/powergrader/setup_autoscore.js` owns model picker / estimate / autoscore setup flow.

Completed backend slices:

- `api/webui/routes/powergrader_late.py` owns late-catchup route support.
- `api/webui/routes/powergrader_helpers.py` owns pure payload/response helpers.
- `api/webui/routes/powergrader_setup_support.py` owns setup/queue page context and estimate payload shaping.
- `api/powergrader/start_workflow.py` owns reusable start-session support helpers.
- `api/powergrader/ai_workflow_support.py` owns reusable AI-workflow result and artifact shaping helpers.
- `api/powergrader/autoscore_claims.py` owns scheduled auto-score claim/lease lifecycle helpers.
- `api/powergrader/autopush_policy_result.py` owns canonical auto-push decision payload builders.
- `api/powergrader/copilot_packet_support.py` owns Copilot packet text/layout shaping helpers.
- `api/powergrader/scheduled_autoscore_support.py` owns scheduled autoscore summary/state helpers used by `routines_powergrader.py`.

Remaining suggested follow-up work:

1. Optional cleanup only: decide whether packet strip rendering should stay in
  `queue_import.js` or move to a later `queue_packet.js`. Do not churn it just to rename modules.
2. Favor durable routing docs and broader validation over further fragmentation unless a new slice grows materially again.

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
