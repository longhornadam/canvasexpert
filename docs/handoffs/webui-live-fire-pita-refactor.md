# Handoff: Web UI Live-Fire Debuggability Refactor

## Context

The Web UI has already had several useful size-driven splits. This handoff is
not line-count driven. The goal is to reduce the files that are painful during
live-fire Canvas testing because one symptom currently forces agents to reason
across browser state, local config, Canvas state, privacy-sensitive data, and
write operations.

Work on `dev`. Do not touch the current uncommitted `engine/` refactor files
unless the user explicitly asks. This handoff is for `api/webui/` and related
Web UI docs only.

Guardrails:

- Keep the local app bound to `127.0.0.1`; do not add public routes.
- Never print, fixture, or commit Canvas tokens, student names, IDs, grades,
  submissions, private notes, or other FERPA data.
- Do not add district-specific URLs, real calendars, teacher names, school
  names, rubric names, or defaults.
- Preserve existing DOM ids, route URLs, request/response shapes, and namespace
  seams unless a slice explicitly says to migrate them and tests cover it.
- After each completed slice, update the relevant docs:
  - `docs/reference/roster-module-map.md`
  - `docs/reference/gradebook-module-map.md`
  - `docs/reference/feedbackexpert-module-map.md`
  - `docs/reference/course-expert-module-map.md`
  - `api/webui/README.md` only when the high-level routing map changes.

## Desired End State

Live-fire failures should route cleanly:

- Roster UI bugs should land in a table, filter, inline edit, or group-state
  browser module instead of the entire `roster.js` file.
- Gradebook route bugs should land in policy, sweep, extra-time, extension,
  curve, or snapshot route modules instead of one large route file.
- FeedbackExpert browser bugs should land in static feature scripts instead of
  the privacy-sensitive template.
- Course Expert's remaining inline browser workflows should be split enough
  that Student Reports, portfolio tools, quick assignment, and tab/delivery
  glue are independently debuggable.

## Slice 1 - Roster Browser Split

Priority: highest.

Why this is painful:

`api/webui/static/roster.js` currently owns course loading, roster fetch, table
rendering, filtering, inline edits, debounced saves, selected Canvas group
category state, status/toasts, and shared hooks. Live-fire roster failures often
span Canvas groups, local roster settings, monitored students, and browser
state; reading one large browser file slows every investigation.

Files to change:

- `api/webui/static/roster.js`
- New files under `api/webui/static/roster/`, likely:
  - `table.js`
  - `filters.js`
  - `inline_edit.js`
  - `group_state.js`
- `api/webui/templates/roster.html` if new scripts need loading.
- `docs/reference/roster-module-map.md`
- `api/webui/README.md` if the page map or script ownership summary changes.

Existing files not to regress:

- `api/webui/static/roster/bulk.js`
- `api/webui/static/roster/groups.js`
- `api/webui/static/roster/safety.js`
- Backend route helpers under `api/webui/routes/roster_*.py`

Implementation requirements:

- Keep `window.CE_ROSTER` as the shared namespace seam.
- Keep `roster.js` as bootstrap/shared state owner only:
  - course selection and initial load wiring
  - shared API helpers such as toast/status and form POST
  - state getter/setter registration
  - hook registration for table-render and reload events
- Move table row construction and row-selection name-map updates to
  `roster/table.js`.
- Move search/filter controls and filtered render triggering to
  `roster/filters.js`.
- Move inline edit/debounced save behavior to `roster/inline_edit.js`.
- Move selected Canvas group category UI state and dropdown coordination to
  `roster/group_state.js` unless it already belongs cleanly in `groups.js`.
- Preserve load order in the template. Feature files may depend on
  `roster.js` defining `window.CE_ROSTER`.
- Do not change backend route behavior in this slice.

Acceptance criteria:

- `roster.js` is mostly bootstrap/state facade.
- Existing bulk/groups/safety behavior continues through the same namespace.
- `docs/reference/roster-module-map.md` lists all roster browser feature files,
  including existing `bulk.js`, `groups.js`, and `safety.js`.
- No PII is added to tests, logs, or fixtures.

Tests:

```powershell
py -m pytest api/tests/test_roster_routes.py api/tests/test_roster_config.py
py -m pytest api/tests/test_route_contract.py
```

Manual smoke if feasible:

- Launch `cd api; py qf_ui.py`.
- Open `/roster`.
- Select a bookmarked course.
- Confirm roster loads, filters work, inline edits save, group category
  selection still populates rows and bulk controls.

## Slice 2 - Gradebook Route Split

Priority: highest backend live-fire pain.

Why this is painful:

`api/webui/routes/gradebook.py` is the single backend route owner for late
policy, school-day sweep, extra-time roster, due-date extensions, curves, and
snapshot reads. Browser code is already split by feature, but a backend
live-fire failure still starts in one broad route file. Canvas write failures
need narrower ownership.

