# Execution brief: Desk operational-console alignment

Status: **ready for implementation**

Risk: **low**

Executor: **Luna**

## Outcome

Make `/` feel like the operational Desk study at
`%USERPROFILE%\.codex\visualizations\2026\07\10\019f4d61-ebcc-78a0-b981-45d66ab59d39\canvasexpert-desk.html`: an information-dense work console rather than a card dashboard. Teachers can start existing workflows from four compact lanes, see Continue and Attention as ledger rows, keep explicit course scope, and see truthful Prepared and Receipts projections.

This is a UI-composition batch. It makes the already available local summaries legible without changing what Desk is authorized to do.

## Locked decisions

- Preserve the Desk route, all eleven current launch destinations, `CE_CONTEXT` scope behavior, Scan, Ignore, Snooze, Complete, and the existing local mutation guards exactly as they are.
- Replace the large Tools card grid with four compact launch groups, in this exact grouping:
  - **Create:** Assignment, Quiz, Quick column, Page, Rubric.
  - **Grade:** PowerGrader, Gradebook.
  - **Manage:** Roster, Reports, Downloads.
  - **Automate:** Routines.
- Treat the mockup as a visual and information-architecture reference, not a data contract. Do **not** add the mockup-only From library, Batch score, Import results, Course info, Run now, or synthetic counts/statuses.
- Keep course selection as the existing explicit course-scope control. Do not render a per-course state matrix: the current Desk projection does not authoritatively provide that view, and no backend or persistence expansion is authorized.
- Prepared uses only the existing PII-minimized `operation_ledger.operations.list_operations_pii_minimized()` / `GET /api/operations` shape. Show operations whose status is `prepared` or `reviewed`, with kind, status, and target count only. It is a passive ledger—no new prepare/review/apply action or invented operation detail route.
- Initial Prepared data must be server-rendered from that same minimized projection, just as jobs and receipts are server-rendered. The browser refreshes all three existing read-only local projections after load.
- Keep Prepared and Receipts as a compact two-column lower rail; Continue and Attention are the upper operational ledger. Empty states remain explicit and honest.
- Do not surface course IDs, assignment IDs, operation IDs, source paths, names, student data, operation payloads, target keys, or any Canvas detail. No new Canvas read/write or AI request is allowed.

## Scope

- `api/webui/routes/pages.py::dashboard`: add the initial minimized operation projection to the render context; import the existing ledger operation helper using the project’s normal route-module style.
- `api/webui/templates/dashboard.html`: restructure only Desk markup around the four launch groups, a compact scope/status/scan header, the two ledger sections, and Prepared/Receipts rail. Preserve existing stable IDs, `data-desk-start`, current links, ARIA labels, and JSON boot data; extend that boot data with operations.
- `api/webui/static/desk.js`: preserve every current mutation and scope behavior. Track/render the filtered Prepared projection, and include `/api/operations` in the existing read-only local refresh with failure behavior that retains the last rendered local view.
- `api/webui/static/workbench.css`: replace Desk-only card-dashboard rules with responsive operational-console styles modeled on the Desk study: rule-led sections, narrow launch rows, color marks, ledger rows, and lower rail. Keep all styles scoped to `.ce-desk-shell`; do not alter other workbench surfaces or global typography/header behavior.
- `api/tests/test_desk_routes.py`: update render contracts for the new truthful Prepared server projection, including empty and populated minimized-operation cases; retain existing PII/local-safety assertions and do not introduce visual/source snapshot tests.

## Out of scope

- Any route, backend domain model, operation adapter, Canvas API call, work-registry schema, course-state endpoint, persistence migration, or workflow-page redesign.
- New summary labels that reveal private record data or imitate unavailable per-course activity.
- Changes to the unrelated dirty worktree files.
- Desktop/sidebar/header redesign outside the Desk content area.

## Reference pattern and routing

