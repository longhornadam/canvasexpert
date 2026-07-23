# Workspace v2 restructure — implementation spec

Status: approved for implementation (2026-07-22). Planner: Claude. Implementer: Codex.

## Why

The sync folder grew by subsystem, not by teacher intent. Folder names describe what
the code did ("Exports", "Courses", "Inbox") rather than what the teacher does next,
and the flat authoring folders never reflected CE's own "Library" concept. The result
was ambiguous names and the long-path budget pressure that prompted this work.

v2 organizes the top level by two things only: the teacher's own nouns, and the one
privacy boundary that has real consequences (real names vs. no real names). Lifecycle
and status stay out of the tree; they are UI/metadata concerns.

## Ground rules

- **Clean break, no migration.** Current sync data is disposable. Do not preserve,
  rename, move, or read legacy folders. Delete the legacy-compat layer outright.
- **One risky idea per slice.** This transition is a pure restructure. The sync-vs-local
  relocation of `_System` (moving rebuildable Mirror/Catalog/logs out of OneDrive) is a
  separate follow-up slice, not part of this work.
- **Name each folder for its reader.** Teacher-facing folders optimize for reading
  (nicknames, titles, minimal IDs). Machine-facing paths optimize for identity (IDs).

## Locked folder names (the contract)

| Teacher concept | Folder |
| --- | --- |
| The Library: reusable collections the teacher authors or keeps | `Library/` |
| Assistant-staged drafts waiting for the teacher to push to Canvas | `To Review/` |
| Outputs to print or photocopy (PDF/DOCX) | `Printables/` |
| Canvas import packages (QTI / `.imscc`) | `Canvas Uploads/` |
| Downloaded student work + derived reports (REAL names, private) | `Student Work/` |
| Pseudonymized packets to hand to an external AI (no real names) | `For AI/` |
| Machine-owned state, not for human browsing | `_System/` |

Two rules a teacher can read straight off the tree: real names live only in
`Student Work/`; `For AI/` is the pseudonymized counterpart that is safe to send out.

## The v2 tree

```
CanvasExpert/
├─ Library/
│  ├─ Quizzes/
│  ├─ Rubrics/
│  ├─ Assignments/
│  ├─ Pages/
│  ├─ Calendars/
│  ├─ AI-TA/               generated paste-ready assistant instructions
│  ├─ Source Materials/
│  └─ Seating Charts/      reserved; add when the feature ships
├─ To Review/
│  ├─ Quizzes/
│  ├─ Assignments/
│  ├─ Pages/
│  └─ Rubrics/
├─ Printables/
├─ Canvas Uploads/
├─ Student Work/
│  ├─ Submissions/         downloaded evidence, course-first (matches download flow)
│  ├─ Reports/             derived reports + portfolios, student-first (matches portfolio flow)
│  └─ Grading Keys/        who-is-who crosswalks + unscrubbed PRIVATE copies
├─ For AI/
└─ _System/
   ├─ Identity Vault/
   ├─ PowerGrader/         Sessions/, Jobs/
   ├─ Audits/
   ├─ Archive/
   ├─ Canvas Catalog/
   └─ Canvas Mirror/
```

Sub-shelf names under `Student Work/` (`Submissions` / `Reports` / `Grading Keys`) are the
current best proposal; confirm against `portfolio_service.py` and `report_local_reads.py`
layouts during Layer 4 and adjust if a shelf name clashes with existing readers.

## Layers

Sequencing: Layer 1+2 in lockstep, then 3, then 4+5, then 6. Layer 7 tests land
alongside each layer, not at the end.

### Layer 1 — `api/webui/workspace.py` (source of truth)
- Rewrite constants block (lines ~26-48): replace flat `WORKSPACE_SUBFOLDERS` with the
  `Library/` subtree; rename `COURSES_NAME` → `Student Work`; `AI_PACKETS_NAME` → `For AI`;
  fold `STUDENT_REPORTS_NAME` into `Student Work/Reports`; add `Printables`,
  `Canvas Uploads`, `To Review`.
- Rewrite `ensure_workspace()` (line ~611) to build the v2 tree.
- Repoint path helpers: `course_folder`, `assignment_folder`, `student_folder`,
  `attempt_folder`, `ai_packet_folder`, `ai_run_folder`, `ai_student_folder`.
