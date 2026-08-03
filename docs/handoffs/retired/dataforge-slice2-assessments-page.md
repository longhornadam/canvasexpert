# Brief: DataForge slice 2, Assessments page

**Status:** Retired GREEN after senior acceptance on 2026-08-02. Superseded by
`docs/handoffs/dataforge-slice3-read-only-join.md`.
**Batch:** DataForge merge initiative, slice 2 of 6.
**Baseline:** `dev` at the slice-1 worktree state; do not merge the DataForge history.

## Teacher-visible outcome

CanvasExpert gains an **Assessments** page under More. A teacher can select local Eduphoria
exports, process them, read populated per-assessment results and a cross-assessment dashboard,
review and re-date history, and download generated artifacts without starting a second app.

This slice does not place students into Canvas groups. The grouping panel is slice 4, after the
read-only join and coverage report in slice 3.

## Required context, read only this

1. `AGENTS.md` and `docs/reference/project-state.md`.
2. `docs/handoffs/senior level/dataforge-merge-initiative.md`, sections 2.3, 5.1, 5.3, 6, 7,
   and 8.4 only.
3. `docs/reference/webui-presentation-system.md`, sections Template API, Who these pages are
   for, Page conventions, CSS ownership, Migration map, and Change propagation.
4. `api/webui/README.md`, sections Rendered verification, Page map, and the route/template
   ownership notes for the existing page surfaces.
5. `api/webui/server.py`: app construction, onboarding gate, router registration, and the
   `templates`/response imports.
6. `api/webui/routes/pages.py`: page route and template-context patterns only.
7. `api/webui/deps.py`: `templates`, `asset_v`, and stable path imports.
8. `api/webui/templates/layouts/workspace.html`, `api/webui/templates/layouts/_app_header.html`,
   and `api/webui/templates/ui/_macros.html`.
9. `api/dataforge/views.py`: result classes plus `index`, `process`, `dashboard`, `history`,
   `history_update`, `history_delete`, `results`, `download`, `download_all`, and
   `export_standards_profile`.
10. `api/dataforge/paths.py` and `api/dataforge/profile_export.py` only where needed by the
    adapter.
11. `api/tests/test_route_contract.py`, `api/tests/test_presentation_contracts.py`, and the
    nearest route-test conftest.

Do not preload the Students route, operation ledger, Canvas transport owners, MCP server, or
the full web UI reference. They are outside this slice.

## Locked decisions

**L2.1.** Add one FastAPI router at `api/webui/routes/assessments.py`, mounted by
`api/webui/server.py`. Use the `/assessments` prefix for the page and all its actions. Do not
add a second server or route shell.

**L2.2.** The adapter owns HTTP concerns only. It maps DataForge's `Render`, `Redirect`,
`FileDownload`, `BytesDownload`, and `NotFound` results to FastAPI responses. Keep
`api/dataforge/` free of FastAPI, Starlette, Flask, or request/session globals.

**L2.3.** Use CanvasExpert-native templates. Add `assessments.html`,
`assessment_results.html`, `assessment_dashboard.html`, and `assessment_history.html` under
`api/webui/templates/`, each extending `layouts/workspace.html` and using the shared macros.
The old Flask templates are not available or authoritative; do not recreate their block API.
The content must appear in `primary`, the title must use `page_header`, and feature CSS must be
page-owned through `head_extra`.

**L2.4.** Expose these page actions only: index, process, dashboard, history, history update,
history delete, results, standards-profile export, single download, and download-all. Do not
expose `views.groups` as a page route. A link to grouping may point to the future Students
surface only if it does not claim that placement is available in this slice.

**L2.5.** Preserve the engine's endpoint symbols for its redirects through an explicit adapter
map. `Redirect("index")`, `Redirect("results", run_id=...)`, and history redirects must resolve
to the assessment routes, without changing view signatures or adding global URL state.

**L2.6.** Upload handling stays local and defensive: accept only `.xlsx`, `.xls`, and `.csv`,
sanitize the client filename, save under `paths.upload_dir`, pass plain paths to
`views.process`, and preserve its unlink behavior. No Canvas call, external AI request, or
operation-ledger entry is allowed.

**L2.7.** Add Assessments to the existing More menu in `_app_header.html`; it is a More item,
not a new top-level navigation slot. The page sets `nav_section` so More is visibly active.

## Files

### Add

- `api/webui/routes/assessments.py`
- `api/webui/templates/assessments.html`
- `api/webui/templates/assessment_results.html`
- `api/webui/templates/assessment_dashboard.html`
- `api/webui/templates/assessment_history.html`
- `api/webui/static/pages/assessments.css`
- `api/tests/webui/routes/test_assessments.py`

### Modify

