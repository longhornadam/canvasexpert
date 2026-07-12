# Execution brief: make the Workbench header belong to the Workbench

Status: **ready for implementation**

Risk: **low**

Executor: **Luna**

## Outcome

The shared header on Desk, Course Expert, Gradebook, PowerGrader, and Roster uses the
same restrained paper/graphite visual language as the Workbench beneath it. Teachers
retain the same destinations, theme control, keyboard behavior, and route contracts,
but the old bright-blue application bar no longer visually fights the newer surfaces.

## Locked decisions

- Change only the shared Workbench header. Legacy pages that inherit the default header
  from `base.html` keep the existing blue navigation and dropdowns.
- Keep `_workbench_header.html` as the single markup owner. Do not fork headers per
  page, introduce a component framework, or add JavaScript.
- Keep the current destinations and labels: CanvasExpert/Desk/Create/Grade/Students/
  Automations/Settings plus the existing theme toggle.
- Add a truthful active state from existing server context: Desk for `/`; Create for
  `nav_section == "create"`; Grade for `"grade"`; Students for `"manage"`;
  Automations for `"automate"`; Settings for `"settings"`. Use `aria-current="page"`
  on the matching link and a stable class for styling.
- Desktop treatment is a compact paper/ink header with a subtle rule, smaller brand,
  quieter navigation, and a restrained Workbench accent for the active destination.
  It must not reuse the bright-blue fill, heavy active stripe, or old oversized type.
- Dark mode uses the Workbench graphite palette and keeps sufficient contrast. The
  readiness strip remains a distinct status band directly below the header.
- At narrow widths, use a CSS-only two-row composition: brand and settings/theme on the
  first row, navigation on the second. Navigation may wrap or own horizontal scrolling,
  but the document must not overflow and no destination may become inaccessible.
- Preserve `topbar`, `brand`, `topbar-right`, `topbar-settings-link`, `theme-toggle`,
  and `theme-toggle`'s existing ID/ARIA contract for compatibility. Add scoped classes
  or attributes rather than changing global legacy selectors.
- All new rules live under `.ce-workbench-header` in `workbench.css`. Do not restyle
  `.topbar` globally or alter `style.css` unless the repository proves a scoped rule
  cannot override it.

## Scope

- `api/webui/templates/_workbench_header.html`
  - add active-route/`aria-current` state without changing destinations;
  - preserve the theme control markup and accessible names.
- `api/webui/static/workbench.css`
  - replace the small legacy-colored Workbench overrides with the complete scoped
    desktop, dark-theme, focus, active, and narrow header composition.
- `api/tests/test_webui_template_contracts.py`
  - add focused boundaries proving the shared header stays Workbench-only, keeps all
    links/theme contracts, provides server-derived active state, and owns a narrow rule.
- At closure, update `docs/reference/operation-ledger-release-status.md` and archive
  this handoff in the same implementation commit.

## Out of scope

- Changing the default `base.html` header, its dropdowns, legacy routes, or global
  `.topbar` design.
- Changing navigation information architecture, destinations, names, permissions, or
  adding a hamburger/menu script.
- Redesigning readiness, Work rails, Summary panels, page bodies, logos, or typography
  outside the scoped header.
- Route/backend changes, persistence, settings behavior, or theme-key changes.

## Reference pattern and routing

- Shared markup owner: `api/webui/templates/_workbench_header.html`
- Inheritance seam: `api/webui/templates/workbench_base.html`
- Scoped design tokens and current overrides: `api/webui/static/workbench.css`
- Legacy styles to override without modifying: `api/webui/static/style.css::.topbar`
- Test pattern: `api/tests/test_webui_template_contracts.py`
- Read project-local `TOOLS.md` before using broad manual inspection.

## Implementation requirements

1. Add the route-aware active classes and `aria-current` attributes in the shared
   partial using `request.url.path` and existing `nav_section`; do not add route data.
2. Implement the compact light/dark Workbench header entirely through scoped CSS.
   Explicitly cover the brand/logo, navigation links, active/hover/focus states,
   Settings link, and theme toggle so legacy `.topbar` color assumptions do not leak.
3. Add one responsive breakpoint that creates the two-row narrow header while keeping
   every link and the toggle reachable. Keep header and navigation overflow internal.
4. Preserve all existing IDs/classes consumed by theme initialization and all
   Workbench template inheritance.

## Verification

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Rendered verification uses a lifespan-disabled local server and makes no Canvas write,
AI request, routine run, PowerGrader session, or private-data action.

- Load `/`, `/course-expert`, `/gradebook`, `/powergrader`, and `/roster` once across
  light/dark desktop checks. Confirm the shared header, correct active destination,
  readiness seam, theme control, unchanged route content, no page overflow, and zero
  new console warnings/errors.
- Check `/course-expert?tab=quiz` and `/powergrader` at approximately 760x900 in the
  opposite themes. Confirm the two-row header, reachable navigation/settings/toggle,
  internal navigation wrapping/scrolling, and no document overflow.
- If no safe existing PowerGrader queue session is available, do not create or inspect
  private session data merely to render `powergrader_queue.html`; rely on the shared
  inheritance/template contract and record the unavailable live route.

## Stop conditions

Stop with RED rather than guessing if:

- A named route does not inherit `workbench_base.html` as expected.
- Active navigation requires new backend context or route changes.
- A usable narrow header requires new JavaScript or a navigation redesign.
- The scoped rules cannot avoid changing legacy/non-Workbench headers.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **not started**
- Changes are uncommitted
- Files changed: none
- Verification commands and pass/fail/skip counts: not run
- Rendered routes checked: not run
- Deviations from the brief: none
- Remaining blocker or decision: none
