# Execution brief: Current courses define Canvas Expert's operational scope

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Teachers manage one clear set of **Current courses** in Settings; saved courses outside
that set appear as **Previous courses** and no longer leak into normal Canvas Expert
pickers or Desk work. Moving a course to Previous preserves local history while ensuring
scheduled PowerGrader work for that course cannot fetch, score, or write until the course
is Current again.

This is the first vertical term-rollover improvement. It fixes course scoping and safety;
it does not redesign Desk row content or add Canvas communications.

## Locked decisions

- The teacher-facing concepts are **Current courses**, **Previous courses**, and **Add
  courses from Canvas**. Do not present Bookmarked/Active/Inactive as separate product
  concepts in the affected UI.
- Preserve the existing `saved_courses` records, `active` boolean, config facade methods,
  and Settings route URLs. Existing `active: true` records are Current; `active: false`
  records are Previous; missing `active` continues to default to Current. No persistence
  migration or new course-state schema is authorized.
- Settings is the only surface that browses the complete live Canvas course list. Normal
  operational pickers render only `config.active_courses()` and must not call
  `/api/courses` to append extra courses.
- Moving a Current course to Previous is reversible. Preserve PowerGrader sessions,
  autoscore queue entries, Desk registry/cache data, receipts, downloads, roster settings,
  and authored work. Do not implement destructive cleanup.
- Desk displays course-scoped work only when at least one `course_ids` value intersects
  the Current course IDs. Jobs with no course scope remain visible. Hidden Previous-course
  jobs remain stored and automatically reappear if that course becomes Current again.
- Shared `CE_CONTEXT` focus/targets must be authoritatively reconciled against the
  server-rendered Current course list on Desk and Course Expert. A Previous course cannot
  survive as focused/target context after one of those operational surfaces loads.
- Existing built-in/custom routines already consume `active_courses()` dynamically and
  remain globally enabled. Do not disable entire routines when one course becomes Previous.
- Scheduled PowerGrader autoscore/auto-push and automatic late catch-up require an explicit
  execution-time Current-course gate. A Previous-course item is skipped before claim,
  Canvas fetch, AI call, session mutation, or Canvas write. Leave its queue/session state
  intact so it resumes automatically if the course becomes Current again; include a concise
  local routine-summary line/count explaining the pause.
- Direct, deliberate access to a preserved historical PowerGrader session remains allowed.
  This brief gates automatic execution, not explicit teacher review of saved history.
- The worktree is already dirty with unrelated staged and unstaged work, including recent
  Desk and Course Expert repairs. Preserve every unrelated hunk. Do not stage, unstage,
  commit, reset, or reformat unrelated files.

## Scope

- Split the Settings course presentation into Current and Previous groups, with reversible
  Move to Previous / Make Current actions and clear non-destructive confirmation copy.
- Change the live Canvas browser action/copy from bookmarking to adding a Current course.
- Constrain Course Expert and Gradebook course pickers to server-rendered Current courses;
  remove their automatic all-course expansion.
- Reconcile Desk and Course Expert shared context to Current courses and update affected
  teacher-facing copy from active/bookmarked terminology to Current/Previous terminology.
- Filter Desk's local/public job projection by Current course IDs without deleting source
  jobs or derived registry records.
- Gate scheduled PowerGrader autoscore/auto-push and automatic late-catchup execution by
  Current course membership.
- Update focused regression tests and the durable Settings/WebUI documentation that
  describes this behavior.

Expected insertion points include:

- `api/webui/routes/pages.py::settings_page`
- `api/webui/templates/settings.html`
- `api/webui/static/settings/courses.js`
- `api/webui/templates/course_expert.html`
- `api/webui/static/push/course_picker.js::bindChecklist` and the current
  `loadAllCoursesIntoChecklist` startup path
