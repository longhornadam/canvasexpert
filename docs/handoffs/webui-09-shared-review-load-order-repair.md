# Toyota handoff: repair shared-review load order and portable tests

## Status and authority

This is a stop-the-line repair for commit `4c3cddd`. Implement only this handoff, in one
commit, then stop and report evidence. Do not start another WebUI slice and do not move
this file to `archive/`; Ferrari or the user will archive it after acceptance.

The cause and solution are already decided. No architecture or product judgment is
delegated.

## Confirmed failure

`api/webui/templates/base.html` currently loads `write_review.js` after
`{% block content %}`. Child templates place page-specific scripts inside that content
block, so Gradebook and Work execute before `window.CE_WRITE_REVIEW` exists.

Confirmed runtime effects:

- `/gradebook`: `gradebook.js` throws while reading `window.CE_WRITE_REVIEW.confirm`;
  `window.CE_GRADEBOOK` is never initialized and feature modules cascade-fail.
- `/course-expert`: `push/core.js` throws at the same dereference;
  `window.CE_PUSH` is not initialized.

The new source-contract test incorrectly checks only that the script name occurs in
`base.html`. It does not prove execution order. The same test file also hard-codes one
developer's repository path.

## Exact files to change

- `api/webui/templates/base.html`
- `api/tests/test_webui_template_contracts.py`

Do not change `write_review.js`, Gradebook/Work feature scripts, routes, APIs, CSS,
templates other than `base.html`, handoffs, documentation, or any engine files.

## Exact implementation

### 1. Load the shared dependency synchronously before content

In `base.html`:

1. Move the existing tag unchanged except for location:

   ```html
   <script src="/static/write_review.js?v={{ asset_v }}"></script>
   ```

2. Place it inside `<head>`, immediately after the `style.css` link and before
   `</head>`.
3. Remove the old trailing copy near the end of `<body>`.
4. Do not add `defer`, `async`, `type="module"`, an inline fallback, or a second copy.

This exact synchronous head placement is required because child-template classic scripts
execute while the body/content block is parsed.

### 2. Make source-contract tests portable

In `test_webui_template_contracts.py`:

1. Add `from pathlib import Path`.
2. Replace the absolute `ROOT` string with:

   ```python
   ROOT = Path(__file__).resolve().parents[2]
   ```

3. Replace `_slurp` with:

   ```python
   def _slurp(rel: str) -> str:
       return (ROOT / rel).read_text(encoding="utf-8")
   ```

4. Update any glob usage to use `ROOT / ...` or `Path.rglob`; no absolute string path may
   remain.

### 3. Correct the load-order contract test

Replace `test_write_review_loaded_before_page_scripts` with assertions that prove all of
the following:

- `/static/write_review.js` occurs exactly once in `base.html`.
- Its index is before `{% block content %}`.
- Its index is before `</head>`.
- The containing script tag has neither `defer` nor `async`.

Do not treat `wr_idx > 0` as meaningful load-order evidence.

## Required automated verification

Run exactly:

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_gradebook_routes.py api/tests/test_push_service.py api/tests/test_route_contract.py
```

Also run:

```powershell
rg -n "D:/Development Projects|D:\\Development Projects" api/tests/test_webui_template_contracts.py
rg -n "write_review.js" api/webui/templates/base.html
```

Expected results:

- pytest passes;
- the developer-path search returns no matches;
- the script-name search returns exactly one match located inside `<head>`.

## Required rendered-app verification

Launch the normal local app with `cd api; py qf_ui.py`. Perform read-only checks only;
do not send an AI request or write to Canvas.

### `/gradebook`

- `window.CE_WRITE_REVIEW` exists.
- `window.CE_GRADEBOOK` exists.
- Policy and sweep controls initialize normally.
- Browser console has zero new errors or warnings from Canvas Expert scripts.

### `/course-expert`

- `window.CE_WRITE_REVIEW` exists.
- `window.CE_PUSH` exists and `typeof window.CE_PUSH.currentCourseId === "function"`.
- Course picker and Work tabs initialize normally.
- Browser console has zero new errors or warnings from Canvas Expert scripts.

### `/feedback-expert`

- `window.CE_WRITE_REVIEW` exists.
- Page initializes without console errors.
- Do not prepare a real batch or invoke OpenRouter.

## Completion evidence required

The implementer reply must contain:

1. Commit hash and exact changed files.
2. Pytest command and pass count.
3. Both `rg` command outcomes.
4. The three route-verification outcomes, including the exact global-state checks and
   zero-console-error result.
5. Explicit confirmation that no Canvas write or external AI request occurred.

If the implementer cannot perform the rendered-app checks, it must stop and report that
limitation. It must not claim completion, archive the handoff, or substitute source-text
tests for runtime evidence.

