# Execution brief: focused assignment refresh owns shared local evidence

Status: **ready for implementation**

Risk: **high**

Executor: **Luna**

## Outcome

Starting a PowerGrader session for an assignment performs one focused Canvas refresh and
opens the session from a canonical private assignment-evidence record.  Unchanged current
attempts and files are reused; only missing or changed evidence is materialized, and the
teacher can see whether the assignment evidence is current, incomplete, stale, or
unavailable.  This establishes one local evidence owner before the duplicate Download Work
workflow is retired in the next batch.

## Locked decisions

- The durable record is a private, versioned assignment-evidence manifest below the
  canonical `Courses/<course>/Assignments/<assignment>/` tree.  It is the immediate
  PowerGrader-session input; it is not a general offline Canvas database or a new public
  contract.
- A valid manifest records `course_id`, `assignment_id`, refresh time/status, the Canvas
  assignment change indicators available in the response, and per-observed-attempt evidence
  identity.  Per evidence record includes the student/user identity, submission identity when
  Canvas supplies one, attempt identity, Canvas object/file or New Quiz item/result identity,
  content/change indicators, canonical relative path(s), and explicit acquisition state.
  Missing identity is `incomplete` or unsupported; filenames never prove identity.
- The manifest is atomically replaced only after its referenced evidence has been finalized.
  It must contain no token, authorization header, signed URL, or raw transport error.
- OneDrive conflicts are fail-closed: never merge conflicting manifests or evidence, never
  delete/rename an existing teacher file, and never select a winner from competing records.
  Detect a conflicting manifest for the same assignment, preserve it, and report the scope as
  `incomplete` until a new focused refresh can establish a clean record.  Queues, locks,
  `.partial` files, retries, and conflict-resolution state remain machine-local.
- Retain every attempt observed after this feature lands.  Do not backfill earlier history;
  a later Canvas attempt becomes current, while already observed attempts and their evidence
  remain untouched.  Legacy/unmanaged evidence is compatibility-read only and is not renamed
  or deleted.
- New managed ordinary-upload paths are deterministic from Canvas identity and attempt, not a
  filename collision suffix.  Reuse a finalized managed file only when its complete identity
  and available content indicators match; materialize a changed object separately without
  modifying legacy files.
- The focused-refresh binary budget is **10 MiB total per assignment refresh**
  (`10 * 1024 * 1024` bytes), including all ordinary and New Quiz file downloads.  Each file
  must have a declared size and fit within the remaining budget before downloading.  Size-less,
  oversized, or over-budget files are not streamed; record them as incomplete evidence with an
  honest Canvas-native-review reason.  There is no binary prefetch at application launch.
- Assignment body/text, URL submissions, ordinary uploads, and the current New Quiz attempt
  are in scope.  A failed report, attempt join, file download, missing identity, or skipped
  binary makes the relevant evidence—and therefore the assignment manifest—`incomplete`;
  do not describe it as a complete snapshot.
- PowerGrader keeps its private session/review/AI/write authority.  Session creation reads the
  shared evidence record and records its manifest reference and completeness; it no longer
  owns an independent general evidence acquisition copy.  Existing pre-write Canvas checks
  remain live and unchanged.

## Scope

- Add a small focused-refresh owner in `api/powergrader/`, using the proven read and file
  routing behavior in `canvas_fetch.py`, `new_quiz_fetch.py`, and `student_attachments.py`.
- Add canonical assignment-evidence manifest path, safe read/write, conflict detection, and
  deterministic managed-evidence path helpers to `api/webui/workspace.py` (or a narrowly
  routed helper next to it).  Keep all records under the existing private workspace roots.
- Route `api/webui/routes/powergrader.py::pg_start` through that owner, then build the session
  from the returned local evidence.  Record the manifest reference and scope status in the
  session through `api/powergrader/session_builder.py` / `start_workflow.py` as appropriate.
- Preserve existing attachment eligibility and New Quiz failed/unsupported states.  Expand
  focused synthetic tests rather than introducing fixtures with real course data.
- Update `docs/reference/powergrader-module-map.md` only if the new owner changes durable
  file ownership or the normal start path.

## Out of scope

- No all-course or application-launch synchronization, background coordinator, roster sync,
  historical attempt backfill, or general offline Canvas store.
- No New Quiz scoring/feedback writes, scheduled scoring/auto-push changes, or grade/comment
  write changes.
- Do not retire Download Work, `api/downloader.py`, routes, routines, templates, or browser
  UI in this batch.
- Do not add a portable export feature, change legacy workspace folders, migrate existing
  evidence, merge OneDrive conflicts, or probe/live-write Canvas.
- Do not add a broad registry, adapter framework, or cross-machine authority model.

## Reference pattern and routing

- Existing implementation to follow: `api/powergrader/canvas_fetch.py::fetch_submissions` and
  `::ingest_ordinary_attachments`; `api/powergrader/new_quiz_fetch.py::fetch` and
  `::_download_item_files`; `api/powergrader/student_attachments.py::ingest_local_file`.
