# Gradebook Module Map

Purpose: give future debugging sessions a low-token routing map for Gradebook so
 they can jump directly to the owning module instead of re-mapping the screen.

As of 2026-07-07, Gradebook is already split into a thin shared bootstrap file
 plus feature files under `api/webui/static/gradebook/`.

## Ownership

- Route owner: `api/webui/routes/gradebook.py`
- Main browser bootstrap: `api/webui/static/gradebook.js`
- Feature scripts: `api/webui/static/gradebook/*.js`

## Current size snapshot

- `api/webui/routes/gradebook.py` - 452 lines
- `api/webui/static/gradebook.js` - 316 lines
- `api/webui/static/gradebook/curves.js` - 257 lines
- `api/webui/static/gradebook/sweep.js` - 130 lines
- `api/webui/static/gradebook/extensions.js` - 105 lines
- `api/webui/static/gradebook/policy.js` - 90 lines
- `api/webui/static/gradebook/extra_time.js` - 86 lines
- `api/webui/static/gradebook/snapshot.js` - 72 lines

## Browser routing

`gradebook.js` owns:

- course selection helpers
- shared banner/log helpers
- tab activation and autoload routing
- shared mutable state for feature files
- common POST helper and holiday parsing

Feature ownership:

- `policy.js` - late-policy load/apply flow
- `extra_time.js` - extra-time roster and save flow
- `extensions.js` - due-date extension tools
- `sweep.js` - late-work sweep preview/apply flow
- `curves.js` - curve preview/apply/history/revert
- `snapshot.js` - whole-course grading snapshot

Namespace seam:

- `window.CE_GRADEBOOK`
  - shared helpers such as `postForm`, `showBanner`, `showLog`, `gbCourseId`
  - mutable accessors for `sweepEntries` and `curveResults`

## First places to look by symptom

- late policy problems:
  - `policy.js`
  - `gradebook.py` late-policy routes
- extra-time problems:
  - `extra_time.js`
  - `gradebook.py` extra-time routes
- extension problems:
  - `extensions.js`
  - `gradebook.py` extend-due route
- sweep problems:
  - `sweep.js`
  - `gradebook.py` sweep routes
  - `api/webui/gradebook_service.py`
- curve problems:
  - `curves.js`
  - `gradebook.py` curve routes
  - `api/webui/gradebook_service.py`
- summary snapshot problems:
  - `snapshot.js`
  - `gradebook.py::api_gradebook`

## Rule of thumb

- keep `gradebook.py` as the route orchestration owner
- put new browser behavior into `gradebook/*.js` feature files instead of growing `gradebook.js`
- use `window.CE_GRADEBOOK` for shared helpers instead of copying fetch/render helpers