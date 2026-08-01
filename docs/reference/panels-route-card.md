# Panels Route Card

A Panel is one URL that renders one thing, chrome-free and responsive, meant to be
dropped into whatever display surface a teacher already uses. The first host is
Classroomscreen's Embed widget, which accepts arbitrary iframe HTML pointed at
`127.0.0.1` (verified live against a running CanvasExpert: the page loads, executes
its own JavaScript, and resizes like any native widget).

Nothing in the implementation is Classroomscreen-specific. The same URL works in a
browser tab fullscreened on a second monitor, an OBS browser source, or any other
iframe host, which is what keeps the display surface swappable and stops any single
third party from being load-bearing.

**Why Panels exist:** CanvasExpert already asks a lot of a teacher before it pays
anything back. A Panel attaches to a tool they already open every morning and shows
Canvas data on their board within a minute of pasting one line. It is an on-ramp
first and a feature second, which is why the wedge panel deliberately needs almost
no setup.

Panels are for the teacher's own machine. The URL resolves only where CanvasExpert
is running, which is a direct consequence of the privacy design (the browser fetches
from localhost, so no student data reaches the host site and the host cannot read
into a cross-origin iframe). Scope Panels as a personal-classroom feature and this
costs nothing.

## Route map

| Route | Purpose |
| --- | --- |
| `GET /panels` | Console: pick a Panel, set its options, copy the embed code |
| `GET /panels/{kind}` | The Panel itself, chrome-free |
| `GET /panels/{kind}/data` | The Panel's single data fetch, JSON |

Owner: `api/webui/routes/panels.py`, registered in `api/webui/server.py` next to
`_smartdeck_router`. Unknown kinds 404 from both the page and the data route.

## Current ownership

| Concern | File |
| --- | --- |
| Routes, catalog, and dispatch | `api/webui/routes/panels.py` |
| Public Calendar payload joins | `api/webui/panel_data.py` |
| Console page | `api/webui/templates/panels.html` |
| Console page CSS | `api/webui/static/pages/panels.css` |
| Today's bell schedule | `api/webui/routes/schedule.py`, `api/webui/schedule_setup.py` |
| what's due panel | `api/webui/templates/panel_whats_due.html` |
| Themes | `api/webui/static/panels/themes.css` |
| Shared responsive kit (CSS) | `api/webui/static/panels/panel.css` |
| Shared responsive kit (JS) | `api/webui/static/panels/panel.js` |
| Tests | `api/tests/test_panels.py` |
| Route surface | `api/tests/test_route_contract.py` |

## Two contracts that are easy to break by accident

**1. Panels are disk-only.** A Panel sits unattended on a projector for a whole
period. A live Canvas call would put network latency and token failures on a
classroom wall in front of thirty students. Every Panel reads the local catalog or
mirror and reports missing data as a named state. `whats-due` uses
`read_service.catalog_assignments` with `api.course_catalog.read_catalog`, the same
disk-only path `mcp_server/tools.get_course_assignments` uses.

**2. The port and URL shape are public contract.** A teacher pastes
`http://127.0.0.1:8765/panels/whats-due?block=ELA-7-B` into a board that Classroomscreen
saves, and that exact string has to keep working across restarts and upgrades. Two
reasonable-looking future changes would silently break every saved board weeks later:

- Adding "helpfully pick a free port" fallback to `api/qf_ui.py`. It currently pins
  `DEFAULT_PORT = 8765` and fails if the port is busy, which is the correct trade.
- Moving Panels onto generated ids instead of readable query params.

Both are noted in the `panels.py` module docstring, where someone would look before
changing them.

## Panel catalog

`PANEL_CATALOG` in `panels.py` is an allowlist, for the same reason SmartDeck has
three fixed layouts: a closed set is what keeps this from sprawling into a hundred
one-off pages nobody sweeps for responsiveness.

```python
PANEL_CATALOG = {
    "whats-due": {
        "title": "What's due",
        "blurb": "Upcoming assignment due dates for one course. No student data.",
        "template": "panel_whats_due.html",
        "needs_course": True,
    },
    "upcoming-events": {"template": "panel_upcoming_events.html"},
    "sports-results": {"template": "panel_sports_results.html"},
    "bobcat-hour": {"template": "panel_bobcat_hour.html"},
}
```

