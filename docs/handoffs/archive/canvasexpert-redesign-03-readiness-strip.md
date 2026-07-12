# Toyota handoff 03: truthful compact readiness strip

## Objective and decision

Add a compact confidence strip for Canvas, configured OpenRouter model, and local
privacy/workspace readiness. Probe state is process-local only and is forgotten on
restart. Configuration alone is never labeled ready.

## Files and load order

- New `api/webui/readiness.py` for pure probe/result normalization helpers.
- New `api/webui/routes/readiness.py`; register it in `api/webui/server.py`.
- New `api/webui/templates/_readiness_strip.html`.
- New `api/webui/static/readiness.js`.
- `api/webui/templates/base.html` (use the slice-01 `status_strip` and
  `scripts_extra` blocks; do not include the partial on legacy pages).
- `api/webui/templates/workbench_base.html` (override `status_strip`; load JS through
  `scripts_extra`, after the strip markup).
- `api/webui/static/workbench.css`.
- New `api/tests/test_readiness_routes.py`; update route/template contract tests.

## Exact probes and API

`GET /api/readiness` returns configuration plus the last probe in this process.
`POST /api/readiness/probe` runs at most once automatically per browser load when the
process state is unknown; an explicit Refresh may run it again. There is no polling.

- Canvas: call the existing `_canvas_get("/api/v1/users/self/profile")` through an
  injected timeout wrapper, with a five-second deadline. It is read-only.
- OpenRouter: move/reuse the pure key check behind `_probe_openrouter_key` from
  `api/webui/routes/settings.py`; it may call only OpenRouter's `/api/v1/auth/key`,
  with a five-second deadline. It sends no model prompt or course/student content.
- Privacy: verify the configured workspace system area is writable using a temporary
  probe file that is always removed, and verify the protection/scrub module imports.

Return `unknown|testing|ready|degraded|unconfigured`, checked time, configured model
label, and only stable redacted codes: `unconfigured`, `timeout`, `unauthorized`,
`network`, `workspace_unwritable`, `protection_unavailable`, or `model_unavailable`.
Never return URLs, keys, tokens, paths, provider bodies, or traces.

## Browser behavior

Desk and Workbench invoke POST once when GET says the process has no probe. The strip
is one line when healthy and expands only for a degraded action. Legacy pages neither
render the strip nor load `readiness.js`.

## Verification and stop conditions

Mock all external calls and test unconfigured, unknown, success, timeout, unauthorized,
network, unwritable workspace, redaction, once-per-process, and manual refresh.

```powershell
node --check api/webui/static/readiness.js
py -m pytest api/tests/test_readiness_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check
```

Render Desk/Workbench in both themes with lifespan off. Confirm exact request count,
zero secret/path content in DOM/network/console, zero writes/scoring calls, and zero
new console errors. Stop if either provider cannot be checked without content, the
five-second bound cannot be enforced, or legacy routes change. One commit; reply with
hash, mocked matrix, request counts, rendered evidence, and redaction evidence.
