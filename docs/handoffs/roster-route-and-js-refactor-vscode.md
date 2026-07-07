# Handoff: Roster Route And JS Refactor For VSCode Agent

## Goal

Reduce the next largest local UI surface after the completed routines/config/gradebook
splits: Roster Console.

Current size report highlights:

- `api/webui/routes/roster.py` - about 711 lines after helper/canvas extraction
- `api/webui/static/roster.js` - about 637 lines after safety/groups extraction
- `api/tests/test_roster_routes.py` - about 655 lines

Make the route and browser script easier to debug without changing behavior,
endpoints, storage format, or privacy posture.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- No live Canvas calls.
- Roster data is FERPA-sensitive. Do not add logs, fixtures, snapshots, or console
  output containing real names, IDs, notes, grades, or group memberships.
- Preserve every route path, method, request shape, and response shape.
- Preserve all DOM ids and visible behavior.
- Do not touch `LLM_Modules/*_Base.md`.
- Do not change Canvas group source-of-truth behavior.
- Do not introduce React, Vue, bundlers, ES modules, TypeScript, or a build step.
- Do not revert unrelated dirty worktree changes.

## Files To Inspect First

- `docs/handoffs/archive/roster-console-v1.md`
- `docs/handoffs/archive/roster-console-ux-tier-alias-v2.md`
- `docs/handoffs/archive/roster-canvas-groups-source-of-truth-v3.md`
- `api/webui/routes/roster.py`
- `api/webui/static/roster.js`
- `api/webui/templates/roster.html`
- `api/tests/test_roster_routes.py`
- `api/tests/test_roster_config.py`

## Backend Slice Plan

Keep `api/webui/routes/roster.py` as the APIRouter owner and route registration file.
Move pure helpers and route-adjacent service code into small modules.

### Slice 1: Pure Normalization Helpers - implemented

Create:

- `api/webui/routes/roster_helpers.py`

Move only pure or nearly pure helpers that do not need the router object and do not
perform Canvas writes.

Good initial candidates from the current file:

- `_enrollment_section_ids`
- `_resolve_tier_display`
- `_compute_warnings`
- `_as_int`
- `_value_name`
- `_parse_group_names`
- `_user_id_set_from_canvas_groups`
- `_compute_canvas_group_display`
- `_annotate_group_labels`

Acceptance:

- `roster.py` still owns all route decorators.
- Helper functions remain available on `roster.py` as thin aliases if tests
  monkeypatch/import them directly.
- `py -m pytest api/tests/test_roster_config.py api/tests/test_roster_routes.py`
  passes.

### Slice 2: Canvas Fetch/Group Mapping Helpers - implemented

Create:

- `api/webui/routes/roster_canvas.py`

Move Canvas read helpers and Canvas group/category mapping helpers. Keep the actual
route handlers in `roster.py`.

Good initial candidates:

- `_fetch_sections`
- `_create_canvas_group`
- `canvas_add_group_membership`
- `canvas_remove_group_membership`
- `_get_group_memberships`
- `_validate_canvas_group_target`
- `_update_student_canvas_group`

Important test seam:

- `api/tests/test_roster_routes.py` monkeypatches names on `roster_routes`, including
  `_fetch_sections`, `load_group_categories`, `_update_student_canvas_group`, and
  `_canvas_send`. Preserve those seams with wrapper functions or explicit dependency
  passing; do not force the whole test suite to patch a new module unless the test
  updates are small and intentional.
- Prefer wrappers in `roster.py` for this slice:

```python
def _fetch_sections(course_id: str) -> dict:
    return roster_canvas.fetch_sections(course_id, canvas_get_all=_canvas_get_all)
```

This keeps the route test monkeypatch surface stable while moving the implementation
out of the route file.
- Be careful with `_get_group_memberships`: it currently imports `requests` and
  `_canvas_headers` locally. Move that implementation only if the new helper accepts
  a header provider or imports `..canvas_client._canvas_headers` directly without
  creating a circular import.

