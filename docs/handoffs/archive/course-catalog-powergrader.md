# Execution brief: PowerGrader opens courses from a durable local catalog

Status: **GREEN — implemented and verified**

Risk: **medium**

Executor: **GPT-5.6 Terra**

## Outcome

When a teacher selects a Current course in PowerGrader, the assignment picker renders
immediately from the last good catalog in the configured synced workspace. Module switching
and assignment search remain local; Canvas refreshes the selected course in the background
without clearing usable local data or blocking unrelated teacher work.

This batch establishes one durable, student-data-free course metadata projection and gives
it one immediate consumer. It does not create a general CanvasSync product or migrate every
Canvas Expert caller in the same change.

## Locked decisions

- Implement one bounded vertical: **Course Catalog v1 plus the PowerGrader setup consumer**.
- Store one validated snapshot per Current course beneath
  `_System/Canvas Catalog/<course-id>/catalog.v1.json`, with
  `catalog.v1.previous.json` as the last-good fallback. Course ID, not display name, owns the
  directory identity.
- The catalog is a reconstructable private Canvas projection, not a cache of student data and
  not a source of truth for Canvas writes.
- One snapshot contains two independently refreshed scopes: `assignments` and `modules`.
  Each scope records `state`, `last_success_at`, `last_attempt_at`, a sanitized `error_code`,
  and `records`. Allowed states are `current`, `stale`, `incomplete`, and `unavailable`.
- Assignment records are keyed by stable Canvas assignment ID. Persist only an explicit
  allowlist: ID, name, normalized description text, points, due/unlock/lock/created/updated
  timestamps, published state, submission types, assignment-group ID, quiz/New Quiz
  classification, and rubric/rubric settings when the collection response supplies them.
- Do not persist raw Canvas responses, raw assignment HTML, user/enrollment/submission data,
  authorization material, signed URLs, transport URLs, private local paths, or arbitrary
  future Canvas fields.
- Module records preserve Canvas position and contain an ordered allowlist of module-item ID,
  type, title, position, and content ID. Do not persist module-item URLs.
- Refresh the complete assignment collection and module collection in parallel with narrowly
  bounded concurrency. Request inline module items via `include[]=items`; when Canvas omits
  them, fall back to the module-items endpoint with a small fixed concurrency bound. Do not
  fan out into one assignment-detail request per assignment.
- Merge scope results independently. A failed scope retains its previous records and becomes
  `stale`; without previous records it becomes `unavailable`. A partially acquired module
  scope is `incomplete`. A failed or empty response never erases last-good records.
- Validate the entire snapshot before every atomic write. Use temp file, flush, `fsync`, and
  `os.replace`. Preserve the previous validated canonical file before replacement. A corrupt
  canonical file is quarantined and the validated previous file is used when available.
- OneDrive-style competing catalog files are never merged, renamed, or deleted automatically.
  Return a warning while continuing from the validated canonical/previous snapshot; a later
  successful refresh may rebuild canonical state.
- Restrict catalog read/refresh routes to `config.active_courses()` (the Current-course
  boundary). Previous-course catalogs remain on disk and are not deleted by this batch.
- PowerGrader reads local data first. If a catalog exists, render it before starting one
  non-blocking refresh for that course per page session. If no catalog exists, perform the
  one-time initial refresh and render any successful scope. A refresh failure leaves the
  existing picker usable and visibly labeled as a local/stale copy.
- The existing default remains the last three modules in Canvas course order. Switching
  modules is local. Search is an in-browser filter across all catalog assignments using
  assignment name, normalized description text, and associated module names; it makes no
  Canvas request and requires no SQLite/FTS service.
- Add a clearly named course-level **Sync course list** action. Do not repurpose or rename the
  existing assignment-level **Refresh from Canvas**, which owns focused submissions/evidence.
- PowerGrader start, focused assignment refresh, New Quiz acquisition, submissions, evidence,
  grades/comments, and every pre-write/post-write verification remain unchanged and live.
- Retain `/api/assignments-full` and `/api/powergrader/modules` for compatibility and other
  consumers. Only PowerGrader setup stops using them in this batch.
- Work on `dev`, preserve unrelated work, update the active handoff's Execution result, and
  commit the completed GREEN implementation.

## Scope

- Add `api/course_catalog.py` as the single backend owner for v1 schema validation,
  normalization, atomic/previous/quarantine storage, conflict reporting, bounded Canvas
  acquisition, and independent scope merge.
- Add Course Catalog workspace-path helpers to `api/webui/workspace.py`.
- Add thin local-read and refresh routes in `api/webui/routes/course_catalog.py` and register
  that router in `api/webui/server.py`:
  - `GET /api/course-catalog?course_id=...` reads local disk only.
  - `POST /api/course-catalog/refresh` accepts `course_id`, performs read-only Canvas
    acquisition, persists the merged snapshot, and returns a PowerGrader-ready projection.