Files to change:

- `api/webui/routes/gradebook.py`
- New route helper/router modules, likely:
  - `api/webui/routes/gradebook_policy.py`
  - `api/webui/routes/gradebook_sweep.py`
  - `api/webui/routes/gradebook_extra_time.py`
  - `api/webui/routes/gradebook_extensions.py`
  - `api/webui/routes/gradebook_curves.py`
  - `api/webui/routes/gradebook_snapshot.py`
- `api/webui/server.py` only if route registration currently assumes one router
  and cannot be preserved from `gradebook.py`.
- `docs/reference/gradebook-module-map.md`
- `api/webui/README.md` if the route ownership summary changes.

Implementation requirements:

- Keep URL paths, HTTP methods, form/query fields, and response JSON stable.
- Prefer `gradebook.py` as a router aggregation facade, similar to the
  FeedbackExpert route split.
- If current tests import helper functions from `gradebook.py`, preserve
  compatibility re-exports unless the import is clearly private and tests are
  updated in the same slice.
- Keep shared Canvas/config/dependency helpers in one small common module only
  if needed; avoid duplicating Canvas send or course validation helpers across
  feature modules.
- Do not change grade math, school-day logic, idempotency behavior, or Canvas
  write semantics.

Suggested ownership:

- Policy routes:
  - load/apply course late policy.
- Sweep routes:
  - preview/apply school-day late-work sweep.
- Extra-time routes:
  - load/save local extra-time roster.
- Extension routes:
  - assignment due-date extension preview/apply.
- Curve routes:
  - curve preview/apply/history/revert.
- Snapshot routes:
  - read-only gradebook summary.

Acceptance criteria:

- `gradebook.py` becomes a thin route registration/facade file.
- Each feature route module maps directly to a Gradebook browser feature file.
- The module map tells future agents where to start by symptom.
- No Canvas write behavior changes.

Tests:

There is no dedicated `test_gradebook_routes.py` today. Use the existing route
contract and any gradebook-adjacent tests, then add focused route tests if this
slice changes import seams or exposes reusable helper behavior.

Minimum:

```powershell
py -m pytest api/tests/test_route_contract.py api/tests/test_schooldays.py
```

Recommended if route helpers are made testable:

```powershell
py -m pytest api/tests/test_gradebook_routes.py
```

Create `api/tests/test_gradebook_routes.py` only with fictional data and mocked
Canvas/config calls.

Manual smoke if feasible:

- Launch `cd api; py qf_ui.py`.
- Open `/gradebook`.
- Confirm each tab can load for a bookmarked course.
- For write flows, use preview or mocked/local-safe paths unless the user is
  explicitly doing live Canvas testing.

## Slice 3 - FeedbackExpert Inline Browser Split

Priority: high, privacy-sensitive.

Why this is painful:

The backend and pipeline are already split, but
`api/webui/templates/feedback_expert.html` still contains a large inline browser
workflow. Guided scoring, manual inbox processing, OpenRouter scoring, folder
actions, push preview/apply, and streaming progress live in one template. That
is expensive and risky during privacy-sensitive debugging.

Files to change:

- `api/webui/templates/feedback_expert.html`
- New files under `api/webui/static/feedback/`, likely:
  - `core.js`
  - `folders.js`
  - `personas.js`
  - `guided_run.js`
  - `manual.js`
  - `openrouter.js`
  - `push.js`
- `docs/reference/feedbackexpert-module-map.md`
- `api/webui/README.md` if the page map changes.

Implementation requirements:

- Use a small `window.CE_FEEDBACK` namespace for shared helpers/state.
- Move inline JavaScript out of the template without changing DOM ids or route
  calls.
- Keep SAFE/PRIVATE wording honest. Do not claim any external AI tool is
  guaranteed FERPA-safe or anonymous.
- Do not log real names, submission text, grades, private comments, or raw
  feedback payloads.
- Keep streaming behavior for guided run unchanged.

Suggested ownership:

- `core.js`: escaping, status helpers, shared folder/config bootstrap.
- `folders.js`: SAFE/PRIVATE/Inbox/FromLLM/ToEnter open actions.
- `personas.js`: persona/pattern loading and save behavior.
- `guided_run.js`: `/run/prepare` and `/run/stream`.
- `manual.js`: process inbox and re-identify flows.
- `openrouter.js`: OpenRouter config and CSV/bundle scoring lane.
- `push.js`: push preview/apply review table.

Acceptance criteria:

- `feedback_expert.html` is mostly markup plus script includes.
- The FeedbackExpert module map lists browser feature ownership.
- Existing route and pipeline tests still pass.

Tests:

```powershell
py -m pytest api/tests/test_feedback_pipeline.py api/tests/test_feedback_safety.py api/tests/test_feedback_scrub.py api/tests/test_feedback_vault.py api/tests/test_openrouter_client.py api/tests/test_route_contract.py
```

Manual smoke if feasible:

- Open `/feedback-expert`.
- Confirm folder buttons, persona loading, lane switching, prepare validation,
  and push preview controls still respond.
- Avoid live push unless the user explicitly asks for live Canvas testing.

## Slice 4 - Course Expert Remaining Inline Workflow Split

Priority: high after FeedbackExpert.

Why this is painful:

Course Expert push modules are mostly split, but
`api/webui/templates/course_expert.html` still has inline browser workflows for
Student Reports, portfolio/New Quizzes CSV helpers, merged portfolio, tab
activation, delivery-option toggles, quick assignment, file-source compatibility
helpers, and copy-skill behavior. Some of these overlap conceptually with the
new `push/*.js` modules, creating load-order and ownership ambiguity.

Files to change:

- `api/webui/templates/course_expert.html`
- New files under `api/webui/static/course_expert/` or existing
  `api/webui/static/push/` depending on ownership:
  - `course_expert/tabs.js`
  - `course_expert/student_reports.js`
  - `course_expert/portfolio.js`
  - `course_expert/quick_assignment.js`
  - optional `push/legacy_compat.js` only for globals that old standalone push
    pages still need.
- `docs/reference/course-expert-module-map.md`
- `api/webui/README.md` if high-level ownership changes.

Implementation requirements:

- Preserve legacy globals documented in the module map unless every caller is
  migrated in the same slice:
  - `window.CE_PUSH`
  - `localToISO`
  - `pushContent`
  - `targetCourses`
  - `initFileSource`
  - `copySkill`
- Do not touch Forge authoring contracts in `LLM_Modules/`.
- Do not alter push route behavior, Canvas write payloads, or Student Report
  packet content.
- Keep Student Reports PII out of tests and logs.

Suggested ownership:

- `tabs.js`: Course Expert tab activation and query/hash deep-link routing.
- `student_reports.js`: roster load, monitor toggle, student packet SSE.
- `portfolio.js`: New Quizzes CSV portfolio and merged portfolio forms.
- `quick_assignment.js`: quick gradebook-column push.
- `legacy_compat.js`: only if needed for file-source/copy-skill globals shared
  by standalone pages.

Acceptance criteria:

- `course_expert.html` is mostly markup and script includes.
- Student Reports/portfolio/quick-assignment symptoms route to their own files.
- Module map explicitly distinguishes Course Expert push modules from non-push
  Course Expert workflows.

Tests:

```powershell
py -m pytest api/tests/test_portfolio_merged.py api/tests/test_nq_report.py api/tests/test_route_contract.py api/tests/test_push_service.py
```

Manual smoke if feasible:

- Open `/course-expert`.
- Confirm each tab activates.
- Confirm Quick Assignment validates required fields and calls existing push
  flow.
- Confirm Student Reports roster load and stream wiring still works with
  mocked/safe data or during explicit live testing.
- Confirm portfolio CSV forms still submit and show open-folder action.

## Slice 5 - Push Service / Source Materials Follow-Up

Priority: only if live push/source bugs are active.

Why this is painful:

`api/webui/push_service.py` and `api/webui/source_materials.py` are not the
worst line-count offenders, but they sit directly on live push and source
context behavior. Refactor only when there is active debugging pressure or when
the earlier Course Expert split exposes a clear ownership boundary.

Possible split for `push_service.py`:

- `push_assignment.py`
- `push_page.py`
- `push_rubric.py`
- `push_quick.py`
- shared `push_canvas_helpers.py`

Possible split for `source_materials.py`:

- `source_extractors.py`
- `source_normalize.py`
- `source_bundle.py`

Tests:

```powershell
py -m pytest api/tests/test_push_service.py api/tests/test_source_materials.py api/tests/test_printable_attach.py api/tests/test_route_contract.py
```

## Documentation Rules For Every Slice

At the end of each completed slice:

1. Run `py tools/size_report.py --root api\webui`.
2. Update the relevant module map with:
   - new files
   - load order
   - namespace seam
   - first places to look by symptom
   - current size snapshot
3. Update `api/webui/README.md` if route/script ownership changed at the
   feature-reference level.
4. Move or archive this handoff only when all slices are complete or the user
   explicitly narrows/closes the active plan.

## Recommended Execution Order

1. Roster browser split.
2. Gradebook route split.
3. FeedbackExpert inline browser split.
4. Course Expert remaining inline workflow split.
5. Push service/source materials only if live-fire pain remains.

This order attacks the files most likely to waste LLM context during real Canvas
debugging while keeping each implementation slice bounded enough for a Toyota
agent.