- `api/webui/static/gradebook.js::loadAllCoursesIntoPicker`
- `api/webui/templates/dashboard.html` and `api/webui/static/desk.js`
- `api/webui/routes/work.py::_all_jobs`
- `api/webui/routes/routines_powergrader.py::_run_routine_powergrader_scheduled_autoscore`
  and `_run_routine_powergrader_late_catchup`
- `api/webui/config/courses.py` docstrings only if needed for durable terminology; preserve
  the public facade and stored fields

## Out of scope

- Desk row/course/assignment enrichment, semantic PowerGrader count redesign, Inbox, and
  student-comment notifications.
- A bulk term-wizard, impact-count API, cache-reset button, deleting Previous courses,
  deleting historical jobs, or a new archive database.
- Changing Canvas course workflow states or inferring terms/semesters from Canvas dates.
- New scheduled-job statuses, queue schema changes, background services, OS notifications,
  live Canvas writes, or live Canvas probes.
- Renaming private route paths/config methods merely for terminology purity.
- Full-repository cleanup, unrelated test pruning, staging, committing, or branch work.

## Reference pattern and routing

- Existing implementation to follow: `api/webui/config/courses.py::saved_courses` and
  `active_courses`
- Existing server rendering: `api/webui/routes/pages.py::_push_base_ctx` and
  `settings_page`
- Existing context contract: `api/webui/static/app_context.js::reconcile`
- Existing Desk projection seam: `api/webui/routes/work.py::_all_jobs`
- Existing scheduled queue behavior: `api/powergrader/autoscore_queue.py::due_jobs`
- Test patterns to follow: `api/tests/test_app_context_contract.py`,
  `api/tests/test_work_routes.py`, `api/tests/test_webui_template_contracts.py`,
  `api/tests/test_powergrader_scheduled_autoscore.py`
- Required durable references: `docs/reference/settings-module-map.md`,
  `api/webui/README.md`, and `docs/reference/powergrader-module-map.md`
- Read project-local `TOOLS.md` before using broad manual inspection. The repo-indexer and
  change-risk tools are currently planned rather than callable; use narrow `rg` searches.

## Implementation requirements

1. Render Current and Previous Settings groups from the unchanged saved-course records.
   Adding a Canvas course makes it Current. Moving Current to Previous requires a concise
   confirmation that local work is retained and automatic work will not run while Previous.
   Moving Previous to Current is immediate and reversible. Preserve remove-course behavior
   but describe it separately from term rollover.
2. Remove operational all-course expansion from Course Expert and Gradebook. On Course
   Expert initialization, reconcile `CE_CONTEXT` authoritatively against the rendered
   Current rows before applying saved focus/targets. On Desk initialization, reconcile
   against the rendered Current select options as well.
3. Filter `_all_jobs()` before public projection: retain global/unscoped jobs; retain a
   course-scoped job only when its normalized course ID set intersects the Current IDs.
   Apply the same result to initial Desk rendering, refreshes, and mutation lookup through
   existing callers. Do not mutate registry/session/queue authorities as part of filtering.
4. In scheduled autoscore, obtain Current IDs once per routine run and skip each non-current
   due job before claiming it. In automatic late catch-up, use the summary's course ID to
   skip non-current sessions before loading/mutating the private session or invoking score
   logic. Report paused/skipped counts without exposing student data.
5. Replace affected teacher-facing Active/Inactive/Bookmarked language with Current/Previous
   language. Internal symbol/route compatibility names may remain. Update durable docs so
   future agents understand that `active_courses()` is the internal Current-course boundary.
6. Add focused regressions for the scope filter, global-job retention, context reconciliation,
   absence of operational `/api/courses` expansion, Settings terminology/actions, and both
   automatic PowerGrader safety gates. Update existing scheduled tests to declare their
   Current course explicitly rather than weakening the new guard.
7. Self-review the final diff against this brief, update `Execution result`, and, if GREEN,
   move this completed handoff into `docs/handoffs/archive/` as part of the same batch.

## Verification

Run the focused behavioral matrix only:

