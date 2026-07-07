# Handoff: Gradebook JS Refactor For VSCode Agent

## Goal

Make `api/webui/static/gradebook.js` easier to debug by splitting one feature at a
time into plain browser scripts. Preserve every visible behavior and endpoint.

Use this handoff if the live-fire focus is teacher UI workflows rather than scheduled
routines.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- No live Canvas calls.
- Do not commit secrets, tokens, student data, roster data, grades, submissions, or
  private teacher notes.
- Preserve all route paths and DOM ids.
- Do not introduce React, Vue, bundlers, ES modules, TypeScript, or a build step.
- Keep plain browser scripts loaded after a small shared `gradebook.js`.
- Do not revert unrelated dirty worktree changes.

## Current Shape

Main file:

- `api/webui/static/gradebook.js` is about 999 lines.

Template:

- Locate the Gradebook template under `api/webui/templates/` by searching for
  `gradebook.js` and `gb-course-sel`.

Major feature areas in `gradebook.js`:

- Shared helpers/course picker:
  - `gbCourseId`
  - `gbCourseName`
  - `gbTargets`
  - `_markLoaded`
  - `_needsLoad`
  - `esc`
  - `showLog`
  - `hideBanner`
  - `showBanner`
  - `postForm`
  - `_renderBanner`
  - tab activation/autoload
  - course picker loading/reset
- Late policy:
  - `_loadPolicy`
  - `btn-apply-policy`
- Extra-time roster:
  - `_loadRoster`
  - `btn-reload-roster`
  - `btn-save-roster`
- Extensions:
  - `_loadExtensions`
  - extension apply handlers
- Sweep:
  - period chips/date presets
  - sweep preview/apply
- Curves:
  - curve assignment load/preview/apply
- Snapshot:
  - gradebook snapshot load/render

## Preferred Pattern

Follow the Course Expert split already done in `api/webui/static/push/*.js`:

- Keep `gradebook.js` as shared helper/bootstrap script.
- Expose a small `window.CE_GRADEBOOK` namespace for shared helpers.
- New feature files should be IIFEs:

```js
(function () {
  "use strict";
  var gb = window.CE_GRADEBOOK || {};
  var ready = ["postForm", "showLog"].every(function (name) {
    return typeof gb[name] === "function";
  });
  function requireReady() {
    if (ready) return true;
    alert("Gradebook controls did not load correctly. Refresh Canvas Expert and try again.");
    return false;
  }
  // handlers...
})();
```

## Slice Order

### Slice 1: Late Policy

Create:

- `api/webui/static/gradebook/policy.js`

Move only:

- `_loadPolicy`
- `btn-apply-policy` handler

Expose from `gradebook.js` as needed:

- `gbCourseId`
- `gbCourseName`
- `gbTargets`
- `_markLoaded`
- `_needsLoad`
- `postForm`
- `showBanner`
- `hideBanner`

Keep visible text, confirmation text, payload fields, and endpoints unchanged:

- `GET /api/late-policy`
- `POST /api/late-policy/apply`

### Slice 2: Extra-Time Roster

Create:

- `api/webui/static/gradebook/extra_time.js`

Move only:

- `_loadRoster`
- `btn-reload-roster`
- `btn-save-roster`

Preserve endpoints:

- `GET /api/students/list`
- `GET /api/extra-time`
- `POST /api/extra-time`

Privacy warning:

- This UI displays student names. Do not add logging, fixtures, snapshots, or console
  output containing roster data.

### Slice 3: Extensions

Create:

- `api/webui/static/gradebook/extensions.js`

Move only extension load/apply behavior.

Preserve endpoints:

- `GET /api/assignments-full`
- `GET /api/students/list`
- `GET /api/extra-time`
- `POST /api/extend-due`

### Slice 4: Sweep

Create:

- `api/webui/static/gradebook/sweep.js`

Move sweep date chips, preview, and apply behavior.

Preserve endpoints:

- `POST /api/sweep/preview`
- `POST /api/sweep/apply`

### Slice 5: Curves

Create:

- `api/webui/static/gradebook/curves.js`

Move curve assignment load, preview, apply, and revert/event behavior if present.

Preserve endpoints:

- `GET /api/curve/assignments`
- `POST /api/curve/preview`
- `POST /api/curve/apply`
- `GET /api/curve/events`
- `POST /api/curve/revert`

### Slice 6: Snapshot

Create:

- `api/webui/static/gradebook/snapshot.js`

Move read-only grade snapshot rendering.

## Template Wiring

After each slice, add the new script tag after `gradebook.js` in the Gradebook
template.

Example:

```html
<script src="/static/gradebook.js?v={{ asset_v }}"></script>
<script src="/static/gradebook/policy.js?v={{ asset_v }}"></script>
```

Only load scripts on the Gradebook page.

## Required Verification

After each slice:

```powershell
node --check api/webui/static/gradebook.js
node --check api/webui/static/gradebook/policy.js
py -m pytest api/tests/test_route_contract.py
```

Before final handoff:

```powershell
node --check api/webui/static/gradebook.js
node --check api/webui/static/gradebook/*.js
py -m pytest api/tests
py tools/size_report.py
```

## Acceptance

- `gradebook.js` is reduced substantially and mostly contains shared helpers,
  course picker/bootstrap, and tab orchestration.
- Each feature script owns exactly its own handlers.
- No route contract changes.
- No new frontend framework or build step.
- Full API tests pass.