- Update `api/webui/static/powergrader/setup_core.js` to use the catalog routes, render local
  state before refresh, preserve selection across successful background refresh, ignore
  superseded course responses, search locally, and keep the current last-three-module view.
- Add minimal course-catalog status and **Sync course list** controls to
  `api/webui/templates/powergrader_setup.html` and the existing setup stylesheet if needed.
- Keep `api/webui/routes/powergrader.py` and
  `api/webui/routes/powergrader_setup_support.py` compatibility routes/helpers unless a thin
  response-shaping seam is needed; do not delete them.
- Add focused backend, route, browser-contract, and rendered-route coverage.
- Add `docs/contracts/course-catalog-contract.md` and update
  `docs/reference/powergrader-module-map.md`,
  `docs/handoffs/local-first-simplification-planning.md`,
  `docs/reference/local-first-execution-roadmap.md`, and `AGENTS.md` so the durable local-read
  authority and completed roadmap state are truthful.
- Archive the already-completed `docs/handoffs/new-quiz-item-finalization-v2.md` as part of
  this implementation/closure batch; preserve its content and Git history.

## Out of scope

- Student submissions, attempts, comments, grades, enrollments, roster, groups, attachments,
  New Quiz item results, or any other FERPA data in the course catalog.
- A new top-level CanvasSync/Course Sync page, global launch job, scheduler, adaptive request
  coordinator, SQLite database, full-text service, or cross-machine locking protocol.
- Background synchronization of every Current course. Refresh only the course selected in
  PowerGrader or explicitly synchronized there.
- Migrating Gradebook, Course Info, Create/Work tools, Work Registry, Automations,
  FeedbackExpert, or Settings to consume the catalog.
- Seeding/updating the catalog from successful operation-ledger writes.
- Assignment-detail N+1 acquisition, course files/pages, binary downloads, evidence backfill,
  cleanup of old catalogs/evidence, or retention UI.
- Removing or changing existing assignment/module endpoints, focused evidence manifests,
  PowerGrader session formats, or Canvas write safeguards.
- Live Canvas probes or production/student-data inspection. Tests use synthetic fixtures only.

## Reference pattern and routing

- Existing architectural decisions:
  `docs/handoffs/local-first-simplification-planning.md` and
  `docs/reference/local-first-execution-roadmap.md`
- Atomic validated workspace storage pattern:
  `api/work_registry/storage.py::_read`, `_atomic_write`
- Existing OneDrive conflict rule and atomic evidence write:
  `api/webui/workspace.py::assignment_evidence_conflicts`,
  `write_assignment_evidence_manifest`
- Current PowerGrader setup owner:
  `api/webui/static/powergrader/setup_core.js::loadAssignments`,
  `renderAssignmentOptions`
- Current module acquisition/shape:
  `api/webui/routes/powergrader_setup_support.py::load_module_picker`
- Current assignment normalization/quiz classification reference:
  `api/webui/routes/reports.py::list_assignments_full`
- Canvas client pagination:
  `api/webui/canvas_client.py::_canvas_get_all`
- Route registration:
  `api/webui/server.py`
- Browser and setup test patterns:
  `api/tests/test_powergrader_module_picker.py`,
  `api/tests/test_webui_template_contracts.py`, `api/tests/test_route_contract.py`
- Read project-local `TOOLS.md` before using broad manual inspection.

Do not read unrelated New Quiz transport, queue-write, FeedbackExpert, Gradebook, or
operation-ledger implementation files unless a named stop condition is reached.

## Implementation requirements

1. Define and test the v1 document validator and normalized allowlists before connecting
   Canvas acquisition. Reject unknown root/scope keys and invalid/mismatched stable IDs.
2. Implement per-course storage with canonical/previous fallback, corruption quarantine,
   conflict warnings, atomic replacement, and a small in-process per-course refresh lock.
   Locks and active request state remain memory-only.
3. Build a refresh function with injected Canvas callbacks for synthetic tests. Fetch the
   assignment and module scopes concurrently, follow pagination through the existing client,
   use inline module items with bounded fallback, merge each scope against last-good state,
   and persist one validated result.
4. Add Current-course-gated routes. The GET route must never contact Canvas. Responses must
   expose enough catalog and state data for PowerGrader without leaking paths or raw errors.
5. Cut PowerGrader setup over to local-first loading. Preserve existing startability and
   quiz-support classification, last-three-module behavior, selection safety, session-lane
   loading, AI estimate/start wiring, and the assignment evidence controls.
6. Search all local assignments by name, description text, and module name without network
   requests. Keep unsupported quiz labeling truthful.
7. Make stale/failure UI concise: local data stays enabled, status identifies the last-good
   timestamp/state, and an explicit sync action can retry. Do not add an app-wide spinner.