### whats-due

`whats_due_payload(course_id, days, *, now=None, catalog_reader=None)` returns
published assignments due through `today + days` local calendar days, future/upcoming
items first then earlier-today items (each bucket chronological). It always returns
`ok`, because a Panel on a wall has no way to report an exception; every outcome is a
named `state` the template renders calmly:

| state | Meaning |
| --- | --- |
| `no_course` | No course chosen yet (only reachable by calling the payload directly) |
| `no_catalog` | No local catalog; tells the teacher to refresh it |
| `nothing_due` | Catalog is fine, window is empty |
| `ready` | Assignments present; `stale` flags an out-of-date catalog but still serves |
| `no_schedule` | Following the schedule, but no Teacher Schedule block resolves |
| `calendar_needs_attention` | The canonical School Calendar is unconfigured, invalid, out of coverage, or names an unknown Bell Schedule for today |
| `not_school_day` | A canonical `no_school`/`no_regular_classes` day: weekend, holiday, summer |
| `day_over` | School day, past the last block |
| `block_without_course` | In a real block with no Canvas course linked (conference, duty, advisory) |
| `previous_course` | The resolved block's course is not a Current course; the panel never reads its catalog |

An earlier-today item stays visible through the end of the local calendar day even
after its due time passes, and is described neutrally, never as missing or late.
`days` is clamped to `MAX_LOOKAHEAD_DAYS = 31` so a hand-edited URL cannot ask for a
year; an item due on local `today + 7` is included, `today + 8` is excluded (with the
default `days=7`). Assignments with no due date, an unparseable due date, or
`published: false` are excluded. Naive timestamps are read as UTC rather than dropped.

`now` and `catalog_reader` exist as injection seams for tests. `catalog_reader` is
the same seam `read_service` already exposes, so tests never write a course to disk.

## The responsive model

This is the part most worth reading before adding a Panel, because getting it wrong
is easy and looks fine in a single screenshot. Teachers resize every panel on their
board, so resize behavior is a correctness property, not polish.

The natural mistake is sizing text off `min(vw, vh)` and multiplying down with `em`
fractions. That collapses on the wide short boxes teachers actually make, and a fixed
row count then crams tiny rows into a panel with dead space above and below.

What the kit does instead:

1. **Panel chrome** (title, footer) scales off `vw`/`vh`, generously.
2. **Rows flex to fill** whatever height is left over.
3. **Row text sizes off each row's own height** via container queries, so text is
   always a fixed fraction of the row it sits in, never of the viewport.
4. **Row count is computed in JS** from the measured box, bounded by *both*
   dimensions. Height alone is wrong: in a tall narrow panel the text ends up
   width-limited, so taller rows only add padding around small type.

Point 4 is the one that matters. A short panel shows three large rows and pages
faster; a tall one shows eight.

### Narrowing drops information, it does not shrink type

Three tiers in `panel.css`, each giving up something so what remains stays legible
from the back of a room:

| Tier | Behavior |
| --- | --- |
| `max-width: 470px` | Two columns become two stacked lines |
| `max-width: 300px` | Secondary line drops entirely; primary gets larger |
| `max-width: 300px` and `max-height: 200px` | Compact: the list is replaced by the headline number |

`departures.html` shows the same idea applied to a column layout: four columns become
three, then two.

### Rules key off structure, not class names

Tier selectors target `.p-row > *` and `.p-stack > *`, not the kit's own `.p-a`/`.p-b`
names. An earlier version keyed off class names, and one panel that happened to use
different names silently kept shrinking its type while every other panel adapted.
Mark badges and pills `.p-fixed` to keep them out of the wrapping rules.

### ResizeObserver alone is not enough

`Panel.onResize` pairs a `ResizeObserver` with a 400ms size poll. Some embedding
contexts never run the rendering lifecycle, and in those the observer never fires
while layout genuinely changes underneath it, so the row count freezes and the panel
looks broken. The poll is two integer reads and a no-op when the box has not moved.

### Kit API

```js
Panel.list({ body, dots, items, render(item, rowEl), every, divisor, minRow, maxRow, floor })
Panel.rowsThatFit(bodyEl, opts)   // for panels that manage their own rows
Panel.onResize(el, fn)            // debounced observer + poll
Panel.clamp(v, lo, hi)
```

