# Roster Module Map

Purpose: give debugging sessions a low-token routing map for Roster without
reading the route, browser script, and helper modules from scratch.

Student Reports is a separate Students page at `/students/reports`; the Roster rail links
there directly. It does not share Roster state or embed report controls.

As of 2026-07-12, Roster is a shared Workbench page split across a shared bootstrap
plus focused browser feature files. The Workbench lenses are visual views over one
loaded roster; they do not own a second dataset or mutation path.

## Ownership

- Route owner: `api/webui/routes/roster.py`
- Browser bootstrap and shared state owner: `api/webui/static/roster.js`
- Table rendering and row-selection name-map updates: `api/webui/static/roster/table.js`
- Search, row filters, visual lenses, and Roster deep links:
  `api/webui/static/roster/filters.js`
- Workbench/lens/responsive composition: `api/webui/static/roster_workbench.css`
- Inline edit and debounced save behavior: `api/webui/static/roster/inline_edit.js`
- Selected Canvas group set state and picker coordination: `api/webui/static/roster/group_state.js`
- Bulk action handlers: `api/webui/static/roster/bulk.js`
- Canvas group builder and group label editor: `api/webui/static/roster/groups.js`
- AI safety tools: `api/webui/static/roster/safety.js`
- Canvas group helpers: `api/webui/routes/roster_canvas.py`
- Pure normalization helpers: `api/webui/routes/roster_helpers.py`
- Student/bulk update helpers: `api/webui/routes/roster_updates.py`

## Load order

`api/webui/templates/roster.html` extends `layouts/workspace.html` with the
`left-main` variant, loads `roster_workbench.css` through `head_extra`, and loads
browser scripts through `workspace_scripts` in this order:

1. `api/webui/static/roster.js`
2. `api/webui/static/roster/table.js`
3. `api/webui/static/roster/filters.js`
4. `api/webui/static/roster/inline_edit.js`
5. `api/webui/static/roster/group_state.js`
6. `api/webui/static/roster/bulk.js`
7. `api/webui/static/roster/groups.js`
8. `api/webui/static/roster/safety.js`

`window.CE_ROSTER` is defined in `roster.js` before the feature scripts load.

## Source-size reports

Use [`tools/size_report.py`](../../tools/size_report.py) for current source-size
reports; this map intentionally does not maintain line-count snapshots.

## Backend routing

`roster.py` currently owns:

- full roster merge
- route decorators and dependency injection for one-student updates
- route decorators and dependency injection for bulk actions
- group-set preference and group-label route flow
- route orchestration around vault, groups, and config merges

Helper ownership:

- `roster_canvas.py`
  - Canvas section fetch
  - Canvas group create/add/remove/validate/update helpers
- `roster_helpers.py`
  - warning computation
  - section parsing
  - group-name parsing
  - canvas-group display shaping
  - pure normalization helpers
- `roster_groups.py`
  - group-set preference persistence
  - group-set creation
  - group creation inside an existing set
  - group-label read/write persistence
- `roster_updates.py`
  - one-student patch validation and update logic
  - bulk extra-time, monitoring, and Canvas-group action logic
  - V3 obsolete local tier/group action rejection
  - dependency-injected Canvas update and config seams for route tests

## Browser routing

`roster.js` currently owns:

- course selection wiring and initial load
- shared toast and form-post helpers
- roster state and hook registration
- roster reload wiring
- shared course/group/filter state facades

`roster/table.js` currently owns:

- roster row HTML construction
- row status cell updates
- row-selection name-map updates for bulk actions

`roster/filters.js` currently owns:

- search box changes
- the Students, Accommodations, Groups, Monitoring, Issues, and Privacy lenses
- the existing row-filter mapping used by those lenses
- `data-roster-lens` presentation state and active rail state
- query updates through `history.replaceState`
- deep links: `extra-time`, `groups`, `monitoring`, `issues`, and `privacy`
- post-course-load focus/open behavior for the existing Groups and Privacy details
- filtered student list recomputation
- triggering table re-renders after filter changes

`roster/inline_edit.js` currently owns:

- nickname editing
- pseudonym editing and regenerate
- extra-time checkbox and day edits
- Canvas group selection per row
- monitored-student toggle and note edits
- debounced save requests

`roster/group_state.js` currently owns:

- selected Canvas group set picker
- group-set preference persistence
- coordination between the picker and shared roster group state

`roster/bulk.js` currently owns:

- select-all wiring
- bulk bar visibility
- Canvas group dropdown population in the bulk bar
- bulk action dispatch for extra time, monitoring, and Canvas groups
- refreshes after table render hooks

`roster/groups.js` currently owns:

- Canvas group-set creation
- adding groups to an existing set
- group label editor rendering and save flow

`roster/safety.js` currently owns:

- protected-name pack loading and save
- scrub test
- who-is-who export
- vault backup

Namespace seam:

- `window.CE_ROSTER`
  - course state getters
  - group state getters
  - filtered-student list setter/getter
  - selected-name-map getter used by bulk actions
  - shared toast and form-post helper
  - course-load hook registration
  - table-render hook registration
  - row-status updates for inline save feedback
  - table-render entry point
  - filter entry point
  - Canvas group selection setter

## First places to look by symptom

- roster fetch/merge problems:
  - `roster.py::roster_get`
  - `roster_helpers.py`
  - `names.py`
- student or bulk update validation problems:
  - `roster_updates.py`
  - `roster.py::roster_student_update`
  - `roster.py::roster_bulk_update`
- Canvas group mutation problems:
  - `roster_canvas.py`
  - `roster.py::_update_student_canvas_group`
- row markup, status, or name-map problems:
  - `roster/table.js`
- search, lens, filter, or Roster deep-link problems:
  - `roster/filters.js`
- inline save or row edit problems:
  - `roster/inline_edit.js`
- selected Canvas group set / picker coordination problems:
  - `roster/group_state.js`
- group label rendering problems:
  - `roster/groups.js`
- bulk bar or bulk action problems:
  - `roster/bulk.js`
- safety tools problems:
  - `roster/safety.js`

## Stability note

Roster is mapped and covered by focused route/template tests. If a symptom lands
in the remaining larger files, use the ownership sections above to inspect the
narrow area first.
