# DeepSeek Toyota handoff: PowerGrader setup visibility state

## Status and authority

This is **slice 1 of 2** for the approved PowerGrader setup-screen UI upgrade.
Implement only this handoff, in one commit, then stop and report evidence. Do not
start slice 2 and do not move this file to `archive/`; Ferrari or the user will
review the diff and runtime evidence before accepting and archiving it.

The product and architecture decisions below are final. This handoff delegates
mechanical implementation, not product judgment.

Work on `dev`. The shared worktree currently contains unrelated engine and handoff
changes. Preserve them and stage only the files authorized below.

## Objective

Make PowerGrader's existing progressive disclosure behave as designed before the
layout is reorganized:

- assignment search and module controls stay hidden until a course's module data
  has loaded;
- AI-only setup stays hidden in `Grade myself`;
- the AI acknowledgment appears only for AI routes;
- OpenRouter-only controls appear only for `Draft-score with OpenRouter`;
- visibility uses one reliable `hidden`-property contract instead of a mixture of
  `style.display`, `[hidden]`, and `display: ... !important`.

This slice must not change page width, visual layout, wording, APIs, session behavior,
or Canvas/AI side effects.

## Confirmed current defect

The screenshot and current source confirm two CSS/state conflicts:

1. `#pg-assignment-tools` has the HTML `hidden` attribute, but
   `.pg-assignment-tools { display:flex; }` overrides the browser's hidden rule.
   Search and Modules therefore appear before a course is selected.
2. `#pg-ai-check-wrap` starts with `style="display:none"`, but
   `.pg-ai-check { display:flex !important; }` wins. The AI acknowledgment therefore
   appears while `Grade myself` is selected.

`setup_core.js::updateRouteMode()` also uses `style.display` for `#pg-ai-options`,
`#pg-rubric-fast`, `.pg-api-only`, and `#pg-ai-check-wrap`, while other setup state
already uses `.hidden`. The mixed contract is the cause; do not paper over individual
elements with more selector specificity.

## Read first

- `AGENTS.md`
- `docs/reference/powergrader-module-map.md`
- `api/webui/README.md`, PowerGrader section
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader/setup_autoscore.js`
- `api/webui/static/powergrader_setup.css`
- `api/tests/test_webui_template_contracts.py`

The setup script load order must remain:

1. `powergrader_setup.js`
2. `powergrader/setup_core.js`
3. `powergrader/setup_autoscore.js`

## Exact files to change

- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader_setup.css`
- `api/tests/test_webui_template_contracts.py`

Do not change any other file in this slice.

## Required implementation

### 1. Establish the template's initial hidden states

In `powergrader_setup.html`:

- Keep `hidden` on `#pg-assignment-tools`.
- Change `#pg-ai-options` from inline `style="display:none"` to the boolean
  `hidden` attribute.
- Keep `#pg-rubric-fast` visible initially because `Grade myself` is the default.
- Add `hidden` to every `.pg-api-only` element:
  - the AI model label;
  - `#pg-model-actions` if an ID is added, otherwise the existing
    `.pg-model-actions.pg-api-only` container;
  - `#pg-late-watch-wrap`.
- Change `#pg-ai-check-wrap` from inline `style="display:none;margin-bottom:12px"`
  to `hidden`; move the bottom margin into PowerGrader CSS.
- Do not add hidden state to `#pg-safety-popout`; its open/closed state is controlled
  by the `open` property.
- Do not rename or remove any existing ID, form name, radio value, class used by JS,
  or `data-open-path` attribute.

### 2. Use only the `hidden` property for route-dependent visibility

In `setup_core.js::updateRouteMode()` replace the relevant `style.display` writes
with these exact state rules:

```javascript
var isAi = mode === 'packet' || mode === 'assisted';
aiOptions.hidden = !isAi;
rubricFast.hidden = isAi;
apiOnly.forEach(function(el){ el.hidden = mode !== 'assisted'; });
ackWrap.hidden = !isAi;
safetyPopout.open = isAi;
```

Null-check elements in the same style as the surrounding code where required. Do
not change how `currentMode()`, `modeInput`, selected-card styling, the AI label,
the acknowledgment checkbox value, or `syncStartEnabled()` works.

The existing behavior that clears `#pg-ai-check` when returning to `Grade myself`
must remain.

Do not change the assignment/module data flow. Existing `asnToolsEl.hidden = true`
and `asnToolsEl.hidden = false` assignments remain authoritative:

- hidden with no course;
- hidden while course data loads;
- visible only after a successful load with at least one course module.

### 3. Make `[hidden]` authoritative inside the setup form

At the top of `powergrader_setup.css`, add a local rule:

```css
#pg-start-form [hidden] { display: none !important; }
```

This is intentionally scoped to the PowerGrader setup form. Do not add or modify a
global `[hidden]` rule in `style.css`.

In `.pg-ai-check`:

- remove `!important` from its flex declaration;
- keep it a flex row when visible;
- move the template's former bottom margin into CSS.

Do not otherwise redesign or widen the page in this slice.

### 4. Add regression contracts

In `test_webui_template_contracts.py`, add focused tests that prove:

