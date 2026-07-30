# SmartDeck slice 3 — management screen

**Lane:** Toyota.
**Depends on:** slice 1 (`deps.resolve_schedule_for`), slice 2 (`deck_store`).
**Parallel with:** slice 4 — different files, one shared contract (the Display route). Agree
the route path `GET /smartdeck/display/{deck_id}` up front and the two slices don't interact.
**Design spine:** `docs/reference/smartdeck-design.md` §3.5, §4.

## Goal

A SmartDeck tab where the teacher sees today's decks and acts on them: **Display**, Archive,
Delete. Plus Templates and Widgets sections (list-only in v1). No authoring UI — the AI
authors via MCP (slice 2); this screen is the teacher's control surface.

## Files to change

### NEW `api/webui/routes/smartdeck.py`

`APIRouter`, following `api/webui/routes/pages.py` and `routes/connections.py` for structure.

```
GET  /smartdeck                         -> smartdeck.html
GET  /smartdeck/api/decks               -> {active: [...], archived: [...]}
POST /smartdeck/api/decks/{id}/archive  -> {ok, problems}
POST /smartdeck/api/decks/{id}/delete   -> {ok, problems}
GET  /smartdeck/api/readiness           -> {ready, missing: [...]}
```

The page context **must** include `"nav_section": "smartdeck"` — that's the convention
(`routes/pages.py:115` etc. pass it in the `templates.TemplateResponse(request, "x.html", {...})`
context dict).

Deck list items carry: `deck_id`, `date`, `title`, `revision`, slide count, whether the date is
today, and the resolved block names from `deps.resolve_schedule_for(date)`. Resolution problems
travel with the item so the UI can show "no schedule for this date" inline rather than
silently rendering a deck that can never advance.

`{id}` is teacher-supplied input reaching a filesystem lookup — it goes through `deck_store`,
which jails it (slice 2). **Do not build paths in this module.**

### EDIT `api/webui/server.py`

Two lines, matching the existing block shape:

- `from .routes.smartdeck import router as _smartdeck_router` (with the imports at ~line 44-65)
- `app.include_router(_smartdeck_router)` (with the calls at ~line 120-139)

### EDIT `api/webui/templates/layouts/_app_header.html`

A 7th primary nav entry after Connections (line 9), copying the exact pattern of its siblings:

```html
<a class="{% if nav_section == 'smartdeck' %}ce-app-nav--active{% endif %}" href="/smartdeck"{% if nav_section == 'smartdeck' %} aria-current="page"{% endif %}>SmartDeck</a>
```

Keep the `aria-current` half — every existing entry has it and screen-reader parity is not
optional.

### NEW `api/webui/templates/smartdeck.html`

`{% extends "base.html" %}`. Layout is left column 1/4 / right column 3/4 (§4). Use the
existing design tokens and component classes (`static/ui/tokens.css`, `foundation.css`,
`components.css`) — **do not introduce a new color, font, or spacing scale.** Read
`templates/roster.html` for a current two-column screen before inventing anything.

Right column sections, in order: **Active**, **Templates** (two lists: Deck Templates, Slide
Templates), **Archived**, **Widgets**.

Per §3.5 there is **no auto-archive by date** — past-day decks stay in Active until the teacher
acts. Show the date on every card so a stale deck is obvious; do not sort past decks away or
grey them out into invisibility.

### NEW `api/webui/static/smartdeck/smartdeck.js` + `smartdeck.css`

Vanilla JS, one folder per screen — matches `static/roster/`, `static/push/`,
`static/powergrader/`. No framework, no bundler, no CDN.

Fetch `/smartdeck/api/decks`, render the four sections, wire the three actions. Archive and
Delete both re-fetch rather than mutating the DOM optimistically — a deck's revision can change
underneath the page when the AI saves.

**Delete needs a confirm dialog** even though slice 2 makes it recoverable (the file moves to
`_System/Archive/SmartDecks/`). The button says Delete; the teacher should not discover the
recoverability by accident.

### EDIT `api/webui/readiness.py`

Add a SmartDeck component to the existing probe set, following `_component(status, code)`.
Ready when a Teacher Schedule, ≥1 bell schedule, and a Day Calendar all load. Otherwise
`unconfigured` with a code naming the first missing piece.

Slice 1 decided the empty state: when schedules are missing, the tab renders a clear "SmartDeck
isn't set up yet" panel listing what's absent — it does **not** offer deck actions, and it does
not crash. Onboarding flow proper (design doc open item 5) is out of scope; a static panel
pointing at the workspace folders is enough.

### NEW `api/tests/test_smartdeck_routes.py`

Follow `api/tests/test_desk_routes.py` / `test_gradebook_routes.py` for the client fixture and
workspace monkeypatching.

## Edge cases (each needs a test)

1. Workspace not configured → `GET /smartdeck` renders 200 with the empty state, no traceback.
2. Schedules missing → readiness reports `unconfigured` with the missing piece; deck actions absent.
3. `POST /smartdeck/api/decks/../../etc/passwd/archive` → refused by `deck_store`'s jail, 4xx or
   `{ok: false}`, nothing touched.
4. Archive a deck_id that doesn't exist → `{ok: false, problems: [...]}`, not a 500.
5. Deck whose `date` has no Day Calendar entry → card renders with the resolution problem shown.
6. Zero decks → Active section renders an empty state, not a blank hole.
7. Deck referencing a block name absent from the Teacher Schedule → surfaced on the card.
8. Templates and Widgets sections with nothing in them → visible headers, empty states.

## Test command

```bash
py -m pytest api/tests/test_smartdeck_routes.py -v
```

Then the suite:

```bash
py -m pytest api/tests
```

Manual check — `cd api; py qf_ui.py` → `http://127.0.0.1:8765/smartdeck`. Confirm the nav item
highlights, the six other nav entries still work, and the layout holds at a narrow window.

## Acceptance criteria

- SmartDeck appears as the 7th nav item and highlights via `nav_section`; the other six are
  unaffected.
- Active / Templates / Archived / Widgets all render, each with a real empty state.
- Archive and Delete round-trip: action → re-fetch → the card moves sections.
- With no workspace configured, the page still renders and explains itself.
- No path construction in `routes/smartdeck.py` — `grep -n "os.path.join" api/webui/routes/smartdeck.py`
  returns nothing; all path work lives in `deck_store`.
- No new CSS custom properties or hardcoded hex colors; `grep -n "#[0-9a-fA-F]\{3,6\}" api/webui/static/smartdeck/smartdeck.css` is empty.
- `py -m pytest api/tests` is green.

## Guardrails

- **#4 (local-only):** the router adds routes to the existing app on the existing `127.0.0.1`
  bind. Do not add a second server, change the bind, or add anything under `web/`.
- **#2 (FERPA):** no student data reaches this screen in v1. Deck cards show authored titles and
  block names. If you need a roster to render a card, you're in the wrong slice.

## Do not touch

- `api/webui/deck_store.py` and `df.py` — slice 2 owns them; call them.
- `static/ui/*.css` — consume the tokens, don't edit them.
- The Display *view* (`smartdeck_display.html`, `display.js`) — slice 4 owns it. This slice
  only links to `GET /smartdeck/display/{deck_id}`.
- The other six nav entries and their routes.
