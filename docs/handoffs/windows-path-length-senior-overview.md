# Windows path-length recovery — PowerGrader teacher-output slice

**Status:** CURRENT direct execution brief  
**Executor:** one implementation agent  
**Branch:** `fix/windows-long-path-writes` at `8fb781b42c39fe6db52c2677991b3e04d319ebc9`  
**Base:** `dev` at `e646d9f70df4b464ccd6e15ddc0e8b870d573a4e`

This replaces the senior overview. It is the only execution authority in
`docs/handoffs/`; do not create a second brief or split this work among agents.

## Objective

Make the complete teacher-facing PowerGrader packet path work in a deep Windows
OneDrive workspace without writing files that Explorer, file pickers, or the
local **Open folder** actions cannot use. The path is:

1. create a packet or assisted session with long fictional course and assignment
   labels;
2. create the SAFE artifacts, legacy packet folder/ZIP, and packet-mode Copilot
   batches;
3. open each returned folder through `/api/open-path`; and
4. download the legacy ZIP.

At the same boundary, restore resolved-target source-material containment and
keep unhandled API failures JSON without exposing raw internal errors.

## Locked senior decisions

1. **Teacher-visible budget:** every returned/generated teacher-facing PowerGrader
   path has `len(os.path.abspath(path)) <= 230`, measured on the ordinary,
   unprefixed absolute Windows path and including every separator, file name, and
   extension. `230` deliberately leaves 30 characters below the legacy 260
   boundary for Explorer/file-picker interoperability. It is a product budget,
   not a promise that Python's extended-path APIs can rescue a longer public path.