- `#pg-assignment-tools` has `hidden` in the template;
- `#pg-ai-options` has `hidden` and no inline `display:none` dependency;
- `#pg-ai-check-wrap` has `hidden` and no inline `display:none` dependency;
- all three `.pg-api-only` containers start hidden;
- `setup_core.js` sets `.hidden` for AI options, fast rubric, API-only controls,
  and acknowledgment;
- `setup_core.js::updateRouteMode()` no longer uses `style.display` for those
  route-dependent elements;
- PowerGrader CSS contains the form-scoped hidden rule.

Keep tests portable by using the existing repository-root helper. Do not hard-code
a developer path. These source contracts are regression guards only; they do not
replace rendered-app verification.

## Required state matrix

| State | Assignment tools | Fast rubric | AI options | API-only controls | AI acknowledgment | Safety details |
|---|---|---|---|---|---|---|
| No course, `fast` | Hidden | Visible | Hidden | Hidden | Hidden | Closed |
| Course loading, `fast` | Hidden | Visible | Hidden | Hidden | Hidden | Closed |
| Course loaded, `fast` | Visible | Visible | Hidden | Hidden | Hidden | Closed |
| Course loaded, `packet` | Visible | Hidden | Visible | Hidden | Visible | Open |
| Course loaded, `assisted` | Visible | Hidden | Visible | Visible | Visible | Open |

If OpenRouter is not configured, the assisted radio remains disabled exactly as it
is today. Do not invent a bypass to test that mode.

## Invariants that must not change

- `fast`, `packet`, and `assisted` remain the radio values and submitted mode values.
- Start-button enablement still requires workspace + course + assignment, and for
  AI modes also requires the acknowledgment checkbox.
- Changing back to `fast` clears the acknowledgment checkbox.
- Course selection still defaults to `Last 3 modules`.
- Assignment search still scans the full course, regardless of module selection.
- Search, course, module, and assignment rendering still escape Canvas-provided text.
- No Canvas write or external AI call occurs during setup-page rendering.
- Privacy wording remains byte-for-byte unchanged in this slice.

## Forbidden changes

- Do not edit `style.css` or `base.html`.
- Do not alter page width, grid structure, spacing, typography, or route-card layout.
- Do not change `setup_autoscore.js`.
- Do not alter PowerGrader routes, backend helpers, endpoint schemas, sessions,
  packets, estimates, queue behavior, late catch-up, or Canvas push behavior.
- Do not modify `LLM_Modules/*_Base.md`.
- Do not touch or stage unrelated engine, handoff-archive, or generated files.
- Do not commit course names, IDs, assignment names, screenshots containing private
  course data, tokens, student data, workspace paths, or other local configuration.

## Required automated verification

Run exactly:

```powershell
node --check api/webui/static/powergrader/setup_core.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_powergrader_module_picker.py api/tests/test_route_contract.py
git diff --check
```

All must pass. Warnings about local line-ending conversion are not test failures.

## Required rendered-app verification

Launch the normal local app with `cd api; py qf_ui.py` and inspect
`http://127.0.0.1:8765/powergrader`. This verification is read-only: do not start a
session, send an AI request, or write anything to Canvas.

Verify:

1. Initial `Grade myself` state:
   - assignment search and Modules are not visible before course selection;
   - fast rubric is visible;
   - AI setup, API controls, and AI acknowledgment are not visible;
   - privacy details are closed.
2. After selecting a course:
   - assignment search and Modules become visible after loading;
   - `Last 3 modules` remains selected;
   - assignment selection works.
3. `Prepare for my AI chat`:
   - fast rubric hides;
   - AI rubric, persona, and source material show;
   - model and late-watch controls stay hidden;
   - acknowledgment shows;
   - privacy details open.
4. `Draft-score with OpenRouter`, only if enabled in local configuration:
   - model actions and late-watch controls show in addition to the common AI setup;
   - acknowledgment shows;
   - privacy details remain open.
5. Return to `Grade myself`:
   - AI controls and acknowledgment hide;
   - acknowledgment checkbox is cleared;
   - fast rubric returns;
   - privacy details close.
6. Browser console has zero new errors or warnings from Canvas Expert scripts.

Do not print or include real course or assignment names in the implementation report.

## Acceptance criteria

- The required state matrix is true in the rendered app.
- The form uses one `hidden`-property contract for route-dependent visibility.
- The two screenshot defects are fixed without a layout redesign.
- All automated and rendered checks pass.
- Only the four authorized files are committed.
- No private data, Canvas write, or external AI request is produced.

## Required implementer reply

Report and stop after the one commit. Include:

1. Commit hash and exact changed files.
2. Short description of the visibility contract implemented.
3. Each automated command and pass result.
4. Rendered state-matrix evidence for every locally available mode.
5. Exact console error/warning count.
6. Explicit confirmation that no Canvas write, session start, or external AI request
   occurred.
7. Explicit confirmation that unrelated worktree changes were left unstaged.

## Mandatory escalation / stop conditions

Stop without guessing if:

- any named ID, class, function, or initial state no longer exists;
- satisfying the matrix requires changing a backend route, shared stylesheet, public
  contract, or safety wording;
- the assisted route cannot be distinguished from packet mode with the existing
  `.pg-api-only` controls;
- a prescribed test cannot prove its stated contract;
- a regression appears in module loading, course-wide search, or start-button gating;
- rendered verification cannot be performed.

Do not archive this handoff or begin slice 2. Ferrari or the user owns acceptance and
sequencing.
