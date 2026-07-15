# Execution brief: Unified WebUI presentation system

Status: **ready for implementation**

Risk: **Cohort 1 medium · Cohort 2 high · Cohort 3 medium** — presentation-only by
contract, but Cohort 2 touches the templates of grade-write, credential, and
private-student surfaces.

Executor: **Terra (supervising senior executor) directing one Luna at a time.**
Terra implements Cohort 1's shared presentation layer itself (architecture-heavy),
then supervises Luna executors for page migrations. At most one implementation agent
is active at any moment. A later cohort starts only after the prior cohort's gate
passes and the user accepts.

## Outcome

Every live WebUI page renders through one template family: a private document root,
three layouts (workspace / document / wizard), shared tokens, and shared components.
Changing the palette, typography, header, columns, or panel structure is a one-file
edit that propagates app-wide. At closure, `style.css` (93KB), `workbench.css`, both
legacy headers, `workbench_base.html`, and all 235 static inline styles are gone, and
architecture tests prevent the debt from regrowing.

No HTTP route, payload, persistence format, Canvas operation, credential behavior, or
public `window.CE_*` contract changes. `api/tests/test_route_contract.py::EXPECTED`
must not change in any cohort.

## Locked decisions (program-wide)

These are decided. Do not reopen them; RED per stop conditions if the repository
contradicts them.

### D1. File map

New files:

- `api/webui/static/ui/tokens.css` — all visual decisions (D3).
- `api/webui/static/ui/foundation.css` — reset + native element defaults.
- `api/webui/static/ui/components.css` — panels, page headers, buttons, fields, tabs,
  notices, action bars, tables, status dots, empty states.
- `api/webui/static/ui/layouts.css` — header, workspace/document/wizard shells,
  columns, gutters, responsive behavior.
- `api/webui/templates/layouts/workspace.html`, `layouts/document.html`,
  `layouts/wizard.html` — the only templates allowed to extend `base.html`.
- `api/webui/templates/layouts/_app_header.html` — the single app header (D6).
- `api/webui/templates/ui/_macros.html` — shared structural macros (D8).
- `api/webui/static/pages/<page>.css` — per-page feature CSS extracted from
  `style.css`/inline styles, only where a page needs one and none exists.
- `api/tests/test_presentation_contracts.py` — registry + architecture checks (D11).
- `docs/reference/webui-presentation-system.md` — template API, CSS ownership rules,
  route map, partial rule, change-propagation matrix. Written in Cohort 1, kept
  current every cohort.

Deleted at closure (Cohort 3, never earlier): `style.css`, `workbench.css`,
`workbench_base.html`, `_workbench_header.html`, `name_manager.html`,
`_course_picker.html`, the legacy header markup and legacy links in `base.html`.
Deletion requires zero references (`rg` proof in the executor report). Existing
feature CSS files (`powergrader_setup.css`, `powergrader_queue.css`,
`roster_workbench.css`) are kept at their current paths and rewritten to consume
tokens in their page's cohort.

The `/name-manager` → `/roster` and `/feedback-expert` → PowerGrader redirects are
routes and stay. Only the dead template files are deleted. Do not confuse dead
`_course_picker.html` with live `static/push/course_picker.js`.

### D2. Stylesheet isolation

`base.html` `<head>` gains `{% block stylesheet_bundle %}` whose default content is
the current `style.css` + `workbench.css` links. `fonts.css` stays outside the block.
Each layout overrides the block with exactly the four `ui/*.css` links (tokens,
foundation, components, layouts — in that order, each with `?v={{ asset_v }}`).
Feature templates add feature CSS only via `head_extra` and may not override
`stylesheet_bundle` (enforced, D11). A migrated page therefore never loads a legacy
sheet and a legacy page never loads the ui bundle. At closure, the default block
content becomes the ui bundle and the legacy files are deleted.

### D3. Token architecture

