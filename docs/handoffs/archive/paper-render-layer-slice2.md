# Handoff — Paper render layer, Slice 2: wire the new path into the live pipeline

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessor:** `paper-render-layer-slice1.md`
(the non-destructive spike, now committed on `dev` at `270c385`).
**Lane:** Toyota (well-scoped), with one guardrail-adjacent note (Playwright provisioning).
**Status:** ready to implement. Slice 1's fidelity verdict is **approved** (DOCX + PDF, incl. code,
prose, and poetry stimuli). Engines settled: **PDF = headless Chromium (Playwright)**, **DOCX =
Pandoc via `pypandoc-binary`**.

## Goal

Make the **real** physical output (the files teachers get in `Finished_Exports`) come from the new
Option-C render path instead of the legacy python-docx renderer — and add the student-locked PDF
alongside the editable DOCX. Retire the legacy student-quiz/answer-key DOCX code. Keep the rationale
sheet and the validation log exactly as they are.

## The single integration seam

Both consumers reach the same function — change it once and both update:

- **Orchestrator (CLI / DropZone):** `orchestrator.py` → `package_quiz()` (`packagers/packager.py`) →
  `PhysicalHandler().package()` → **`generate_physical_outputs(quiz, output_folder)`**
  (`packagers/physical_handler.py`).
- **Web UI:** `api/webui/routes/push.py::api_physical_quiz` (a **sync** `def`, runs in FastAPI's
  threadpool) calls **`generate_physical_outputs(quiz, str(folder))`** directly.

> **Why sync matters:** Playwright's **sync** API raises if called inside a running asyncio loop.
> Both call sites are synchronous (CLI; sync FastAPI route in a worker thread), so the spike's sync
> Playwright code works unchanged. **Guardrail:** do NOT call `generate_physical_outputs` (or the new
> emitters) from an `async def`. If that's ever needed, wrap it with `anyio.to_thread.run_sync`.

## What to change

### 1. Rewrite `generate_physical_outputs(quiz, output_folder)` — `packagers/physical_handler.py`
Keep the signature and the existing return keys; render via the new path (mirror `spike.py`). Produce
**both** a locked student PDF and an editable teacher DOCX for the quiz and the key:

```python
def generate_physical_outputs(quiz: Quiz, output_folder: str) -> Dict[str, str]:
    from engine.rendering.physical.quiz_adapter import to_printdoc
    from engine.rendering.physical.html_renderer import render_html, default_css_path
    from engine.rendering.physical.emit_docx import html_to_docx
    from engine.rendering.physical.emit_pdf import html_to_pdf
    from engine.rendering.physical.reference_doc import build_reference_docx
    import tempfile

    printdoc = to_printdoc(quiz)                      # no validation (trust input)
    base = sanitize_filename(quiz.title) or "Untitled_Quiz"
    quiz_html = render_html(printdoc, variant="quiz")
    key_html  = render_html(printdoc, variant="key")

    out = Path(output_folder)
    quiz_docx, quiz_pdf = out / f"{base}.docx", out / f"{base}.pdf"
    key_docx,  key_pdf  = out / f"{base}_KEY.docx", out / f"{base}_KEY.pdf"

    # Render each artifact independently so a missing engine degrades gracefully
    # (see "graceful degradation" below) rather than zeroing the whole bundle.
    with tempfile.TemporaryDirectory(prefix="ce-printdoc-") as tmp:
        ref = build_reference_docx(str(Path(tmp) / "reference.docx"))
        _try(lambda: html_to_docx(quiz_html, ref, str(quiz_docx)), "quiz docx")
        _try(lambda: html_to_docx(key_html,  ref, str(key_docx)),  "key docx")
    css = default_css_path()
    _try(lambda: html_to_pdf(quiz_html, css, str(quiz_pdf)), "quiz pdf")
    _try(lambda: html_to_pdf(key_html,  css, str(key_pdf)),  "key pdf")

    rationale_path = _create_rationale_sheet(quiz, output_folder)   # UNCHANGED
    log_path = Path(output_folder) / "physical_validation.log"
    _log_validation_stats(quiz, str(log_path))                      # UNCHANGED

    return {
        "quiz_path":     str(quiz_docx) if quiz_docx.exists() else "",   # back-compat key = editable master
        "quiz_pdf_path": str(quiz_pdf)  if quiz_pdf.exists()  else "",   # NEW: student-locked
        "key_path":      str(key_docx)  if key_docx.exists()  else "",   # back-compat
        "key_pdf_path":  str(key_pdf)   if key_pdf.exists()   else "",   # NEW
        "rationale_path": rationale_path,
        "log_path":       str(log_path),
    }
```

- **Back-compat:** `quiz_path`/`key_path` keep their meaning (the `.docx`, same filenames as today) so
  `orchestrator.py` and `push.py` keep working untouched. PDFs are **additive** (`*_pdf_path`).
