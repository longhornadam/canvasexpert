# Execution brief: Restore Course Expert Download Work assignment loading

Status: **ready for implementation**

Risk: **medium**

Executor: **Luna**

## Outcome

Make **Work → Download Work → Load assignments…** load the focused course's Canvas
assignments instead of showing the controls-not-loaded alert. The existing Download
Work picker must populate from the canonical read-only assignments route while all
download actions remain explicitly teacher-triggered.

This batch also restores the two namespaced shared helpers still consumed by the
canonical Course Expert scripts after the July 12 standalone-surface cleanup, without
reviving any removed compatibility globals or routes.

## Locked decisions

- Confirmed defect 1: commit `5e5f552` removed `postForm` and `esc` from
  `window.CE_PUSH` while retained Course Expert consumers still call
  `push.postForm` and `push.esc`. `push/download.js` includes `esc` in its readiness
  gate, so it deliberately emits the user's alert.
- Restore `esc` and `postForm` only as properties of the existing `window.CE_PUSH`
  export in `push/core.js`. Do not restore bare `window.esc`, `window.postForm`, or
  `window.pushContent`; do not restore the generic `/api/content/push` path.
- Confirmed defect 2: `push/download.js` calls nonexistent `/api/assignments`, while
  the established read-only picker route is `GET /api/assignments-full`. Point the
  Download Work loader at the canonical route; do not add a backend alias or change
  the route contract.
- The canonical route returns `points_possible`. Render that field in the Download
  Work table; do not fork or reshape the backend response.
- Keep all existing course focus/target behavior, assignment filters, selectable
  submission types, confirmation, SSE download action, folder handling, and download
  destinations unchanged.
- Preserve the existing staged/uncommitted integration work and the prior Desk fix.
  Leave this batch uncommitted and do not reset, unstage, or restage unrelated paths.

## Scope

- `api/webui/static/push/core.js`: restore the two still-supported namespaced helper
  exports.
- `api/webui/static/push/download.js`: use `/api/assignments-full` and its
  `points_possible` field.
- `api/tests/test_webui_template_contracts.py`: add the smallest useful runtime
  regression for the shared-helper/Download Work initialization and request contract.
  Prefer a Node/VM execution test over CSS/layout/source snapshots.
- This handoff's `Execution result` section.

## Out of scope

- Backend routes, Canvas client behavior, assignment response schema, downloader
  implementation, SSE download behavior, persistence, or operation-ledger contracts.
- Any live submission download, Canvas write, AI call, routine, file-picker action, or
  folder mutation during implementation or verification.
- Reintroduction of deleted standalone `/download-work` or `/push/*` pages, global
  compatibility helpers, generic content-push behavior, or template/script-order
  redesign.
- New abstractions or cleanup of other shared-script consumers.

## Reference pattern and routing

- Canonical composition and script order:
  `api/webui/templates/course_expert.html` and
  `api/webui/templates/_push_common_scripts.html`
- Shared namespace owner: `api/webui/static/push/core.js`
- Course focus helpers: `api/webui/static/push/course_picker.js`
- Download Work owner: `api/webui/static/push/download.js`
- Canonical assignment picker route and response:
  `api/webui/routes/reports.py::list_assignments_full`
- Current safety/runtime test style:
  `api/tests/test_webui_template_contracts.py::test_operation_alias_runtime_cancellation_never_applies`
- Ownership reference: `docs/reference/course-expert-module-map.md`
- Read project-local `TOOLS.md` before broad inspection.

## Implementation requirements

1. Add `esc` and `postForm` to the existing `Object.assign(window.CE_PUSH || {}, …)`
   export. Preserve their current implementations and every write-review/typed-operation
   behavior. Do not add any bare global assignment.
2. Change only the Download Work assignment-list request to
   `/api/assignments-full?course_id=…` and display `points_possible` in the Points
   column. Preserve escaping and current empty/error behavior.
3. Add a focused runtime regression that fails on the current code and proves the
   namespaced helpers exist without recreating the removed bare globals. Exercise or
   otherwise lock the Download Work loader's canonical URL and `points_possible`
   consumption without making a live request or depending on developer settings.
4. Self-review all retained `push.esc`/`push.postForm` consumers against the shared
   namespace; do not widen scope if no additional missing export is found.
5. Preserve all unrelated staged and unstaged edits byte-for-byte and leave staging
   state untouched.

## Verification

```powershell
node --check api/webui/static/push/core.js
node --check api/webui/static/push/download.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check HEAD
```

After executor handback, restart the app through `api/qf_ui.py`, render
`/course-expert?tab=download`, and confirm zero new browser-console errors. With the
user's focused `Master Shell 18-19` course, click **Load assignments…** once. This may
make the authorized read-only Canvas assignment-list request. Confirm no alert/dialog,
the button returns to enabled state, the assignment table becomes visible with one or
more rows, and a populated row shows a points value when Canvas supplied one.

Do not select an assignment, invoke **Download selected**, open/change a folder, or
perform any Canvas write during rendered verification. Report only aggregate row/count
state; do not print assignment names, IDs, URLs, dates, or student/submission data.

## Stop conditions

Stop with RED rather than guessing if:

- The canonical assignment route or its documented `points_possible` field is absent.
- Restoring the namespaced helpers requires a bare global, generic push fallback,
  script-order change, backend alias, or public response change.
- Load assignments reaches a Canvas-write, submission-download, credential, or FERPA
  boundary not described here.
- An unrelated worktree change blocks the scoped files or would be overwritten.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — implementation and senior rendered-route acceptance are complete.
- Changes are uncommitted; existing staged and unstaged work was preserved.
- Files changed:
  - `api/webui/static/push/core.js`
  - `api/webui/static/push/download.js`
  - `api/tests/test_webui_template_contracts.py`
  - `docs/handoffs/course-expert-download-work-controls.md`
- Verification:
  - `node --check api/webui/static/push/core.js` — passed (1 file, 0 failures)
  - `node --check api/webui/static/push/download.js` — passed (1 file, 0 failures)
  - `py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py`
    — 20 passed, 0 failed, 0 skipped
  - `git diff --check HEAD` — passed (0 whitespace errors; existing line-ending
    conversion warnings only)
- Rendered routes checked: the senior restarted the shipped `api/qf_ui.py` launcher,
  loaded `/course-expert?tab=download`, focused the user's active course, and clicked
  **Load assignments…** once. The old alert did not appear; the button entered its
  disabled `Loading…` state, returned enabled, and revealed 444 assignment rows. Of
  those rows, 421 displayed a Canvas-supplied points value. There were zero new
  browser-console errors. No assignment was selected, no submission download or folder
  action ran, and no Canvas write occurred.
- Self-review: every retained `push.esc` and `push.postForm` consumer resolves through
  the restored `CE_PUSH` namespace; no other missing helper export was found.
- Deviations from the brief: none.
- Remaining blocker or decision: none.
