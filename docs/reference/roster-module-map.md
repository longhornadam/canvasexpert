# Roster Module Map

Purpose: give debugging sessions a low-token routing map for Roster without
reading the route, browser script, and helper modules from scratch.

As of 2026-07-07, Roster is partly modular on the backend and the browser side is
 split across a shared bootstrap plus feature files.

## Ownership

- Route owner: `api/webui/routes/roster.py`
- Browser owner: `api/webui/static/roster.js`
- Bulk action handlers: `api/webui/static/roster/bulk.js`
- Canvas group helpers: `api/webui/routes/roster_canvas.py`
- Pure normalization helpers: `api/webui/routes/roster_helpers.py`
- Student/bulk update helpers: `api/webui/routes/roster_updates.py`

## Current size snapshot

- `api/webui/routes/roster.py` - 467 lines
- `api/webui/static/roster.js` - 564 lines
- `api/webui/static/roster/bulk.js` - 155 lines
- `api/webui/routes/roster_updates.py` - 267 lines
- `api/webui/routes/roster_helpers.py` - 211 lines
- `api/webui/routes/roster_canvas.py` - 165 lines
- `api/webui/routes/roster_groups.py` - 149 lines

## Backend routing

`roster.py` currently owns:

- full roster merge
- route decorators and dependency injection for one-student updates
- route decorators and dependency injection for bulk actions
- group scheme/tier scheme route flow
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

- course load and roster fetch
- table rendering and filters
- inline editing and debounced save
- selected Canvas group category flow
- status/toast helpers
- shared roster state and hooks for feature files

`roster/bulk.js` currently owns:

- select-all wiring
- bulk bar visibility
- Canvas group dropdown population in the bulk bar
- bulk action dispatch for extra time, monitoring, and Canvas groups
- refreshes after table render hooks

Namespace seam:

- `window.CE_ROSTER`
  - course state
  - group state
  - reload hook registration
  - shared toast and form-post helper
  - row-selection name map for bulk actions
  - table-render hook registration

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
- inline save / UI state problems:
  - `roster.js`
- group label rendering problems:
  - `roster_helpers.py::_annotate_group_labels`
  - `roster.js`

## Stability note

Roster is mapped and covered by focused route tests. If a symptom lands in the
remaining larger files, use the ownership sections above to inspect the narrow
area first; there is no active roster handoff.
