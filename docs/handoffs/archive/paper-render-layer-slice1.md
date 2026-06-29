# Handoff — Paper render layer, Slice 1: Option-C fidelity spike (non-destructive)

**Parent spec:** `docs/handoffs/paper-render-layer.md` (read it first — architecture + the Option-C decision).
**Lane:** Toyota (well-scoped build) **with a Ferrari checkpoint at the end** — Adam judges output
fidelity before anything in the live path changes.
**Status:** ready to implement.

## Why this slice exists / what it is NOT

The whole effort lives or dies on **how good the printed output looks to teachers**. Before we touch
the working quiz renderer, we build the full Option-C pipeline *beside* it and produce real files to
judge. This slice is a **spike**: it adds new code and a dev CLI, and **changes nothing in the live
pipeline**. If the fidelity is great, slice 2 wires it in and retires the old path. If not, we learn
exactly where HTML→DOCX/PDF falls short before committing.

**Do NOT** in this slice: modify `packager.py`, `physical_handler.py`, `orchestrator.py`, the Canvas/
QTI path, validation, or any `LLM_Modules/*_Base.md` contract. Leave the existing
`{title}.docx / _KEY.docx / _RATIONALE.docx` output exactly as-is.

## Goal

A standalone dev command that takes a QuizForge JSON/TXT, and emits — *next to* whatever the current
engine produces — a **student quiz** and **answer key** as both `*_NEW.docx` (Pandoc) and `*_NEW.pdf`
(Edge via Playwright), rendered from **one** Jinja2 HTML + print-CSS substrate. Then Adam compares.

