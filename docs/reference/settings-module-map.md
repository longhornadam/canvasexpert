# Settings Module Map

Routing scope: open this map only when the active handoff touches Settings, then use the
relevant section. It is not global executor context and does not replace the handoff's
exact file/symbol list.

As of 2026-07-08, Settings browser logic is split into plain feature files loaded
from a small shared bootstrap. Keep this map current if the load order or ownership
changes again.

## Ownership

- Page template: `api/webui/templates/settings.html`
- Browser owner: `api/webui/static/settings.js`
- Feature files: `api/webui/static/settings/*.js`
- Settings route owner: `api/webui/routes/settings.py`
- Calendar routes: `api/webui/routes/calendar.py`
- AI-TA file/rebuild routes: `api/webui/ai_ta.py` and `api/webui/routes/library.py`
- Persistence facade: `api/webui/config/__init__.py`
- Persistence modules: `api/webui/config/*.py`

## Source-size reports

Use [`tools/size_report.py`](../../tools/size_report.py) for current source-size
reports; this map intentionally does not maintain line-count snapshots.

## Browser Routing

`settings.js` + feature files currently own:

- Canvas base/token reveal, save, and connection test flow
- OpenRouter key/model save, test, and current-model price loading
- Canvas course browser plus Current/Previous and removal actions
- download root, workspace folder open, and AI-TA folder/rebuild actions
- academic calendar list, built-in load/remove, custom CSV parse, preview, save,
  and copy-LLM-prompt behavior

Current split:

- `settings.js` - shared status/helpers bootstrap
- `settings/account.js` - Canvas token/base URL and connection testing
- `settings/openrouter.js` - OpenRouter key/model/model-list UX
- `settings/courses.js` - Canvas course browser and Current/Previous actions
- `settings/workspace.js` - download root, workspace, AI-TA file actions
- `settings/calendars.js` - calendar list/load/parse/save/copy prompt

## Backend Routing

`routes/settings.py` owns:

- `/settings/canvas`
- `/settings/openrouter`, `/settings/openrouter/test`, `/settings/openrouter/models`
- `/settings/courses/bookmark`
- `/settings/courses/{course_id}/remove`
- `/settings/courses/{course_id}/set-active`
- `/settings/download-root`
- `/settings/test-connection`

Config persistence is already split under `api/webui/config/`. Keep the
`from .. import config` facade stable; callers should not import submodules directly
unless there is a strong reason.

## First Places To Look By Symptom

- token/base URL problems: `settings/account.js`, `settings.js`, `routes/settings.py`, `config/canvas.py`
- OpenRouter settings/model list: `settings/openrouter.js`, `settings.js`, `routes/settings.py`,
  `config/canvas.py`, `api/openrouter_client.py`
- Current/Previous course problems: `settings/courses.js`, `settings.js`, `routes/settings.py`,
  `config/courses.py`
- calendar parse/load problems: `settings/calendars.js`, `settings.js`, `routes/calendar.py`,
  `config/calendars.py`
- workspace/AI-TA folder issues: `settings.html`, `settings/workspace.js`, `settings.js`,
  `api/webui/workspace.py`, `api/webui/ai_ta.py`

## Guardrails

- Never write Canvas tokens to disk; keep token persistence in the OS credential
  store path already implemented by config.
- Do not add district URLs, real calendars, teacher names, or other district-specific
  defaults to source.
- Keep Settings local-only and do not introduce a public callback or OAuth route.
- Preserve the `config.*` facade and storage keys unless a migration is explicitly
  planned and tested.
- `config.active_courses()` is the compatibility-named Current-course boundary for
  normal pickers, Desk discovery, and automatic work. `saved_courses()` includes both
  Current and Previous courses.
