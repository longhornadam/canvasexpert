# Execution brief: Desk rows identify the work and explain the counts

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Desk no longer presents opaque rows such as “PowerGrader work · 24 items.” Each row
shows its Current-course context, the assignment name when a local PowerGrader authority
already knows it, a plain-language progress sentence, and a specific action label.

This is batch 2 of the agreed Desk work. It improves the existing Continue and Attention
rows without changing registry persistence, scanning Canvas, exposing student records, or
adding Inbox/comment notifications.

## Locked decisions

- Keep the Work Registry job schema, `registry.v1.json`, discovery cache, suppressions,
  `models.public_job()`, fingerprints, material versions, adapters, and mutation payloads
  unchanged. Registry jobs remain the exact generic PII-minimized shape in
  `docs/contracts/work-registry-contract.md`.
- Add a **transient Desk presentation sidecar**, not fields on the job. `GET /api/work`
  returns `presentations`, a mapping keyed by opaque `job_id`; the dashboard initial JSON
  receives the same separate mapping. Each presentation has exactly four string fields:
  `course_label`, `title`, `summary`, and `action_label`.
- Presentation data is computed on demand from local authorities and is never written to
  registry, discovery cache, suppressions, sessions, queue entries, receipts, logs, or
  settings. `_find_current()` and every mutation/persistence path continue to use raw exact
  jobs, never presentation dictionaries.
- The loopback-only presentation may show the configured Current-course nickname/name and
  a teacher-authored assignment title already present in a PowerGrader session summary or
  scheduled autoscore queue. It may show aggregate student/submission counts. It must never
  include student names or IDs, grades, comments, submission content, feedback, roster
  notes, or per-student state.
- Do not perform a Canvas read, open full private PowerGrader session payloads, or change an
  authority to obtain display text. Use only `session_store.list_session_summaries()`, the
  autoscore queue's existing job metadata, Current-course config, and the already-public
  registry job/counts. Fail closed to generic presentation when a local authority cannot be
  read.
- Keep Continue and Attention as the primary Desk sections. Use a compact course label/chip
  inside each row; do not restructure Desk into nested per-course groups in this batch.
- Initial server-rendered rows and asynchronous `/api/work` refreshes must use the same
  presentation values and fallbacks. The UI must not briefly relabel counts as generic
  “items” after refresh.
- PowerGrader count semantics are locked:
  - `total` = students in the session.
  - `pending` = students awaiting review (`total - approved`).
  - `affected` = approved results not yet posted (`approved - posted`).
  - Example: `24 students · 22 awaiting review · 2 approved, not posted`.
  - Omit zero-valued pending/affected clauses. If total is positive and both are zero, say
    `all reviewed and posted`; if total is zero, say `No students in session`.
- PowerGrader title is the local assignment name, falling back to `PowerGrader session`.
  Use `Review & post` when `affected > 0`, otherwise `Continue grading`.
- Scheduled PowerGrader title is its local assignment name, falling back to
  `Scheduled PowerGrader`. Its summary uses its local queue state without exposing queue
  internals: waiting to run, draft ready for review, needs attention, completed, or in
  progress. Its action label is `Open grading`.
- Detected jobs get semantic but aggregate-only fallbacks:
  - `grade.debt`: `Grading needed`; “N submission(s) awaiting grading”; `Open PowerGrader`.
  - `late.work`: `Late work`; “N late submission(s)”; `Open Gradebook`.
  - `roster.warning`: `Roster attention`; “N roster issue(s) need review”; `Open Roster`.
  These rows receive a course label but no assignment title lookup or new Canvas request.
- Other job kinds retain generic safe titles but receive a plain-language aggregate summary
  and appropriate Continue/Review fallback action. Do not display raw namespaced `kind`
  values in normal Desk row text.
- The worktree is already dirty with unrelated staged and unstaged work, including batch 1
  and earlier Desk/Course Expert repairs. Preserve every unrelated hunk. Do not stage,
  unstage, commit, reset, branch, or reformat unrelated files.

## Scope

- Document the transient presentation sidecar as distinct from the exact persisted registry
  job contract.
