# Toyota handoff: shared scope and Canvas-write review primitives

## Objective

Replace the three duplicated Canvas-write confirmation implementations with one accessible shared primitive, and establish a uniform, local scope summary immediately before consequential actions.

This is deliberately **not** a global-course-context feature. A global context would be unsafe because Work supports multi-course push while Gradebooks, PowerGrader, and Feedback operate on one course/assignment. Scope remains owned by each workflow; the shared component only makes it unmistakable.

## Dependencies

Complete `docs/handoffs/webui-01-responsive-readiness.md` first. This handoff may rely on `window.CE_GRADEBOOK.syncReadiness`.

## Files to change

- **New:** `api/webui/static/write_review.js`
- `api/webui/templates/base.html`
- `api/webui/static/push/core.js`
- `api/webui/static/gradebook.js`
- `api/webui/static/feedback/push.js`
- `api/webui/static/style.css`
- `api/webui/templates/gradebook.html`
- `api/webui/templates/feedback_expert.html`
- `api/webui/static/push/course_picker.js`
- `api/webui/README.md` after implementation, to document the shared primitive's owner and load order.

Do not change POST endpoints, Canvas payloads, result formats, activity logging, or the contracts under `LLM_Modules/`.

## Required implementation

### 1. Create one global, accessible review API

Create `static/write_review.js`, loaded by `base.html` after the toast setup and before page-specific scripts. It must expose exactly:

```js
window.CE_WRITE_REVIEW = {
  confirm(options) // returns Promise<boolean>
};
```

`options` supports the currently-used fields: `title`, `action`, `targets`, `details`, `warnings`, `confirmText`, `cancelText`.

The dialog must retain the current useful behavior:

- target list including course name and ID;
- change detail list;
- explicit Canvas-effects warning list;
- Escape and backdrop cancel;
- focus moves to the safer Cancel button initially, restores to the original trigger when closed, and has a visible focus outline;
- `role="dialog"`, `aria-modal="true"`, and an accessible title;
- a clear destructive confirm label such as `Post grades/comments`, never generic `OK`.

Improve the existing dialogs rather than redesigning their visual language. Add a small focus trap using the dialog's two buttons: Tab from confirm moves to cancel and Shift+Tab from cancel moves to confirm. Do not add a dependency.

### 2. Delete the duplicate implementations

Remove the local `canvasWriteReview` function bodies from:

- `push/core.js`
- `gradebook.js`
- `feedback/push.js`

Replace all calls with `window.CE_WRITE_REVIEW.confirm(...)` (or a very thin local alias to that exact function). Preserve all existing caller-specific target, detail, warning, and button text. A missing global is a page-load integration error; do not silently fall back to `window.confirm`.

### 3. Add visible scope blocks where they are currently missing

Use a common visual class, e.g. `.ce-action-scope`, but keep content workflow-specific.

- **Work:** retain and refine the existing `course-scope-summary` behavior from handoff 01. Do not duplicate it beside every action.
- **Gradebooks:** add one `aria-live="polite"` scope block directly below the course picker. With no course it says `No course selected. Gradebook changes are unavailable.` With a course it says `Working in: <course>. Changes on this page affect this course only.` Update it inside `syncGradebookReadiness()`.
- **Feedback Push to Canvas:** add an `aria-live="polite"` scope block immediately above Preview. It has three states: select a course; select an assignment; or `Will post reviewed grades/comments for <assignment> in <course>.` Update it from existing course/assignment change handlers.

Do not expose student names, grades, submission content, or private paths in these scope blocks.

### 4. Make review semantics consistent

All Canvas writes available in the three areas below must use the shared primitive exactly once immediately before the POST that changes Canvas:

- Work pushes/quick assignment;
- Gradebook policy, sweep, extensions, and curves;
- Feedback result posting.

Preview, validation, downloads, local file generation, and opening a local folder must **not** invoke the Canvas-write dialog.

## Guardrails

- This UI component does not authorize a write. Existing backend validation remains authoritative.
- Do not collect or persist confirmation acknowledgements in the browser or workspace.
- Do not make claims that a local review makes any AI provider FERPA-safe.
- Keep the application local-only and do not introduce external JavaScript or analytics.

## Verification

Run:

```powershell
py -m pytest api/tests/test_gradebook_routes.py api/tests/test_push_service.py api/tests/test_feedback_pipeline.py api/tests/test_route_contract.py
```

Manual browser checks:

1. On a Work push, Gradebook policy apply, Gradebook curve/sweep apply, and Feedback post, confirm that the same dialog is used, Escape cancels, focus returns to the trigger, and no write happens after cancel.
2. Confirm the review dialog's Target section names the actual selected scope.
3. Change Gradebook and Feedback course/assignment selections; verify each scope block updates immediately and no student data appears.
4. Check keyboard-only navigation through the dialog, including Tab wrap and Escape.

## Acceptance criteria

- There is one implementation of Canvas-write review in `static/write_review.js` and no copies remain in the three former owners.
- Every listed write path receives a pre-write, cancelable review dialog.
- Scope is explicit at the point of action without creating unsafe global state.
- Existing backend tests pass and no Canvas API contract changes.

