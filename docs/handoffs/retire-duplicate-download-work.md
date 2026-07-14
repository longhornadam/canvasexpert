# Execution brief: retire duplicate Download Work acquisition

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Canvas Expert no longer offers Download Work as a separate acquisition job.  From the
existing PowerGrader course-and-assignment context, a teacher can deliberately refresh
that assignment from Canvas or open its canonical local evidence folder.  The built-in
download routine uses the same focused assignment-refresh owner, so preserved evidence
has one live acquisition authority.

## Locked decisions

- Luna 1's `api/powergrader/assignment_refresh.py::refresh_assignment` is the sole live
  assignment-evidence acquisition owner.  The new explicit refresh route and the existing
  PowerGrader start route call it; neither reimplements Canvas submission/file acquisition.
- Place **Refresh from Canvas** and **Open local folder** immediately below/alongside the
  selected assignment control in `/powergrader`.  They stay disabled without both a selected
  course and assignment.  Refresh makes a focused read only; it creates no PowerGrader
  session, AI artifact, Canvas write, background job, or live student data in a global UI
  status.  Opening a folder computes the canonical private assignment path server-side and
  returns only success/failure, not a private path to the browser.
- The existing start action continues to refresh evidence itself; an explicit refresh merely
  lets the next start reuse it.  Surface only the manifest scope state and generic error text.
- Remove the Course Expert Download Work rail item, tab, template markup, `push/download.js`,
  its script include, and its SSE flow.  Do not replace it with another course-wide selector,
  portable-export feature, or background binary prefetch.
- Remove `/api/submissions/download/stream` and `/api/download-root` after their only UI
  callers are gone and route-contract evidence is updated.  Keep `/api/assignments-full`,
  `/api/course-folder`, `/api/open-folder`, `/api/pick-download-folder`, and settings/course
  compatibility surfaces when they still have non-Download-Work callers; they must not depend
  on `downloader.py` afterward.
- Retire `api/downloader.py` only after repository search shows no imports/callers.  Its report
  and portfolio helper consumers are real: move only the existing pagination/binary helper
  behavior to a narrowly named shared helper with those immediate consumers, move
  Student-Reports-only filename helpers into `student_packet.py`, and use
  `workspace.safe_component` for safe names.  Do not create a generic sync/download framework.
- The built-in `download` routine retains its current opt-in/scheduled semantics and date
  window, but enumerates eligible assignments then calls the focused refresh owner once per
  assignment.  It reports aggregate current/incomplete/failure counts without names, paths,
  submission text, grades, or Canvas URLs.  Each assignment has its own Luna 1 10 MiB focused
  refresh budget; no job-wide binary prefetch is introduced.
- Preserve all existing workspace evidence and compatibility reads.  Never delete, rename,
  migrate, merge, or backfill teacher evidence.  No Canvas writes, credential persistence,
  external AI transmission, or scheduled auto-push behavior is authorized.

## Scope

- Add the narrow PowerGrader explicit-refresh and open-canonical-folder routes near
  `api/webui/routes/powergrader.py::pg_start`, and bind the buttons in
  `api/webui/templates/powergrader_setup.html` and
  `api/webui/static/powergrader/setup_core.js`.
- Remove the obsolete Course Expert Download Work card from
  `api/webui/templates/course_expert.html`, `api/webui/static/push/download.js`, its script
  include, and its template/runtime tests.  Remove `CE_PUSH.streamSSE` from
  `api/webui/static/push/core.js` only after proving this was its sole caller.
- Replace `api/webui/routes/reports.py::submissions_download_stream` and
  `api/webui/routes/routines_builtin.py::_run_routine_download` with the locked behavior;
  maintain only compatibility paths that still serve another feature.
- Retire `api/downloader.py` after narrowly relocating its genuine Student Reports/portfolio
  utility consumers.  Update imports and tests with synthetic data only.
- Update `docs/reference/course-expert-module-map.md`,
  `docs/reference/powergrader-module-map.md`, and the relevant sections of
  `api/webui/README.md` so they no longer present Download Work as a live workflow.

## Out of scope

- No course-wide launch synchronization, batch export, new workspace config, data migration,
  historical attempt backfill, or new persistence contract.
- No change to Student Reports, portfolio output, PowerGrader AI/review/write paths, New Quiz
  writes, routine coordinator semantics, or course/Settings navigation beyond retiring the
  Download Work UI.
- Do not remove a compatibility route or settings field solely because its name includes
  `download`; remove only proven-dead standalone-acquisition callers.
- No live Canvas probe or real course/student evidence in verification.

## Reference pattern and routing

- Shared acquisition owner: `api/powergrader/assignment_refresh.py::refresh_assignment` and
  the locked decisions in `docs/handoffs/archive/focused-assignment-refresh.md`.
- Existing setup insertion point: `api/webui/templates/powergrader_setup.html` lines 62–94 and
  `api/webui/static/powergrader/setup_core.js::loadAssignments` / `::bindStartSession`.
