# Execution brief: consolidate readiness into the Workbench header

Status: **ready for implementation**

Risk: **low**

Executor: **Luna**

## Outcome

Workbench pages use one compact piece of application chrome instead of a navigation bar
stacked over a separate readiness bar. Desk begins with its actual controls and Tools,
without a large visible page title that repeats the active `Desk` navigation state.

## Locked decisions

- Move the existing `_readiness_strip.html` instance into `_workbench_header.html`, between
  Workbench navigation and the Settings/theme cluster. There remains exactly one readiness
  root and one readiness script per Workbench page.
- `workbench_base.html` no longer renders readiness through the separate `status_strip`
  block. Legacy pages and the default `base.html` header remain unchanged and do not gain
  readiness.
- Preserve all readiness IDs, `data-*` hooks, `aria-live`, component labels, refresh button,
  degraded details, fetch behavior, and `readiness.js`. This is composition, not logic.
- Desktop is one compact header row. Readiness is a quiet inline instrument cluster, not a
  second dark band. Brand, nav, readiness, Settings, and theme remain reachable.
- In light mode the inline cluster uses the paper-header ink/muted palette; in dark mode it
  uses the graphite-header contrast palette. Ready/attention dots retain their semantic
  colors.
- At intermediate/narrow widths, the header may wrap navigation and readiness into compact
  internal rows. It must not hide status, Settings, the theme control, or navigation, and
  the document must not overflow. Consolidation means one header container, not necessarily
  one physical line on a 760px viewport.
- Degraded readiness details must open as a contained header popover/dropdown or otherwise
  remain readable without stretching the whole page horizontally. Do not add JavaScript.
- Remove Desk's visible intro/hero entirely, including the `Desk` h1 and its now-unused
  intro/kicker/lede styling. The document title and active `Desk` header state provide page
  orientation; `#desk-root` receives an accessible `aria-label="Desk"`.
- Move Course context into the existing Desk toolbar. That single compact row contains:
  course context/select/note, `#desk-local-status`, and the existing Scan button. Preserve
  all IDs, course options, scan behavior, and local-state messages.
- Desk Tools remains the first content panel. Do not change its cards, operational sections,
  grid, work/receipt behavior, or the instrument-language vocabulary just accepted.

## Scope

- `api/webui/templates/_workbench_header.html`
- `api/webui/templates/workbench_base.html`
- `api/webui/templates/dashboard.html`
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- `docs/reference/operation-ledger-release-status.md` at closure
- Archive this handoff in the implementation commit.

## Out of scope

- Backend readiness routes, probe caching, status semantics, `readiness.js`, or refresh
  behavior.
- Default/legacy header markup or styling in `base.html`/`style.css`.
- Navigation destinations, active-state logic, theme storage, Desk data behavior, cards,
  drafting grid, Work rails, Summary, or other page bodies.
- Hamburger menus, new scripts, component systems, persistent preferences, or responsive
  redesign outside the header/Desk control row.

## Reference pattern and routing

- Shared header: `api/webui/templates/_workbench_header.html`
- Current readiness composition: `api/webui/templates/workbench_base.html` and
  `api/webui/templates/_readiness_strip.html`
- Readiness behavior contract: `api/webui/static/readiness.js`
- Header/status/Desk layout: `api/webui/static/workbench.css`
- Desk IDs and behavior: `api/webui/templates/dashboard.html` and
  `api/webui/static/desk.js`
- Test pattern: `api/tests/test_webui_template_contracts.py`
- Read project-local `TOOLS.md` before broad manual inspection.

## Implementation requirements

1. Recompose the partials so the readiness root is a child of `.ce-workbench-header` and
   `workbench_base.html` supplies only the readiness script. Keep legacy base composition
   untouched.
2. Replace the full-width `.ce-status-strip` visual treatment with header-scoped readiness
   rules while retaining generic semantic dot/detail behavior. Ensure global old dark-strip
   declarations cannot win through specificity.
3. Extend the existing responsive Workbench-header rules for the inline cluster. Verify
   intermediate widths as well as the named desktop/narrow sizes; prefer CSS wrapping or
   internal scrolling over hidden controls.
4. Remove the Desk intro markup and dead intro-only CSS. Recompose the toolbar around the
   unchanged course/status/scan controls, preserving all JS selectors and accessible labels.
5. Add focused static contracts for single readiness ownership, header containment, legacy
   isolation, preserved behavior hooks, absence of the visible Desk hero, and compact Desk
   control ownership. Do not duplicate readiness backend tests.

## Verification

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
node --check api/webui/static/readiness.js
node --check api/webui/static/desk.js
git diff --check
```

Rendered verification uses a lifespan-disabled local server and performs no Canvas write,
AI request, routine run, PowerGrader session action, or student-data interaction.

- Load `/`, `/course-expert`, `/gradebook`, `/powergrader`, and `/roster` once across a
  light/dark desktop matrix. Confirm one header, readiness inside it, correct active route,
  exactly one readiness root/script, no separate status bar, no page overflow, unchanged
  page content, and zero new console warnings/errors.
- At `/`, confirm no visible Desk hero/h1; the compact row contains Course context, local
  status, and Scan, followed immediately by Tools.
- Check `/`, `/course-expert?tab=quiz`, and `/powergrader` at approximately 1000x800 and
  760x900 in opposite themes. Confirm header-contained wrapping, readable status items,
  reachable navigation/Settings/theme, contained degraded details, and no document overflow.
- Do not print or capture course names, work items, session names, roster rows, notes, or
  private local content; return structural booleans/counts only.
- If no safe PowerGrader queue session exists, do not create or inspect one merely to render
  its inherited header; record the shared template contract as the available evidence.

## Stop conditions

Stop with RED rather than guessing if:

- Readiness behavior requires duplicate markup or a second script.
- The existing readiness JS cannot operate when its root moves into the header.
- A usable narrow header requires hiding a status/control or adding JavaScript.
- Desk control consolidation changes scan/course/local-state behavior.
- The scoped implementation would alter the legacy header or another subsystem.

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
