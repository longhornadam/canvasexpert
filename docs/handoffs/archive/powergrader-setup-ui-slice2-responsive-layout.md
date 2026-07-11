# DeepSeek Toyota handoff: PowerGrader responsive setup workspace

## Status and authority

This is **slice 2 of 2** for the approved PowerGrader setup-screen UI upgrade. It is
dependent on Ferrari/user acceptance of
`powergrader-setup-ui-slice1-visibility-state.md`.

Do not begin this handoff merely because slice 1 has a commit. Begin only after
Ferrari or the user explicitly accepts slice 1 and authorizes slice 2. Implement this
handoff in one commit, then stop and report evidence. Do not archive either handoff.

The product behavior, layout hierarchy, responsive breakpoints, safety boundaries,
and verification oracle are decided below. The implementer may choose only local CSS
syntax and equivalent private markup details that cannot alter those decisions.

Work on `dev`. Preserve and do not stage unrelated worktree changes.

## Objective

Replace the narrow, 680px-centered PowerGrader setup card with a bounded wide,
responsive workspace that uses desktop space to shorten and clarify the setup flow.

The finished screen must present three sequential sections:

1. Choose work: Course and Assignment.
2. Choose how to grade: the three existing routes and privacy disclosure.
3. Configure and start: compact fast-mode setup or two-column AI setup, followed by
   one clear action footer.

This is a setup-page layout change only. It must not change backend behavior, form
payloads, mode semantics, safety wording, module/search behavior, or the grading queue.

## Approved desktop composition

Use this information architecture at wide desktop sizes:

```text
PowerGrader
Grade one assignment...

┌─ 1. Choose work ──────────────────────────────────────────────────────┐
│ Course (about 35%) │ Assignment (about 65%)                          │
│                    │ Search all assignments │ Modules                │
│                    │ Assignment selector                            │
└──────────────────────────────────────────────────────────────────────┘

┌─ 2. Choose how to grade ─────────────────────────────────────────────┐
│ Grade myself │ Prepare for my AI chat │ Draft-score with OpenRouter │
│ Privacy and review details                                           │
└──────────────────────────────────────────────────────────────────────┘

Grade myself:
┌─ 3. Grading setup ───────────────────────────────────────────────────┐
│ Rubric                                              Start grading →  │
└──────────────────────────────────────────────────────────────────────┘

AI routes:
┌─ AI setup ─────────────────────┐  ┌─ Source material ────────────────┐
│ Rubric, persona, model         │  │ Existing files, uploads, text   │
│ Model actions, late watch      │  │ Estimate tokens and cost        │
└────────────────────────────────┘  └───────────────────────────────────┘
│ AI acknowledgment / status                         Start grading →   │

Resume a session — full-width table below
```

Do not add a resume-session sidebar. The session table and AI configuration both need
horizontal room, and a sidebar would reintroduce cramped controls.

## Expected dependency state from slice 1

Before editing, confirm all of these are true:

- `#pg-start-form [hidden] { display:none !important; }` exists in PowerGrader CSS.
- `#pg-ai-options` starts hidden and JS toggles its `.hidden` property.
- `.pg-api-only` elements start hidden and JS toggles their `.hidden` property.
- `#pg-ai-check-wrap` starts hidden and JS toggles its `.hidden` property.
- `#pg-rubric-fast` visibility is controlled by `.hidden`.
- assignment tools remain hidden until module data loads.

If any dependency is missing or materially different, stop. Do not fold a repair for
slice 1 into this commit.

## Read first

- `AGENTS.md`
- accepted slice-1 handoff and its implementation report
- `docs/reference/powergrader-module-map.md`
- `api/webui/README.md`, PowerGrader section
- `api/webui/templates/base.html`, especially the `main_class` block
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/style.css`, only the shared `.page`, `.page-wide`, `.card`,
  form-control, and action primitives
- `api/webui/static/powergrader_setup.css`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader/setup_autoscore.js`
- `api/tests/test_webui_template_contracts.py`

## Exact files to change

- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader_setup.css`
- `api/tests/test_webui_template_contracts.py`
- `api/webui/README.md`
- `docs/reference/powergrader-module-map.md`

Do not change `setup_core.js`, `setup_autoscore.js`, backend Python, route contracts,
shared `style.css`, or any queue file in this slice. The existing IDs and DOM events
are sufficient for the approved layout.

## Required template structure

### 1. Use a PowerGrader-specific wide page shell

At the top of `powergrader_setup.html`, add:

```jinja2
{% block main_class %}page-wide pg-page{% endblock %}
```

Keep the existing title block. CSS will extend `.page-wide` only for this page.

Replace the setup section's inline `max-width:680px;margin:0 auto` with classes:

```html
<section class="card pg-setup-card">
```

Replace the resume section's inline max-width and margins with:

```html
<section class="card pg-sessions-card" id="pg-sessions-card" style="display:none">
```

Its inline `display:none` is retained because `loadSessions()` currently owns that
state via `card.style.display`. Do not migrate session visibility in this slice.

### 2. Create a real page header

Inside `.pg-setup-card`, wrap the title and current introductory paragraph in
`.pg-setup-header`.

- Change the page title from `<h2>` to one `<h1>` with text `PowerGrader`.
- Preserve the introductory sentence and its wording exactly.
- Do not add decorative icons, gradients, illustrations, badges, or invented help
  text.

### 3. Section 1: Choose work

Wrap Course and Assignment in a section with:

```html
<section class="pg-step pg-step-work" aria-labelledby="pg-step-work-title">
```

Add a visible section heading `1. Choose work` using ID `pg-step-work-title`.

Inside it, use `.pg-work-grid` with two children:

- `.pg-field.pg-course-field`
- `.pg-field.pg-assignment-field`

At desktop width, Course is approximately 35% and Assignment 65%.

Correct the current nested-label markup while preserving control IDs:

- use `<label for="pg-course">Course</label>` before `#pg-course`;
- use `<label for="pg-assignment">Assignment</label>` before the assignment tools;
- change `.pg-assignment-group-control` from a `<label>` nested inside the outer
  Assignment label to a neutral container;
- inside that container use `<label for="pg-assignment-group-by">Modules</label>`;
- give `#pg-assignment-search` an accessible label, either a visually hidden
  `<label for>` or `aria-label="Search all assignments and quizzes"`;
- keep the visible placeholder `Search assignments...`;
- keep the unsupported-quiz hint immediately after `#pg-assignment`.

Preserve exactly:

- all course options and Jinja expressions;
- `#pg-course`, `name="course_id"`, and `required`;
- `#pg-assignment-tools` and its initial `hidden` state;
- `#pg-assignment-search`;
- `#pg-assignment-group-by` and its `Last 3 modules` option;
- `#pg-assignment`, `name="assignment_id"`, `required`, and `disabled`;
- `#pg-assignment-unsupported-hint` and its wording.

### 4. Section 2: Choose how to grade

Wrap the existing route selector and safety disclosure in:

```html
<section class="pg-step pg-step-route" aria-labelledby="pg-step-route-title">
```

Add heading `2. Choose how to grade` with ID `pg-step-route-title`.

Keep the existing three radio-card labels, values, default checked state, disabled
OpenRouter state, descriptions, and class hooks. Remove the old duplicate inline
`Choose how to grade` `<strong>`.

Keep `#pg-safety-popout` directly after `.pg-route-grid` within this section. Preserve
all privacy wording exactly. Do not shorten, paraphrase, hide, or move safety wording
into tooltips.

### 5. Section 3A: Grade-myself configuration

Turn `#pg-rubric-fast` into a semantic configuration section with classes:

```html
<section id="pg-rubric-fast" class="pg-step pg-configuration pg-configuration-fast"
         aria-labelledby="pg-fast-title">
```

Add heading `3. Grading setup` with ID `pg-fast-title`.

Inside, use `.pg-fast-row` so the rubric label/select gets the flexible width and the
existing folder button remains compact. Preserve:

- `#pg-rubric-fast-sel`;
- `name="rubric_name"`;
- all rubric options;
- the `data-open-path` button behavior;
- the optional-reference hint wording.

Do not add controls to fill space.

### 6. Section 3B: AI configuration

Turn `#pg-ai-options` into:

```html
<section id="pg-ai-options" class="pg-step pg-configuration pg-configuration-ai"
         aria-labelledby="pg-ai-title" hidden>
```

Add heading `3. AI setup and source material` with ID `pg-ai-title`.