- Retired workflow: `api/webui/static/push/download.js`,
  `api/webui/routes/reports.py::submissions_download_stream`, and
  `api/webui/routes/routines_builtin.py::_run_routine_download`.
- Existing non-download callers to preserve: `api/portfolio_service.py`, `api/student_packet.py`,
  `api/webui/static/course_info.js`, and `api/webui/static/push/course_picker.js`.
- Tests to follow: `api/tests/test_powergrader_attachment_workflow.py`,
  `api/tests/test_downloader.py`, `api/tests/test_route_contract.py`,
  `api/tests/test_webui_template_contracts.py`, and `api/tests/test_routine_receipts.py`.
- Required references: `AGENTS.md`, `TOOLS.md`,
  `docs/reference/local-first-execution-roadmap.md` (Luna 2),
  `docs/reference/course-expert-module-map.md`, and
  `docs/reference/powergrader-module-map.md`.

Read `TOOLS.md` before broad inspection.  The repository-indexer is planned, so use focused
`rg` caller evidence when it is unavailable.

## Implementation requirements

1. Implement focused-refresh/folder routes that validate course and assignment IDs, never accept
   a browser-provided filesystem path, and return content-minimized status.  Reuse the existing
   local-only open-folder mechanism internally only after computing the canonical assignment
   directory from saved course identity and assignment ID.
2. Bind the two PowerGrader actions to current selector state.  Refresh must show generic
   current/incomplete/unavailable feedback, leave selection and setup controls usable, and not
   navigate to or create a session.  Folder opening must be a single local side effect from a
   deliberate click.
3. Remove the standalone Download Work Course Expert path and all of its live client/server
   callers.  Update tests from implementation-shape assertions to the teacher-visible
   replacement and route-surface removal.
4. Refactor the built-in download routine to enumerate its eligible current-course assignments
   and call `refresh_assignment` once per assignment with an ephemeral non-session correlation
   ID.  Preserve its error isolation and scheduled opt-in behavior; distinguish current from
   incomplete/failed results.
5. Prove all `downloader` imports have been retired before removing the module.  Preserve report
   and portfolio helper behavior in their new narrow homes; do not change their output layout
   or write real student data in tests.
6. Update the routed documentation and record the execution result below before handback.

## Verification

```powershell
py -m pytest api/tests/test_powergrader_attachment_workflow.py api/tests/test_downloader.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_routine_receipts.py
git diff --check
rg -n "(^|from )downloader|run_download|_download_assignment|submissions/download/stream|streamSSE" api
```

Migrate/remove `test_downloader.py` only after the caller proof is clean.  Add focused synthetic
tests for explicit refresh delegation/no-session creation, canonical folder computation without
path input, routine delegation and partial-failure aggregation, and surviving report/portfolio
helper behavior.  The final `rg` output may contain only explanatory historical documentation
outside `api/`; no live API/client import or caller may remain for retired acquisition symbols.

Render `/course-expert`, `/powergrader`, and `/routines` in the local app.  Verify that Course
Expert has no Download Work tab/rail or console errors, PowerGrader exposes disabled-until-
selected refresh/folder actions, and Routines has no browser-console errors.  Do not choose a
real course/assignment, start a session, run a routine, or display/log student-derived data;
synthetic tests cover action behavior.

## Stop conditions

Stop with RED rather than guessing if:

- A surviving Download Work caller needs a behavior the focused refresh owner cannot supply
  without broadening its persistence contract or adding course-wide acquisition.
- Removing the flow would break Student Reports, portfolio generation, course info, or settings
  compatibility beyond the narrow helper relocation authorized here.
- A safe folder action requires accepting an arbitrary browser path, exposing private paths in a
  generic status, or changing local-only boundaries.
- The scheduled routine needs a queue, distributed coordination, or a new job platform rather
  than its existing coordinator and focused calls.
- A required change would add a Canvas write, external transmission, credential persistence,
  evidence migration/deletion, or live verification involving real student data.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: `7bf0859` (this execution record follows in a closure commit)
- Files changed: focused PowerGrader setup routes/assets, Course Expert template/push core,
  reports and built-in routine ownership, narrow report/portfolio transport helpers, route/template tests,
  and routed module/teacher-facing references. Retired `api/downloader.py`, its test, and `push/download.js`.
- Verification: focused PowerGrader/route/template/routine suite passed **52** tests; `git diff --check` passed;
  the required retired-symbol search returned no live `api/` callers. `test_downloader.py` was deliberately removed
  with the retired module.
- Rendered routes: `/course-expert`, `/powergrader`, and `/routines` rendered in the local browser with zero console errors.
  Course Expert had no Download Work label; PowerGrader exposed Refresh from Canvas and Open local folder.
  No course or assignment was selected, no session/routine was started, and no student data was accessed.
- Deviations: none.
- Remaining blocker or decision: none.
