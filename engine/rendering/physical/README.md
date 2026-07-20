# Physical Rendering

This package renders printable classroom artifacts from the shared `PrintDoc`
content model.

## Outputs

- Quiz student DOCX and PDF
- Quiz answer-key DOCX and PDF
- Rationale sheets and physical render logs

## Pipeline

Authored content is adapted once into `PrintDoc`, then rendered to HTML with
print CSS. The same HTML substrate feeds both final formats:

- PDF: `emit_pdf.py` launches the installed Microsoft Edge through Playwright.
- DOCX: `emit_docx.py` uses `pypandoc-binary`, which bundles Pandoc.

The PDF path intentionally uses the system Edge install instead of Playwright's
downloaded Chromium because district-managed PCs may block browser downloads.
For nonstandard Edge installs, set `CANVAS_EXPERT_EDGE_PATH` to the full
`msedge.exe` path.

## Dependencies

Runtime dependencies live in `api/requirements.txt` because the render stack is
used by the local app:

- `playwright` for browser automation
- Microsoft Edge installed and allowed by device policy
- `pypandoc-binary` for DOCX conversion
- `python-docx` for generated DOCX reference styles and rationale sheets

The launcher installs Python packages only; it does not download a Playwright-managed
browser.

## Entry Points

- `engine.packagers.physical_handler.generate_physical_outputs(quiz, output_folder)`
- `engine.rendering.physical.html_renderer.render_html(printdoc, variant=...)`
- `engine.rendering.physical.emit_pdf.html_to_pdf(html, css_path, out_path)`
- `engine.rendering.physical.emit_docx.html_to_docx(html, reference_docx, out_path)`

Missing converters are logged as physical render warnings so available formats
can still be emitted.