Defaults worth leaving alone unless measured: `divisor 4.5`, `minRow 52`,
`maxRow 100`, `floor 15`. Raising `maxRow` starves rows of column width, because text
is sized against row width but constrained to its own column, so very tall rows clip
rather than fill.

## Following the schedule

**A Panel does not ask which course. It works that out from the clock.**
`resolve_panel_course` in `panels.py` is the single resolver every kind calls, so a
timer Panel and a what's-due Panel can never disagree about what period it is.

The chain reuses SmartDeck's own resolution, now via the canonical calendar:

```
today  -> school_calendar.resolve_date()   day kind + schedule_id, or a named repair state
       -> deps.load_bell_schedules()       periods with start/end
       -> deps.load_teacher_schedule()     blocks with raw_periods and course_id
       -> deck_schedule.resolve_day()      today's blocks, sorted by start
       -> now "HH:MM"                      the block meeting now, else the next one
```

`course_id` is an optional field on every schedule block, which is what makes this
work at all; the resolver also enforces the Current-course boundary before returning
one (`config.active_courses()`), so a block mapped to a Previous course reports
`previous_course` rather than reading that course's catalog. `_bell_schedule_feed` in
`smartdeck_feeds.py` does the same last step for SmartDeck's own display.

**Why a stable block name is a durability fix, not a convenience.** A course ID can
expire at the year rollover, leaving a saved board unable to distinguish "nothing due"
from "that course is gone". A schedule survives the rollover: the teacher updates it
once and every saved board follows.

`?block=<teacher-block-name>` is the one intentional override: a second monitor dedicated
to one section, or showing next period during conference. It still resolves through the
Teacher Schedule and still enforces the Current-course boundary -- it bypasses only
date/clock resolution, not the schedule or the course gate.

Between blocks the Panel looks ahead to the next one and labels itself `Next · ELA 7`,
rather than going blank during passing period. After the last block it stops, instead of
rolling to tomorrow, because an after-school board showing tomorrow's work reads as
today's.

**Following a schedule changes the refresh contract.** A 15-minute poll would leave last
period's work on the wall for up to 15 minutes after the bell, which defeats the point.
The payload returns `next_change` (the boundary this answer is good until) and the panel
sets one timer for 20 seconds past it. The 15-minute poll stays as the backstop for
catalog refreshes.

`resolve_panel_course` never raises. A missing workspace, an unreadable schedule file,
or a broken calendar all resolve to a named state with a calm message -- a projected
Panel shows the canonical Calendar's own repair states (`calendar_needs_attention`,
`not_school_day`) rather than a distinct, parallel notion of "no schedule."

Correcting a bell schedule for one date is the same operation as any other day edit --
preview/apply on the Calendar page -- not a Panels-local shortcut.

## Themes

