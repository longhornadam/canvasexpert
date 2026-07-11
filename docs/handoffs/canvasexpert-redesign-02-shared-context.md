# Toyota handoff 02: shared course context contract

## Objective

Create one browser context for focused course and explicit write targets while preserving
all existing push behavior and legacy storage for one release.

## Files

- New `api/webui/static/app_context.js`
- `api/webui/templates/base.html`
- `api/webui/static/push/course_picker.js`
- `api/tests/test_webui_template_contracts.py`
- New `api/tests/test_app_context_contract.py` if behavior is easier to test separately
- `docs/reference/course-expert-module-map.md`

## Load order and API

Load `app_context.js` synchronously in `<head>` immediately after `write_review.js` and
before `{% block content %}`. It exposes exactly:

```javascript
window.CE_CONTEXT.snapshot()
window.CE_CONTEXT.setFocus(course, source)
window.CE_CONTEXT.setTargets(courses, source)
window.CE_CONTEXT.reconcile(availableCourses, {source, authoritative})
window.CE_CONTEXT.subscribe(callback) // returns unsubscribe function
```

Every mutation dispatches `ce:contextchange` with
`{focusedCourse, targetCourses, source}`. IDs are strings. Focus and targets are
independent; `setFocus` never changes targets. Duplicate/stale values are pruned only when
`reconcile` receives `{authoritative:true}` after a successful all-course response.
Bookmark-only initialization uses `authoritative:false`; `/api/courses` failure performs no
destructive reconciliation. A saved valid non-bookmarked target survives bookmark render.

Persistence key: `canvasExpert.context.v1`. On first load only, migrate from
`canvasExpert.push.coursePicker.v1`; retain old-key read fallback but never dual-write.

## Course picker adapter

`push/course_picker.js` remains the DOM owner for CourseExpert and standalone push pages.
It hydrates from `CE_CONTEXT`, publishes focus/target changes to it, and retains existing
legacy globals/functions. Focus continues to drive modules/categories/groups/downloads;
checked targets continue to define multi-course pushes. Do not change any live-write
endpoint or target count.

To preserve current picker semantics only, clicking/focusing an unchecked CourseExpert
course explicitly checks it in picker state and then publishes targets and focus. Other
pages changing focus never gain a write target.

## Tests

Cover empty/malformed storage, migration, string normalization, target deduplication,
independent focus/targets, authoritative vs bookmark-only reconciliation, saved
non-bookmarked target, failed all-course fetch, subscribe/unsubscribe, event detail, and no
silent target expansion.

```powershell
node --check api/webui/static/app_context.js
node --check api/webui/static/push/course_picker.js
py -m pytest api/tests/test_app_context_contract.py api/tests/test_webui_template_contracts.py api/tests/test_push_service.py api/tests/test_route_contract.py
git diff --check
```

## Runtime

Verify `/course-expert` and every `/push/*` route: reload persistence, focus vs targets,
module/category refresh, deactivated/stale repair, deep links, and zero console errors.
Do not perform a Canvas write.

## Stop conditions

Stop if existing picker symbols differ, a deep link conflicts with explicit target state,
or preserving behavior requires changing push payloads/endpoints.

## Required implementer reply

One commit; report hash/files, storage migration and state-matrix tests, every push route
runtime result, exact console count, and no Canvas write/unrelated staging.