Tokens live on `:root` in `tokens.css`, dark values under `html[data-theme="dark"]`.
The existing `localStorage('ce-theme')` + `data-theme` mechanism and the
`id="theme-toggle"` button are unchanged. Seed values come from the instrument
vocabulary in `workbench.css` (the accepted Home/Create/Grade look), renamed
semantically. Canonical set (extend as needed, never bypass):

| Token | Light seed | Notes |
|---|---|---|
| `--ce-font-body` | `'Public Sans', system-ui, sans-serif` | |
| `--ce-font-display` | `'Schibsted Grotesk', system-ui, sans-serif` | |
| `--ce-font-mono` | `'JetBrains Mono', ui-monospace, Consolas, monospace` | |
| `--ce-surface` | `#f4efe6` | was `--ce-paper` |
| `--ce-surface-raised` | `#fbf8f1` | was `--ce-paper-raised` |
| `--ce-ink` / `--ce-ink-muted` | `#29251f` / `#6f6a61` | |
| `--ce-rule` / `--ce-rule-strong` | `rgba(61,55,46,.2)` / `.38` | borders |
| `--ce-chrome` / `--ce-chrome-soft` | `#20252a` / `#323940` | was graphite; header |
| `--ce-accent-canvas` | `#2f7d77` | Canvas-connected state |
| `--ce-accent-model` | `#8f6b32` | AI/model state |
| `--ce-ok` | `#4d7759` | was `--ce-privacy` |
| `--ce-attention` / `--ce-danger` | `#b85e36` (both) | danger may diverge later |
| `--ce-prepared` | `#527a8c` | |
| `--ce-create` / `--ce-grade` | `#aa633f` / `#5c718e` | section accents |
| `--ce-focus` | `#d9893f` | focus rings |
| `--ce-radius` / `--ce-radius-lg` | `8px` / `12px` | |
| `--ce-shadow-panel` | `0 8px 24px rgba(22,25,28,.08)` | |
| `--ce-space-1..6` | `4/8/12/16/20/24px` | spacing scale |
| `--ce-width-workspace` | `1760px` | |
| `--ce-width-doc` / `--ce-width-doc-wide` | `920px` / `1240px` | |

Dark seeds come from `workbench.css` lines 31–47. Legacy `style.css` tokens
(`--ce-blue`, `--accent`, etc.) are not carried into the new system; pages that used
them adopt the instrument palette when they migrate.

### D4. One component vocabulary

The tripled `.ce-desk-* / .ce-workbench-* / .ce-instrument-*` selector families in
`workbench.css` collapse into one set of component classes in `components.css`
(`.ce-shell`, `.ce-panel`, `.ce-rail`, `.ce-page-header`, `.ce-btn`, `.ce-field`,
`.ce-tabs`, `.ce-notice`, `.ce-actions`, `.ce-table`, `.ce-status-dot`,
`.ce-empty`). Migrated templates re-class to the new vocabulary. Where JavaScript
queries an old class, apply D9 in the same commit.

### D5. Responsive replaces fixed minimum width (deliberate behavior change #3)

`.ce-workbench-shell` currently forces `min-width: 1600px`. The new layouts drop
every fixed minimum width. Central responsive rules in `layouts.css`:
workspace max-width `--ce-width-workspace` with fluid gutters; three-column desktop
grid `240px / minmax(0,1fr) / 280px`, 20px gap; at **1180px** the right rail moves
below the main stage; at **760px** layouts become one column, the left rail becomes a
compact top control, and horizontal page overflow is forbidden. PowerGrader's
internal submission/grading split remains feature-owned inside the shell and may keep
its own internal breakpoints.

### D6. One header