Privacy requirement:

- Do not print names, IDs, or memberships.
- Tests must use synthetic names only.

Acceptance:

- `roster.py` keeps route decorators and monkeypatch-compatible wrappers.
- `roster_canvas.py` accepts injected dependencies for Canvas calls and headers.
- `py -m pytest api/tests/test_roster_config.py api/tests/test_roster_routes.py`
  passes.

## Frontend Slice Plan

Keep `api/webui/static/roster.js` as the bootstrap/shared state owner for now, using
`window.CE_ROSTER` for cross-file hooks. Do not add a build step.

### Slice 1: Safety Panel - implemented

Created:

- `api/webui/static/roster/safety.js`

Moved protected-name packs, scrub testing, who-is-who export, vault backup, and scrub
rerun behavior.

### Slice 2: Canvas Groups UI - implemented

Created:

- `api/webui/static/roster/groups.js`

Moved group-set picker, Canvas group creation, and local group label editor behavior.
The table rendering and inline student save behavior remain in `roster.js`.

## Remaining Suggested Slices

1. Extract student table rendering and inline row save behavior only if a small state
   API can keep the current optimistic-update behavior intact.
2. Split `api/tests/test_roster_routes.py` by route group if future backend changes
   keep touching the same large test file.

Acceptance:

- Canvas group source-of-truth behavior is unchanged.
- No route contract change.

### Slice 3: Persistence/Settings Adapter

Create only if it reduces real complexity:

- `api/webui/routes/roster_settings.py`

Move wrappers around `config.get_roster_student_settings`,
`config.set_roster_student_settings`, tier scheme, and group scheme only if this makes
route handlers thinner. Do not duplicate config logic already in `api/webui/config/`.

## Frontend Slice Plan

Follow the established split style from `static/push/*.js` and
`static/gradebook/*.js`.

Create:

- `api/webui/static/roster/core.js` or keep `roster.js` as the shared bootstrap
- `api/webui/static/roster/table.js` for render/filter/inline row saves
- `api/webui/static/roster/groups.js` for group-set picker, group creation, group
  labels, and Canvas group display helpers
- `api/webui/static/roster/bulk.js` for selected-row bulk actions
- `api/webui/static/roster/safety.js` for protected-name packs, scrub test,
  who-is-who export, and vault backup

Keep `api/webui/static/roster.js` as the small shared bootstrap initially, or move to
`roster/core.js` only after the template is wired cleanly.

Expose a small namespace:

```js
window.CE_ROSTER = {
  postForm,
  esc,
  showStatus,
  // shared state/accessors only where needed
};
```

Each feature file should be an IIFE loaded after the shared script and should guard
against missing shared helpers with a short refresh alert.

Completed frontend slices:

- `api/webui/static/roster/safety.js` now owns protected-name packs, scrub test,
  who-is-who export, and vault backup.
- `api/webui/static/roster/groups.js` now owns group-set picker, group creation,
  group-set preference save, and group-label editor rendering/saving.

Remaining suggested frontend slices:

1. Extract bulk actions to `static/roster/bulk.js`.
2. Leave table rendering/inline saves for last because it owns most shared state.

## Required Verification After Each Slice

```powershell
node --check api/webui/static/roster.js
node --check api/webui/static/roster/*.js
py -m py_compile api/webui/routes/roster.py
py -m pytest api/tests/test_roster_config.py api/tests/test_roster_routes.py api/tests/test_route_contract.py
```

Before final handoff:

```powershell
py -m pytest api/tests
py tools/size_report.py
```

## Acceptance

- `api/webui/routes/roster.py` is substantially smaller and mostly route
  orchestration.
- `api/webui/static/roster.js` is substantially smaller and feature handlers live in
  named files.
- All roster tests pass.
- Full API tests pass.
- No privacy-sensitive test fixtures or logs are introduced.
- No route path, response shape, DOM id, or storage shape changes.
