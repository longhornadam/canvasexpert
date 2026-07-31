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
- AI Authoring file/rebuild routes: `api/webui/ai_ta.py` and `api/webui/routes/library.py`
- Persistence facade: `api/webui/config/__init__.py`
- Persistence modules: `api/webui/config/*.py`
- Self-update download/verify/stage: `api/webui/self_update.py`
- Update routes: `api/webui/routes/updates.py`

## Source-size reports

Use [`tools/size_report.py`](../../tools/size_report.py) for current source-size
reports; this map intentionally does not maintain line-count snapshots.

## Browser Routing

`settings.js` + feature files currently own:

- Canvas base/token reveal, save, and connection test flow
- OpenRouter key/model save, test, and current-model price loading
- Canvas course browser plus Current/Previous and removal actions
- download root, workspace folder open, and AI Authoring folder/rebuild actions
- academic calendar list, built-in load/remove, custom CSV parse, preview, save,
  and copy-LLM-prompt behavior
- checking for, downloading, and applying an in-app update (teacher-initiated
  only; no automatic check, ever)

Current split:

- `settings.js` - shared status/helpers bootstrap
- `settings/account.js` - Canvas token/base URL and connection testing
- `settings/openrouter.js` - OpenRouter key/model/model-list UX
- `settings/courses.js` - Canvas course browser and Current/Previous actions
- `settings/workspace.js` - download root, workspace, AI Authoring file actions
- `settings/calendars.js` - calendar list/load/parse/save/copy prompt
- `settings/class_schedule.js` - class schedule readiness line, block editor, and Calendars folder action
- `settings/updates.js` - update check/download/apply/cancel UX

## Backend Routing

`routes/settings.py` owns:

- `/settings/canvas`
- `/settings/openrouter`, `/settings/openrouter/test`, `/settings/openrouter/models`
- `/settings/courses/bookmark`
- `/settings/courses/{course_id}/remove`
- `/settings/courses/{course_id}/set-active`
- `/settings/download-root`
- `/settings/test-connection`

Class schedule setup is owned by `routes/schedule.py` and `schedule_setup.py`:

- `GET /api/schedule` returns readiness, the raw Teacher Schedule blocks, and folder paths.
- `POST /api/schedule/teacher` atomically replaces only the blocks array.

A block's `name` is the key a Slide binds to (`routes/smartdeck.py` `_resolve_slides` keys
blocks by name); `label` is display text only, and two blocks may share one. The editor keeps
them in separate fields for that reason. Deriving either from the other renames blocks on save,
which breaks existing slides and trips the duplicate-name check.

`readiness()` returns only what the panel renders. Add a field there when a surface starts
showing it, not in advance: an unrendered field costs a directory scan on every `/settings`
load and reads as covered when it is not.

`routes/updates.py` owns the self-update surface:

- `/api/update/status`, `/api/update/download`, `/api/update/apply`, `/api/update/cancel`

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
- workspace/AI Authoring folder issues: `settings.html`, `settings/workspace.js`, `settings.js`,
  `api/webui/workspace.py`, `api/webui/ai_ta.py`

## Guardrails

- Never write Canvas tokens to disk; keep token persistence in the OS credential
  store path already implemented by config.
- Do not add district URLs, real calendars, teacher names, or other district-specific
  defaults to source.
- Keep Settings local-only and do not introduce a public callback or OAuth route.
- Nothing in Settings writes to the Calendars folder. Bell schedule and day calendar CSVs are
  teacher-authored; the panel reads them and reports what it found. Every workspace is seeded
  with real district calendars, so the CSV shape is already on disk before anyone asks.
- Preserve the `config.*` facade and storage keys unless a migration is explicitly
  planned and tested.
- `config.active_courses()` is the compatibility-named Current-course boundary for
  normal pickers, Desk discovery, and automatic work. `saved_courses()` includes both
  Current and Previous courses.
- The self-update downloader only ever talks to the pinned public GitHub repo (or a
  loopback feed for local testing); never add a teacher-configurable update source.
