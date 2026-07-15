# Execution brief: Finish the teacher-facing product surface

Status: **ready for implementation**

Risk: **medium** — navigation and private-report entry points move, but no Canvas write,
credential, or private-data authority changes.

Executor: **Luna**

## Outcome

Canvas Expert's teacher-facing navigation consistently says **Home, Create, Grade,
Students, Automations, and Settings**. Student Reports is no longer a Create tab: it has a
dedicated page under Students, while existing roster behavior remains available at its
current route.

Old saved Student Reports links keep working through a cheap redirect. Internal routes,
Forge contract names, package names, and workspace identifiers stay stable.

## Locked decisions

- Lunas 2, 5, and 6 are GREEN. Luna 6 browser-console/keyboard verification was accepted
  by the user on 2026-07-15. This is the final teacher-surface slice, not a new product
  redesign.
- Student Reports lives at **`/students/reports`**, inside the existing Students/Roster
  surface. `/roster` remains the Students navigation destination and current roster owner.
  Do not create a Students dashboard, embed reports in Roster, or redesign reports.
- `GET /course-expert?tab=students` redirects to `/students/reports`; all first-party links
  point directly to `/students/reports`. Preserve other Course Expert tab deep links.
- Teacher-facing labels use `Home`, `Create`, `Grade`, `Students`, `Automations`, and
  `Settings`. Use `Grade an assignment` for the teacher action where a concrete
  PowerGrader link is needed. Keep internal `PowerGrader`, `FeedbackExpert`, operation-ledger,
  Course Expert route, and Forge contract names unchanged.
- Rename presentation copy only after ownership is true: FeedbackExpert is already a
  PowerGrader redirect, Download Work was already retired, and Student Reports is moved in
  this slice. Do not cosmetically rename a still-mixed or compatibility-only surface.
- Student Reports continues to use its existing private routes, report roots, monitored
  student data, CSV uploads, and portfolio logic. No data migration, report expansion,
  public route, or Canvas write is authorized.

## Scope

- Extract the existing Student Reports/portfolio markup and browser wiring from
  `course_expert.html` into a dedicated `student_reports.html` page that extends the existing
  workbench shell. Reuse `course_expert/student_reports.js` and its current private report
  APIs unchanged unless a direct-page bootstrap requires a narrow compatibility adjustment.
- Add the `/students/reports` page route and the old Course Expert students-tab redirect in
  `api/webui/routes/pages.py`. Keep the destination loopback-only and bind it to the
  existing `manage` section so Students remains active.
- Remove the Student Reports tab, rail item, client tab registration, and script inclusion
  from Course Expert only after search proves no other live Course Expert behavior consumes
  them. Update Desk and all navigation links to the new direct path.
- Apply the locked teacher vocabulary to the workbench header, legacy base navigation,
  dashboard/page titles, and concise teacher-facing copy. Preserve internal identifiers and
  technical docs where they are ownership names, not navigation labels.
- Update `docs/reference/workbench-canonical-flow-map.md`,
  `docs/reference/course-expert-module-map.md`, any affected Students/Roster map,
  `api/webui/README.md`, and `docs/reference/local-first-execution-roadmap.md` together.
  Archive or remove the completed active handoff only as part of this closure batch.

## Out of scope

- No package, API-prefix, workspace-root, Forge-contract, operation-ledger, PowerGrader, or
  Feedback engine rename.
- No Student Reports/portfolio feature work, CSV schema change, report persistence change,
  monitored-student change, AI transmission, Canvas write, or live Canvas probe.
- No new Home/Students dashboard, symmetric feature variants, broad CSS redesign, or route
  removal beyond search-proven Course Expert students-tab presentation wiring.
- No unrelated cleanup or separate acceptance/archive executor after this slice.

## Reference pattern and routing

- Existing report UI/API: `api/webui/templates/course_expert.html` (Student Reports panel),
  `api/webui/static/course_expert/student_reports.js`, and `api/webui/routes/reports.py`.
- Existing page/nav patterns: `api/webui/routes/pages.py`,
  `api/webui/templates/workbench_base.html`,
  `api/webui/templates/_workbench_header.html`, and `api/webui/templates/base.html`.
- Existing Course Expert tab routing: `api/webui/static/course_expert/tabs.js` and
  `api/webui/templates/course_expert.html`.