Inside it, add `.pg-ai-grid` with two subtle bordered panels. These are not nested
`.card` components and must not use the global card shadow.

Left `.pg-ai-settings` panel:

- panel heading `AI setup`;
- existing AI rubric control and folder button;
- existing persona control and folder button;
- existing `.pg-api-only` model label and model picker;
- existing `.pg-model-actions.pg-api-only`;
- existing `#pg-late-watch-wrap.pg-api-only`.

Right `.pg-source-box` panel:

- all existing Source material content and wording;
- source-folder button;
- response type;
- source-file multi-select;
- hidden `source_files_json` input;
- local file uploads;
- pasted source text;
- estimate action/status/panel.

Preserve every existing ID, `name`, `accept`, Jinja expression, initial hidden state,
and `data-open-path`. Do not move the estimate controls out of Source material.

### 7. Action footer

Replace the current generic inline-styled `.actions` wrapper with
`.pg-start-actions` containing:

- `#pg-ai-check-wrap` as the flexible left side, retaining its slice-1 hidden state,
  exact wording, and `#pg-ai-check`;
- `.pg-start-primary` as the right side, containing `#pg-start-btn` and
  `#pg-start-status`.

Keep the action footer after both alternative configuration sections and before
`#pg-privacy-run`. There must be only one submit button.

Do not make the footer sticky; it must never obscure source fields or privacy output.

### 8. Resume sessions

Keep Resume sessions below the setup card. Do not convert it into a sidebar or cards.

Wrap the existing table in:

```html
<div class="pg-sessions-scroll">
```

Preserve `#pg-sessions-card`, `#pg-sessions-tbody`, table columns, session-rendering
markup, and Resume links. Remove table width/collapse/font inline styles and move them
to PowerGrader CSS. Header-cell alignment may move from inline style to CSS without
changing column order.

## Required CSS behavior

Implement only in `powergrader_setup.css`; do not edit global `style.css`.

### Page width and card measure

- `.pg-page`: width `100%`, maximum width between `1160px` and `1200px`; use
  `1180px` unless an existing token makes that impossible.
- Preserve the shared page's 24px desktop padding.
- `.pg-setup-card`: 24px desktop padding.
- `.pg-sessions-card`: same width as setup card, 16px top separation, no extra
  competing max width.
- Do not exceed `1240px` maximum content width.

### Visual hierarchy

- `.pg-setup-header h1`: 20-24px, existing display font, compact bottom margin.
- `.pg-setup-header` ends with 20-24px spacing before Section 1.
- `.pg-step + .pg-step`: use spacing plus a subtle top border; do not wrap each step
  in another shadowed card.
- Section headings: 14-16px, semibold/bold, using existing ink variables.
- Use existing CSS variables for background, borders, text, warning colors, accents,
  and dark mode. Do not hard-code a new light-only palette.

### Desktop grids

At widths above `980px`:

- `.pg-work-grid`:
  `grid-template-columns: minmax(260px, .75fr) minmax(0, 1.45fr)` or an equivalent
  35/65 ratio; gap 20-28px.
- `.pg-route-grid`: exactly three equal columns; gap 10-14px. Cards align to the
  tallest route but should have no arbitrary fixed or minimum height.
- `.pg-safety-body`: three equal columns with 14-20px gap when open; paragraphs use
  zero bottom margin in the grid.
- `.pg-ai-grid`:
  `grid-template-columns: minmax(300px, .85fr) minmax(0, 1.15fr)` or equivalent;
  gap 16-24px; align items to start.
- `.pg-ai-settings` and `.pg-source-box`: subtle border, shared alternate-surface
  background, 14-18px padding, 8-10px radius; no box shadow.
- `.pg-start-actions`: flex or grid with acknowledgment consuming available width and
  `.pg-start-primary` compact and right-aligned.

### Assignment controls

- Assignment tools stay one row when space permits.
- Search flexes wider than Modules.
- Modules label and select remain compact.
- Do not make either select narrower than its readable contents.
- Hidden assignment tools must remain `display:none` through the slice-1 rule.

### Fast configuration

- Keep the fast-mode rubric area one compact horizontal band on desktop.
- The rubric select owns the flexible width.
- The folder button must not float; use flex/grid alignment.
- Remove reliance on `.pg-inline-open { float:right; }` for controls inside the new
  layout. Equivalent non-floating layout is required for both fast and AI panels.

