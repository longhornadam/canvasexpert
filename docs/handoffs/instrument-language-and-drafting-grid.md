# Execution brief: restore the drafting surface and remove SaaS-style framing

Status: **ready for implementation**

Risk: **low**

Executor: **Luna**

## Outcome

The main Workbench panes again read as precision working surfaces: a subtle drafting
grid sits behind solid controls and cards, while headings describe operational state
without slogans, sales language, or label-plus-subtitle repetition. Functional guidance,
safety warnings, button verbs, validation messages, and confirmation questions remain.

## Locked decisions

- This is an instrument-language correction, not a global copy rewrite. Remove ornamental
  framing and redundant headings only on the shared Workbench surfaces named below.
- Functional verbs remain functional. Do not replace `Continue`/`Review` action links,
  confirmation-dialog questions, error messages, safety warnings, or field guidance just
  because they contain words such as “continue,” “ready,” or “attention.”
- Restore the existing 24px drafting-grid vocabulary rather than inventing a new visual.
  The grid belongs only to central working panes; headers, readiness, rails, Summary,
  forms, cards, tables, and controls retain solid backgrounds.
- Apply one explicit `ce-drafting-grid` marker to these current working panes:
  `ce-course-expert-center`, `gb-content`, `roster-workbench-main`, and
  `pg-workbench-content`. Do not grid the whole page or PowerGrader queue.
- Give marked panes a small consistent inset so the grid remains visible as a work-surface
  gutter around their solid child cards. Preserve existing responsive containment.
- Light and dark grid lines remain deliberately faint. The treatment must not reduce text,
  form, table, or focus contrast.
- Desk keeps a real accessible `h1`, but it becomes simply `Desk`; remove its kicker and
  promotional lede. Operational sections get one heading each, not an eyebrow plus a
  clever sentence.
- Use this exact Desk vocabulary:
  - `Course context`; note `Saved targets are unchanged.`
  - toolbar status starts `Local state.` and refresh success becomes `Local state updated.`
  - `Tools`, `In progress`, `Needs review`, `Prepared`, and `Receipts` as the sole section
    headings;
  - empty states: `No open work.`, `No items need review.`, `No prepared operations.`,
    and `No receipts.`
- Course Expert rail headings become `Tools`, `In progress`, and `Review`; empty rail
  states become `None.` Existing job links and their functional destinations remain.
- PowerGrader keeps `PowerGrader` and its useful mode explanation, but `Your grading work`
  becomes `Sessions`; its duplication warning becomes `Open an existing session instead
  of starting a duplicate.` Lane headings become `Ready to post` and `In progress`, with
  redundant lane descriptions removed. Rail labels match those headings. Empty lane text
  becomes `None.`; loading/error/status counts remain informative.
- Roster's intro becomes one `Roster` heading. Remove the `Rosters` kicker and the paragraph
  that restates the visible lenses and course control.
- Do not turn terse operational language into cryptic abbreviations. Existing field labels,
  tool-card descriptions, privacy wording, and side-effect explanations stay intact.

## Scope

- Templates:
  - `api/webui/templates/dashboard.html`
  - `api/webui/templates/course_expert.html`
  - `api/webui/templates/gradebook.html`
  - `api/webui/templates/roster.html`
  - `api/webui/templates/powergrader_setup.html`
- Browser copy owners:
  - `api/webui/static/desk.js`
  - `api/webui/static/course_expert/work_rail.js`
  - `api/webui/static/powergrader/setup_sessions.js`
- Shared visual owner: `api/webui/static/workbench.css`
- Page-specific CSS may be adjusted only where needed to keep the marked pane/card inset
  and responsive behavior correct.
- Focused regression boundaries: `api/tests/test_webui_template_contracts.py`.
- At closure, update `docs/reference/operation-ledger-release-status.md` and archive this
  handoff in the same implementation commit.

## Out of scope

- Rewriting backend/API messages, confirmation dialogs, onboarding, Settings, validation,
  errors, safety language, or legacy/non-Workbench pages.
- Changing information architecture, feature names, route behavior, data loading, empty
  state logic, job/session classification, or action labels.
- Replacing the existing 24px grid with canvas/SVG/JavaScript, adding animation, or creating
  a theme/design subsystem.
- Redesigning cards, tables, rails, Summary, navigation, or the PowerGrader queue.

## Reference pattern and routing

- Existing grid tokens/rule: `api/webui/static/workbench.css::--ce-grid-line` and
  `.ce-drafting-grid`
- Desk copy/state owners: `api/webui/templates/dashboard.html` and
  `api/webui/static/desk.js`
- Course Expert rail owner: `api/webui/static/course_expert/work_rail.js`
- PowerGrader session owner: `api/webui/static/powergrader/setup_sessions.js`
- Test pattern: `api/tests/test_webui_template_contracts.py`
- Read project-local `TOOLS.md` before using broad manual inspection.

## Implementation requirements

1. Generalize the existing explicit `ce-drafting-grid` rule so all four named panes can
   consume the same light/dark grid token even when their immediate shell differs. Add the
   marker classes in templates; do not target unrelated panes by broad descendant selector.
2. Keep every child card/control solid and legible. Use the smallest pane inset/radius
   needed to reveal the grid, and reconcile page-specific padding at narrow widths.
3. Apply the locked copy changes in template initial states and their JavaScript rerenders
   so refreshes do not restore the old SaaS-style language.
4. Preserve IDs, ARIA relationships, action labels, routes, job/session logic, and script
   order. A single operational heading must continue to label each region accessibly.

## Verification

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
node --check api/webui/static/desk.js
node --check api/webui/static/course_expert/work_rail.js
node --check api/webui/static/powergrader/setup_sessions.js
git diff --check
```

Rendered verification uses a lifespan-disabled local server and performs no Canvas write,
AI request, routine run, PowerGrader session creation, or student-data interaction.

- `/`, `/course-expert?tab=quiz`, `/gradebook`, `/powergrader`, and `/roster` across a
  compact light/dark desktop matrix: confirm locked headings/copy, grid only on named central
  panes, solid cards/controls, correct active route, no page overflow, and zero new console
  warnings/errors.
- `/course-expert?tab=quiz`, `/powergrader`, and `/roster` at approximately 760x900:
  confirm the pane inset/grid survives responsive stacking without document overflow or
  squeezed controls.
- Do not print or capture course names, roster rows, session names, notes, or other private
  local content as verification evidence; return structural booleans/counts only.

## Stop conditions

Stop with RED rather than guessing if:

- The named pane marker changes a page's behavior or requires a layout redesign.
- A locked phrase is also an API/public contract rather than presentation copy.
- Solid form/table/card backgrounds cannot preserve readability over the grid.
- A change would require touching backend state, private data, or another subsystem.
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
