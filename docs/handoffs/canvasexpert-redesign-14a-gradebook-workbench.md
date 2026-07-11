# Toyota handoff 14a: Gradebook Workbench composition

## Objective

Convert Gradebook to the Workbench shell after its live-write adapters are accepted.
This is layout/state integration, not another Canvas-write change.

## Files

- `api/webui/templates/gradebook.html`
- `api/webui/static/gradebook.js`
- `api/webui/static/gradebook/{policy,extra_time,extensions,sweep,curves,snapshot}.js`
  only for `CE_CONTEXT` hydration/subscription and ledger summaries; feature behavior and
  ownership do not move
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- `docs/reference/gradebook-module-map.md`

## Layout/behavior

Work rail retains Policy & Sweep, Extra-time, Extensions, Curves, Snapshot, and Routines.
The center renders the existing active panel once. Right rail shows explicit focused
course, read-only/current state, real prepared operations, and receipts. Read-only
Snapshot is never styled as a write operation. Routines link/state consumes the shared
adapter without duplicating controls.

Preserve `window.CE_GRADEBOOK`, facade-before-features script order, `?tab=` and hashes,
all critical IDs, source contracts, calendar/extra-time math, and shared review behavior.
Focused course hydrates from `CE_CONTEXT`; Gradebook remains single-course and must not
inherit multi-course write targets.

`gradebook.html` extends `workbench_base.html`; it must not load shared Workbench CSS a
second time. Routines remain their own panel/link and are not absorbed into a gradebook
feature module.

## Verification

```powershell
node --check api/webui/static/gradebook.js
py -m pytest api/tests/test_gradebook_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Render every tab at 1920/2560 and
both themes; deep links, one ID each, context persistence, prepared/receipt hooks, visible
focus, no horizontal page scroll, zero console errors. Use fakes/no live Canvas writes.

Stop if layout would clone panels or if shared target context broadens a Gradebook action.

## Required implementer reply

One commit; report hash/files, commands/pass counts, per-tab/deep-link/context runtime
matrix, ID/global evidence, console count, and no Canvas write/unrelated staging.
