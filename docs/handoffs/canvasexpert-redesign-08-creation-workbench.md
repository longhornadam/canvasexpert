# Toyota handoff 08: Course Expert creation Workbench shell

## Objective

Convert `/course-expert` into the full-width Workbench composition while preserving every
creation capability, DOM ID, public browser seam, script dependency, deep link, and live
write behavior.

## Files

- `api/webui/templates/course_expert.html`
- `api/webui/static/course_expert/tabs.js`
- `api/webui/static/push/course_picker.js` only for context rendering
- New `api/webui/static/course_expert/work_rail.js`
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- `docs/reference/course-expert-module-map.md`

## Layout

`course_expert.html` extends `workbench_base.html`; use its `app_header`, `status_strip`,
and `scripts_extra` contract and do not reload shared CSS.

Use exactly one copy of every existing form/panel/ID:

```text
Work rail | active creation workspace | operation summary
```

Work rail sections: Start, Continue, Attention. Start activates existing Quiz,
Assignment, Page, Rubric, Quick, Download, and Reports panels. Continue/Attention consume
registry summaries and navigate rather than cloning forms.

The shell exposes kind-specific phases using existing controls only:

- Quiz: Source -> Validate -> Preview -> Delivery.
- Assignment/Page/Rubric: Source -> Validate -> Delivery.
- Quick: Define -> Delivery.
- Download: Select -> Download.
- Reports: Select -> Generate.

Unavailable phases are absent, not disabled or fabricated. The right rail is called
**Summary**, not Prepared,
until a real operation exists in slice 10. It states “Canvas unchanged” only when true.

## Hard compatibility

Preserve `_push_common_scripts.html` and its exact order, followed by feature scripts and
CourseExpert scripts. Preserve `window.CE_PUSH`, `CE_QUIZ`,
`CE_COURSE_EXPERT.activateTab`, legacy globals, `?tab=`, hashes, focused-vs-target course
semantics, standalone `/push/*` routes, and all form IDs.

No endpoint/payload change. Do not call immediate results prepared or receipts.

Change CourseExpert to extend `workbench_base.html`; standalone `/push/*` pages continue
extending legacy `base.html`. Preserve CourseExpert body/main classes used by current
selectors and add namespaced classes rather than replacing them.

## Verification

```powershell
node --check api/webui/static/course_expert/tabs.js
node --check api/webui/static/course_expert/work_rail.js
node --check api/webui/static/push/course_picker.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_push_service.py api/tests/test_route_contract.py
git diff --check
```

Runtime all tabs plus every standalone push route at 1920/2560, dark/light: one critical
ID each, globals, deep links, source selection, fictional validation/dry-run, context,
no horizontal page scroll, zero console errors. No live push.

Stop if layout requires duplicated forms/IDs or script reordering.

## Required implementer reply

One commit; report hash/files, JS/test results, per-tab and standalone-route runtime matrix,
ID/global/load-order evidence, console count, and no live push.
