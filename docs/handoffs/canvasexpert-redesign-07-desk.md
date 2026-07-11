# Toyota handoff 07: Desk launch and cross-course command surface

## Objective

Replace `/` with the professional full-width Desk: Start, Continue, Attention, Prepared,
Receipts, and course field. Creation is equal to reactive work.

## Files

- `api/webui/routes/pages.py::dashboard`
- `api/webui/templates/dashboard.html`
- New `api/webui/templates/workbench_base.html`
- New `api/webui/templates/_workbench_header.html`
- New `api/webui/static/desk.js`
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- New `api/tests/test_desk_routes.py`
- `api/webui/README.md`

## Shell and data

`workbench_base.html` extends `base.html`, opts into the component vocabulary through
body/main classes, readiness partial,
full-width main, and shared context. It does not duplicate the document head, global
toast/open-path behavior, theme key, or shared synchronous scripts.
`workbench.css` is already loaded once by `base.html`; Workbench base must not add another
stylesheet tag. Add a once-only source assertion.

It overrides the slice-01 `app_header` and `status_strip` blocks. The new header contains
brand/home, Desk, Create, Grade, Students, Automations, compact system/settings access,
and the existing theme-toggle ID/behavior. It must not render fake active states or remove
legacy navigation from legacy pages. `scripts_extra` loads `desk.js` after Desk markup.
Workbench base emits the process CSRF token in a meta element; Desk sends it for scan,
ignore, snooze, and complete. It is absent from URLs, storage, logs, and legacy pages;
the server also checks same-origin and loopback.

Desk data comes from `/api/work`, `/api/receipts`, `/api/readiness`, and active-course
config. Initial render is immediate from local data; Scan refreshes asynchronously. Slice
07 does not call `/api/operations` because that route does not exist until slice 10;
Prepared renders a static honest “No prepared operations yet” state with no failed fetch.

Start actions call `CE_CONTEXT.setFocus` / `setTargets` for only the scope explicitly chosen
on Desk, then navigate to the existing unchanged route. Without JavaScript, links are plain
route links and use already-persisted context; no new query convention is introduced.
Start actions open:
Assignment, Quiz, Quick column, Page, Rubric, PowerGrader, Gradebook, Roster, Reports,
Downloads, and Routines. Continue/Attention open registry `resumable_url`. Receipts
are real receipt projections, not legacy activity relabeled.

No redundant language such as “Teacher Jobs.” Use Work, Start, Continue, Attention,
Prepared, Receipts, and terse professional copy.

## Compatibility

Tokenless onboarding redirect remains. Existing dashboard route is `/`; no route removal.
Legacy `/api/activity` remains. Do not change any target workflow page in this slice.

## Verification

```powershell
node --check api/webui/static/desk.js
py -m pytest api/tests/test_desk_routes.py api/tests/test_work_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Rendered at 1920/2560, both themes: full width, no page horizontal scrollbar, Start links,
empty and populated local fixtures, async scan failure, ignore/snooze, readiness, keyboard
focus, zero console errors. Lifespan off; no Canvas write/AI request.

Stop if any panel needs invented/mock data or if an existing route must be removed.

## Required implementer reply

One commit; report hash/files, commands/pass counts, Desk fixture states, 1920/2560 and
theme evidence, exact console count, and no Canvas write/AI/routine execution.