- Workspace ownership pattern: `api/webui/workspace.py::assignment_folder`,
  `::attempt_folder`, `::bounded_join`, and `::path_within_workspace`.
- Session-start insertion point: `api/webui/routes/powergrader.py::pg_start` (the fetch at
  lines 229–269 and `session_builder.build_students` at lines 320–328).
- Test pattern: `api/tests/test_powergrader_attachment_workflow.py`,
  `api/tests/test_powergrader_new_quizzes.py`, and `api/tests/test_workspace.py`.
- Required durable references: `AGENTS.md`, `TOOLS.md`,
  `docs/handoffs/local-first-simplification-planning.md`,
  `docs/reference/local-first-execution-roadmap.md` (Luna 1), and
  `docs/reference/powergrader-module-map.md`.

Read project-local `TOOLS.md` before broad inspection.  The listed project tools are planned;
use targeted `rg` and the routed files when they are unavailable.

## Implementation requirements

1. Create one cohesive refresh API that reads the target assignment and submissions, normalizes
   ordinary/New Quiz current-attempt evidence, evaluates the existing manifest, and returns a
   URL-free local evidence payload plus manifest reference/status.  Keep Canvas tokens, signed
   URLs, and credentials memory-only.
2. Implement the minimal manifest schema and safe atomic persistence.  Validate the assignment
   identity before consuming a manifest; reject malformed, mismatched, conflicting, or missing
   managed evidence as `incomplete` rather than guessing.  Use relative paths in durable
   records and revalidate that resolved paths remain in the configured workspace.
3. Make ordinary and New Quiz file materialization reuse evidence only after exact
   identity/attempt/content-indicator checks.  Apply the locked 10 MiB aggregate budget before
   each download; preserve errors/skips in the returned evidence and manifest without signed
   URLs.  Retain the existing transport security boundaries (including off-host credential
   stripping and HTTPS-only signed-file handling).
4. Make `pg_start` obtain its submission payload from the refresh owner and attach the returned
   manifest reference/status to the saved session.  Existing AI, privacy, review, and write
   flows must continue to receive the same necessary local submission shape; no duplicate
   ordinary attachment ingestion may remain on the start path.
5. Add concise teacher-facing status in the existing PowerGrader start response only if the
   route already has a suitable surface.  Do not add a new dashboard or expose student names,
   evidence paths, signed URLs, or private error detail in generic UI/logging.
6. Keep docs truthful if an owning module is added.  Before handback, record the completed
   execution result below and commit the complete brief implementation on `dev` if the normal
   worktree state permits it.

## Verification

```powershell
py -m pytest api/tests/test_powergrader_attachment_workflow.py api/tests/test_powergrader_new_quizzes.py api/tests/test_workspace.py
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_route_contract.py
git diff --check
```

Add focused synthetic coverage for unchanged managed-evidence reuse, changed evidence creating
one deterministic new managed object, partial download/report failure, 10 MiB boundary and
over-budget skip, retained observed attempts, manifest identity validation, OneDrive conflict
fail-closed behavior, and the absence of a second start-path acquisition.  Use synthetic IDs
only; do not perform live Canvas reads/writes for verification.

Run the local app and render `/powergrader`: select a course/assignment and start a Grade
Myself session.  Confirm the start response/session scope state is coherent, existing setup
globals remain available, and the browser has zero new console errors.  Do not place real
student evidence in screenshots, logs, or the repository.

## Stop conditions

Stop with RED rather than guessing if:

- A Canvas response cannot supply enough identity to distinguish assignment, student, attempt,
  and evidence object without filename inference.
- The current ordinary or New Quiz transport cannot provide the locked change/identity checks
  without changing an external or public contract.
- Safe OneDrive conflict handling requires merging records, a distributed lock, a new
  cross-machine authority service, or deletion/renaming of existing evidence.
- The 10 MiB policy cannot be enforced before an unbounded transfer or contradicts the required
  current New Quiz/ordinary evidence behavior.
- Implementing the shared refresh requires a grade/comment write, credential persistence,
  external AI transmission, a broad synchronization system, or an unauthorized migration.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **YELLOW**
- Commit hash: pending executor commit
- Files changed: `api/powergrader/assignment_refresh.py`, `canvas_fetch.py`,
  `new_quiz_fetch.py`, `session_builder.py`, `start_workflow.py`,
  `api/webui/workspace.py`, `api/webui/routes/powergrader.py`,
  `powergrader_helpers.py`, focused attachment/workspace tests, and the PowerGrader module map.
- Verification: `py -m compileall -q api/powergrader api/webui` passed; focused attachment/New Quiz/workspace suite passed **35** tests; packet/Copilot/import/route-contract suite passed **14** tests; `git diff --check` passed.  `GET /powergrader` returned **200** from the local app.
- Rendered route: `/powergrader` was served locally. Browser-console verification is unavailable because this environment has no controllable browser binding; no real course or student evidence was used.
- Deviations: none in implementation scope. The managed evidence directory uses the immutable assignment ID as its readable component so it can be located before and after the authoritative assignment title response.
- Remaining blocker: rerun the required rendered setup/start check with a controllable browser and confirm zero new console errors before accepting GREEN.