- Durable maps: `docs/reference/workbench-canonical-flow-map.md`,
  `docs/reference/course-expert-module-map.md`, `docs/reference/roster-module-map.md`, and
  `docs/reference/local-first-execution-roadmap.md`.
- Test patterns: `api/tests/test_route_contract.py`, `api/tests/test_webui_template_contracts.py`,
  route tests for `reports.py`, and navigation/template checks.
- Read project-local `TOOLS.md` before broad inspection; use targeted `rg` because its
  repository indexer is planned, not callable.

## Implementation requirements

1. Preserve every current Student Reports control, ID, endpoint, private-path open action,
   upload handling, and generated-artifact behavior. The new template is a presentation move,
   not an opportunity to change its private workflow.
2. Make `/course-expert?tab=students` redirect before rendering Course Expert. Retain direct
   Course Expert behavior for its actual Create tabs and keep query-only external bookmarks
   cheap and predictable.
3. Ensure both navigation shells identify `/students/reports` as Students and offer a direct
   Student Reports link under that surface. Do not leave a first-party link to the removed
   Course Expert tab or retired Download Work workflow.
4. Use concise action labels: Home; Create; Grade; Grade an assignment; Students; Student
   reports; Automations; Settings; AI instructions. Do not change internal subsystem names in
   routes, DOM contracts, storage, code, or durable technical references.
5. Add focused redirect/template tests and retain report route tests. Use fictional IDs only;
   do not put student names, report content, or paths into test output/fixtures.
6. Render `/`, `/course-expert`, `/students/reports`, `/roster`, `/powergrader`, `/routines`,
   and `/settings`; verify nav/deep links, keyboard focus, and zero new console errors.
   Update the handoff with compact evidence before handback.

## Verification

```powershell
py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_desk_routes.py api/tests/test_work_routes.py
git diff --check
rg -n "course-expert\?tab=students|data-tab=students|ce-tab-students|Student Reports" api docs
```

Run focused reports tests if a report route/template contract changes. Render the seven named
routes with synthetic-only configuration; test the old deep link redirect, the new direct
page, keyboard focus, and browser console.

## Stop conditions

Stop with RED rather than guessing if:

- The extracted report UI relies on Course Expert state, script order, or DOM IDs that cannot
  be preserved without changing report behavior or private data flow.
- A compatibility redirect would capture another live Create tab, a saved report artifact,
  or a live Canvas/write route.
- A requested label would misrepresent an unmigrated mixed surface, or cleanup requires a
  package/workspace/contract rename.
- A report, monitored-student, credential, AI, or Canvas-write behavior would change.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — senior accepted the required local browser-console and
  keyboard-focus verification reported by the user on 2026-07-15.
- Commit hash: changes are uncommitted and preserve the existing Luna 5/6 worktree changes.
- Files changed: `api/webui/routes/pages.py`; new
  `api/webui/templates/student_reports.html`; `course_expert.html`, `dashboard.html`,
  `roster.html`, `base.html`, `_workbench_header.html`, and `roster_workbench.css`;
  `test_route_contract.py` and `test_desk_routes.py`; `api/webui/README.md`; and the
  routed canonical-flow, Create, Roster, and roadmap references.
- Verification: `py -m pytest api/tests/test_route_contract.py
  api/tests/test_webui_template_contracts.py api/tests/test_desk_routes.py
  api/tests/test_work_routes.py` — **36 passed**. `git diff --check` — **passed**.
  TestClient render/redirect check — **8 passed**: `/`, `/course-expert`,
  `/students/reports`, `/roster`, `/powergrader`, `/routines`, and `/settings` each returned
  200; `/course-expert?tab=students` returned `307 /students/reports`.
- Rendered routes: server rendering was checked with TestClient. The user subsequently
  verified the seven local routes, keyboard focus, and zero new browser-console errors;
  senior accepted this evidence on 2026-07-15.
- Deviations: none. Student Reports keeps the existing DOM IDs, report scripts, private APIs,
  report roots, CSV handling, monitored-student behavior, and portfolio behavior. The only
  styling addition makes the Roster rail's direct report link present as its existing lens
  affordance.
- Remaining blocker: none. No live Canvas or AI call was made.
