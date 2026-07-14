# Execution brief: split source-material extraction from the PowerGrader facade

Status: **complete**

Risk: **medium**

Executor: **external VS Code agent**

## Outcome

Source-material debugging has a short facade for workspace listing, source-context
assembly, token/warning policy, and response presets. PDF/DOCX/PPTX/XLSX/ODT/text
decoding and normalization live in one focused extractor module, so format-specific
changes can be debugged without reading the PowerGrader context builder.

This is a behavior-preserving structural refactor. It must not change what source text,
warnings, truncation limits, path checks, or context payloads are sent to the existing
PowerGrader AI workflow.

## Locked decisions

- Keep `api.webui.source_materials` as the stable public facade imported by PowerGrader
  code and tests. Existing public names used by the repository must continue to work:
  `source_folder`, `ensure_source_folder`, `estimate_text_tokens`, `list_source_files`,
  `extract_text_from_bytes`, `extract_folder_file`, `parse_source_files_json`,
  `build_source_context`, `context_warnings`, `response_preset`,
  `synthetic_student_response`, `RESPONSE_PRESETS`, `SUPPORTED_EXTS`,
  `UNSUPPORTED_LEGACY_EXTS`, and `MAX_EXTRACTED_CHARS`.
- Create exactly one focused helper module:
  `api/webui/source_material_extractors.py`.
- The helper owns byte/text extraction and normalization only. The facade owns workspace
  paths, safe relative-path resolution, source-material listing, context assembly,
  token estimation, warnings, response presets, and synthetic response generation.
- Keep the current extraction behavior byte-for-byte at the contract level:
  encoding fallback order, HTML/RTF cleanup, whitespace collapse, page/slide/sheet
  labels, DOCX table joining, legacy-extension errors, unsupported-extension errors,
  empty-text errors, and the 750,000-character truncation warning.
- Keep lazy optional imports for `pypdf` and `python-docx` inside their format-specific
  extraction functions. Do not make either dependency a module-import requirement.
- Use ordinary module functions and constants. Do not add a registry, extractor class
  hierarchy, plugin interface, generic parser abstraction, or new persistence format.
- Preserve the facade's private compatibility names if existing repository callers or
  tests rely on them; otherwise keep private implementation helpers in the extractor
  module and import only the facade-level `extract_text_from_bytes` entry point.
- No changes to the PowerGrader routes, AI workflow, OpenRouter calls, workspace layout,
  upload handling, Canvas access, or authoring contracts.

## Scope

Modify:

- `api/webui/source_materials.py`

Create:

- `api/webui/source_material_extractors.py`

Update tests only as needed to make the ownership split directly testable without
duplicating the full source-context suite:

- `api/tests/test_source_materials.py`

Add a concise stable routing entry to:

- `docs/reference/powergrader-module-map.md`

The reference entry should say that `source_materials.py` owns source-context/facade
behavior and `source_material_extractors.py` owns file-format decoding/normalization.
Update only the source-material size snapshot if it is now materially stale; do not
rewrite the PowerGrader map.

## Out of scope

- Do not change any route, template, browser script, AI prompt, OpenRouter request,
  token-budget rule, Canvas call, workspace folder name, or student-data handling.
- Do not broaden supported file formats or change optional dependency behavior.
- Do not change source-context dictionary keys, material metadata, warning strings,
  error strings, ordering, or truncation semantics.
- Do not split `api/webui/source_materials.py` into multiple facade modules.
- Do not add broad new tests for every format unless an existing behavior is lost during
  extraction; this task is a structural split, not a test-expansion project.
- Do not touch unrelated dirty-worktree changes or private workspace/output files.

## Reference pattern and routing

- Current mixed owner: `api/webui/source_materials.py`
- Current consumers: `api/powergrader/context.py`, `api/powergrader/ai_workflow.py`,
  `api/powergrader/estimates.py`, `api/powergrader/copilot_packet.py`,
  `api/webui/routes/powergrader.py`, `api/tests/test_source_materials.py`
- Existing test pattern: `api/tests/test_source_materials.py`
- PowerGrader map: `docs/reference/powergrader-module-map.md`
- Read `TOOLS.md` before broad inspection; use `py tools/size_report.py` for the
  before/after inventory rather than manually counting unrelated files.

