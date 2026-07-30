# Glass Route Card

Glass is a local, student-free projector surface. An MCP-connected assistant can read its
contracts and public schedule/calendar context, then write only pending drafts in
`To Review/Glass`. The teacher previews and approves exact bytes in `/glass`; approved panes
are immutable content-addressed revisions in `Library/Glass/panes`, and one approved dated
scene is authoritative in `Library/Glass/scenes`.

`api/schedule/` remains CE-general and pure: `models.py`, `validate.py`, `loader.py`, and
`resolver.py` do not import Glass or routes. Glass calls it only to select a complete scene
block variant and to update its local display clock. Calendar reads are selected-settings
projections only; Glass neither reads arbitrary source CSVs nor writes Canvas.

The display rail is host-owned: it reports `Ready.`, the exact no-scene fallback, or the
generic `Some content is unavailable.` status. Pane source cannot supply rail text or error
details.

## Current ownership

| Path | Owns |
|---|---|
| `api/glass/panes.py` | Pane/scene schema validation, pending drafts, immutable pane revisions, atomic scene publication. |
| `api/webui/routes/glass.py` | Teacher review, guarded approval/discard, preview, and headerless display routes. |
| `api/mcp_server/tools.py` | Student-free contract, public context, pending draft, and compact list tools. |
| `api/webui/static/glass/display.js` | Local clock/current-block message updates only; no server subscription. |

## Sandbox limits

Each pane is an iframe with `sandbox="allow-scripts"`, opaque origin, `no-referrer`, and an
inline CSP that blocks network, navigation, forms, frames, and plugin content. Source and
assets are inlined. The parent accepts readiness only from the exact iframe window; it never
trusts opaque-origin `"null"`. Preview reduces but cannot prove away CPU-exhaustion from
approved JavaScript. A broken pane must not stop the host rail or other panes.

## Verification gate

Run the active handoff's focused Glass/MCP/calendar gate, then `py -m pytest api/tests`.
Rendered verification covers `/glass`, `/glass/display`, preview, populated display, and the
calm no-scene fallback at 1280x720, 1920x1080, 1280x800, and 1920x1200 with no overflow or
new console errors. Browser checks use a fictional temporary workspace only.