8. Update the durable contract, module map, roadmap/planning decision gate, and canonical
   project guidance in the same commit. Do not claim other CE consumers use the catalog yet.
9. Self-review the diff for secrets, student data, URLs, private paths, unsafe OneDrive
   behavior, accidental Canvas writes, compatibility endpoint removal, and scope expansion.

## Verification

Run focused tests only unless their failures reveal unexpected shared coupling:

```powershell
py -m pytest api/tests/test_course_catalog.py api/tests/test_powergrader_module_picker.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
```

New tests must cover at least:

- valid normalization and rejection of raw/unapproved fields;
- assignments/modules success, independent scope failure, first-sync partial result, and
  preservation of last-good records;
- inline module items and omitted-items fallback with bounded calls;
- no assignment-detail N+1 calls;
- canonical corruption fallback, previous corruption/unavailable behavior, atomic update,
  and OneDrive conflict warning without deletion;
- Current-course route gate and proof that GET is disk-only;
- local-first warm render, first cold refresh, background success/failure, explicit retry,
  rapid course switching, selection preservation, last-three modules, and network-free local
  search across name/description/module text.

Rendered verification is required on `/powergrader` using synthetic/safe course state:

- warm catalog selection renders before refresh completion;
- missing catalog performs the initial sync state honestly;
- failed background refresh leaves local assignments enabled;
- module selection and search work without new browser requests;
- course-level sync and assignment-level evidence refresh are visibly distinct;
- no new browser-console errors.

Do not run the full API or engine suites unless focused failures demonstrate broader coupling.

## Stop conditions

Stop with RED rather than guessing if:

- The Canvas assignment collection cannot supply the locked normalized context without an
  assignment-detail N+1 fan-out.
- Module-item omission cannot be distinguished from a legitimate empty module.
- Any proposed record would persist student data, credentials, signed/transport URLs, raw
  private paths, or unbounded raw Canvas payloads.
- Existing PowerGrader behavior requires changing focused evidence acquisition, New Quiz
  transport, session formats, or grade/comment write safeguards.
- Reliable atomic canonical/previous behavior contradicts the configured OneDrive workspace
  semantics or requires a distributed-lock protocol.
- A generalized scheduler, database, adapter registry, or migration of another subsystem is
  required to make the PowerGrader consumer work.
- A regression is discovered outside the authorized scope.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — the brief is complete, the focused matrix passed, and rendered
  synthetic acceptance found no browser-console errors.
- Commit hash: **the commit containing this finalized execution result; exact hash is reported
  at handback**.
- Files changed:
  - `AGENTS.md`
  - `api/course_catalog.py`
  - `api/tests/test_course_catalog.py`
  - `api/tests/test_route_contract.py`
  - `api/tests/test_webui_template_contracts.py`
  - `api/webui/routes/course_catalog.py`
  - `api/webui/server.py`
  - `api/webui/static/powergrader/setup_core.js`
  - `api/webui/static/powergrader_setup.css`
  - `api/webui/templates/powergrader_setup.html`
  - `api/webui/workspace.py`
  - `docs/contracts/course-catalog-contract.md`
  - `docs/handoffs/new-quiz-item-finalization-v2.md` moved unchanged to
    `docs/handoffs/archive/new-quiz-item-finalization-v2.md`
  - `docs/handoffs/local-first-simplification-planning.md`
  - `docs/reference/local-first-execution-roadmap.md`
  - `docs/reference/powergrader-module-map.md`
  - this execution brief
- Verification:
  - `py -m pytest api/tests/test_course_catalog.py api/tests/test_powergrader_module_picker.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py`
  - **38 passed, 0 failed, 0 skipped**.
  - `git diff --check` passed; only repository line-ending notices were emitted.
- Rendered route checked: `/powergrader` against a fresh synthetic-only workspace with empty
  session summaries and fictional warm/cold courses. Verified:
  - warm catalog assignments rendered enabled before the delayed refresh completed;
  - the last-three-module default showed only assignments 2–4 and excluded assignment 1;
  - a failed background refresh retained enabled local assignments with honest stale status;
  - description and module-name searches found the older assignment locally;
  - clearing search and switching to one module changed the picker without a request;
  - request counts stayed at one catalog GET plus one refresh POST through search/module
    interactions, with zero legacy `/api/powergrader/modules` requests;
  - a cold course showed the initial syncing state, then rendered its assignment/module after
    one GET plus one POST;
  - **Sync course list** and assignment-evidence **Refresh from Canvas** were visibly distinct;
  - browser console error log was empty.
  The temporary harness was removed and its server stopped after verification.
- Deviations from the brief: the frozen route-contract list also gained the two already-live
  New Quiz review/finalize routes that predated this work; this was required to make the
  contract truthful and did not change product behavior. No implementation-scope deviation.
- Remaining blocker or decision: **none**.
