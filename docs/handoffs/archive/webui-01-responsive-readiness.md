# Toyota handoff: WebUI foundation — responsive dashboard and readiness gating

## Objective

Remove the dashboard overflow visible at ordinary laptop widths and make it impossible for the UI to present a Canvas write as available before its required scope is selected. This is a front-end-only safety and polish pass. Do not alter Canvas API routes, persistence, authoring contracts, or default business behavior.

## Why this is first

The dashboard is the app's first impression and currently clips job cards between the 1100px breakpoint and the dashboard's 1400px maximum width. Separately, a write affordance that is visibly enabled with no selected course creates avoidable anxiety and trains teachers to discover prerequisites through errors.

## Files to change

- `api/webui/static/style.css`
- `api/webui/templates/dashboard.html`
- `api/webui/templates/gradebook.html`
- `api/webui/static/gradebook.js`
- `api/webui/static/gradebook/policy.js`
- `api/webui/static/gradebook/sweep.js` only if it owns button-state updates
- `api/webui/static/push/course_picker.js`
- `api/webui/templates/course_expert.html` only for persistent, noninteractive readiness text

Do not touch `LLM_Modules/`, `api/webui/routes/`, Canvas client code, or any student/workspace data paths.

## Required implementation

### 1. Make dashboard grids intrinsically responsive

Replace the fixed desktop column counts in `.dash-job-grid` and `.dash-lane-grid` with intrinsically responsive grids. The intended behavior is:

- Jobs: cards must never overflow horizontally. Use `repeat(auto-fit, minmax(230px, 1fr))` or a comparable CSS-only rule.
- Tool lanes: use `repeat(auto-fit, minmax(190px, 1fr))` or comparable CSS-only rule.
- Preserve the one-column small-screen experience at `<= 760px`.
- Remove now-redundant width-specific `4 → 2` / `5 → 3` grid rules if they fight the intrinsic layout. Keep any breakpoint rule that is still necessary for typography or spacing.
- The dashboard's `max-width: 1400px` remains valid. Do not shrink the content area merely to hide overflow.

At 1280px wide, every dashboard job and lane must be fully visible without horizontal scrolling, clipping, or a hidden fourth/fifth column. At 1440px the layout may use more columns naturally; visual density must remain comparable to today.

### 2. Standardize disabled prerequisites for Gradebooks

The selected course is a hard prerequisite for every gradebook action. Implement a single `syncGradebookReadiness()` helper in `api/webui/static/gradebook.js`, expose it as `window.CE_GRADEBOOK.syncReadiness`, and call it:

- during initial page setup;
- at the beginning and end of `_resetGradebookState()`;
- whenever `#gb-course-sel` changes.

At minimum it must:

- disable `#btn-apply-policy` without a course;
- disable `#btn-sweep-preview` without a course;
- ensure `#btn-sweep-apply` is hidden/reset as it is today when course state changes;
- leave read-only date controls usable, but show an adjacent neutral prerequisite message: `Select a course to preview or apply gradebook changes.`

Do **not** rely on the existing `alert("Pick a course first.")` in `gradebook/policy.js` as the ordinary interaction path. Keep the defensive guard in JavaScript and preserve server-side validation.

When a course is selected, re-enable only actions whose other existing prerequisites are satisfied. Do not accidentally enable an Apply button which is intentionally hidden pending a preview.

### 3. Clarify Work's selected-state semantics without changing them

The Work course picker already has the correct behavior: checked courses receive pushes and one checked course is focused for course-specific options. Preserve that model.

Improve the readiness copy rendered by `renderCourseScopeSummaries()`:

- no selection: `Choose one or more target courses to continue.`
- one target: `Ready to push to: <course>.`
- multiple targets: `Ready to push to N courses: <first three names> +N more.`
- retain the focused-course line only when relevant and phrase it as `Focused course for modules and categories: <course>.`

This is copy/state work only. Do not introduce a global selected-course state, pre-check courses automatically, or change the existing localStorage convenience behavior.

## Accessibility and interaction requirements

- Disabled buttons must use the native `disabled` attribute, not only a CSS class.
- The prerequisite message must be in an `aria-live="polite"` region.
- Do not remove keyboard tab navigation or the current tab ARIA behavior.
- No hover-only explanation is acceptable.

## Verification

Run:

```powershell
py -m pytest api/tests/test_gradebook_routes.py api/tests/test_route_contract.py
```

Then run `cd api; py qf_ui.py` and manually verify at 1280px, 1440px, and 390px widths:

1. Dashboard has no horizontal overflow or clipped cards.
2. Gradebooks opens with no course selected: policy apply and sweep preview are disabled and the prerequisite message is visible.
3. Selecting a course enables the policy/sweep preview controls and loads the current policy as before.
4. Work's picker shows the revised exact target/focus summary after zero, one, and multiple checked courses.

## Acceptance criteria

- No dashboard horizontal overflow at any width from 390px through 1440px.
- A teacher can see, before acting, whether a course has been selected and what needs to happen next.
- No API request, Canvas write, local settings write, or student-data operation occurs as part of readiness synchronization.
- Existing Gradebook and Work behavior is otherwise unchanged.

