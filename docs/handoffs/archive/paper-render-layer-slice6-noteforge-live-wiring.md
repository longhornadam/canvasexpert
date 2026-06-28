# Handoff — NoteForge live wiring

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessors:** slices 1-5 on `dev`
through `bab361f`.
**Lane:** Ferrari-authored; Toyota-executable implementation below.
**Status:** ready to implement.

## Goal

Turn the review-only NoteForge renderer from slices 4-5 into a first-class local web workflow:
paste or upload `<NOTEFORGE_JSON>`, generate tiered printable note artifacts, and save them to the
teacher's `Exports` workspace folder or the existing `Finished_Exports` fallback.

This slice does **not** push to Canvas. Canvas attach is slice 7.

## Design

Mirror the working quiz printable seam instead of inventing a new rendering path:

- Add `engine.packagers.note_handler.generate_note_outputs(note: dict, output_folder: str) -> dict`.
- Keep native dependencies lazy via `engine.rendering.physical.emit_docx` and `emit_pdf`.
- Use the same sync Chromium/Pandoc path as `generate_physical_outputs`.
- Add a sync FastAPI route `POST /api/physical/note` in `api/webui/routes/push.py`.
- Add a `/push/note` page, linked from the Assignments nav/dashboard, with paste/upload/library file
  source, validate, and generate controls.

## Engine contract

`generate_note_outputs(note, output_folder)` trusts the parsed NoteForge payload exactly like the CLI.
It returns:

```python
{
    "artifacts": {
        "Support": {"docx_path": "...", "pdf_path": "..."},
        "Core": {"docx_path": "...", "pdf_path": "..."},
        "Accelerate": {"docx_path": "...", "pdf_path": "..."},
        "Extend": {"docx_path": "...", "pdf_path": "..."},
        "KEY": {"docx_path": "...", "pdf_path": "..."},
    },
    "log_path": ".../physical_validation.log",
}
```

For `mode == "exemplar"`, emit `Exemplar` plus `KEY`. For blank mode, emit `TIERS` plus `KEY`.
If DOCX/PDF conversion is unavailable, catch `RuntimeError`, leave the affected path as `""`, and append
`PHYSICAL RENDER WARNING [note <label> <kind>]: ...` to the render log. Do not fail the whole request.

## Web route contract

`POST /api/physical/note` accepts form field `path`.

Route behavior:

1. Import engine code after adding `REPO_ROOT` to `sys.path`.
2. Parse with `load_noteforge_json(path)`.
3. Adapt to `PrintDoc` only long enough to derive a safe title.
4. Create an output subfolder under `_exports_dir()` with `create_quiz_folder(Path(base), title)`.
5. Call `generate_note_outputs(note, folder)`.
6. Read and remove `physical_validation.log` warning lines, same as `/api/physical/quiz`.
7. Return:

```json
{
  "ok": true,
  "folder": "...",
  "files": ["...pdf", "...docx"],
  "artifacts": {"Support": {"docx_path": "...", "pdf_path": "..."}, "...": "..."},
  "primary_pdf": "...",
  "warnings": [],
  "warning": "",
  "fallback": false
}
```

`primary_pdf` is the best student-facing PDF for slice 7: `Core.pdf`, then `Exemplar.pdf`, then the first
available non-KEY PDF.

## Note validate route

Add `POST /api/nf/validate` with form `path`.

It is intentionally light: parse the NoteForge payload and summarize title, type, mode, and slot count.
The render layer still trusts input; deeper contract validation remains future NoteForge work.

## UI

Add `api/webui/templates/push_note.html` and route `/push/note`.

Controls:

- course picker is included only because slice 7 will attach to Canvas from the same page; generation
  itself remains zero-auth engine work.
- NoteForge file source: library, paste, upload.
- `Validate` button calls `/api/nf/validate`.
- `Generate printable notes` calls `/api/physical/note`.
- Generated banner shows the output folder and, when present, stores `primary_pdf` in
  `window.CE_LAST_NOTE_PRINTABLE` for slice 7.

Add `NOTE_FOLDERS` and `list_note_files()` in `api/webui/deps.py`. Include `DropZone`,
`Finished_Exports`, and workspace `Notes` if present.

## Tests

Add engine tests for the new packager with mocked emitters:

- blank mode emits 4 tiers + KEY, with `.docx` and `.pdf` paths.
- converter failures log warnings and leave missing paths blank.
- exemplar mode emits `Exemplar` + `KEY`.

Add API tests as needed to keep the route contract snapshot deliberate.

## Guardrails

- Route must be `def`, not `async def`; sync Playwright must stay on the known sync path.
- No Canvas token use in this slice.
- No student data or PII in fixtures.
- Do not change QuizForge/QTI push behavior.
- Native emitters stay lazy-imported.

## Acceptance criteria

- `/push/note` can paste or upload a NoteForge file and generate PDFs/DOCXs into Exports.
- The route returns a `primary_pdf` suitable for Canvas attach in slice 7.
- Full `pytest engine/tests api/tests` passes.
- Guardrail grep on the diff shows no tokens, secrets, or student data.
