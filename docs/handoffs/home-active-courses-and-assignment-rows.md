# Execution brief: Make Home an assignment-level teacher dashboard

Status: **ready for implementation**

Risk: **medium** — this is a local read-only presentation change, but selecting one
canonical PowerGrader session per assignment must not hide a session with approved grades
waiting to be posted.

Executor: **Luna**

## Outcome

Home opens as the teacher's overall desktop. Its top line plainly lists the configured
active courses and links to the exact Settings section where that list is changed; it no
longer exposes or mutates a hidden "course context."

Continue and Attention are assignment-level on Home. Multiple saved PowerGrader sessions
for the same course and assignment produce one truthful row with one useful resume target,
while the full session history remains available inside PowerGrader.

## Locked decisions

- The observed duplicate is not one job rendered twice. Local inspection confirmed two
  distinct PowerGrader session projections for the same active course and assignment, with
  the same counts. The Work Registry currently keys those rows by session ID.
- Home is cross-course and assignment-level; PowerGrader remains session-level. Do not
  delete, merge, rewrite, or migrate session files, and do not remove any session from the
  PowerGrader setup/history UI.
- Coalesce PowerGrader projections only for Home's existing local Work Registry adapter.
  Group summaries only when both `course_id` and `assignment_id` are present, using the
  exact `(course_id, assignment_id)` pair. Missing-identity summaries remain independent so
  uncertain records are never merged.
- Select one canonical session per group in this order: (1) a session with approved results
  not yet posted, choosing the greatest unposted count and then the newest `created` value;
  (2) another incomplete session, choosing the newest `created` value; (3) the newest
  completed session. A group therefore appears in Attention or Continue, never both. Use
  the selected session's existing counts and resume URL; do not sum counts because sessions
  may cover the same students.
- Home's first line is plain teacher-facing text: **Active courses:** followed by configured
  nicknames/names in saved order, comma-separated and allowed to wrap. Show **None selected**
  when empty. Place **Change in Settings** beside it and link directly to
  `/settings#current-courses-card`. Do not add a dropdown, badges, course switcher, or new
  settings store.
- Remove Home's `Course context`, `Keep saved context`, target note, and course selector.
  Home Start links become ordinary navigation and must not call `CE_CONTEXT.reconcile`,
  `setFocus`, or `setTargets`. Destination pages keep ownership of their own course/focused
  work choices; the shared internal context contract remains unchanged elsewhere.
- Keep the explicit bounded Canvas read, but label it **Check active courses**. Replace
  Home's visible `Local state`, `projections`, and `context` phrasing with direct copy such
  as **Showing saved work**, **Checking active courses…**, **Checked active courses**, and a
  plain partial/failure sentence. Do not change scan behavior, timing, cache, or API shape.
- The teacher-facing word `context` is also removed from the currently visible PowerGrader
  privacy/source copy found by the scoped search. Say that pseudonymized files **may still
  contain details that could identify a student**, and call batch-wide input **shared source
  material**. Keep internal names such as `CE_CONTEXT`, `source_context`, DOM classes, Python
  parameters, contracts, and technical documentation unchanged.

## Scope

- Update `api/work_registry/adapters.py::_powergrader_jobs` with a small deterministic
  summary-selection helper before jobs are projected.
- Update `api/webui/templates/dashboard.html` and
  `api/webui/static/pages/dashboard.css` for the informational active-course line, Settings
  anchor, wrapping, empty state, and retained check button.
- Remove Home-only course-selection behavior and revise direct status copy in
  `api/webui/static/desk.js`.
- Revise the four currently visible PowerGrader `context` phrases in
  `api/webui/templates/powergrader_setup.html` and
  `api/webui/static/powergrader/setup_autoscore.js`; use a narrow post-change search to catch
  any other literal teacher-facing occurrence in templates/static assets.
- Add focused adapter, route/template, and Desk JavaScript coverage. Update
  `docs/contracts/work-registry-contract.md`, `api/webui/README.md`, and, only if ownership
  wording requires it, `docs/reference/powergrader-module-map.md`.
- Archive the completed, directly superseded
  `docs/handoffs/home-attention-luna5.md` as part of this closure batch. Do not archive or
  alter unrelated active briefs.

## Out of scope

- No session deletion, session-file migration, automatic archival, PowerGrader setup/history
  redesign, or prevention of creating another session for the same assignment.
- No change to Canvas reads/writes, grading/comment behavior, scan providers, discovery
  cache, operation ledger, suppression storage, Course Catalog, Settings persistence, or
  shared `CE_CONTEXT` behavior outside Home.
- No aggregation of student counts across sessions, new assignment registry shape, new API
  fields, live Canvas probe, or background page-load scan.
- No broad vocabulary rewrite of internal code, API contracts, developer documentation,
  privacy field names, or legitimate non-UI use of the word `context`.

## Reference pattern and routing

- Existing Home projection: `api/work_registry/adapters.py::_powergrader_jobs`,
  `api/webui/routes/work.py::_raw_jobs`, and `api/webui/routes/work.py::_presentations`.
