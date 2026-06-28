# Handoff — Canvas attach for printable NoteForge PDFs

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessors:** slices 1-6 on `dev`.
**Mandatory reading:** `api/README.md` before edits.
**Lane:** Ferrari-authored; guardrail-sensitive `api/` implementation.
**Status:** ready to implement after slice 6.

## Goal

Let a teacher take a generated printable NoteForge PDF and attach it to a Canvas assignment in every
checked target course.

The app remains local-only. Canvas token handling stays inside existing `api/` config/client helpers.

## Design

Use the existing `/api/content/push` multi-course pattern instead of a one-off route:

- Add a `"printable"` content pusher in `api/webui/push_service.py`.
- Add Canvas file upload helper(s) in `push_service.py`.
- Extend `/push/note` with assignment metadata controls and an `Attach PDF to Canvas assignment` button.
- Reuse the existing `pushContent()` confirm dialog and per-course result rendering.

## Canvas flow

For each selected course:

1. Validate `pdf_path` is an existing local `.pdf` under an app-known root (`Exports`, `Finished_Exports`,
   workspace root, or `api/temp` when applicable).
2. Start Canvas course file upload:
   `POST /api/v1/courses/{course_id}/files`
   with `name`, `size`, `content_type`, `parent_folder_path`, and `on_duplicate: "rename"`.
3. POST the file bytes to Canvas's returned `upload_url` with returned `upload_params`.
4. Use the final uploaded file JSON (`id`, `url`, `display_name`) to compose the assignment description.
5. Create a Canvas assignment through the same `_push_assignment()` helper used by other assignment
   workflows, with `submission_types: ["none"]` unless the UI later adds a different submission mode.
6. If a module is selected or created, add the assignment to that module through the existing helper.

## Payload contract

`pushContent("printable", payload, ...)` sends:

```json
{
  "pdf_path": "C:\\...\\Water_Cycle_Notes_Core.pdf",
  "name": "Water Cycle Notes",
  "description": "<p>Use the attached printable notes in class.</p>",
  "points": 0,
  "assignment_group_name": "Daily",
  "module_name": "Unit 3",
  "due_at": "...",
  "unlock_at": "...",
  "lock_at": "...",
  "published": false
}
```

The server appends a short Canvas file link to `description`. It must not read, display, or log PDF
contents.

## UI

On `/push/note`, after generation:

- Keep `window.CE_LAST_NOTE_PRINTABLE = { pdf_path, folder, title }`.
- Show controls for assignment title, description, optional points, due/unlock/lock, category, module,
  and publish checkbox.
- Button label: `Attach PDF to Canvas assignment...`.
- The button is disabled until a generated `primary_pdf` exists, but a hidden/advanced `pdf_path` input
  may be populated by tests or future deep links.

Dry-run/confirm discipline:

- Validate/generate is local and can be repeated.
- Canvas attach uses the existing confirm dialog listing all checked courses and Canvas base URL before
  any network write.
- Server-side path validation blocks arbitrary local file upload.

## Guardrails

- `api/README.md` is mandatory context.
- Do not add token fields, print tokens, or persist Canvas credentials.
- Do not log PDF contents.
- Do not introduce student names or FERPA-sensitive fixture data.
- Keep upload helper unit-testable by monkeypatching `_canvas_send`, `_canvas_headers`, and
  `requests.post`.
- Do not touch QuizForge/QTI push behavior.

## Tests

Add API tests for:

- upload helper rejects non-PDF, missing file, and disallowed path.
- printable pusher uploads once and creates an assignment whose description links the uploaded file.
- upload failure returns `(False, title, None, error)` and does not create assignment.
- route contract snapshot includes any new public routes.

No live Canvas calls in tests.

## Acceptance criteria

- From `/push/note`, generated `Core` or `Exemplar` PDF can be attached as a Canvas assignment across
  checked courses.
- User sees a confirmation before Canvas writes and per-course success/failure afterward.
- Full `pytest engine/tests api/tests` passes.
- Guardrail grep on the diff shows no token, secret, or student-data leak.