`layouts/_app_header.html` is created from `_workbench_header.html` (flat teacher
vocabulary already accepted 2026-07-15: Home, Create, Grade, Students, Automations,
Settings, plus `_readiness_strip.html` and the theme toggle with `id="theme-toggle"`
preserved). Workspace and document layouts include it; wizard does not. The legacy
dropdown menus in `base.html`'s topbar are not carried forward — dropdown deep links
(`/gradebook?tab=policy`, `/course-expert?tab=quiz`, …) remain working URLs reachable
from Home and in-page tabs, and the URLs themselves must keep working. During
coexistence three headers exist (legacy topbar, `_workbench_header.html` on
not-yet-migrated instrument pages, the new shared header). Do not unify early; both
legacy headers are deleted only in Cohort 3. Layouts that include the header also load
`readiness.js` in their scripts block; wizard does not.

### D7. Layout variants are Jinja blocks

The variant is declared by the page as a block rendering into a class, e.g.
`<div class="ce-workspace ce-workspace--{% block workspace_variant %}full{% endblock %}">`
(document: `document_variant`, default `standard`). Rails are provided wholly by the
page inside `{% block left_rail %}` / `{% block right_rail %}` using the shared rail
macro; the layout provides the grid container. Empty or fabricated rails are
forbidden — the rendered-route registry (D11) asserts the exact rail count per route.
Workspace block API: `workspace_variant`, `workspace_header`, `left_rail`, `primary`,
`right_rail`, plus inherited `head_extra` / `scripts_extra`.

### D8. Shared macros

`ui/_macros.html` owns repeated structure: `page_header(title, lede)`,
`panel(title)` (call-block body), `notice(kind)`, `empty_state(msg)`,
`action_bar()`, `rail()`. Native interactive controls stay plain HTML with component
classes — do not macro-wrap forms, inputs, or buttons.

### D9. Behavior preservation and JS hooks

Preserve all DOM IDs, form names, endpoint calls, payloads, script order, deep links,
and `window.CE_*` globals. Shared component classes must never be JavaScript hooks.
Before re-classing any template, grep that page's scripts for every class it queries;
where a queried class must change, add `data-ce-hook="<name>"`, switch the script to
the data attribute, and update its tests in the same commit. Runtime style writes:
prefer state classes and `hidden`; genuinely dynamic values (progress bars) use a
custom property (`el.style.setProperty('--ce-progress', …)`). Existing JS `.style`
writes are not chased in this program; new code follows the rule.

### D10. The three deliberate presentation deltas (and only these)

1. Settings gains a left section index: anchor links to its existing form regions
   (adding `id` attributes where missing is allowed); stores no state, changes no
   form or submission behavior.
2. Welcome loses the authenticated app header (wizard layout, focused card, theme
   pre-load script retained).
3. Fixed 1600px minimum width is replaced by responsive reflow (D5).

Anything else that changes what a teacher can see or do is out of scope.

### D11. Enforcement registry and architecture tests

`api/tests/test_presentation_contracts.py` follows the source-contract style of
`test_webui_template_contracts.py` plus rendered TestClient checks (fictional
config, no Canvas, no student data — follow existing `test_desk_routes.py` /
PowerGrader fixture patterns; the queue page renders against a synthetic local
session fixture, never a live scan).

It contains one registry, the single source of truth:
`EXPECTED_PRESENTATION: dict route -> (template, layout, variant, rail_count,
migrated: bool)`. Each cohort flips its rows to `migrated=True` in the same commit
as the migration.

Source checks (scoped to `migrated=True` rows during coexistence, repo-wide at
closure):

- Page templates extend a `layouts/*` template; only layouts extend `base.html`.
- No page overrides `stylesheet_bundle`.
- No `style="` in migrated templates (partials included).
- Feature/page CSS contains no `font-family:`, hex colors, `rgb(`/`hsl(`,
  `border-radius:`, or `box-shadow:` — visual literals live only in `ui/*.css`.
  A short explicit allowlist constant in the test covers justified exceptions.
