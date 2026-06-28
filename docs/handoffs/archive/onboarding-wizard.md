# Handoff: First-run onboarding wizard

**Lane:** Toyota (VS Code agent). **Planner:** Claude Code.
**Status:** ready to implement. This spec is self-contained — you should not need to ask the
planner anything. If something here conflicts with the code, trust the code and note it.

## Why

Canvas Expert is a local web app for teachers. A brand-new user currently has **no guided way**
to tell the app which Canvas instance they use, where to get a token, or where their working
folder should live. As of the de-district purge, `CANVAS_BASE_DEFAULT` is `""` — so a fresh
install has no Canvas URL at all. We need a friendly, neophyte-proof first-run flow that
collects: (1) workspace folder location, (2) Canvas URL, (3) API token, (4) optional calendars.

Read `CLAUDE.md` first — guardrails (token only in keyring, no PII/district data in repo,
local-only, contracts canonical) are non-negotiable and this feature touches credentials.

## What already exists (reuse — do NOT rebuild)

All in `api/webui/`:

- **`config.py`**
  - `get_canvas_base() -> str` / `set_canvas_base(url)` — machine-local Canvas base URL.
  - `get_token() -> str|None` / `set_token(token)` — token in OS keyring (Windows Credential
    Manager). `token_is_set() -> bool`.
  - `save_canvas_account(base_url, token=None)` — saves base always, token if provided.
  - `set_calendar(key, label, dates, periods)` — activate a calendar.
  - **No workspace-path setter yet — you will add one (see below).**
- **`workspace.py`**
  - `workspace_root()` — returns machine `workspace_path` override → else `$OneDrive\CanvasExpert`
    → else `None`. The override is read from `config.json`'s `workspace_path` key (line ~41).
  - `ensure_workspace()` — creates the subfolders and seeds them from `api/default_docs/`
    (including `Calendars/` → `calendar_template.csv` + `Summer_Session_Sample.csv`).
  - `onedrive_root()` — for suggesting a default location.
- **`deps.py`** — `list_calendar_files() -> [{name,label,path}]` lists CSVs in the workspace
  Calendars folder. Use for the calendar step.
- **Routes** (`routes/settings.py`, `routes/calendar.py`):
  - `POST /settings/canvas` — Form `base_url`, optional `token`. Saves both.
  - `POST /settings/test-connection` — Form `base_url`, optional `token` (falls back to stored
    token). Returns `{ok, display_name}` or `{ok:false, error}`. Read-only probe of
    `{base}/api/v1/users/self`.
  - `POST /api/calendar/load-builtin` — Form `name` (a filename in the Calendars folder).
    Activates that calendar. Returns `{ok, key, label, count, grading_periods}`.
- **Settings page** (`routes/pages.py` `settings_page`, `templates/settings.html`) — already
  renders the Canvas-account card and a data-driven calendar list with an empty-base state.
  Reuse its markup/JS patterns; the wizard is the *guided* version of the same actions.

## New work

### 1. Add a workspace-path setter — `config.py`
```python
def get_workspace_path() -> str | None:
    return _machine_load().get("workspace_path") or None

def set_workspace_path(path: str):
    state = _machine_load()
    state["workspace_path"] = path.strip()
    _machine_save(state)
```
(`workspace.py` already reads this key, so this is the only wiring needed.)

### 2. The gate — redirect unconfigured users to `/welcome`
Add FastAPI middleware (or a dependency on the page routes) in `server.py`:
- If `not config.token_is_set()` **or** `not config.get_canvas_base()`: redirect any HTML page
  request to `/welcome` (303). **Allowlist:** `/welcome*`, `/settings*`, `/static/*`, and the
  POST endpoints the wizard calls (`/settings/canvas`, `/settings/test-connection`,
  `/api/calendar*`, the new workspace endpoint). Never gate API/static, or you'll deadlock the
  wizard itself.
- Once configured, `GET /welcome` still works (reachable via a "Re-run setup" link in Settings)
  but is not forced.

### 3. New routes — `routes/onboarding.py` (new APIRouter, register in `server.py`)
- `GET /welcome` → renders `templates/welcome.html` (the wizard shell). Pass current state:
  `workspace_suggestion = workspace.onedrive_root()`, `canvas_base`, `token_is_set`.
- `POST /welcome/workspace` → Form `path`. Call `config.set_workspace_path(path)` then
  `workspace.ensure_workspace()`. Return `{ok, root, subfolders}`.
- Reuse `POST /settings/canvas`, `POST /settings/test-connection`,
  `POST /api/calendar/load-builtin` for the other steps — do not duplicate them.

### 4. The wizard UI — `templates/welcome.html` + `static/welcome.js`
A single page with stepped sections (show one at a time; client-side `next`/`back`). Match the
existing visual style (`static/style.css`, the `.card`/`.hint`/`.callout`/`.actions` classes).

- **Step 0 — Workspace.** "Where should Canvas Expert keep your files?" Prefill with
  `workspace_suggestion` (OneDrive) when present; let them edit/confirm. Explain it syncs across
  PCs if it's in OneDrive. On save → `POST /welcome/workspace`, show the created folders.
- **Step 1 — Canvas address.** "What web address do you use to log into Canvas?" One text input.
  **Normalize client-side** before saving: accept a full pasted URL (e.g.
  `https://x.instructure.com/courses/123`), strip path + trailing slash, prepend `https://` if
  missing → origin only. Show generic examples (`https://yourschool.instructure.com`). Validate
  with `POST /settings/test-connection` is not possible yet (no token) — just format-check here,
  save base via `POST /settings/canvas` (base only).
- **Step 2 — Token.** Now that the base is known, show a button linking
  `{base}/profile/settings` (new tab) + illustrated steps ("Approved Integrations → + New Access
  Token → purpose 'Canvas Expert' → Generate → copy"). Password input. **Live test:**
  `POST /settings/test-connection` with the pasted token; on `ok` show "✓ Connected as
  {display_name}" and enable Continue. Save via `POST /settings/canvas` (base + token).
- **Step 3 — Calendars (optional, skippable).** Fetch `GET /api/calendar` → show `available`
  (from `list_calendar_files()`, will include the seeded `Summer_Session_Sample.csv`). Let the
  user activate zero or more via `POST /api/calendar/load-builtin`. **None active by default.**
- **Step 4 — Done.** "You're set up." Link to dashboard (`/`).

## Acceptance criteria
- Fresh install (no `config.json`, no token) → opening any page lands on `/welcome`.
- Completing all steps results in: `workspace_path` set + folders seeded; `canvas_base` set;
  token in keyring (`token_is_set()` true); chosen calendars active.
- After completion, normal pages load and `/welcome` is no longer forced.
- The wizard never writes a token to disk or logs it. No district/PII strings introduced.
- URL normalization: pasting a deep link or a no-scheme host both yield a clean origin.

## Tests
- Add `api/tests/test_onboarding.py`: gate redirects when unconfigured; allowlist passes;
  `POST /welcome/workspace` sets the path + seeds; wizard not forced once configured.
- `api/tests/test_route_contract.py` — add the new routes to the contract list.
- Note: `TestClient` needs `httpx` (not currently installed). Either add `httpx` to
  `api/requirements.txt` (dev) or test the route handlers directly without the HTTP layer,
  matching how existing tests are written — check `test_route_contract.py` first.

## Do NOT touch
- The `LLM_Modules/*_Base.md` contracts.
- Token storage mechanism (keyring) or the local-only `127.0.0.1` bind.
- Anything that would put a real district URL, calendar, or name back into source.