- Existing session summary ordering: `api/powergrader/session_store.py::list_session_summaries`.
- Existing Home surface: `api/webui/templates/dashboard.html`,
  `api/webui/static/desk.js`, and `api/webui/static/pages/dashboard.css`.
- Test patterns: `api/tests/test_work_routes.py`, `api/tests/test_desk_routes.py`, and
  `api/tests/test_webui_template_contracts.py`.
- Durable behavior: `docs/contracts/work-registry-contract.md` and `api/webui/README.md`.
- Read project-local `TOOLS.md` before broad inspection. Its repository indexer is planned,
  so use targeted `rg` only.

## Implementation requirements

1. Add pure, focused ranking/grouping logic around the existing session summaries. Cover two
   identical incomplete sessions, Attention taking precedence over Continue, greatest
   unposted count, newest tie-breaking, completed-only groups, different assignments,
   different courses, and missing course/assignment identity. Use fictional IDs only.
2. Preserve adapter job validation and the exact generic job shape. The chosen source session
   remains the job/source identity, so Ignore/Snooze/Complete continue using existing local
   mutations without a group-job schema.
3. Render active course names directly from the existing `saved_courses` template input.
   Keep escaping, saved order, narrow-screen wrapping, keyboard-visible Settings/check
   controls, and a useful empty state. Do not expose Canvas IDs on Home's new top line.
4. Delete Home's selector wiring completely. In particular, do not reconcile an empty course
   list after removing the field; Home must leave previously saved destination choices
   untouched rather than clearing or broadening them.
5. Use direct teacher language in every changed status. Partial/failure messages must state
   that some courses could not be checked and that saved work remains; they must not imply a
   Canvas write or promise live completeness.
6. Record the compact traffic-light report below, including browser evidence, before
   handback. Commit on `dev` only if the senior's current authorization and worktree state
   permit it.

## Verification

```powershell
py -m pytest api/tests/test_work_routes.py api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py
git diff --check
rg -n "Keep saved context|Course context|Saved targets are unchanged|Scan Current courses|Local state|shared context|identifying context" api/webui/templates api/webui/static
```

Render `/` with zero, one, and four active fictional courses at wide and narrow widths.
Confirm the names and Settings anchor, wrapping without horizontal overflow, absence of the
selector, ordinary Start-link navigation, the check button/status states, keyboard focus,
and zero new console errors. Render `/powergrader` and confirm the revised privacy/source
copy with zero new console errors. Use synthetic/local data only; do not invoke a Canvas scan,
Canvas write, AI call, or routine.

## Stop conditions

Stop with RED rather than guessing if:

- A useful canonical resume target cannot be chosen from existing summary fields without
  reading full private sessions or inventing aggregate counts.
- Coalescing requires a new persisted group identity, mutation contract, session migration,
  or change to the PowerGrader history surface.
- Removing Home's selector would require changing shared course behavior on another route.
- A credential, FERPA, live Canvas/write, AI transmission, or external call becomes necessary.
- An unrelated regression or overlapping uncommitted edit blocks the scoped files.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — the assignment-level Home projection, active-course line,
  direct teacher language, tests, and accepted browser evidence are complete.
- Commit hash: changes are uncommitted on `dev`.
- Files changed: `api/work_registry/adapters.py`, `api/webui/templates/dashboard.html`,
  `api/webui/static/desk.js`, `api/webui/static/pages/dashboard.css`,
  `api/webui/templates/powergrader_setup.html`,
  `api/webui/static/powergrader/setup_autoscore.js`,
  `api/tests/test_work_routes.py`, `api/tests/test_desk_routes.py`,
  `api/tests/test_webui_template_contracts.py`,
  `docs/contracts/work-registry-contract.md`, `api/webui/README.md`, this handoff, and
  the archived `docs/handoffs/archive/home-attention-luna5.md`.
- Verification: `py -m pytest api/tests/test_work_routes.py
  api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py` — **39 passed,
  0 failed, 0 skipped**. `git diff --check` — passed. The required scoped `rg` search for
  removed Home/PowerGrader copy returned no matches.
- Rendered routes checked: senior-supplied browser evidence on the updated local app checked
  `/` at 1440x1000 and 390x844 with the one configured active course. The exact Settings
  anchor, absent selector, single coalesced Continue row, no horizontal overflow, ordinary
  `Grade an assignment` navigation to `/powergrader`, and zero console warnings/errors were
  confirmed. `/powergrader` showed the revised pseudonymization wording with zero console
  warnings/errors. Synthetic route tests separately cover zero and four fictional active
  courses, saved order, escaping, no exposed course IDs in the top line, and the empty state.
  No scan, Canvas write, AI call, or routine was invoked.
- Deviations: the executor's in-app browser binding was unavailable; the senior supplied
  and accepted the required local browser evidence. The live browser had one active course;
  zero/four-course cases were rendered through focused synthetic route tests, not overstated
  as additional live-browser runs.
- Remaining blocker or decision: none.