(Rationale sheet is **out of scope** for the spike — it already renders via `CorrectionDocRenderer`
and isn't where the layout risk lives. Student quiz + answer key are the fidelity test.)

## The "highest fidelity" rules baked into this slice

1. **Convergent HTML.** Author templates using constructs that survive *both* Edge PDF and Pandoc→DOCX:
   semantic `<table>`, `<p>`, `<ol>/<ul>`, `<strong>/<em>`. **Avoid** CSS grid, flexbox, and absolute
   positioning for anything that must appear in the DOCX — those render in PDF but degrade or vanish in
   DOCX. Where PDF wants a richer layout than DOCX can hold, it's fine for the PDF to be nicer; just
   never let a DOCX construct silently drop content.
2. **Pandoc, with a reference doc.** Use Pandoc for html→docx (best-in-class fidelity). Drive DOCX
   styling (Calibri, margins, heading sizes) via a generated `--reference-doc` so the teacher master
   matches the house style in `engine/rendering/physical/styles/default_styles.py`, not Pandoc defaults.
3. **CSS values mirror the existing style constants.** Page margins 0.75in, body Calibri 11pt, title
   16pt, heading 12pt, small 9pt, line-spacing 1.15 — pull these from `default_styles.py` so PDF and the
   reference-doc DOCX agree with today's look.

## Dependencies to add

Add to **`api/requirements.txt`** (CE is local-only; no Netlify/Pyodide constraint here — but keep the
new emitters **lazy-imported** so importing the core engine stays light):

```
playwright>=1.40        # html+print-CSS → PDF via installed Microsoft Edge
pypandoc-binary>=1.13   # html → DOCX (teacher-editable; bundles Pandoc)
```

**Browser/Pandoc binaries:** the current implementation uses the Windows Microsoft Edge install for
PDF output and `pypandoc-binary` for DOCX output. No Playwright-managed browser download or system
Pandoc install is required.

## Files to create

```
engine/rendering/physical/
  printdoc.py            # PrintDoc content model (dataclasses) — see schema below
  quiz_adapter.py        # to_printdoc(quiz: Quiz) -> PrintDoc
  html_renderer.py       # render_html(printdoc: PrintDoc, *, variant: "quiz"|"key") -> str  (Jinja2)
  emit_pdf.py            # html_to_pdf(html: str, css_path: str, out_path: str) -> str  (Edge via Playwright, lazy import)
  emit_docx.py           # html_to_docx(html: str, reference_docx: str, out_path: str) -> str (pypandoc-binary, lazy import)
  reference_doc.py       # build_reference_docx(out_path) -> str  (python-docx; styles from default_styles)
  spike.py               # dev CLI (see below)
  templates/
    base.html.j2         # <html><head> with linked print.css; block content
    quiz.html.j2         # student quiz layout (extends base)
    answer_key.html.j2   # answer-key table (extends base)
  styles/
    print.css            # convergent print-CSS; values mirror default_styles.py
```

No new files under `tests/` are required to pass; a tiny smoke test is welcome (below) but the real
acceptance is the human fidelity check.

## `PrintDoc` schema (slice-1 scope — quiz only; notes come later)

Plain dataclasses in `printdoc.py`. Keep it small and content-type-agnostic in spirit, but only
populate what the quiz needs now.

```python
@dataclass class PrintDoc:        # title + instructions + ordered blocks
    title: str
    instructions: str
    blocks: list                  # list[Block]
    answer_key: "AnswerKey|None"

# Block union (slice 1):
@dataclass class Stimulus:        title:str; author:str; fmt:str("text"|"poetry"); body_html:str
@dataclass class Question:        number:int; qtype:str; prompt_html:str; payload:"QPayload"
# QPayload variants by qtype:
#   MC/MA      -> choices: list[Choice(letter:str, html:str)]; two_column:bool
#                 (two_column = all choice texts < MC_TWO_COLUMN_THRESHOLD chars)
#   TF         -> (render fixed "A. True  B. False")
#   MATCHING   -> pairs: list[Pair(prompt:str, answer:str)]   (blanks + lettered legend)
#   ORDERING   -> items: list[str]                            (blank-line prefixes)
#   CATEGORIZATION -> categories: list[str]; items: list[str]
#   FITB       -> prompt already contains the inline blank (replace [token] with ____)
#   NUMERICAL/ESSAY -> answer line; FILEUPLOAD -> no answer line
@dataclass class AnswerKey:       rows: list[KeyRow(number:int, answer:str, points:str)]; total:str
```

`quiz_adapter.to_printdoc(quiz)` **reuses the existing, proven logic** in `physical_handler.py` rather
than reinventing it — copy/adapt these helpers into pure functions that fill the model:
`_group_questions_by_stimulus`, `_detect_stimulus_format`, `_clean_prompt_text`, `_get_correct_answer_text`,
and the per-type rendering decisions (FITB `[token]`→`____`, matching blanks+legend, ordering/categorization
blanks). Answer-key rows mirror `_create_answer_key`. Keep the "**no validation; trust input**" contract.

## Template / CSS specifics (the fidelity-critical part)

- **Page:** `@page { size: Letter; margin: 0.75in; }`. Body `font-family: Calibri, "Carlito", sans-serif;
  font-size: 11pt; line-height: 1.15;` (Carlito = metric-compatible Calibri fallback on machines without
  Calibri — improves PDF fidelity).
- **Name line + title:** name line (`Name: ____`) above the title, title 16pt bold — matches current.
- **MC choices:** single column by default; for the **two-column** case (all choices <
  `MC_TWO_COLUMN_THRESHOLD` = 50 chars) use a 2-col **`<table>`** (convergent — survives DOCX), not CSS
  columns. Letter prefixes A./B./C…
- **Stimulus (prose):** attribution header (title bold 12pt, author italic), body indented; paragraph
  numbering `(n)` like today. **Poetry:** every-5th-line numbering in a left gutter — render as a
  two-column `<table>` (gutter | line) so it survives DOCX; this is the single trickiest layout, get it
  reviewed.
- **Answer key:** bordered `<table>` (Question # | Correct Answer | Points), bold header, total below.
- Keep inline `<strong>/<em>` from prompts intact (prompts already contain limited HTML).

## Dev CLI (`spike.py`)

```
py -m engine.rendering.physical.spike --input <quiz.(json|txt|md)> --output <dir>
```
Behavior: read the file → `import_quiz_from_llm(text).quiz` (reuse the real importer) →
`to_printdoc(quiz)` → render `quiz.html.j2` and `answer_key.html.j2` → emit four files into `<dir>`:
`<title>_NEW.docx`, `<title>.pdf`, `<title>_KEY_NEW.docx`, `<title>_KEY.pdf`. Also dump the raw
`<title>_NEW.html` so layout problems are debuggable. Print the output paths. No archiving, no DropZone
scanning — this is a dev tool, not the orchestrator.

## How to run / verify (implementer)

```powershell
py -m pip install -r api/requirements.txt        # pulls playwright and pypandoc-binary
# ensure Microsoft Edge is installed and allowed by device policy
py -m engine.rendering.physical.spike --input engine/tests/fixtures/<a-quiz> --output out/spike
```
Pick **three** fixtures from `engine/tests/fixtures` that together exercise: (a) MC with short choices
(two-column path), (b) a **poetry stimulus**, (c) **matching + ordering + categorization**. If the
fixtures don't cover these, author a tiny fictional quiz JSON in `out/spike/` (do NOT commit student
data; fictional content only).

## Acceptance criteria

1. `py -m engine.rendering.physical.spike` runs clean on the three fixtures and writes the 4 files +
   HTML per fixture.
2. The student-quiz **PDF** opens, paginates sanely (no clipped content), and is non-editable.
3. The student-quiz **DOCX** opens in Word, is editable, uses Calibri/0.75in margins, and **contains all
   the same content** as the PDF (no dropped choices/stimulus/blanks).
4. `py -m pytest engine/tests` still green (you changed nothing in the live path — this just proves it).
5. The Pandoc-vs-binary sub-decision is recorded at the bottom of this file.
6. **STOP and hand back to Adam** with the `out/spike/` files for the fidelity verdict. Do not proceed
   to slice 2 (wiring in / retiring the old renderer) without sign-off.

## Optional smoke test (nice to have)
`engine/tests/unit/test_printdoc_adapter.py`: build a 2-question `Quiz` in-memory, assert
`to_printdoc` yields the right block count, question numbers, two-column flag, and answer-key rows.
Pure-Python, no Edge/Pandoc needed (don't make the suite depend on native libs).

## Guardrails that apply
- **Non-destructive:** live pipeline untouched (see the NOT-list up top).
- **Lazy imports:** import Playwright / `pypandoc` only inside `emit_pdf`/`emit_docx` functions,
  so importing the engine doesn't require the native libs.
- **No PII / FERPA:** fixtures and any hand-authored sample quiz use fictional content only; `out/` is
  gitignored — keep generated files out of the repo.
- **Offline:** no network in the render path.
- **Don't add Playwright / `pypandoc-binary` to the repo-root `requirements.txt`** (kept lean for the Netlify
  web build in the sibling QuizForge repo); they go in `api/requirements.txt`.

---

### Sub-decision log (RESOLVED 2026-06-25 after Adam's verdict)
- **html→docx engine: `pypandoc-binary` (bundled Pandoc).** Initial build used system Pandoc via
  `pypandoc`, which stopped at DOCX emission (no `pandoc` on PATH). Switched to `pypandoc-binary` so
  no teacher ever installs Pandoc; `api/requirements.txt` updated.
- **PDF engine: installed Microsoft Edge via Playwright** (`emit_pdf.py` rewritten again on
  2026-06-29). WeasyPrint was tried first and failed on Windows for missing GTK/Pango
  (`libgobject-2.0-0`, error `0x7e`). The initial Chromium download path was replaced because
  district-managed PCs may block Playwright's browser download; Edge is expected on Windows.
  `api/requirements.txt`: `weasyprint` → `playwright`.
- **Verdict:** DOCX fidelity approved after round-2 template fixes (code-stimulus de-styling + boxing,
  inter-question spacing, title de-dup, categorization paper instruction). Full pipeline emits HTML +
  student/key DOCX + student/key PDF, exit 0, 96 tests green. → proceed to slice 2.