2. **Fallback:** keep `workspace.extended_path()` only for existing/user-owned
   deep inputs and internal machine-owned I/O. Do not return `\\?\` or
   `\\?\UNC\` values in session metadata, API payloads, or UI attributes.
   Do not lower/retarget its existing general threshold in this slice.
3. **Small immediate API:** add one `workspace` helper named
   `teacher_visible_path(...)`. It accepts an absolute base, ordered fixed or
   identity-bearing components, an optional final filename, and projected
   reserved suffix components. It projects the *complete* ordinary path before
   writing; it shortens only readable portions of identity-bearing components,
   preserves their Canvas ID or deterministic short hash, and raises a dedicated
   path-budget exception when even the compact form cannot fit. Do not introduce
   a filesystem wrapper, registry, persistence format, or adapter layer.
4. **Normal then compact packet layout:** retain the current readable packet
   folder and descriptive Copilot file names when the full projected layout fits.
   When it does not, use the compact, deterministic layout below. The compact
   packet component must contain a stable assignment identifier (a safe Canvas
   assignment ID or deterministic short hash), not a lossy truncation.

   | Item | Compact name |
   | --- | --- |
   | Packet folder | `Packet-<stable-id>` |
   | Copilot container | `Batches` |
   | Batch folder | `Batch-<index>` (no total-count text) |
   | Upload files | `01-info.md`, `02-rubric.md`, `03-work.md` |

   Packet contents stay ordered and teacher-readable; the containing stable
   packet/batch folders provide the identity that the repeated assignment label
   used to provide. `<stable-id>` is a deterministic eight-or-more-character
   assignment-ID hash, extended deterministically on a collision. The normal
   layout stays readable-first. The compact layout
   must be selected before any packet/batch directory is made, and its projected
   deepest file must include the actual batch index and extension. No collision
   suffix or atomic temporary name exists in this particular packet writer; do
   not invent one. The new helper's reserved-suffix parameter is required so the
   next writer can supply such headroom explicitly.

   In the same compact mode, SAFE/private leaf names are `bundle.json`,
   `how-to-score.txt`, `context.txt`, `private.json`, and `who-is-who.csv`.
   SAFE student text is `s-<pseudonym-hash>.txt`; SAFE derivative media is under
   `S/<pseudonym-hash>/<item-hash>-<index>.<ext>`. Hashes use the same
   deterministic collision-extension rule. Keep today's descriptive names in
   the normal layout. Returned dictionaries, not filename guessing, remain the
   compatibility contract between these writers and their callers.
5. **Workspace too deep:** when the configured root plus fixed hierarchy and the
   compact PowerGrader layout cannot preserve the stable identifier within 230,
   stop before producing SAFE/packet/Copilot output. Return the teacher-safe
   message: `This workspace location is too deep for PowerGrader packet files.
   Choose a shorter workspace location, then try again.` Do not disclose the
   actual path, silently drop identity, move/rename existing content, or fall
   back to an extended-length public path. No external AI request or Canvas write
   may occur on this failure.
6. **Existing unmerged work:** make one additive follow-up commit on the current
   branch; do not amend, reset, rebase, merge, or delete `8fb781b`. The senior
   will decide integration into `dev` after accepting this slice.
7. **No new reference document:** the helper's docstring and focused tests are
   the immediate consumed policy. Do not add a speculative path-policy document.

## Exact scope and insertion points

Read `AGENTS.md`, this brief, and only these exact reference sections before
editing:

- `api/webui/README.md` — **Rendered verification (read-only)**,
  **PowerGrader module routing**, and **PowerGrader (`/powergrader`)**.
- `docs/reference/powergrader-module-map.md` — **Entry points**, **Ownership
  routes**, **Privacy and write boundaries**, **Symptom routing**, and **Test
  routing**.

Modify only the following implementation/test owners unless a stop condition is
met:

- `api/webui/workspace.py` — `teacher_visible_path`, its dedicated exception,
  identity-preserving shortening, and the PowerGrader-specific reservation
  plumbing in `ai_run_folder` / `assignment_folder`. Leave unrelated
  `bounded_join` callers and `extended_path` policy alone.
- `api/powergrader/privacy.py::feedback_artifact_dirs` — pass the complete
  PowerGrader child-layout reserve while constructing SAFE and PRIVATE homes;
  propagate the dedicated budget exception to the workflow boundary.
- `api/powergrader/ai_workflow.py::run_ai_workflow` and
  `api/powergrader/ai_workflow_support.py::build_privacy_artifacts` — turn that
  exception into the locked safe failure before `write_safe_and_private` or an
  external request; keep the existing result/session keys and store only plain
  paths.
- `api/feedback_artifacts.py::write_safe_and_private` and its
  `_prepare_attachment_safe_bundle` call — use the selected bounded directory
  layout/leaf-name limits, including SAFE student media, rather than relying on
  an extended-path write to make a public artifact. Do not alter scrub, vault,
  or SAFE-versus-PRIVATE semantics.
- `api/powergrader/student_attachments.py::write_safe_derivatives` — consume the
  compact SAFE media leaf names supplied by the artifact writer; preserve media
  validation and returned metadata shape.
- `api/powergrader/packet.py::{safe_ai_packet_name, packet_paths,
  build_safe_ai_packet}` — select the normal or compact packet component before
  creation and validate all legacy packet children and ZIP paths against the
  budget. Pass the assignment stable ID through the real workflow; retain
  backwards-compatible optional parameters for direct library callers only when
  they can still meet the budget.
- `api/powergrader/copilot_packet.py::build_copilot_batches` and
  `api/powergrader/copilot_packet_support.py::write_text` — consume the chosen
  packet folder, build normal or compact batch/file names before directory
  creation, and validate every batch file path. Do not change batch splitting,
  prompts, result matching, or import schema.
- `api/webui/routes/pages.py::{_allowed_open_roots,api_open_path}` and
  `api/webui/routes/powergrader.py::pg_download_packet` — resolve/check old deep
  paths through the extended fallback for containment/read purposes, but only
  invoke Explorer/open actions for a plain, allowed, teacher-visible path.
  Return a fixed safe error for a too-deep legacy path or opener failure; never
  return `str(exception)`. Preserve ZIP download's existing basename and headers.
- `api/webui/source_materials.py::_resolve_folder_file` — resolve the root and
  selected candidate through a long-path-safe canonical helper, compare resolved
  targets with Windows case-insensitive containment, and return/read the
  resolved in-tree target. Lexical `abspath/commonpath` alone is insufficient.
- `api/webui/server.py::_api_errors_return_json` and
  `api/webui/static/powergrader/setup_core.js::{renderStartError,bindStartSession}`
  — preserve parseable JSON and the local printed traceback, but send/show a
  fixed generic server error. Do not expose an exception type, message, absolute
  path, student detail, setting, or credential.
- Tests: extend `api/tests/test_workspace.py`,
  `test_powergrader_packet.py`, `test_powergrader_copilot_packet.py`,
  `test_powergrader_attachment_workflow.py`, `test_source_materials.py`, and
  `test_api_error_contract.py`; add one focused
  `api/tests/test_powergrader_path_budget.py` only if the existing owners cannot
  contain the cross-owner end-to-end path assertions. Update
  `test_route_contract.py` only if its existing route declaration assertion
  genuinely changes.

Do not modify `api/storage_support.py`, `api/report_local_reads.py`,
`api/course_catalog.py`, `api/powergrader/assignment_refresh.py`, mirror code,
Operation Ledger code, Canvas write policy, or any other output surface. They
are later seams, not permission to broaden this slice.

## Required behavior and acceptance criteria

All tests use fictional names/IDs only and derive all roots from `tmp_path`.
Do not use a developer path, a real workspace, credential, Canvas call, or
external AI request in a test.

1. Build the complete packet workflow under a synthetic absolute root
   padded to **80 characters**, with 120-character fictional course and
   assignment labels, stable IDs `course-1000001` and `assignment-1000002`, a
   fixed session timestamp, and a multi-batch fictional bundle. Assert every
   returned SAFE, PRIVATE, legacy packet, ZIP, Copilot folder, batch folder,
   upload file, and returned metadata path is plain and at most 230 characters.
   This root must exercise the compact fallback: assert its compact folders and
   files use exactly the locked names above, read every artifact, and open the
   ZIP to confirm its expected entries.
2. Under a short synthetic root, assert the readable normal layout and existing
   packet/session metadata behavior remain compatible with current callers. Two
   distinct 120-character assignment names sharing their readable prefix but
   having different stable IDs must produce distinct, deterministic compact
   paths.
3. A root constructed so that even the compact deepest path exceeds 230 raises
   the dedicated exception before a directory/file is written. At the workflow
   boundary it returns exactly the locked safe message and makes neither an
   external-AI call nor a Canvas write.
4. The actual `/api/open-path` route accepts an allowed, returned compact packet
   folder and compact batch folder after `_open_in_os` is mocked, and calls the
   mock with an ordinary (unprefixed) path. A legacy `>230` or prefixed public
   value is rejected with a fixed safe error. The download endpoint can read a
   legacy `>260` ZIP through the fallback but its downloadable filename and any
   metadata remain plain.
5. A Source Materials file whose resolved symlink/junction target lies outside
   Source Materials is rejected. A genuinely `>260` in-tree file is accepted
   and read through the long-path-safe canonical path. The test may skip only
   when Windows explicitly denies test-symlink creation; record that exact
   platform limitation in the execution result.
6. A simulated unhandled `/api/` exception returns JSON with `ok: false` and a
   generic teacher-safe error. Its body contains neither a unique exception
   message nor a fictional private absolute path. Non-API behavior and local
   traceback printing remain unchanged. The PowerGrader start UI displays the
   returned generic message and its network-failure fallback does not stringify
   low-level exception text to the teacher.
7. No returned/session/API path contains an extended-path prefix. No Canvas
   mutation, Canvas fetch, external AI request, auto-post, routine, or real
   session start occurs during the focused test or rendered verification.

## Preflight, named gate, and rendered verification

Before writing, run:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
py -m pytest api/tests/test_workspace.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_source_materials.py api/tests/test_api_error_contract.py api/tests/test_route_contract.py
```