- `api/webui/server.py` — import and include the assessments router.
- `api/webui/templates/layouts/_app_header.html` — More menu entry and active state.
- `api/tests/test_route_contract.py` — registered assessment route/method contract.
- `api/tests/test_presentation_contracts.py` — `/assessments` presentation row and feature CSS.
- `api/webui/README.md` — page map and ownership entry for `/assessments`.

Do not modify `api/dataforge` logic, Canvas transport ownership, `api/requirements.txt`, or
the Students page in this slice.

## Adapter contract

The route module must keep one small response mapper and one endpoint map. The mapper must:

- render the four CE-native templates with the view context plus `nav_section="assessments"`,
  CSRF context where a form needs it, and the existing asset globals;
- resolve engine endpoint symbols to the `/assessments` route names;
- return attachment responses for both disk files and in-memory ZIP/JSON bytes;
- map `NotFound` to HTTP 404 without leaking absolute paths or private details; and
- use standard FastAPI form/file parameters, never a framework object passed into the engine.

The page templates must render the actual contexts returned by the engine: existing input files,
run results/errors, dashboard comparisons, snapshots, and download controls. Empty and missing-run
states must be explicit, not blank shells.

## Acceptance criteria

1. `/assessments` and its declared GET/POST actions are registered exactly once, and the route
   contract passes.
2. The More menu contains an Assessments link and marks it active on all assessment pages.
3. The four assessment templates extend `layouts/workspace.html`, place content in declared
   layout blocks, use shared macros, contain no inline `style=` attributes, and load only shared
   bundles plus `assessments.css`.
4. A synthetic route test proves the index, results, dashboard, and history pages return
   populated HTML with the expected `ce-layout`/`h1`/content markers; a 200 response alone is
   insufficient.
5. A synthetic upload example proves filename sanitization, extension rejection, delegation to
   `views.process`, and transient upload cleanup. Fixtures are generated in code; no workbook,
   CSV, student name, or SIS ID is written to the repository.
6. Redirects, single downloads, ZIP downloads, and traversal/missing-run 404s map correctly
   through FastAPI.
7. The presentation contract passes, `api/requirements.txt` and
   `docs/contracts/canvas-transport-owners.json` are unchanged, and no module under
   `api/dataforge/` imports a web framework.
8. Read-only rendered verification loads `/assessments`, a populated results/dashboard state,
   and history through the local server with lifespan disabled. Confirm content is visible,
   no new browser console errors/warnings occur, the viewport does not overflow, and no Canvas
   or external-AI activity occurs.

## Explicit non-goals

- Student matching, SIS coverage, or any join to Canvas users; slice 3.
- Group proposal, no-data placement, tier validation, or Canvas group writes; slice 4.
- Retiring `NameAnonymizer` or re-keying snapshots; slice 5.
- MCP exposure or product-guide changes; slice 6.
- A `groups.html` page, a second settings page, a standalone Flask process, or a new
  dependency.
- Canvas writes, grades, comments, external AI, scheduled work, or operation-ledger entries.

## Stop conditions

- Any route or template needs a Canvas mutation or a transport-owner entry.
- The adapter requires changing DataForge parser/view logic or adding a framework import to
  `api/dataforge/`.
- A rendered route returns an empty shell, has a new browser error, or needs a second navigation
  slot to be understandable.
- Upload handling would persist raw assessment data in the repository or outside the workspace
  zones defined by slice 1.
- The route contract or presentation registry exposes the grouping page or a second settings
  surface.

## Named verification gate

```powershell
py -m pytest api/tests/webui/routes/test_assessments.py api/tests/test_route_contract.py api/tests/test_presentation_contracts.py -q
py -m pytest api/tests -q
git diff --check
```

Then perform the bounded rendered verification named in acceptance criterion 8. Report the
traffic light, changed files, test counts, rendered routes, browser-console result, deviations,
and unresolved decisions here before senior acceptance.

## Execution result

**Traffic light:** GREEN. The FastAPI adapter, CE-native templates, More-menu entry, upload
staging, endpoint map, and route/presentation contracts are complete. `api/dataforge/` remains
framework-free; the Canvas transport-owner contract and dependency manifest are unchanged.

**Changed files:** `api/webui/routes/assessments.py`; four assessment templates;
`api/webui/static/pages/assessments.css`; `api/webui/server.py`; the More-menu partial;
`api/webui/README.md`; route/presentation contracts; and
`api/tests/webui/routes/test_assessments.py`.

**Verification:** focused gate `21 passed`; full API suite `2056 passed`; `git diff --check`
passed. Browser verification used the local server with lifespan disabled and synthetic,
in-memory run state only: `/assessments`, `/assessments/results/browser-run`,
`/assessments/dashboard/browser-run`, and `/assessments/history` all rendered expected
content, had no horizontal overflow, and reported zero browser console warnings/errors. The
temporary server and synthetic workspace were stopped/cleaned after verification.

**Deviations:** none. **Unresolved decisions:** none for this slice.
