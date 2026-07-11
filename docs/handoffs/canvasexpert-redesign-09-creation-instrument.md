# Toyota handoff 09: creation Instrument view

## Objective

Add an expanded Instrument state for creation preview/delivery comparison using the same
Workbench job and DOM. No behavior or endpoint changes.

## Files

- `api/webui/templates/course_expert.html`
- `api/webui/static/course_expert/tabs.js`
- New `api/webui/static/course_expert/instrument.js`
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- `docs/reference/course-expert-module-map.md`

## Behavior

The explicit URL/query state is `?view=instrument`; Workbench is default. On load, query
`tab` overrides legacy hash when both exist. View changes preserve `tab` and unrelated
query params, use `history.pushState`, and do not change tab-selection URL behavior.
Unsupported/invalid Instrument state normalizes with `history.replaceState`. `popstate`
reapplies tab+view without adding history. Switching views does not reload, clone, reset,
or serialize form state. Instrument expands the active panel,
hides peripheral rails, and retains readiness, course focus, write targets, action scope,
and a visible return to Workbench.

Initial supported instruments:

- Assignment/Page/Rubric: existing source/validation output plus aggregate target/delivery
  summary. Do not fabricate a student preview or per-course server comparison.
- Quiz: existing whole/differentiated configuration and dry-run output at full width.
- Quick: compact multi-course target comparison.

Download and Reports remain Workbench-only. If an unsupported tab receives
`view=instrument`, normalize to Workbench without error.

## Verification

Prove same-node identity and retained values across Workbench -> Instrument -> Workbench,
query/deep-link behavior including `?tab=assignment&view=instrument`, legacy hash,
unsupported tabs, back/forward navigation, one ID each, keyboard focus, 1920/2560,
both themes, and zero console errors.

```powershell
node --check api/webui/static/course_expert/instrument.js
node --check api/webui/static/course_expert/tabs.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Stop if any instrument needs a second form or separate source of truth.

## Required implementer reply

One commit; report hash/files, same-node/state-retention proof, URL/back-forward matrix,
width/theme results, console count, and no live push.