### Action emphasis

- Keep the primary button's existing global color and disabled state.
- It must be visually easy to find at the lower right on desktop.
- Do not make it fixed or sticky.
- On a typical 1440x900 viewport in `Grade myself`, the start action should be visible
  without page scrolling once the top navigation is accounted for.

### Responsive breakpoints

At `max-width: 980px`:

- `.pg-work-grid` becomes one column.
- `.pg-ai-grid` becomes one column.
- route cards may remain three columns if they fit without overflow.
- safety details may become one or two columns; they must not overflow.

At `max-width: 760px`:

- reduce `.pg-page` padding to 12-16px;
- reduce card padding to 16px;
- `.pg-route-grid` becomes one column;
- `.pg-safety-body` becomes one column;
- assignment tools stack vertically and both controls use full width;
- `.pg-assignment-group-control` becomes a full-width grid/flex row with its select
  able to grow;
- `.pg-fast-row` stacks;
- `.pg-start-actions` stacks with acknowledgment first;
- `.pg-start-primary` stacks or wraps safely;
- `#pg-start-btn` uses full available width;
- `.pg-sessions-scroll` provides horizontal scrolling and the table has a readable
  minimum width rather than crushing columns.

No horizontal page overflow is allowed at 390px viewport width.

## Required source-contract tests

In `test_webui_template_contracts.py`, add or update tests proving:

- the template overrides `main_class` with `page-wide pg-page`;
- setup and session cards no longer contain the 680px inline max width;
- `#pg-course`, `#pg-assignment`, `#pg-assignment-search`,
  `#pg-assignment-group-by`, all three mode values, `#pg-ai-options`,
  `#pg-rubric-fast`, `#pg-start-btn`, and `#pg-sessions-tbody` still occur exactly
  once;
- Course, Assignment, and Modules use explicit `for` labels and the Assignment
  area no longer nests a label inside another label;
- the AI acknowledgment remains after the fast/AI configuration alternatives and
  before the start button;
- CSS contains the 1180px-class page cap, desktop work/AI grids, and both required
  responsive breakpoints.

Use structural assertions that explain the contract when they fail. Do not assert
the entire template as one large string and do not hard-code a developer path.
Source-text tests are not runtime proof.

## Documentation updates

In `api/webui/README.md`, update the PowerGrader setup description to state that the
setup page uses a wide responsive workspace with:

- side-by-side course/assignment selection on desktop;
- mode-aware fast versus AI configuration;
- course-wide search and module filtering unchanged.

In `docs/reference/powergrader-module-map.md`:

- update line-count snapshots for changed implementation files;
- add template/CSS ownership for responsive setup layout and action footer;
- preserve the existing module/search ownership notes.

Do not turn either document into an implementation diary.

## Behavior and safety invariants

- No form ID, field name, radio value, submitted value, or endpoint changes.
- No backend or persistence changes.
- Module dropdown still defaults to `Last 3 modules`.
- Assignment search still scans all course assignments and quizzes regardless of the
  selected module and clearing search restores the selected-module view.
- Quizzes remain visible but disabled with the existing honest unsupported wording.
- `Grade myself` remains local and skips AI packet creation.
- AI modes retain the exact acknowledgment and privacy wording.
- AI routes still auto-open privacy details; fast mode closes them.
- Start-button gating remains unchanged.
- OpenRouter model picker, live model loading, price text, late-watch state, source
  selection, uploads, pasted text, estimates, and privacy strip remain functional.
- Light and dark themes remain usable.
- No Canvas write or external AI request occurs during verification.

## Forbidden changes

- Do not edit `style.css`, `base.html`, setup JavaScript, backend Python, route tests,
  queue templates/scripts, or `LLM_Modules/*_Base.md`.
- Do not redesign the top navigation.
- Do not add a sidebar, wizard pages, tabs, accordions around source material, sticky
  action bars, icons, gradients, animations, or new dependencies.
- Do not shorten, paraphrase, hide, or weaken privacy/pseudonymization wording.
- Do not add filler controls or explanatory content merely to occupy space.
- Do not alter Canvas reads/writes, OpenRouter behavior, session creation, scheduled
  jobs, grading, or push behavior.
- Do not commit screenshots containing private course/session information.
- Do not touch or stage unrelated worktree files.

