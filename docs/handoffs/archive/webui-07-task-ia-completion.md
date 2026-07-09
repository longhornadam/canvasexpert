# VSCode Toyota handoff: complete task-oriented navigation and dashboard

## Purpose

Implement the task-oriented IA slice that is currently absent. The live UI still uses `PowerGrader / Work / Rosters / Gradebooks / Settings / Extras` and the dashboard still uses `Most common jobs` / `More tools by job`.

## Dependencies

Complete `webui-05-p1-regression-repair.md` and `webui-06-shared-scope-review-completion.md` first.

## Product decision — fixed

Use this navigation taxonomy. Do not invent another taxonomy while implementing:

| Navigation | Existing destinations |
| --- | --- |
| **Create** | Work home, quiz, assignment, page, rubric, quick assignment |
| **Grade** | PowerGrader, Score writing with AI, Gradebooks policy/sweep/extensions/curves/snapshot |
| **Manage** | Rosters, Download student work, Student reports, Course info |
| **Automate** | Routines |
| **Settings** | Settings |
| **Help & tools** | About, AI helper files, QuizForge compiler, contract downloads |

No routes are removed, renamed, or redirected. PowerGrader is a featured Grade destination, not a separate top-level item. Feedback belongs under Grade, not Help & tools.

## Files to change

- `api/webui/templates/base.html`
- `api/webui/templates/dashboard.html`
- `api/webui/static/style.css`
- `api/webui/routes/pages.py` only for active-nav values
- `api/webui/routes/powergrader_setup_support.py` only for active-nav values on session routes
- `api/webui/README.md`
- `api/tests/test_webui_template_contracts.py`

Do not edit individual tool templates, routes, API behavior, settings, contracts, or Canvas operations.

## Required implementation

### Top bar

Replace the legacy taxonomy in `base.html` with the fixed taxonomy above, using the current `<details>` approach. Preserve every legacy deep link in exactly one appropriate menu. Grade must receive the active visual/semantic state on PowerGrader, Feedback, and Gradebook pages.

Keep current keyboard menu behavior. At 390px use the existing wrapping/two-column strategy; do not add a hamburger menu or dependency.

### Dashboard

Replace the old top-level dashboard sections with:

1. `Start a job` — four labelled intent lanes: Create, Grade, Manage, Automate.
2. `Continue working` — the existing recent-activity list; do not claim it is resumable state.
3. `All tools` — compact, collapsible directory by the same four labels, below the primary work.

Primary cards are fixed:

- Create: Quick assignment, Push assignment, Push quiz.
- Grade: PowerGrader, Score writing with AI, Gradebook sweep.
- Manage: Rosters, Download student work, Grant extension.
- Automate: Routines, Student reports.

Keep the connection/workspace strip secondary. Never imply a globally active course.

## Verification — required, not optional

Run:

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
```

Add source-contract tests asserting the legacy top-level labels are absent and all six new taxonomy labels are present in `base.html`.

Launch the app and check at 1280px, 1440px, and 390px:

1. `/`, `/course-expert`, `/powergrader`, `/feedback-expert`, `/gradebook`, `/roster`, `/routines`, `/settings`, `/ai-expert`, `/about` show the correct active navigation intent.
2. Every old deep link remains reachable from the new nav.
3. Header and dashboard have no clipping or horizontal page scrolling.
4. Menu navigation works with keyboard.

Do not archive or claim completion without explicit results for every route and viewport above.

