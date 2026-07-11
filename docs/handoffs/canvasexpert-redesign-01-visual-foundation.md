# Toyota handoff 01: scoped scientific-instrument visual foundation

## Objective

Add the warm, dark-first, full-width visual vocabulary without changing any route,
workflow, persistence, Canvas call, or existing page layout.

## Files

- New `api/webui/static/workbench.css`
- `api/webui/templates/base.html`
- `api/tests/test_webui_template_contracts.py`

Do not edit `style.css` or any feature template/script.

## Load order

In `base.html`, load `/static/workbench.css?v={{ asset_v }}` immediately after
`style.css` and before the synchronous `write_review.js`. Preserve theme initialization
before CSS and `write_review.js` before `{% block content %}`.

Add these empty/default-compatible extension points without changing rendered legacy DOM:

```jinja2
{% block head_extra %}{% endblock %}
{% block app_header %}<header class="topbar">...existing header unchanged...</header>{% endblock %}
{% block status_strip %}{% endblock %}
{% block scripts_extra %}{% endblock %}
```

`head_extra` is inside `<head>` after shared dependencies; `app_header` replaces only the
header; `status_strip` is between header and main; `scripts_extra` is immediately before
`</body>`. Default rendering must be byte/DOM-equivalent aside from block whitespace.

## Required CSS contract

All new selectors are namespaced under one of:

```text
.ce-desk-* .ce-workbench-* .ce-instrument-* .ce-status-* .ce-operation-*
```

Define scoped custom properties for warm paper/graphite dark and light surfaces,
Canvas connectivity, model/privacy ready state, attention, prepared state, Create/Grade
subject marks, ledger rules, drafting grid, 1920/2560 shells, and visible focus.

Do not redefine generic `.card`, `.page`, `button`, `input`, `select`, headings,
`html[data-theme]`, or legacy page classes. New shells use width `100%`, a documented
desktop minimum of 1600px, and no arbitrary 736/880/1100/1440 cap. Existing pages must
remain unchanged because none yet use the new classes.

## Tests

Add source contracts proving the stylesheet appears exactly once, after `style.css`,
before content, and with `asset_v`; new selectors are namespaced; forbidden generic
selectors are absent; all four blocks occur exactly once in the required positions.
Preserve existing load-order tests.

```powershell
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

## Runtime verification

Before editing, capture untracked JSON for every indexed route/theme/width containing
topbar/main bounding rectangles, document scroll width, critical ID counts, and required
global types. After editing, repeat with lifespan off. Because legacy markup uses none of
the new classes, every numeric layout invariant must match within one CSS pixel, ID/global
values must match exactly, and the console must have zero new errors/warnings. Screenshots
are supporting evidence, not a pixel-diff oracle.

## Forbidden changes / stop

No visual redesign of a legacy page, no font download, no external asset, no new route,
no inline style migration. Stop if namespaced CSS cannot be loaded without altering an
unmigrated page or if `base.html` ownership from slice 00 is unresolved.

## Required implementer reply

One commit on `dev`; report hash/files, automated results, every rendered route/theme/width,
console count, and confirmation of no Canvas/AI/routine action and untouched unrelated work.
