# Toyota handoff: task-oriented navigation and dashboard

## Objective

Reorganize navigation and the dashboard around a teacher's jobs without changing routes, backend ownership, or tool capability. The app remains an expert toolkit; this pass makes the first choice easier.

## Dependencies

Complete handoffs 01 and 02 first. Reuse their scope and review behavior; do not recreate it in dashboard cards.

## Product decision (do not reopen during implementation)

Adopt this top-level information architecture:

| Top-level destination | Teacher intent | Existing routes included |
| --- | --- | --- |
| **Create** | Make/publish instructional content | Work home; quiz; assignment; page; rubric; quick assignment |
| **Grade** | Grade work, score with AI, or correct grades | PowerGrader; Score with AI; Gradebooks (policy/sweep, extensions, curves, snapshot) |
| **Manage** | Work with people, files, and course records | Rosters; Download work; Student reports; Course info |
| **Automate** | Run or configure local recurring work | Routines |
| **Settings** | Configure this local app | Settings |

`About`, AI helper files, QuizForge compiler, and contract downloads move to a low-prominence `Help & tools` menu. They are not daily navigation. No route is removed, renamed, or redirected in this handoff.

Keep **PowerGrader** as the first featured item inside Grade. It is not a separate peer top-level nav item.

## Files to change

- `api/webui/templates/base.html`
- `api/webui/templates/dashboard.html`
- `api/webui/static/style.css`
- `api/webui/routes/pages.py` only to provide corrected active-navigation values, if necessary
- `api/webui/routes/powergrader_setup_support.py` only to provide corrected active-navigation values for PowerGrader session routes
- `api/webui/README.md`

Do not change endpoint URLs, templates for individual tool pages, Canvas service code, stored settings, activity schemas, or any `LLM_Modules` contract.

## Required implementation

### 1. Replace the current topbar taxonomy

In `base.html`, replace the current `PowerGrader / Work / Rosters / Gradebooks / Settings / Extras` arrangement with the Product decision above.

- Use the existing `<details>` dropdown pattern and current accessibility behavior.
- Every existing deep link must remain available in one appropriate menu.
- `Score with AI` and `Push feedback to Canvas` belong under **Grade**, not Help & tools.
- The topbar must use one active accent for the current top-level intent. PowerGrader, Feedback, and Gradebook pages all activate **Grade**.
- `Course info` may be found from Manage; it is acceptable for it to also remain reachable contextually from the Work picker.
- At mobile widths, preserve the existing two-column nav layout. Five top-level items plus Help & tools is acceptable; do not introduce a hamburger menu or a new dependency in this handoff.

### 2. Rebuild the dashboard around "Start a job"

Replace `Most common jobs` plus the long `More tools by job` directory with the following structure:

1. **Start a job** — four intent lanes: Create, Grade, Manage, Automate. Each contains one sentence and 2–3 high-value cards.
2. **Continue working** — retain the existing recent-activity component; label it honestly as activity, not resumable state.
3. **All tools** — a compact, collapsible directory by the same four intent labels. It must be below the fold and should not compete with starting a job.

The primary cards must be exactly:

- Create: Quick assignment; Push assignment; Push quiz.
- Grade: PowerGrader; Score writing with AI; Gradebook sweep.
- Manage: Rosters; Download student work; Grant extension.
- Automate: Routines; Student reports.

Do not use an algorithmic "recommended" label. This app has no trustworthy per-user usage telemetry. The cards are fixed, teacher-legible entry points.

Keep the connection/workspace status strip, but make it visually secondary to `Start a job`. Do not show a course as globally selected there.

### 3. Update documentation and names, not routing

Update `api/webui/README.md`'s page map and navigation description to use Create / Grade / Manage / Automate / Settings / Help & tools. Preserve the canonical route list.

Use sentence case consistently:

- `Score writing with AI`, not `Score With AI`.
- `Download student work`, not `Download Work` when used as a verb.
- `Gradebook tools` is an internal page label; navigation calls it `Grade`.

## Accessibility and visual requirements

- The active top-level section must be indicated by more than color: retain the current underline/selection treatment and accessible text.
- All menu controls must work via keyboard exactly as current `<details>` menus do.
- At 1280px and 1440px, no menu item or dashboard card clips or causes page-level horizontal scrolling.
- At 390px, the header may wrap but must not cover content or create an unreachable menu.

## Verification

Run:

```powershell
py -m pytest api/tests/test_route_contract.py
```

Manual browser matrix:

1. Visit `/`, `/course-expert`, `/powergrader`, `/feedback-expert`, `/gradebook`, `/roster`, `/routines`, `/settings`, `/ai-expert`, and `/about`.
2. Confirm each page exposes the intended active top-level navigation and every former topbar destination remains reachable.
3. At 1280px, 1440px, and 390px, inspect header and dashboard for horizontal overflow, clipped labels, and keyboard access to menu items.
4. Confirm old bookmarked URLs such as `/push/quiz`, `/download-work`, and `/gradebook?tab=extensions` still work unchanged.

## Acceptance criteria

- The first choice on the dashboard is a teacher job, not a subsystem.
- Feedback/AI grading is clearly a Grade workflow.
- No public URL, API, feature, or stored configuration changes.
- The user can still reach every feature in no more than two topbar interactions.