## Implementation requirements

1. Move only the format/normalization cluster into `source_material_extractors.py`:
   `_decode_bytes`, `_strip_html`, `_strip_rtf`, `_collapse_ws`, `_truncate`,
   `_extract_pdf`, `_extract_docx`, `_xml_text_nodes`, `_extract_pptx`, `_extract_xlsx`,
   `_extract_odt`, and the dispatch/truncation/error behavior of
   `extract_text_from_bytes`.
2. Keep the facade's `extract_text_from_bytes` import-compatible. It may be a thin
   re-export or wrapper, but `source_materials.extract_folder_file` and
   `build_source_context` must continue to call the same public entry point.
3. Keep constants with the owner that makes the public contract clearest. Re-export
   `MAX_EXTRACTED_CHARS` and the extension sets from the facade if the extractor needs
   them, so current imports remain valid and there is one source of truth.
4. Add at least one focused test that imports the extractor module directly and proves
   its ownership with a dependency-light case (plain text, HTML, or RTF). Keep the
   existing DOCX and context tests; do not replace behavior coverage with import-only
   assertions.
5. Preserve optional dependency loading and ensure importing
   `api.webui.source_material_extractors` succeeds on an environment without pypdf or
   python-docx installed.
6. Update the PowerGrader module map with the final physical line counts. The split is
   useful only if the facade becomes materially smaller and the new extractor is a
   focused file; do not compress readable code merely to hit an arbitrary number.

## Verification

```powershell
py -m pytest api/tests/test_source_materials.py
py -m py_compile api/webui/source_materials.py api/webui/source_material_extractors.py
py tools/size_report.py
git diff --check
```

Because this touches a shared PowerGrader source-context module, also run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_late_catchup.py
```

No live Canvas/OpenRouter call or rendered browser check is required unless the
implementation changes an out-of-scope route/template/browser file; that would be an
undeclared deviation and cannot be GREEN.

## Stop conditions

Stop with RED rather than guessing if:

- A caller imports a private extraction helper with semantics not covered by this brief.
- Moving the extractor requires changing source-context payloads, warning/error text,
  optional dependency behavior, or a public import outside the named files.
- The split creates an import cycle or requires moving workspace/path safety logic into
  the format reader.
- A test failure indicates behavior drift rather than a mechanical import/ownership
  issue.
- Student data, private workspace artifacts, credentials, Canvas, or OpenRouter access
  would be needed for verification.

Return YELLOW if the behavior is preserved and focused verification passes but the
facade/new-module size result is not materially better without a less-readable design.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave execution state or test evidence only in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: uncommitted
- Files changed and created:
  - **Created:** `api/webui/source_material_extractors.py` (244 lines) — owns all format-specific decoding, normalization, and `extract_text_from_bytes` dispatch
  - **Modified:** `api/webui/source_materials.py` (420 → 216 lines) — slimmed to workspace-path, context-assembly, token-estimation, warning, and response-preset facade. Re-exports constants and helpers from the extractor module.
  - **Modified:** `api/tests/test_source_materials.py` — added 2 focused tests that import the extractor module directly (plain text, HTML)
  - **Modified:** `docs/reference/powergrader-module-map.md` — added source-material routing section
- Before/after physical line counts:
  - `source_materials.py`: 420 lines → 216 lines
  - `source_material_extractors.py`: (new) 244 lines
  - Total: 420 → 460 lines (+40 lines of module boundaries, docstrings, and re-exports)
- Verification commands and pass/fail/skip counts:
  - `py -m pytest api/tests/test_source_materials.py` — **5 passed** in 0.33s
  - `py -m py_compile api/webui/source_materials.py api/webui/source_material_extractors.py` — clean
  - `py tools/size_report.py` — completed; `source_materials.py` no longer appears in
    the ≥300-line list. The inventory still reports unrelated large source/test files.
  - `py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_late_catchup.py` — **21 passed** in 0.94s
  - `git diff --check` — clean
- Deviations from the brief: None.
- Remaining blocker or decision: None.
