# VSCode Toyota handoff: complete shared scope and review primitives

## Purpose

Implement the previously specified scope/review slice that is currently absent. Commit `2b70abe` archived the old handoff without implementing it: three `canvasWriteReview` copies still exist, there is no `write_review.js`, and Gradebook/Feedback lack the requested action-scope blocks.

## Dependency

Complete `webui-05-p1-regression-repair.md` first. Do not begin this work on top of known P1 UI regressions.

## Files to change

- **New:** `api/webui/static/write_review.js`
- `api/webui/templates/base.html`
- `api/webui/static/push/core.js`
- `api/webui/static/gradebook.js`
- `api/webui/static/feedback/push.js`
- `api/webui/templates/gradebook.html`
- `api/webui/templates/feedback_expert.html`
- `api/webui/static/push/course_picker.js`
- `api/webui/static/style.css`
- `api/webui/README.md`
- **New/updated tests:** `api/tests/test_webui_template_contracts.py`

Do not alter POST endpoints, Canvas request payloads, backend validation, data contracts, local storage behavior, or activity logging.

## Required implementation

### One review implementation

Create `window.CE_WRITE_REVIEW.confirm(options)` in `write_review.js`, loaded from `base.html` before page scripts. It returns `Promise<boolean>` and supports `title`, `action`, `targets`, `details`, `warnings`, `confirmText`, and `cancelText`.

It must provide all of the following:

- one dialog style compatible with current `.ce-review-*` CSS;
- explicit target/change/warning lists;
- focus initially on Cancel, not the destructive action;
- Tab and Shift+Tab wrap between Cancel and Confirm;
- Escape and backdrop cancel;
- focus restored to the invoking control;
- no dependency or external script.

Remove the local dialog bodies from exactly these files and migrate all call sites:

- `api/webui/static/push/core.js`
- `api/webui/static/gradebook.js`
- `api/webui/static/feedback/push.js`

After migration, `rg "function canvasWriteReview" api/webui/static` must return no results.

### Scope blocks

Add a reusable `.ce-action-scope` visual style and `aria-live="polite"` content:

- Gradebooks, below course selection: no course = `No course selected. Gradebook changes are unavailable.`; selected = `Working in: <course>. Changes on this page affect this course only.`
- Feedback Push to Canvas, above Preview: state must explain whether course, assignment, or both are missing; when complete, say `Will post reviewed grades/comments for <assignment> in <course>.`
- Work: retain the revised summary from the prior slice. Do not create global scope state.

Scope text must never expose student names, grades, submissions, token values, or private paths.

### Review coverage

All existing Canvas-write code paths must call the new primitive once immediately before their POST write:

- Work push and quick assignment;
- Gradebook policy, sweep, extensions, and curves;
- Feedback posting.

Validation, preview, download, local artifact creation, and local-folder opening never show a Canvas-write review dialog.

## Verification — required, not optional

Run:

```powershell
rg "function canvasWriteReview" api/webui/static
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_gradebook_routes.py api/tests/test_push_service.py api/tests/test_feedback_pipeline.py api/tests/test_route_contract.py
```

The first command must produce no matches. Add source-contract tests that assert:

- `base.html` loads `write_review.js` before page-specific scripts;
- no legacy function definition remains;
- Gradebook and Feedback templates contain their action-scope elements.

Manual local-browser checks, with no final write confirmation:

1. Open one write dialog in Work, Gradebook, and Feedback; verify it is visually/behaviorally the same.
2. Cancel with Escape and with Cancel; verify focus returns to the original trigger and no request is made.
3. Keyboard-tab through each dialog; focus must not escape.
4. Change Gradebook and Feedback scope selections; verify action-scope copy changes immediately.

## Completion evidence required

Report command output, exact changed files, the zero-match result, and the four manual checks. Do not archive this handoff or claim completion without that evidence.