- No `querySelector`/`getElementsBy` against shared component classes in
  `static/**/*.js` (maintain a `FORBIDDEN_JS_SELECTORS` list from D4's vocabulary).

Rendered checks per registry row: expected layout/variant class present, exactly one
`<header>` (zero for wizard) and one `<main>`, expected rail count, stylesheet
isolation (migrated: all four ui links present and no legacy link; legacy: inverse),
no duplicate IDs, redirects preserved.

### D12. Branch, commits, rollback

All work on `dev` per the two-branch policy — no cohort branches. Each cohort lands
as a small series of reviewable commits ending in a green gate. Rollback is
`git revert` of a cohort's commits; because of D2 isolation, reverting a page
migration cleanly restores its legacy presentation.

## Route registry (initial state)

| Route | Template | Layout · variant | Rails | Cohort | Inline styles now |
|---|---|---|---|---|---|
| `/` (Home) | dashboard.html | workspace · full | 0 | 1 | 0 |
| `/course-expert` (Create) | course_expert.html | workspace · three | 2 | 1 | 53 |
| `/powergrader` | powergrader_setup.html | workspace · full | 0 | 1 | 5 |
| `/powergrader` session | powergrader_queue.html | workspace · full | 0 | 1 | 9 |
| `/gradebook` | gradebook.html | workspace · left-main | 1 | 2 | 46 |
| `/roster` | roster.html | workspace · left-main | 1 | 2 | 5 |
| `/settings` | settings.html | workspace · left-main | 1 | 2 | 48 |
| `/routines` | routines.html | document · wide | 0 | 2 | 1 (panel) |
| `/students/reports` | student_reports.html | document · wide | 0 | 3 | 7 |
| `/course` | course.html | document · wide | 0 | 3 | 10 |
| `/about` | about.html | document · wide | 0 | 3 | 1 |
| `/ai-expert` | ai_expert.html | document · standard | 0 | 3 | 14 |
| `/welcome` | welcome.html | wizard | 0 | 3 | 19 |

Shared partials migrate with their consumers, as one unit: `_readiness_strip.html`
with the header (Cohort 1); `_routines_panel.html` with Gradebook — which is why the
Routines page is in Cohort 2; `_push_common_scripts.html` is behavior-only and keeps
its load order. Regenerate the include call graph with `rg "{% include"` before each
cohort and RED if it disagrees with this table.

A layout's interface is provisional until its first real consumer renders and passes
the gate: workspace is proven in Cohort 1, document in Cohort 2 (Routines), wizard in
Cohort 3 (Welcome). Build `wizard.html` in Cohort 3, not before. Interface
adjustments discovered at first consumption are Terra's to approve and must update
`docs/reference/webui-presentation-system.md` in the same commit.

## Cohort 1 — Foundation and reference surfaces (Terra implements)

1. Add `stylesheet_bundle` to `base.html` (D2). Build `ui/tokens.css`,
   `foundation.css`, `components.css`, `layouts.css` (D3–D5), `layouts/workspace.html`
   + `layouts/document.html` (D7), `layouts/_app_header.html` (D6), `ui/_macros.html`
   (D8), and `test_presentation_contracts.py` with the full registry, all rows
   `migrated=False` (D11). Write `docs/reference/webui-presentation-system.md`.
2. Migrate Home, Create, PowerGrader setup, PowerGrader queue (synthetic session) to
   `workspace`. These pages already carry the instrument look; the work is
   re-parenting from `workbench_base.html` to the layout, re-classing to the D4
   vocabulary with D9 hook discipline, eliminating their static inline styles
   (53 + 5 + 9), and rewriting `powergrader_setup.css` / `powergrader_queue.css` to
   consume tokens. Extract any rules these pages still need from
   `style.css`/`workbench.css` into components (if shared) or `static/pages/*.css`
   (if page-specific); migrated pages must render with no legacy sheet loaded.
3. Do not touch legacy pages, `workbench_base.html` (still parents Gradebook, Roster,
   Student Reports), or either legacy header.

Gate: presentation + route-contract + template-contract suites green; PowerGrader
focused suites green (`test_powergrader_packet.py`, `test_powergrader_copilot_packet.py`,
`test_powergrader_import_results.py`); `node --check` on changed JS; rendered check of
the four routes per Verification. User accepts before Cohort 2.

## Cohort 2 — Operational workspaces (Luna, Terra supervises)

1. Migrate Gradebook, Roster, Settings to `workspace · left-main`; migrate
   `_routines_panel.html` and the Routines page (`document · wide` — first document
   consumer) in the same cohort.
2. High-risk seams, preserve exactly: Gradebook write-review dialogs and confirmation
   flows (`write_review.js`, `CE_WRITE_REVIEW`, `CE_GRADEBOOK`), Roster private-data
   handling and safety controls (`roster/safety.js`), Settings credential forms
   (token/keyring flows — form names, IDs, and submit behavior untouched), Routines
   execution controls. Grep each page's scripts for queried classes before any
   re-classing (D9).
3. Settings section index per D10.1. Rewrite `roster_workbench.css` to tokens.
   Eliminate the 46 + 5 + 48 + 1 static inline styles.
4. Flip registry rows. Update the reference doc if the document layout needed
   adjustment at first consumption.

Gate: presentation + route-contract suites green; `test_gradebook_routes.py`,
`test_roster_routes.py`, `test_roster_config.py`, `test_workspace.py`,
`test_readiness_routes.py` green; rendered checks; **user diff review is required
for this cohort** (high risk) before Cohort 3.

## Cohort 3 — Documents, onboarding, closure (Luna, Terra supervises)

1. Migrate Student Reports, Course Info, About (document · wide), AI Expert
   (document · standard). Build `layouts/wizard.html` and migrate Welcome per D10.2.
   Eliminate remaining static inline styles (7 + 10 + 1 + 14 + 19).
2. Closure deletions per D1, each with `rg` zero-reference proof: legacy topbar
   markup and legacy stylesheet links out of `base.html` (default bundle becomes the
   ui links), `workbench_base.html`, `_workbench_header.html`, `workbench.css`,
   `style.css`, `name_manager.html`, `_course_picker.html`.
3. Widen every D11 source check to repo-wide; add the closure assertion that no live
   template references either legacy stylesheet; all registry rows `migrated=True`.
4. Update `api/webui/README.md` and affected module maps; finalize
   `docs/reference/webui-presentation-system.md`; record the final execution result
   below and archive this handoff — as part of this cohort, not a separate pass.

Gate: full `py -m pytest api/tests` green (integration boundary); rendered checks of
all thirteen routes; acceptance criteria below.

## Out of scope (program)

- QuizForge compiler (`/forge/quizforge/`) and generated DOCX/PDF/HTML artifacts.
- Any route, payload, persistence, Canvas write, credential, or scheduling change;
  any change to `test_route_contract.py::EXPECTED`.
- New frameworks, bundlers, npm, component registries, or CSS preprocessors.
- Feature work, copy rewrites beyond the accepted teacher vocabulary, new navigation
  beyond D10.1, chasing existing JS `.style` writes, engine/ suite.
- Restyling generated print/PDF output.

## Reference pattern and routing

- Instrument seed: `api/webui/static/workbench.css`; legacy layer being replaced:
  `api/webui/static/style.css`.
- Header source: `api/webui/templates/_workbench_header.html`; document root:
  `api/webui/templates/base.html`.
- Source-contract test style: `api/tests/test_webui_template_contracts.py`; rendered
  route style: `api/tests/test_desk_routes.py`; route freeze:
  `api/tests/test_route_contract.py`.
- Module maps under `docs/reference/*-module-map.md` for per-page JS ownership before
  re-classing (course-expert, gradebook, roster, powergrader, settings).
- Read project-local `TOOLS.md` before broad manual inspection; use targeted `rg`.

## Verification (every cohort)

```powershell
py -m pytest api/tests/test_presentation_contracts.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
# plus the cohort's affected suites named in its gate
node --check <each changed .js>   # list files changed in the cohort
git diff --check
```

Rendered verification, per migrated route: light and dark themes at 1920px and 390px
widths, in the locally run app (`cd api; py qf_ui.py`) with fictional configuration —
fictional workspace, no real token, no district URL. Verify shell columns and
responsive order (D5), theme switching, visible focus, no horizontal overflow, no
duplicate IDs. Console policy: capture each route's console on the pre-migration
baseline first; after migration the console must be identical-or-better (fetch
failures caused by fictional config are acceptable only if present at baseline).
Never scan courses, run routines, validate/prepare/apply operations, upload private
files, or make any Canvas/AI call during verification.

## Acceptance (closure)

- Every live page extends one approved layout; registry fully `migrated=True`.
- Global chrome change = edit `layouts/_app_header.html` only. Outer column change =
  `layouts.css`/tokens only. Palette/typography/radius/shadow change = `tokens.css`
  (± `components.css`) only. Panel structure change = its macro only.
- Zero static inline styles in live templates; zero visual literals outside `ui/`.
- Legacy files from D1 deleted; architecture checks active repo-wide.
- No feature behavior or safety boundary changed beyond D10's three deltas.

## Stop conditions

Stop with RED rather than guessing if:

- A named file, block, symbol, or the include call graph contradicts this brief.
- Preserving behavior would require changing a route, payload, `window.CE_*` global,
  or `test_route_contract.py::EXPECTED`.
- A D9 grep shows JS coupling too tangled to hook-swap within the cohort's scope.
- Anything touches credentials, grade writes, FERPA data, or external transmission in
  a way this brief does not explicitly cover.
- A rendered route regresses against its console/interaction baseline and the cause
  is not an intended presentation change.

## Execution results

### Cohort 1 result

- Traffic light: **YELLOW** — implementation, automated gate, and the required
  fictional rendered-route checks are complete. The one execution deviation below
  requires user review before Cohort 2.
- Commit hash / files changed / verification counts / rendered routes / deviations:
  - Implementation commit `f1c978b` on `dev` (24 files, 868 insertions, 309 deletions).
    Added the Cohort 1 `ui/` token/foundation/component/layout
    bundle, workspace/document layouts, shared header/macros, page CSS for Home/Create,
    presentation contract registry, and the durable presentation reference. Migrated
    `base.html`, Home, Create, PowerGrader setup, and PowerGrader queue; tokenized both
    existing PowerGrader feature sheets; changed only Create/queue presentation hooks.
  - `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py -q` — **41 passed**.
  - `node --check` passed for `course_expert/tabs.js`, `work_rail.js`,
    `instrument.js`, `powergrader/queue_core.js`, and `queue_new_quiz.js`.
    `git diff --check` passed.
  - TestClient rendered checks covered `/`, `/course-expert`, `/powergrader`, and
    synthetic `/powergrader/session/synthetic-session`, including shell, rail,
    stylesheet-isolation, header/main, duplicate-ID, and redirect checks. A second,
    fully stubbed fictional local server rendered all four routes in light and dark
    themes at 1920px and 390px: each had one header/main, no duplicate IDs or
    page-level horizontal overflow, Create's left/stage/right mobile order was correct,
    and no console warnings or errors were captured.
  - **Execution deviation:** the first temporary local-server fixture did not stub
    `readiness.js`. Its automatic local `/api/readiness/probe` call invoked the
    configured read-only Canvas profile and OpenRouter readiness probes before the
    server was stopped. No Canvas write, course scan, routine, upload, grade/comment,
    student-submission operation, or AI-content transmission was initiated; no secrets
    or response data were printed. The fixture then stubbed both readiness endpoints
    and all subsequent visual checks were isolated. This was a verification-process
    error, not a product-code change.
  - No route, payload, `window.CE_*`, credential, Canvas, AI, or student-data contract
    changed. The only deviation is the read-only readiness probe above.

### Cohort 2 result

- Traffic light: **GREEN** — Cohort 2's implementation, automated checks, and fully
  synthetic rendered checks are complete. The user must still review this high-risk
  diff before Cohort 3 begins.
- Commit hash / files changed / verification counts / rendered routes / deviations:
  - Implementation commit `1e6a45f` on `dev` (16 files, 600 insertions, 351
    deletions) migrates Gradebook, Roster, and Settings to
    `workspace · left-main`, migrates Routines to `document · wide`, moves the shared
    routines partial with its consumers, adds the stateless Settings anchor index, and
    replaces all Cohort 2 static template inline styles. Added token-consuming
    Gradebook, Settings, and Routines page CSS; rewrote `roster_workbench.css` to
    tokens; flipped all four registry rows; and documented the first document-layout
    consumption. Gradebook's `CE_WRITE_REVIEW`/`CE_GRADEBOOK` and feature-script
    order, Roster's private-data/safety scripts and order, Settings form IDs/names and
    credential routes, and Routines control IDs/routes are unchanged. The two narrow
    dynamic-visibility changes replace removed template inline display styles with
    page-specific CSS classes in Settings token/key controls and Gradebook curve
    settings; they preserve the same show/hide and form-submission behavior.
  - Correction commit `e1f0eba` on `dev` adds `overflow-wrap: anywhere` only to
    code text inside Settings panels. That first, narrow correction did not resolve
    the mobile overflow; no template, form, link, ID/name, script, route, or
    credential behavior changed.
  - `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py -q` — **28 passed**.
  - `py -m pytest api/tests/test_gradebook_routes.py api/tests/test_roster_routes.py api/tests/test_roster_config.py api/tests/test_workspace.py api/tests/test_readiness_routes.py -q` — **73 passed**.
  - `node --check` passed for `gradebook/curves.js`, `settings.js`,
    `settings/account.js`, and `settings/openrouter.js`; `git diff --check` passed.
  - After the migration, a senior's fully synthetic browser render found
    `/settings` at 390px had `documentElement.scrollWidth = 413`; the other three
    Cohort 2 routes were clean. The correction's focused
    `py -m pytest api/tests/test_presentation_contracts.py -q` check passed
    (**6 passed**) with `git diff --check` green. The senior will rerun the isolated
    light/dark mobile visual suite. No Canvas or OpenRouter request was made during
    this correction.
  - Correction checkpoint `450d5bd` on `dev` identifies the actual 390px source as
    the Current/Previous Courses `.profiles` tables: their action columns produced
    the 413px document width. It applies a Settings-only `max-width: 760px` table
    restack, retaining each `course-row-*` ID and all existing action buttons and
    data attributes. The form/credential markup, IDs/names, routes, and scripts are
    unchanged. `py -m pytest api/tests/test_presentation_contracts.py -q` passed
    (**6 passed**); `git diff --check` passed.
  - The senior's fully synthetic browser verification passed all four Cohort 2 routes
    (`/gradebook`, `/roster`, `/settings`, `/routines`) in light and dark themes at
    1920px and 390px. At 390px every route had its expected layout/rail count, one
    header/main, no duplicate IDs, no page-level horizontal overflow, and no console
    warnings or errors; Settings now has a 375px page width. The 760px-only table
    restack does not affect the earlier clean 1920px checks. No Canvas or OpenRouter
    request was made. The local untracked `api/.codex_cohort2_verify.py` is a fully synthetic
    resume-only verifier; it stubs every `/api/*` response, readiness endpoint,
    host label, courses, and routine paths, and must not be committed as product
    code.

### Cohort 3 result

- Traffic light: **not started**
- Commit hash / files changed / verification counts / rendered routes / deviations:
