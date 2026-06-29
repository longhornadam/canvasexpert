# Codex Ferrari handoff — Paper render layer, slices 6 & 7

**You (Codex, Extra High) are taking over as the architect ("Ferrari").** Author slices 6 and 7:
design them as self-contained handoffs in this `docs/handoffs/` folder (match the format of the slice
1–5 files), then you may implement them. Everything below is the context you need cold — the previous
architect is out of context, so this doc is the source of truth.

Repo: `D:\Development Projects\CanvasExpert` (Windows, PowerShell; Python 3.13 launched as `py`).
Read first: `CLAUDE.md` (repo guardrails) and `docs/handoffs/paper-render-layer.md` (the parent spec —
the slice roadmap lives there). The slice 1–5 handoffs in this folder are your **format exemplars**.

---

## What's been built (slices 1–5, all committed on `dev`)

A **paper render layer** that turns authored content into print-ready PDF + DOCX. Architecture =
**Option C**: render content to **one HTML + print-CSS substrate**, then emit from it two ways:
- **PDF** via **installed Microsoft Edge (Playwright)** — student-locked, highest fidelity.
- **DOCX** via **Pandoc (`pypandoc-binary`)** — teacher-editable; styled by a generated reference doc.

Pipeline: `source JSON → adapter → PrintDoc (content model) → [redact(tier)] → render_html → emit_pdf /
emit_docx`.

Key modules under `engine/rendering/physical/`:
- `printdoc.py` — the content model. Blocks: `Stimulus`, `Question`, `Slot`, and note blocks
  `Heading`/`Para`/`BulletList` (+ `CornellLayout`/`FrayerGrid` after slice 5). `Slot(id, content_html,
  key, given)` is the redaction unit.
- `quiz_adapter.py` (`to_printdoc(quiz)`) and `note_adapter.py` (`to_printdoc(note_dict)`,
  `load_noteforge_json`, `parse_noteforge_json`).
- `html_renderer.py` — `render_html(printdoc, *, variant, tier=None)`; `variant ∈ {"quiz","key","note"}`.
- `emit_pdf.py` (Playwright launching installed Edge, **lazy import**), `emit_docx.py` (pypandoc, lazy), `reference_doc.py`.
- `tiers.py` — `TIERS=("Support","Core","Accelerate","Extend")`, `TIER_BLANK_FRACTION=25/50/90/100%`.
- `redact.py` — `redact(printdoc, tier)` (pure, deepcopy, deterministic via sha256(slot.id), monotonic),
  `filled(printdoc)` (answer key = all slots given), `iter_slots(doc)` (recursive walk).
- `templates/` (Jinja: `base/quiz/answer_key/note.html.j2`, `_slot.html.j2` macro), `styles/print.css`.
- `spike.py` (quiz dev CLI), `note_spike.py` (NoteForge dev CLI: per-tier PDF+DOCX + KEY).

**The live quiz seam** (already wired): `engine/packagers/physical_handler.py::generate_physical_outputs(
quiz, output_folder) -> dict` returns `{quiz_path(.docx), quiz_pdf_path, key_path(.docx), key_pdf_path,
rationale_path, log_path}`. It renders via the substrate, degrades per-artifact if an engine is missing
(`_try_emit` logs a `PHYSICAL RENDER WARNING` and continues), keeps the rationale sheet
(`CorrectionDocRenderer`) and the validation-log stats. **Two consumers reach this one function:**
1. `engine/orchestrator.py` (DropZone CLI) → `package_quiz()` → `PhysicalHandler().package()`.
2. `api/webui/routes/push.py::api_physical_quiz` — a **sync** `def` route `POST /api/physical/quiz`.

**NoteForge** (slices 4–5) is **review-only via `note_spike` CLI** — NOT yet wired into the live app.
Contract: `LLM_Modules/NoteForge_Base.md`, `<NOTEFORGE_JSON>` envelope, inline `{{slot}}` authoring.
Types: `guided_notes`, plus `cornell`/`frayer` after slice 5. `mode ∈ {blank, exemplar}`.

---

## Conventions & guardrails — DO NOT relitigate or violate

- **Contracts are canonical.** Authoring semantics live in `LLM_Modules/*_Base.md`, never in engine code.
- **`api/` is token-holding, local-only, FERPA-sensitive.** Binds `127.0.0.1`; never exposed. Student
  names/IDs/grades/submissions never touch the repo, fixtures, logs, or commits. Read `api/README.md`
  before touching Canvas push logic — it records hard-won live-API facts (e.g. New Quizzes write-back is
  parked on a PAT/403 limit). The Canvas token lives only in the OS keychain / `api/.env` (gitignored).