```powershell
py -m pytest api/tests/test_workspace.py api/tests/test_app_context_contract.py api/tests/test_work_routes.py api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_routine_receipts.py api/tests/test_route_contract.py
node --check api/webui/static/settings/courses.js
node --check api/webui/static/push/course_picker.js
node --check api/webui/static/gradebook.js
node --check api/webui/static/desk.js
git diff --check HEAD
```

Rendered verification is required for `/settings`, `/`, `/course-expert`, and `/gradebook`:

- Each page loads with zero new browser-console errors.
- Settings visibly separates Current and Previous course groups and keeps live Canvas browse
  inside Settings.
- Desk, Course Expert, and Gradebook show only Current courses in their normal selectors.
- Course Expert does not append an `All courses` group after load.

Do not mutate the user's real course settings during rendered verification. Do not run a live
Desk scan or any Canvas write. Use the smallest isolated/local route-rendering setup available;
if a safe rendered interaction cannot be isolated, record that exact limitation as YELLOW
rather than altering real settings. Do not run the full API or engine suite unless a focused
failure demonstrates unexpected coupling.

## Stop conditions

Stop with RED rather than guessing if:

- A named insertion point or assumed interface is missing.
- Existing behavior contradicts a locked decision.
- Correct gating requires a queue/session schema change or prevents automatic resumption when
  a course becomes Current again.
- The requested outcome requires a new public contract, persistence format, subsystem, or
  external transmission not authorized here.
- A credential, FERPA, live-write, or scheduled-write question is underspecified.
- Preserving the existing staged/unstaged work is not possible at an overlapping file.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — implementation is complete and the senior supplied the
  required in-app browser verification after executor handback.
- Changes remain uncommitted; existing staging was not altered.
- Files changed: `api/webui/config/courses.py`, `api/webui/routes/pages.py`,
  `api/webui/routes/work.py`, `api/webui/routes/routines_powergrader.py`,
  `api/webui/templates/settings.html`, `api/webui/templates/dashboard.html`,
  `api/webui/templates/course_expert.html`, `api/webui/static/settings/courses.js`,
  `api/webui/static/push/course_picker.js`, `api/webui/static/gradebook.js`,
  `api/webui/static/desk.js`, `api/tests/test_workspace.py`,
  `api/tests/test_work_routes.py`, `api/tests/test_webui_template_contracts.py`,
  `api/tests/test_powergrader_scheduled_autoscore.py`, `api/webui/README.md`,
  `docs/reference/settings-module-map.md`, `docs/reference/powergrader-module-map.md`,
  and this handoff.
- Verification commands and pass/fail/skip counts: focused pytest matrix **62 passed,
  0 failed, 0 skipped**; four required `node --check` commands **4 passed, 0 failed**;
  isolated `TestClient` render assertions **4 routes passed**; `git diff --check HEAD`
  **passed with line-ending warnings only**; senior browser-console checks **4 passed,
  0 errors**.
- Rendered routes checked: isolated local `/settings`, `/`, `/course-expert`, and
  `/gradebook` requests all returned 200; Settings contained distinct Current,
  Previous, and Add-from-Canvas groups; the three operational pages contained both
  fictitious Current courses and excluded the fictitious Previous course; Course
  Expert contained no `All courses` group. Senior in-app browser verification loaded
  all four routes with zero console errors; Settings visibly showed all three course
  groups and Canvas browse, Desk showed only the configured Current course and Current
  terminology, Course Expert showed only the configured Current row with zero
  `.cc-all-divider` elements, and Gradebook showed only the configured Current option
  with zero `All courses` optgroups. The already-running server had stale imported
  Python for `settings_page`, so populated Settings-row evidence remains the isolated
  render; no real settings were mutated.
- Deviations from the brief: none. No real settings, Desk scan, Canvas read, AI call,
  session mutation, or Canvas write was used during verification.
- Remaining blocker or decision, if any: none.
