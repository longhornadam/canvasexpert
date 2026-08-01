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
| `GET /panels` | Console: pick a Panel, point it at a course, copy the embed code |
| `GET /panels/{kind}` | The Panel itself, chrome-free |
| `GET /panels/{kind}/data` | The Panel's single data fetch, JSON |

Owner: `api/webui/routes/panels.py`, registered in `api/webui/server.py` next to
`_smartdeck_router`. Unknown kinds 404 from both the page and the data route.

## Current ownership

| Concern | File |
| --- | --- |
| Routes, catalog, due-window logic | `api/webui/routes/panels.py` |
| Console page | `api/webui/templates/panels.html` |
| what's due panel | `api/webui/templates/panel_whats_due.html` |
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
`http://127.0.0.1:8765/panels/whats-due?course=123` into a board that Classroomscreen
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
}
```

### whats-due

`whats_due_payload(course_id, days, *, now=None, catalog_reader=None)` returns
published assignments due between now and `days` out, soonest first. It always
returns `ok`, because a Panel on a wall has no way to report an exception; every
outcome is a named `state` the template renders calmly:

| state | Meaning |
| --- | --- |
| `no_course` | No course chosen yet |
| `no_catalog` | No local catalog; tells the teacher to refresh it |
| `nothing_due` | Catalog is fine, window is empty |
| `ready` | Assignments present; `stale` flags an out-of-date catalog but still serves |

`days` is clamped to `MAX_LOOKAHEAD_DAYS = 31` so a hand-edited URL cannot ask for a
year. Assignments with no due date, an unparseable due date, or `published: false`
are excluded. Naive timestamps are read as UTC rather than dropped.

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

## Adding a Panel

1. Add an entry to `PANEL_CATALOG` with `title`, `blurb`, `template`, `needs_course`.
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
  `py -m pytest api/tests -q` (1761 passing at time of writing)
- **Responsive sweep, required for any new or changed Panel.** Load the panel in
  iframes at a spread of shapes and assert no overflow, no clipped text, and a
  legible floor. Shapes that have caught real defects: `240x140`, `430x200`,
  `590x300`, `720x270`, `900x560`, `1100x180`, `200x800`, `300x900`, `1920x1080`.
  Measure **leaf** elements that actually contain text; selecting `.p-row > *`
  measures wrapper divs once a panel nests content and reports a font size no human
  sees. Force-revalidate the shared assets first
  (`fetch(url, { cache: "reload" })`), or the sweep silently measures a cached
  `panel.css`.

## State as of this card

Shipped and committed: the three routes, the `whats-due` panel, the console with a
course picker, days control, live preview and copy-embed button, the shared kit, and
10 tests.

Observed by measurement: every route and status, both empty states, the 31-day clamp,
the panel across seven shapes from 240x140 to 900x500 with no overflow or clipping
and message text 14.4-44px, and the console's embed string updating live.

Inferred rather than observed: the populated-row layout. Its markup is structurally
identical to the swept demo panels, but no course catalog exists to fill it until the
district populates courses in mid-August. A local `list_courses` returning zero is
the expected state before then, not a broken install.

## Natural next steps

- A `/panels` entry in the top nav.
- More kinds from local data: today's schedule, a timer bound to the bell schedule,
  gradebook summaries.
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
  already uses. SmartDeck's schedule resolution, deck store and feed system are the
  reusable engine if a schedule-aware Panel is ever wanted.
- `api/webui/README.md` - rendered-verification recipe.