- Visual reference: `%USERPROFILE%\.codex\visualizations\2026\07\10\019f4d61-ebcc-78a0-b981-45d66ab59d39\canvasexpert-desk.html` — read only its escaped `#ce-desk-study` fragment (around source lines 751–844).
- Current Desk owners: `api/webui/routes/pages.py::dashboard`, `api/webui/templates/dashboard.html`, `api/webui/static/desk.js`, and the Desk block in `api/webui/static/workbench.css`.
- Existing safe Prepared projection: `api/operation_ledger/operations.py::list_operations_pii_minimized` and `api/webui/routes/operations.py::list_operations_route`.
- Existing safety/render test: `api/tests/test_desk_routes.py`.
- Read `AGENTS.md` and project-local `TOOLS.md` before broad inspection. Do not read unrelated historical handoffs.

## Implementation requirements

1. Keep the current compact Desk toolbar’s real selection and scan controls, but make it a visual Desk status/control strip rather than a detached dashboard toolbar. Its state message stays visible and usable.
2. Render all eleven existing start links as semantically labelled links in the four locked launch groups. Preserve `data-desk-start` so selecting a scope continues to be applied before navigation. Use lightweight directional/arrow affordances only; never replace routes with buttons or mocks.
3. Render Continue and Attention as ordered ledger rows with their existing action link and local action controls. Maintain each current local action and focus restoration. Use no new data fields.
4. Add a Prepared list to initial data and browser state. Filter it to `prepared` and `reviewed`; show only the minimized operation kind, status, and singular/plural target count. When it is empty, use `No prepared operations.`
5. Preserve the current receipts data and real receipt links. Group Prepared and Receipts into the locked lower rail, with sensible narrow-screen stacking.
6. Keep dark theme, keyboard focus treatment, and responsive behavior. At the current wide desktop form, the Desk should visibly read as compact horizontal launch lanes + three-column operational body + Prepared/Receipts lower rail, not a panel of large action cards.
7. Update only the smallest focused tests needed for the changed Desk render contract. Do not add brittle source-text or CSS-layout tests.

## Verification

```powershell
node --check api/webui/static/desk.js
py -m pytest api/tests/test_desk_routes.py api/tests/test_work_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Render `/` in the local app at a wide desktop viewport in both themes and at one narrow viewport. Confirm: all eleven start links navigate to their unchanged targets; course selection still affects a start link; Continue/Attention actions remain available; empty and populated Prepared states are truthful; Scan failure keeps the prior local view; zero new browser-console errors. Do not invoke a Canvas write, a scan, an AI call, or a routine run as part of verification.

## Stop conditions

Stop with RED rather than guessing if:

- The minimized operation projection cannot be safely used from the page render or its shape contradicts this brief.
- A desired mockup element requires a new course-state endpoint, unredacted operation data, a new persistence shape, or a Canvas call.
- A current launch target or Desk safety/mutation behavior would need to change.
- An unrelated worktree change blocks the scoped files.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — implementation, focused automated checks, and senior rendered-route acceptance are complete.
- Commit: changes are uncommitted (per instruction).
- Files changed: `api/webui/routes/pages.py`, `api/webui/templates/dashboard.html`, `api/webui/static/desk.js`, `api/webui/static/workbench.css`, `api/tests/test_desk_routes.py`, and this handoff.
- Verification: `node --check api/webui/static/desk.js` passed; `py -m pytest api/tests/test_desk_routes.py api/tests/test_work_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py` passed (25 passed); `git diff --check` passed.
- Rendered routes checked: senior acceptance checked `/` wide/light, wide/dark, and narrow/dark after restarting the local app. All 11 locked launch links, Continue actions, prepared empty state, responsive no-horizontal-overflow condition, and zero new browser-console errors were confirmed. The focused route test covers the populated minimized-operation render. No scan, Canvas write, AI call, or routine run was invoked.
- Deviations: none in implementation scope. The server boot projection intentionally drops operation IDs before serialization; Prepared renders only kind, status, and target count.
- Remaining blocker or decision: none. Existing launch, scope, and local-action behavior was preserved without invoking mutations.