- **Graceful degradation:** a small `_try(fn, label)` helper runs an emit, and on `RuntimeError`
  (Chromium/Pandoc not provisioned) logs a clear line into `physical_validation.log` and continues, so
  a teacher who hasn't run `playwright install chromium` yet still gets the DOCX (and vice-versa).
  Surface the first missing-engine message to the webui (see step 3).

### 2. Delete the legacy renderer code — `packagers/physical_handler.py`
Remove `_create_student_quiz`, `_create_answer_key`, and the python-docx layout helpers they use:
`_FormattedHTMLParser`, `_group_questions_by_stimulus`, `_add_question_to_doc`, `_add_mc_two_column`,
`_add_mc_single_column`, `_add_matching_block`, `_add_ordering_block`, `_add_categorization_block`,
`_add_tf_options`, `_render_stimulus_boxed`, `_render_poetry_to_doc`, `_render_html_to_paragraph`,
`_detect_stimulus_format`, `_clean_prompt_text`, `_get_correct_answer_text`,
`_format_rationale_with_answer`, `_generate_basic_rationale`. (Their logic now lives in
`quiz_adapter.py` / the templates.) **Keep:** `_create_rationale_sheet`, `_log_validation_stats`,
and the `_log_*` stat helpers it calls, and the `PhysicalHandler` class wrapper.

### 3. Minor surfacing (do in the same PR)
- `orchestrator.py::_handle_validation_success` — it prints `quiz_path`/`key_path`. Add prints for
  `quiz_pdf_path`/`key_pdf_path` when present.
- `api/webui/routes/push.py::api_physical_quiz` — the success JSON / copy says "printable DOCX bundle";
  include the new PDF paths in the response and update copy to "PDF + DOCX". If `generate_physical_outputs`
  recorded a missing-engine warning, return it so the UI can tell the teacher to run
  `py -m playwright install chromium`.
- Check the download/open surface (`pages.py` open-path roots already include `Finished_Exports`; the
  `download_work`/`push_quiz.html`/`push.js` paths) still list the produced files — PDFs should appear.

### 4. Provisioning (flag; small follow-on, not core slice 2)
Chromium must be present: `py -m playwright install chromium` (~150 MB download). For the local app this
belongs in first-run/onboarding (`docs/handoffs/onboarding-wizard.md`) — detect-and-offer, since
**district-managed machines may block the download** ([[distribution-strategy]]). Out of scope to fully
solve here; leave a clear TODO + the graceful-degradation message so the app is usable meanwhile.

## Tests

1. **HTML content-parity test (pure-Python, no native libs)** — `engine/tests/unit/`. For a fixture
   quiz covering MC (both column modes), TF, matching, ordering, categorization, FITB, a code stimulus,
   and a poetry stimulus: assert `render_html(to_printdoc(quiz), "quiz")` contains every prompt, choice,
   stimulus body line, and blank; and `render_html(..., "key")` contains every answer row + the total.
   This is the regression baseline that replaces "diff the old DOCX." Author the fixture with fictional
   content only (FERPA).
2. **Native render smoke test** behind a skip guard: `pytest.importorskip` + a check that Chromium/Pandoc
   are available; if so, assert `generate_physical_outputs` writes a non-empty `.pdf` and `.docx`. Never
   make CI hard-depend on the browser/Pandoc.
3. Keep green: `py -m pytest api/tests engine/tests` (esp. `api/tests/test_route_contract.py`,
   `test_downloader.py`, `test_portfolio_merged.py`). Fix any consumer that assumed python-docx internals.

## Acceptance criteria
- `generate_physical_outputs` returns the 6-key dict above; `quiz_path`/`key_path` still point to `.docx`.
- DropZone run (`orchestrator`) and the webui `POST /api/physical/quiz` both drop `.docx` **and** `.pdf`
  for quiz + key into the `Finished_Exports` quiz folder, plus the unchanged `_RATIONALE.docx` and log.
- Legacy python-docx student/key code deleted; rationale + log stats unchanged.
- With Chromium/Pandoc absent, the DOCX (or whichever engine is present) still emits and a clear
  "install chromium" message is recorded/surfaced — no traceback, no empty bundle.
- HTML content-parity test passes; full `pytest` green.

## Guardrails / do NOT touch
- **Contracts canonical** — no `LLM_Modules/*_Base.md` edits.
- **Canvas/QTI path** (`engine/rendering/canvas/`, `canvas_handler.py`) untouched.
- **Validation** untouched; renderers keep the "trust input, no validation" contract.
- **engine offline / lazy imports** — emitters stay lazily imported; importing the engine must not
  require Playwright/Pandoc.
- **No PII/FERPA** in fixtures or output; `out/` stays gitignored.
- **Don't call the render path from `async def`** (Playwright sync constraint).
- Keep `spike.py` — it stays as the dev iteration tool.