- **Engines are settled:** PDF = installed Microsoft Edge via Playwright (chosen over WeasyPrint's GTK
  pain and Playwright's downloaded Chromium on district-managed PCs), DOCX = `pypandoc-binary`
  (bundled, no PATH). The app uses the standard Windows Edge install; set `CANVAS_EXPERT_EDGE_PATH`
  only for nonstandard Edge locations.
- **Playwright sync API must not run inside an async event loop.** Both current live call sites are sync
  (CLI; sync FastAPI route in a threadpool) — keep it that way, or wrap with `anyio.to_thread.run_sync`.
- **Renderers trust input — no validation in the render path.** Convergent HTML only (semantic tables,
  not CSS grid/abs-pos) so layouts survive Pandoc→DOCX. Native emitters stay **lazy-imported** so the
  engine imports without the browser/Pandoc stack.
- **Tier fractions stay 25/50/90/100** (Adam confirmed; short notes having fewer effective tiers is fine).
- **Quiz path + Canvas/QTI path are stable** — don't regress them.

## Workflow — match the cadence used for slices 1–5

- **Ferrari/Toyota split** (`CLAUDE.md`): you (Ferrari) author self-contained handoffs; a cheap agent or
  you implement. A good handoff states exact files+signatures, behavior + edge cases, the test to pass,
  acceptance criteria, applicable guardrails, and what NOT to touch.
- **Review discipline before committing:** run `py -m pytest engine/tests api/tests` (from repo root;
  green baseline is ~239 passed, 1 skipped + new tests). Guardrail-grep the diff for stray edits to
  contracts / Canvas / validation / live paths. For anything that hides content, keep the **no-leak test**
  (a blanked slot's `content_html` must never appear in student HTML).
- **Commit per slice on `dev`** (keep everything on `dev`). End commit messages with
  `Co-Authored-By: ...`. A pre-commit hook blocks the Canvas-token pattern — don't bypass it. Benign
  `LF will be replaced by CRLF` warnings are expected on Windows.
- **Review-first for anything visible:** new content paths shipped as a dev CLI first (like `note_spike`)
  so Adam eyeballs the artifacts before live wiring. Generated files go under `out/` (gitignored).

---

## Slice 6 — Live wiring for NoteForge (you design it)

**Goal:** NoteForge notes reach `Finished_Exports` through the live app, the way quizzes do — not just
the `note_spike` CLI. Mirror the quiz seam.

What you'll need to decide/author (this is the architecture work):
- A NoteForge analog to `generate_physical_outputs` — e.g. `generate_note_outputs(note_dict,
  output_folder) -> dict` emitting the per-tier PDFs/DOCX + KEY, with the same per-artifact
  graceful-degradation + warning pattern. Decide the return-dict shape and file-naming.
- A **sync** webui route mirroring `api_physical_quiz` (e.g. `POST /api/physical/note`) in
  `api/webui/routes/push.py`, plus the UI surface (mirror `push_quiz.html`/`push.js`) and the
  download/open-path listing (`pages.py` already exposes `Finished_Exports`).
- **Input routing:** how a teacher supplies a note. Likely detect `<NOTEFORGE_JSON>` vs `<QUIZFORGE_JSON>`
  in the DropZone/orchestrator and route accordingly, and/or a dedicated note input box. You decide.
- A content-parity / no-leak test for the live path; keep the route-contract test green.

Constraints: sync only (Playwright); reuse `note_adapter` + `redact`/`filled` + `render_html("note")` +
the emitters; don't fork the contract. Output set: 4 tier PDFs + DOCX + KEY (tunable).

## Slice 7 — Canvas-attach (you design it)

**Goal:** attach a generated printable (PDF) to a Canvas assignment via the live API, so "AI content →
both a Canvas assignment AND a downloadable/printable file" is one action (the both/and Adam wants).

This lives in **`api/`** (token-holding). **Read `api/README.md` first** for the Canvas file-upload +
assignment APIs and known limits. Likely shape: upload the PDF via Canvas's file-upload flow, create or
update an assignment, and link/attach the file. Apply Canvas-Expert conventions: actions DO things via
the API; destructive/grade-affecting actions get dry-run + confirm; respect FERPA + token guardrails;
multi-course by name where relevant. You author the design and the integration points.

---

## Pointers
- Parent spec + roadmap: `docs/handoffs/paper-render-layer.md`.
- Format exemplars: `paper-render-layer-slice{1,2,3,4-...,5-...}.md` in this folder.
- Repo guardrails: `CLAUDE.md`. Canvas API facts: `api/README.md`.
- Run: `cd api; py qf_ui.py` (web UI on 127.0.0.1:8765). Tests: `py -m pytest engine/tests api/tests`.
- Quiz live seam to mirror: `engine/packagers/physical_handler.py` + `api/webui/routes/push.py`.
- NoteForge to wire: `engine/rendering/physical/{note_adapter,note_spike}.py`, `LLM_Modules/NoteForge_Base.md`.