- Add route-local presentation helpers and `GET /api/work` response projection.
- Supply the same presentation mapping to `pages.dashboard` for initial HTML/JSON.
- Render course label, semantic title, semantic summary, and specific link label in both the
  Jinja initial rows and `desk.js` refresh path.
- Add minimal Desk styling for the course label and readable three-line detail hierarchy.
- Add focused privacy, persistence-boundary, semantics, server-render, and browser-runtime
  regressions plus durable WebUI/reference documentation.

Expected insertion points:

- `docs/contracts/work-registry-contract.md` — add a transient presentation section; do not
  alter the exact registry job JSON shape
- `api/webui/routes/work.py::_all_jobs`, `_find_current`, and `get_work`
- `api/webui/routes/pages.py::dashboard`
- `api/webui/templates/dashboard.html`
- `api/webui/static/desk.js::renderJobList` and `refreshLocal`
- `api/webui/static/workbench.css` Desk job styles
- `api/tests/test_work_routes.py`
- `api/tests/test_desk_routes.py`
- `api/tests/test_webui_template_contracts.py`
- `api/webui/README.md` and `docs/reference/workbench-canonical-flow-map.md`

## Out of scope

- Canvas Inbox, assignment-comment notifications, polling cadence, OS notifications, or any
  new Canvas endpoint.
- Loading Canvas assignment names for detected grading-debt/late-work findings.
- Student names, message/comment previews, grades, per-student progress, or submission text
  anywhere on Desk.
- Changing registry version/schema, public job keys, validators, adapter job facts,
  fingerprints, material versions, discovery persistence, or suppression behavior.
- Changing PowerGrader sessions/queue formats or opening full session payloads for display.
- Per-course Desk grouping, sorting redesign, filtering controls, badges elsewhere in the
  app, or Prepared/Receipts redesign.
- Live Canvas probes/writes, AI calls, real settings mutations, full-suite runs, staging,
  commits, or unrelated cleanup.

## Reference pattern and routing

- Persisted contract: `docs/contracts/work-registry-contract.md`
- Exact generic projection: `api/work_registry/models.py::public_job`
- Local summary authority: `api/powergrader/session_store.py::list_session_summaries`
- Scheduled metadata authority: `api/powergrader/autoscore_queue.py::load_queue`
- Existing local adapter boundary: `api/work_registry/adapters.py::collect_local_jobs`
- Desk API/persistence seam: `api/webui/routes/work.py::_all_jobs` and `_find_current`
- Initial render: `api/webui/routes/pages.py::dashboard` and
  `api/webui/templates/dashboard.html`
- Browser render: `api/webui/static/desk.js::renderJobList`
- Test patterns: `api/tests/test_work_routes.py`, `api/tests/test_desk_routes.py`, and
  `api/tests/test_webui_template_contracts.py`
- Read project-local `TOOLS.md` before broad inspection. Repo-indexer and change-risk tools
  are currently planned rather than callable; use narrow `rg` searches.

## Implementation requirements

1. Separate raw jobs from presentation. A private raw-job collector may be introduced so
   `_find_current()` and completion persistence never receive the sidecar. Keep `jobs` in
   `GET /api/work` exactly valid under `validate_job()`/`public_job()` and place all enriched
   text only in the top-level `presentations` mapping.
2. Implement small route-local helpers that load Current-course labels, PowerGrader session
   summary assignment names, and scheduled queue assignment names/states. Catch unavailable
   workspace/authority errors and emit generic presentation rather than failing `GET /` or
   `GET /api/work`. Do not add a new registry adapter/module solely for presentation.
3. Build presentations only for returned/visible Current-scope jobs. Normalize counts to the
   existing non-negative integers and produce the locked semantic text/pluralization. Do not
   copy entire summary or queue dictionaries into the response.
4. Add `initial_presentations` to the dashboard context and initial JSON. Both Jinja and JS
   use sidecar values by job ID, with safe generic fallbacks if a presentation is absent.
   Render via Jinja escaping and browser `textContent`, never `innerHTML` with local labels.
5. Give the course label a visually subordinate but recognizable style. Preserve keyboard
   navigation, Ignore/Snooze/Complete behavior, layout at current breakpoints, and existing
   link destinations.
