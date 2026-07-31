# SmartDeck Route Card

SmartDeck is a local, student-free projector surface: a teacher-authored **Deck** of
**Slides** bound to their own Teacher Schedule block names (never clock times), displayed
full-screen on a classroom projector. An MCP-connected assistant authors a Deck and calls
`save_deck` directly -- there is no review/approval queue, no draft state. A valid call writes
the Deck live to `Library/SmartDecks/Decks/` immediately; the teacher's Display click is the
only human gate.

This supersedes an earlier, deleted feature called Glass, which used freeform sandboxed
HTML/CSS/JS "panes" instead of structured Slides. Nothing of that name or architecture
survives; do not resurrect it. See `docs/reference/Architecture Narrative - Scenes.md` for
the teacher's own historical origin brainstorm (terminology and numbers in that document are
historical, not current -- this route card is authoritative).

## Data flow

1. **Author**: an assistant calls `get_authoring_contract("deck")` for the SlideForge
   contract, then `save_deck(date, title, slides, widgets=None)`. `api/webui/sf.py` validates
   the payload (closed schema: `version`/`type`/`date`/`title`/`slides`/`widgets` only --
   `feed` is rejected outright, see "Feed system" below). `api/webui/deck_store.py` writes it
   atomically, archiving any prior revision for that date first.
2. **Manage**: the teacher opens `/smartdeck` to see Active / Templates / Archived / Widgets.
   Archive and Delete are moves, never deletes -- `delete_deck` relocates a file to
   `_System/Archive/SmartDecks/`, recoverable by hand.
3. **Display**: the teacher clicks Display, landing on `/smartdeck/display/{deck_id}`. The
   entire resolved Deck (every Slide's Teacher Schedule block resolved to today's actual
   start/end time) ships in one payload from `/smartdeck/display/{deck_id}/data` -- zero
   further network requests for the rest of the page's life. The display page picks which
   Slide to show via wall-clock matching (automatic, ties broken by authored order) or a
   manual Shuffle override (whole-deck, 29s interval, suspends wall-clock while active; Home
   resets to Slide 1 and hands control back to the clock).

## Current ownership

| Path | Owns |
|---|---|
| `api/webui/deck_schedule.py` | Pure stdlib: parses Bell Schedule / Day Calendar CSVs and a Teacher Schedule JSON; `resolve_day()` binds a block name to today's actual start/end. No file IO, no FastAPI, no workspace import. |
| `api/webui/deps.py` | IO layer over `deck_schedule.py`: discovers the workspace's Bell Schedule/Day Calendar CSVs and Teacher Schedule, and `resolve_schedule_for(date)` ties them together. |
| `api/webui/sf.py` | SlideForge parse/validate -- the `<SLIDEFORGE_JSON>` envelope, structural twin of `pf.py`/`af.py`/`rf.py`. |
| `api/webui/deck_store.py` | Revisioned, path-jailed (`Library/SmartDecks/`), atomic Deck storage: `save_deck`, `list_decks`, `load_deck`, `archive_deck`, `delete_deck`, `list_templates`. |
| `api/webui/routes/smartdeck.py` | `GET /smartdeck` (management page), `GET/POST /smartdeck/api/*` (list/archive/delete/readiness), `GET /smartdeck/display/{deck_id}` (display page) and `.../data` (the one-shot display payload). |
| `api/webui/templates/smartdeck.html` + `static/smartdeck/smartdeck.{js,css}` | Management UI: Active, Templates (Deck Templates + Slide Templates), Archived, Widgets. |
| `api/webui/templates/smartdeck_display.html` + `static/smartdeck/display.{js,css}` | The projector display: wall-clock Slide matching, manual Shuffle/Home, wall-clock-based timer widget (never `requestAnimationFrame`), persistent Maximize/Minimize/Close chrome. Extends the generic, feature-agnostic `layouts/display.html` (no app header, fills the viewport, no page scroll). |
| `api/smartdeck_feeds.py` | Feed resolution -- see "Feed system" below. Moved here from a now-deleted `api/glass/day_context.py`. |
| `api/default_docs/Calendars/` | Seeded Bell Schedule/Day Calendar CSVs (real Berry Miller Junior High / Pearland ISD data, public and non-PII) and academic-calendar CSVs (an older, unrelated feature). |
| `api/default_docs/SmartDecks/` | Seeded `Teacher Schedule.template.json` (a placeholder; the real one is created in the workspace, never the repo). |