- Delete legacy layer: `legacy_feedback_root`, `feedback_folder`, `feedback_root`,
  `FEEDBACK_NAME`, `FEEDBACK_SUBFOLDERS`, `LEGACY_FEEDBACK_NAME`.
- Rewrite the workspace README seed text (line ~598) for the v2 names.
- Keep `named_id_folder`, `teacher_visible_path`, `bounded_join`, and the length budgets.
  Re-verify the 230-char budget math: shorter roots return headroom, so confirm the
  compact-fallback path still triggers only when genuinely needed.

### Layer 2 — `api/runtime_paths.py` (second source of truth)
- Split `exports_dir()` into `printables_dir()` and `canvas_uploads_dir()`.
- `_KIND_WORKSPACE_NAMES` / `content_folders()` → `Library/{kind}`.
- `inbox_folder()` → `To Review/{kind}` (keep the marker-gate behavior).
- `ai_ta_dir()` → `Library/AI-TA`.
- Decide the fate of the app-root fallbacks (`DropZone`, `Finished_Exports`) and the
  `qf_materials` example folders; keep them only if still used as read sources.

### Layer 3 — Exports split (behavioral, verify end to end)
The one change that is more than a rename. Route by artifact type:
- `engine/rendering/canvas/canvas_packager.py` QTI output → `Canvas Uploads/`
- `engine/rendering/correction_doc/*` DOCX/PDF output → `Printables/`

`engine/packaging/folder_creator.py` receives `output_dir` as an argument, so the split
is decided by the ~3 callers (pages route, powergrader, orchestrator). Trace each caller,
pass the correct destination, and verify a real quiz run lands QTI and print docs in the
right roots.

### Layer 4 — Student + AI-packet trees
- `Courses` + `Student Reports` + who-is-who → `Student Work/` (`Submissions`/`Reports`/
  `Grading Keys`). Preserve course-first for submissions, student-first for reports.
- Fix the nickname inconsistency: `api/webui/routes/reports.py` passes raw course names;
  switch it to the Settings nickname that PowerGrader already uses via
  `config.course_display_name()`.
- `AI Packets (Pseudonymized)` → `For AI/` across `api/powergrader/packet.py`,
  `api/powergrader/copilot_packet.py`, and the three `ai_*_folder` helpers.
- Keep the SAFE/PRIVATE split intact: SAFE packet → `For AI/`; unscrubbed PRIVATE copy +
  who-is-who → `Student Work/Grading Keys/`. The crosswalk never enters `For AI/`.

### Layer 5 — `_System` consolidation
- Confirm vault, PowerGrader Sessions/Jobs, Audits, Archive, Canvas Catalog, Canvas Mirror
  all resolve under one `_System/`.
- Fix the `_System` vs `_system` case mismatch (work_registry uses the lowercase form) so
  there is one spelling everywhere.
- Do NOT relocate anything out of OneDrive here; that is the follow-up slice.

### Layer 6 — Frontend, templates, docs, seeded content
- Templates naming folders: `settings.html`, `student_reports.html`, `course_expert.html`,
  `about.html`, `welcome.html`, `powergrader_setup.html`.
- JS: `welcome.js`, `settings/calendars.js`; audit `push/*.js` to separate folder-name
  refs from `targetCourses` (the Canvas concept, not the folder).
- Seeded `default_docs/AI-TA/*` instructions that name folders.
- `docs/reference/*` maps and `docs/contracts/work-registry-contract.md`.

### Layer 7 — Tests (acceptance)
Update and treat as the acceptance gate: `test_workspace`, `test_inbox_files`,
`test_inbox_files_route`, `test_report_local_reads`, `test_powergrader_packet`,
`test_app_context_contract`, `test_webui_template_contracts`, `test_source_materials`,
`test_mirror_store`, `test_mirror_new_quizzes`, and engine `test_full_migration` /
`test_orchestrator_manual`.

## Blast radius (measured 2026-07-22)
- Folder-name constants: ~40 refs, 36 of them inside `workspace.py`.
- Path-helper calls: ~114 refs across 24 files.
- Raw folder-name strings: ~166 raw matches across 56 files, but inflated by
  `targetCourses` (Canvas concept) in the JS layer; true folder-string count is lower.

## Out of scope (follow-up slices)
- `_System` sync-vs-local relocation (Mirror/Catalog/logs out of OneDrive, vault stays synced).
- Seating Charts library (folder slot reserved only).
- Portfolio Export portable-naming mode.