6. Add focused tests proving: exact job keys remain unchanged; the sidecar is separate and
   never persisted; a fictitious 24/22/2 session renders the locked sentence; course and
   assignment labels come from local summaries; scheduled/detected fallbacks are semantic;
   forbidden private fields from oversized fake summary/queue dictionaries are not copied;
   `_find_current()` has no presentation; initial and refresh rendering use the same fields;
   and Desk no longer displays raw kind plus “N items” for enriched jobs.
7. Update the durable contract/reference docs, self-review against this brief, record the
   compact result in this file, and archive the handoff if GREEN.

## Verification

Run only the focused matrix:

```powershell
py -m pytest api/tests/test_work_registry.py api/tests/test_work_routes.py api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py
node --check api/webui/static/desk.js
git diff --check HEAD
```

Rendered verification is required for `/` only:

- The real local page loads with zero new browser-console errors.
- A populated isolated route render proves a course label, assignment title, the
  `24 students · 22 awaiting review · 2 approved, not posted` sentence, and the specific
  action label appear together.
- Refresh rendering does not revert to raw kind/“items” text.
- Do not click Scan, Ignore, Snooze, Complete, or any navigation/action link during browser
  verification. Do not expose or record real course/assignment labels in the report.

Do not run the full API/engine suites unless a focused failure demonstrates unexpected
coupling. If browser control is unavailable, record the exact limitation as YELLOW after the
isolated render/runtime checks; the senior may close only that missing evidence.

## Stop conditions

Stop with RED rather than guessing if:

- Keeping enriched text out of exact jobs and persistence is not possible with the named
  seams.
- A named insertion point or assumed interface is missing.
- Assignment display requires opening full private sessions, scanning Canvas, or changing an
  authority schema.
- The work-registry exact job contract or version must change.
- Student identity/content, grades, comments, or other FERPA material would enter the sidecar,
  initial HTML, logs, fixtures, or persisted files.
- Preserving existing staged/unstaged work is not possible at an overlapping file.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **YELLOW** — implementation, privacy/persistence review, isolated
  render, browser-runtime, and focused verification are complete; the required
  real-page console check remains blocked before page load.
- Changes remain uncommitted; existing staging was not altered.
- Files changed: `api/webui/routes/work.py`, `api/webui/routes/pages.py`,
  `api/webui/templates/dashboard.html`, `api/webui/static/desk.js`,
  `api/webui/static/workbench.css`, `api/tests/test_work_routes.py`,
  `api/tests/test_desk_routes.py`, `api/tests/test_webui_template_contracts.py`,
  `docs/contracts/work-registry-contract.md`, `api/webui/README.md`,
  `docs/reference/workbench-canonical-flow-map.md`, and this handoff.
- Verification commands and pass/fail/skip counts: focused pytest matrix **38 passed,
  0 failed, 0 skipped**; `node --check api/webui/static/desk.js` **passed**;
  `git diff --check HEAD` **passed with line-ending warnings only**; real-browser
  console inspection **0 completed, 3 attempts unavailable/blocked** (the executor
  had no browser backend; the senior later had a backend but two fresh tabs were
  client-side denied before loading the local URL).
- Rendered route checked: a populated isolated `/` render passed with a fictitious
  course label, assignment title, `24 students · 22 awaiting review · 2 approved, not
  posted`, and `Review & post` in one row, with no raw kind/`24 items` text. A Node/VM
  runtime regression proved the same four presentation values survive the automatic
  `/api/work` refresh without reverting to raw kind/items text. The real local page was
  not inspected. The executor had no available browser backend. In senior closure,
  the in-app browser exposed a backend, but two fresh read-only tabs were both denied
  `http://127.0.0.1:8765/` by a client-side block before page load; both tabs were
  finalized. No Desk action or mutation occurred.
- Deviations from the brief: no implementation deviation. Browser availability was the
  only missing verification evidence; no live Canvas/settings mutation or real private
  label capture was used as a fallback.
- Remaining blocker or decision, if any: the browser client must permit the loopback
  Desk URL to load. Once it does, load `/`, confirm zero new console errors, and inspect
  without clicking any action. If that passes, the senior may mark this handoff GREEN
  and archive it without repeating the accepted implementation review or successful
  focused matrix.
