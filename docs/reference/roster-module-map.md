# Roster Module Map

Purpose: give future debugging sessions a low-token routing map for Roster and
 make the current monolithic hotspots explicit so future refactors know where to cut.

As of 2026-07-07, Roster is partly modular on the backend but still has two large
 primary owner files that are good candidates for future splitting.

## Ownership

- Route owner: `api/webui/routes/roster.py`
- Browser owner: `api/webui/static/roster.js`
- Canvas group helpers: `api/webui/routes/roster_canvas.py`
- Pure normalization helpers: `api/webui/routes/roster_helpers.py`

## Current size snapshot

- `api/webui/routes/roster.py` - 598 lines
- `api/webui/static/roster.js` - 568 lines
- `api/webui/routes/roster_helpers.py` - 181 lines
- `api/webui/routes/roster_canvas.py` - 140 lines

## Backend routing

`roster.py` currently owns:

- full roster merge
- one-student updates
- bulk actions
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

## Browser routing

`roster.js` currently owns:

- course load and roster fetch
- table rendering and filters
- inline editing and debounced save
- bulk actions
- selected Canvas group category flow
- status/toast helpers

Namespace seam:

- `window.CE_ROSTER`
  - course state
  - group state
  - reload hook registration

## First places to look by symptom

- roster fetch/merge problems:
  - `roster.py::roster_get`
  - `roster_helpers.py`
  - `names.py`
- Canvas group mutation problems:
  - `roster_canvas.py`
  - `roster.py::_update_student_canvas_group`
- inline save / UI state problems:
  - `roster.js`
- group label rendering problems:
  - `roster_helpers.py::_annotate_group_labels`
  - `roster.js`

## Current refactor note

Roster is not yet at the same modularity level as PowerGrader or Gradebook.
For low-token future work, treat `roster.py` and `roster.js` as the two primary
 hotspots to split next rather than searching broadly.