`?theme=` skins a Panel. `PANEL_THEMES` in `panels.py` is the allowlist and the
dropdown order; `static/panels/themes.css` holds one rule block per key. Eight ship:
`ce` (default, the app's own palette), `natural`, `ocean`, `cottage`, `console`,
`wizardtrain`, `bauhaus`, `lisa`.

**A theme is a palette, a font, and one decorative layer. Nothing else.** It sets
custom properties on `html[data-panel-theme="…"]` and draws ornament on `body::before`.
It must never set a box property on `.p-row`, `.p-body`, `.p-head`, `.p-foot`,
`.p-stack` or `.p-title`, because `panel.js` measures the body box to decide the row
count: a theme that moved that box would change *what a panel shows*, not just how it
looks. `test_themes_never_restyle_the_sizing_model` enforces the selector boundary, and
the sweep below confirms the row count is identical across all eight themes at every
shape.

Three details worth keeping:

- **Ornament sits under the panel, not over it.** `.panel` is transparent so decoration
  shows through the gutters, while `.p-row` keeps an opaque background so row text
  always lands on flat colour. That is what lets `lisa` and `cottage` be busy without
  becoming unreadable. Ornament is switched off below 320x210, where the panel is
  already dropping content.
- **Colour literals belong to themes only.** `panel_whats_due.html` maps its own classes
  onto theme variables (`--row`, `--pill-bg`, `--today-ink`, `--when-ink`, `--warn-ink`)
  and hardcodes nothing. A literal left in a panel survives theme switching and looks
  broken in the other seven skins.
- **`resolve_theme` never rejects.** An unknown, retired, or hand-edited theme falls back
  to `ce` with a 200. 404-ing here would take a saved board down weeks later over a
  decoration.

Fonts come from `/static/fonts/fonts.css`, which is self-hosted. A theme must not
reference a webfont the machine would have to fetch; `cottage`'s serif is Georgia
precisely because it is already on every machine this ships to.

Contrast is a correctness property, not taste: a panel is read from the back of a room.
Every text-on-background pairing in every theme measures at least 4.5:1, verified rather
than eyeballed. When adding a theme, measure it.

## Adding a Panel

1. Add an entry to `PANEL_CATALOG` with `title`, `blurb`, `template`, `needs_course`.
   Consume theme variables for every colour; hardcode none.
2. Add a payload function returning `ok` plus a named `state`, never raising.
3. Branch to it in `panel_data`.
4. Write the template: link `panel.css` and `panel.js`, use `.panel` / `.p-head` /
   `.p-body` / `.p-foot`, set theme via the CSS custom properties (`--bg`, `--ink`,
   `--title`, `--muted`, `--rule`, `--accent`).
5. Add the three routes' paths to `EXPECTED_PRESENTATION`'s sibling in
   `api/tests/test_route_contract.py` only if you add new route *paths*; new kinds
   need no route-contract change, which is a benefit of `{kind}` being a path param.
6. Sweep it (below).

Templates must not contain inline `style="` attributes; a presentation contract test
enforces this repo-wide.

## Verification gate

- `py -m pytest api/tests/test_panels.py api/tests/test_route_contract.py -q`
- Full suite for anything touching `server.py` or the macros:
  `py -m pytest api/tests -q`
- **Responsive sweep, required for any new or changed Panel.** Load the panel in
  iframes at a spread of shapes and assert no overflow, no clipped text, and a
  legible floor. Shapes that have caught real defects: `240x140`, `430x200`,
  `590x300`, `720x270`, `900x560`, `1100x180`, `200x800`, `300x900`, `1920x1080`.
  Measure **leaf** elements that actually contain text; selecting `.p-row > *`
  measures wrapper divs once a panel nests content and reports a font size no human
  sees. Force-revalidate the shared assets first
  (`fetch(url, { cache: "reload" })`), or the sweep silently measures a cached
  `panel.css`.

## The console

`/panels` is a builder, not a brochure. It sits in the top nav where SmartDeck used to,
and SmartDeck moved into More.

The rail lists the panel kinds first and a Reference group (Embedding, Limits) second.
The stage opens on one builder per kind. Explanation lives in those two reference
sections and nowhere else, per the "Who these pages are for" section of
`docs/reference/webui-presentation-system.md`: a teacher opening this page mid-day is
configuring a panel, not learning what panels are.

Two things on the page are deliberate:

- **The shape buttons under the preview** (Wide, Banner, Tall, Small) stand in for a
  teacher dragging the widget's corner. They resize only the preview frame, never the
  address. Resize behavior is the property most likely to disappoint someone who only
  ever saw one screenshot, so the page shows it instead of describing it.
- **The address is shown in full next to the embed code.** A teacher who does not want
  an iframe still needs the URL, and the whole string visible is what makes the
  durability claim checkable.

## Natural next steps

- More kinds from local data: today's schedule, a timer bound to the bell schedule,
  gradebook summaries. The console's "Coming next" section names these, so adding one
  means removing its card there.
- MCP authoring. Two distinct modes worth keeping separate: *configuring* a data
  panel (pick kind, course, options, hand back a URL), and *authoring* a content
  panel (write the words, route through the existing staging and approval flow).
  Configuration lets an assistant build a panel without ever seeing a student,
  because the panel fetches its data locally at render time.
- Keep generation parameterized rather than freeform. An assistant emitting bespoke
  HTML per teacher inherits every responsiveness failure mode above with none of the
  sweep that catches them.

## Related

- `docs/reference/smartdeck-module-map.md` - SmartDeck's own route card. SmartDeck is
  CanvasExpert's in-house projector surface; Panels target surfaces the teacher
  already uses. Panels now share SmartDeck's schedule resolution (see Following the
  schedule above); its deck store and feed system remain unused by Panels.
- `api/webui/README.md` - rendered-verification recipe.