## Required automated verification

Run exactly:

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_powergrader_module_picker.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_late_catchup.py api/tests/test_route_contract.py
git diff --check
```

All must pass. A source-text test is evidence only; it cannot substitute for the
rendered checks below.

## Required rendered-app verification

Launch the normal app with `cd api; py qf_ui.py`. Use read-only interactions on
`http://127.0.0.1:8765/powergrader`. Do not start a session, send anything to
OpenRouter, or write to Canvas.

### Viewports

Verify at all three widths:

- Desktop: 1440x900 or wider.
- Intermediate: approximately 900x900.
- Mobile: 390x844.

### Desktop checks

- Page content is centered and approximately 1180px wide when viewport permits.
- Course and Assignment are side by side at the approved ratio.
- Route cards are three equal columns without artificial fixed height.
- Fast-mode rubric is compact and the start action is visible without scrolling at
  1440x900.
- After selecting a course, assignment search and Modules align without overflow.
- Searching still expands to course-wide results and clearing search restores the
  selected module view.
- Packet mode shows a two-column AI setup/source layout; OpenRouter-only controls are
  absent.
- Assisted mode, when locally available, shows model and late-watch controls without
  overlap; the model list panel overlays above adjacent content.
- Open privacy details render in three readable columns.
- Resume sessions uses the full page width below the setup card.

### Intermediate checks

- Course/Assignment and AI setup/source stack to one column at the 980px breakpoint.
- Route cards remain readable with no clipped text or overflow.
- No control exceeds the card width.

### Mobile checks

- One-column layout throughout.
- No horizontal page overflow at 390px.
- Route cards, folder buttons, module selector, file input, textarea, acknowledgment,
  and start button remain reachable and readable.
- Sessions table scrolls inside its wrapper without widening the page.

### Functional checks in every relevant mode

- Hidden-state matrix from slice 1 still passes.
- Folder buttons still carry valid `data-open-path` behavior; do not click if doing
  so would expose private paths in evidence.
- Native selects remain keyboard-accessible.
- Browser console has zero new errors or warnings from Canvas Expert scripts.
- Required globals remain initialized:
  - `window.CE_POWERGRADER_SETUP` exists;
  - `typeof window.CE_POWERGRADER_SETUP.currentMode === "function"`;
  - `typeof window.CE_POWERGRADER_SETUP.syncStartEnabled === "function"`.

Do not include real course, assignment, rubric, path, or session names in the report.

## Acceptance criteria

- The rendered screen matches the approved composition and responsive behavior.
- Desktop space is used up to the bounded 1180px measure without becoming full-width.
- Fast mode is materially shorter and clearer than the current 680px layout.
- AI modes use two useful columns on desktop and a safe single column on smaller
  screens.
- Progressive disclosure, safety wording, module/search behavior, and form submission
  contracts are unchanged.
- All automated and rendered checks pass.
- Only the five authorized files are committed.
- No private data, Canvas write, session start, or external AI request is produced.

## Required implementer reply

Report and stop after the one commit. Include:

1. Commit hash and exact changed files.
2. Concise DOM/layout summary.
3. Automated test command and pass count.
4. Desktop, intermediate, and mobile verification results.
5. Mode-by-mode visibility and layout results.
6. Course-wide search and module-restoration result without private names.
7. Required global-state checks and exact console error/warning count.
8. Explicit confirmation that no Canvas write, session start, or external AI request
   occurred.
9. Explicit confirmation that unrelated worktree changes were left unstaged.

## Mandatory escalation / stop conditions

Stop without guessing if:

- slice 1 has not been explicitly accepted or its expected dependency state differs;
- any named ID, class, form name, radio value, or script load order differs from this
  handoff;
- the layout requires a JavaScript, backend, shared-style, or public-contract change;
- existing safety wording or visibility behavior conflicts with the required layout;
- responsive behavior cannot be achieved without page-level horizontal overflow;
- the model panel is clipped by the new grid and fixing it requires behavioral JS;
- a prescribed test cannot prove its claimed contract;
- a regression appears in module loading, course-wide search, model selection,
  estimates, source materials, acknowledgment gating, or session start gating;
- rendered verification at all three viewports cannot be performed.

Do not archive either handoff or begin unrelated work. Ferrari or the user owns final
acceptance.