Proceed only when the branch is `fix/windows-long-path-writes`, `HEAD` is
`8fb781b42c39fe6db52c2677991b3e04d319ebc9`, and the only pre-existing change is
this current handoff file. Otherwise stop RED; do not absorb unrelated work.

The focused acceptance gate after implementation is:

```powershell
py -m pytest api/tests/test_workspace.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_attachment_workflow.py api/tests/test_source_materials.py api/tests/test_api_error_contract.py api/tests/test_route_contract.py api/tests/test_powergrader_path_budget.py
```

If no new cross-owner file is needed, remove only the final nonexistent test
argument and report where those assertions live. Do not substitute the full API
suite for this gate.

Then start the read-only server and use an existing locally configured, already
saved **fictional/test** PowerGrader session if one is available. Do not create a
session, enter credentials, or make a Canvas request merely to render it.

```powershell
cd api
py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

At 1440×900, load `/powergrader` and its existing queue route
`/powergrader/session/<existing-test-session-id>`. Confirm each route has no
horizontal document overflow, required `CE_POWERGRADER_SETUP` or
`CE_POWERGRADER_QUEUE` global appears once in template load order, and the
browser console has zero new CanvasExpert errors/warnings. On the queue route,
click the packet-folder and Copilot-batch-folder actions only when they point to
the fictional local test artifacts; confirm the generic UI error is readable for
a rejected deep legacy path. Do not capture student content, path values, or
screenshots in the report. If onboarding/configuration or no suitable fictional
session prevents this read-only check, return YELLOW with that exact limitation;
do not alter the credential store or substitute source-text assertions.

## Non-goals

- No Canvas mutation, grade/comment/auto-post policy, operation-ledger behavior,
  or external AI behavior change.
- No OS registry setting, `LongPathsEnabled` dependency, installation, PATH
  change, elevation, or tunnel.
- No rename, move, or deletion of teacher-owned source material or existing
  workspace content.
- No broad filesystem-call conversion or new general storage abstraction.
- No claims that SAFE/pseudonymized material is anonymous or FERPA safe.

## Stop conditions

Return **RED** rather than guessing if any of these occur:

- The compact layout cannot keep a stable ID in a 230-character ordinary path.
- A needed normal/compact leaf name, attachment derivative, or session metadata
  requires an unapproved format/schema change.
- Secure resolved-target source containment cannot be preserved for a deep
  in-tree file.
- The change alters Operation Ledger atomicity, Canvas writes, or a non-scoped
  artifact surface.
- Preflight truth differs from the stated commit/branch/worktree condition.
- The rendered check exposes a browser error caused by this slice that cannot be
  fixed inside the listed scope.

## Execution result

**Traffic light:** pending  
**Commit:** pending  
**Changed files:** pending  
**Preflight / gate:** pending  
**Rendered verification:** pending  
**Deviations:** pending  
**Unresolved senior decisions:** pending
