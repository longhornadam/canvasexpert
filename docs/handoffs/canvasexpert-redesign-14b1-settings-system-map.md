# Toyota handoff 14b1: Settings system map

## Objective

Replace the long Settings card stack with a professional system map while preserving every
form, ID, credential boundary, persistence owner, and onboarding behavior.

## Files

- `api/webui/templates/settings.html`
- `api/webui/static/settings.js` and feature modules only for map section activation
- `api/webui/static/workbench.css`
- `api/tests/test_webui_template_contracts.py`
- `api/tests/test_workspace.py`
- `docs/reference/settings-module-map.md`

## Map

`settings.html` extends `workbench_base.html` and does not reload shared Workbench CSS.

Nodes: Canvas, Workspace, AI provider, Courses & Calendars, Privacy & Identity, and Content
Library. Each node shows truthful configured/unknown/ready/degraded state and
reveals exactly one existing form region. Do not duplicate forms or call configured
credentials ready without probe evidence.

First add stable semantic IDs to the six existing form regions, one ID per region, and
map nodes to those IDs; do not infer ownership from card position. Canvas includes its
base/token controls, Workspace its configured root and download location, AI provider its
OpenRouter controls, Courses & Calendars bookmarked courses/calendar activation, Privacy
& Identity tier/protection controls, and Content Library the AI-TA rebuild. There is no
invented “Application” node.

Do not change keyring use, synced vs machine-local ownership, OpenRouter cost/model
warnings, course/calendar data, workspace paths, tier tags, library rebuild, or Welcome.

Run settings/workspace/route/template tests and JS checks. Render every node at 1920/2560,
both themes, configured/unconfigured/degraded states. Settings may intentionally display
the configured path inside its protected form; that path must not appear in logs, console,
network evidence, screenshots committed to the repo, or readiness/list APIs. No page
horizontal scroll, zero console errors. Stop if grouping needs persistence changes.

```powershell
node --check api/webui/static/settings.js
py -m pytest api/tests/test_workspace.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

One commit; report hash/files, commands/pass counts, node/state runtime matrix, redaction,
console count, and no credential/persistence change or unrelated staging.