## Storage layout

```
<workspace>/Library/SmartDecks/
  Decks/                  active decks, one JSON file per revision: <date>.r<N>.json
  Decks/Archived/         archived revisions, moved here (never deleted) on re-save or Archive
  Deck Templates/         starter decks (listed, not yet authorable -- no "save as template" flow exists)
  Slide Templates/        reusable slide layouts (same status)
<workspace>/Library/SmartDecks/Teacher Schedule.json    the teacher's real block-name mapping
<workspace>/_System/Archive/SmartDecks/                 where delete_deck moves a file (soft delete)
```

## Deck/Slide schema (SlideForge v1)

- Deck: `{version: "1.0-json", type: "DECK", date, title, widgets: [...], slides: [...]}` --
  closed schema, unknown top-level keys rejected, a `feed` key anywhere rejected outright.
- Slide: `{id, block, layout, title, body, widgets: [id, ...]}`. `layout` is one of
  `title_body`, `title_only`, `bulleted` -- the only three in v1, deliberately not arbitrary
  HTML. `block` is a Teacher Schedule block **name**, resolved to a real time only at Display
  time, never authored as a clock time.
- Widget: `{id, scope, kind, params}`. `kind = "timer"` is the only kind in v1
  (`duration_seconds` 1-86400, `label`, `autostart`). `scope` is `"deck"` (mounts once, the
  first Slide that references it; persists across every later Slide regardless of whether
  they reference it) or `"slide"` (fresh mount/unmount with every Slide's own showing, no
  preserved state).

## MCP tools (schema v14, 19 tools total; SmartDeck's own 9)

| Tool | Reads/writes |
|---|---|
| `get_bell_schedule(schedule_id="")` | Bell schedule CSV(s) from the workspace |
| `get_day_schedule(date)` | Resolved blocks for one date |
| `get_teacher_schedule()` | The teacher's own block-name mapping |
| `get_authoring_contract("deck")` | The SlideForge contract text (no staging/review appendix -- SmartDeck has no review queue, unlike every other Forge kind) |
| `save_deck(date, title, slides, widgets=None)` | Validates and writes a Deck live |
| `list_active_decks()` | Active decks only |
| `archive_deck(deck_id)` | Moves a Deck to Archived |

All seven skip the course gate and the outbound safety gate (no `course_id`, no student data)
-- same class of exception as `get_product_guide`/`list_staged_content`.

## Feed system (backend-only, not yet wired to authoring or display)

`api/smartdeck_feeds.py` holds a closed allowlist (`FEED_CATALOG`) of named references to
classroom-facing data: `bell_schedule`, `district_calendar_events`, and `school_events` have
real producers; `birthdays_today`, `missing_assignments`, `positive_achievements`, and
`staar_masters` are named (so a typo is still rejected the same way) but resolve to a graceful
"not yet available" -- that data has no producer yet (unstarted Canvas Mirror/roster work).
`resolve_feed(name, date)` raises only for a name outside the catalog entirely; a recognized
name never raises, degrading to less data on any internal failure. Every event resolved
through this module is tagged via `api/audience.py`, filtered to classroom-safe items only,
and has its `audience` tag stripped before it's returned -- see
`docs/contracts/classroom-facing-data-contract.md` for the enforcement rules this reuses
as-is.

**`sf.py` still rejects a `feed` key outright, on every Slide and at the top level.** Wiring
a Feed into what an assistant can author, and into what the display page renders, is
deliberately future work -- neither the design that led to this module nor any slice built so
far specifies how a Slide would bind to or render one, and inventing that model without a
spec would be scope creep. When that work happens, it must preserve this module's rule: an
assistant is told a feed exists and how it's shaped, never given a real value; only the local
display page ever resolves and renders one.

## Verification gate

`py -m pytest api/tests -q`. Manual/browser checks (the in-app preview pane used during
development has no compositing, so `requestAnimationFrame`/screenshots don't work there --
verify timer and Shuffle/Home behavior in a real browser): open `/smartdeck` on a fresh
workspace and confirm all four sections render with correct empty states; open
`/smartdeck/display/{deck_id}` for a seeded Deck and confirm Shuffle/Home work, the timer
counts down and survives a Slide change if deck-scoped, and the browser's network tab shows
nothing firing after the initial load.
