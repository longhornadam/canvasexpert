# Glass Route Card

Routing scope: open this card when the active handoff touches Glass, the schedule engine, or
the projector display. It carries the subsystem's durable state so nobody has to re-read the
foundation brief or re-derive a decision already made. It does not replace a handoff's exact
file and symbol list.

## What this subsystem is

Glass is a classroom projector display: an always-on screen at the front of the room showing
the period and countdown, the day's learning goal, today's work, what is on offer during
Bobcat Hour, upcoming events, and a rotating banner. It is driven by a **day plan** composed
by the assistant each morning and reviewed by the teacher. At runtime Glass is a dumb player
of that plan plus a clock resolved against a bell schedule.

The projectors are touch-aware, so Glass is also an interactive surface. It carries widgets
the teacher operates with a finger. One exists: a work timer.

`api/schedule/` is a separate, CE-general engine. Glass is its first consumer, not its owner.

## Invariants

These are the rules a future executor should check work against. The reasoning is attached to
each so it does not have to be rebuilt from scratch or argued again.

1. **Two layers, split by whether they need human review.** The day plan is composed once
   each morning, reviewed, and durable for the day. Live state (a timer running, which widget
   holds the focus slot, which banner item is showing) is transient, unreviewed, and lost on
   refresh. Only the plan is persisted. This split is what makes the review gate mean
   something.
2. **The runtime is dumb.** Glass renders a plan and resolves a clock against a schedule. No
   scoring, no derivation, no Canvas calls, no model calls, anywhere in `api/schedule/`,
   `api/glass/`, `api/webui/routes/glass.py`, or `static/glass/`. Every judgement that needs
   intelligence happens at compose time, outside the runtime.
3. **The intelligence is the assistant, not a form.** There is no goal editor, criteria
   builder, assignment picker, or club manager, and there must not be one. The assistant reads
   the week's module and writes the goal; corrections happen by the teacher telling the
   assistant. Every field the schema pins down is leverage; an editor around a field the
   assistant should fill is a liability.
4. **Staleness within a day is acceptable and must not be engineered against.** No polling, no
   cache invalidation, no period-boundary recomputation. A plan composed at 7:15 is correct
   enough at 3:00. This is a product decision from the teacher, not an oversight, and the whole
   client architecture depends on it.
5. **The real files live in the workspace, not the repo.** Bell schedules, day plans, Bobcat
   Hour offerings, and section names are workspace files the teacher authors. The repo carries
   a blank template plus one fictional sample, following the `Library/Calendars` precedent.
6. **Glass reads; it never writes to Canvas and never touches the operation ledger.** It will
   consume the mirror in a later batch and writes only its own display state, which is to say
   nothing on disk at all today. A Canvas mutation here is a stop and an architecture
   conversation, not a slice.
7. **The schedule engine is CE-general.** `api/schedule/` must not import `api/glass/` or
   `api/webui/routes/`, and `api/glass/` must not import `api/webui/routes/`. "Which section is
   in the room right now" is useful to CE proper, so the engine stays independent of its first
   consumer.
8. **Identity is per-widget, not per-app.** When the data layer arrives it must be able to
   return either the real name or the vault pseudonym, and each widget declares which it wants:
   real names for seating and turn-taking, pseudonyms for anything score-adjacent. Nothing is
   wired this batch, and the plan schema deliberately does not foreclose it.
9. **Nothing on the glass is addressed to one student by name.** The display is public. The
   banner will use vault pseudonyms; no panel resolves a real student to a place, a score, or
   an obligation. A Bobcat Hour feature that needs to know which student goes where is a stop.
10. **Touch changes live state only.** A finger can start a timer. It cannot edit the day plan,
    the bell schedule, or the offering list. If a widget appears to need a persisted setting,
    that setting is a compose-time plan field, not a touch affordance.

### Why Glass is a CanvasExpert surface and not a separate project

This reverses an earlier recommendation made in design conversation. The reversal is
deliberate and is recorded so it is not relitigated.

Glass has no independent existence: it needs the workspace, the vault, the mirror, the MCP
server, and the WebUI shell. It is structurally identical to PowerGrader and Seating, which is
to say a page under `api/webui`, state in the workspace, engine modules in `api/`. The earlier
argument for separation rested on Glass having a runtime profile that had to be independently
bulletproof. That evaporated once Glass became a player of a prebuilt file: it has no runtime
Canvas dependency at all, which makes it less demanding than the surfaces already shipping,
not more. CE already models a district academic calendar and already loads it from a workspace
folder, and the bell schedule is the same kind of object.

## This batch

The first batch built the data model, the resolver, the page, and one widget. Nothing calls a
model, reads the mirror, touches the vault, or exposes an MCP tool.

### Modules

| Path | Owns |
|---|---|
| `api/schedule/models.py` | Vocabulary: `Block`, `SubBlocks`, `DayType`, `BellSchedule`, `Resolved`, `NextOccurrence`. No I/O, no clock. |
| `api/schedule/validate.py` | Structural checks over a parsed `BellSchedule`. Reports problems, never raises. |
| `api/schedule/resolver.py` | `resolve(schedule, at, no_school_dates=, override=)` and `next_occurrence(schedule, at, kind, ...)`. Pure. |
| `api/schedule/loader.py` | JSON to models, discovery in `Library/Glass`, the sample rule, and `SectionMap` parsing. |
| `api/schedule/calendar.py` | Thin no-school wrapper over `api.webui.config`. The only impure file in the engine. |
| `api/glass/schema.py` | Character budgets, day-plan dataclasses, `parse_day_plan`, `validate_day_plan`, `clamp`. |
| `api/glass/store.py` | Day-plan discovery and load from `Library/Glass/day-plans`. |
| `api/glass/view.py` | Builds the render blob from schedule, plan, and instant. No Jinja, no FastAPI, no disk, no clock. |
| `api/webui/routes/glass.py` | The `/glass` route. Picks the instant, gathers the pieces, hands one structure to the template. |
| `api/webui/templates/layouts/display.html` | The fourth template family: header-less, full bleed, no width clamp, no page scroll. |
| `api/webui/templates/glass.html` | The page. Every element the browser writes into is rendered, hidden rather than omitted. |
| `api/webui/static/pages/glass.css` | Internal layout only. Two declared numbers carry the design. |
| `api/webui/static/glass/widgets.js` | The widget contract: registration, tray ownership, focus-slot arbitration, period-change notification. |
| `api/webui/static/glass/runtime.js` | One clock ticking against one static day. Paints rail, progress, strip, panes, banner. |
| `api/webui/static/glass/timer.js` | The one widget. |

### The layered architecture

**Pure engine.** `api/schedule/` resolves a moment against a schedule with no I/O and no clock
read. The instant arrives as a parameter and no-school dates arrive as a frozenset. Two
conventions it holds all day: when a period splits into A and B lunch, elapsed and remaining
are measured across the active sub-block rather than the parent period, and remaining minutes
round up while elapsed minutes round down, so a rail never says "0 min" while a class is
still in session.

**On-disk layer.** `loader.py` and `store.py` read the workspace. Both import
`api.webui.workspace` lazily inside functions, because `api.webui.config._io` pulls in
`keyring` and a bare schedule import must not drag a credential backend along with it.
Neither raises for a bad file: every failure comes back as a note to display, because a blank
projector is a worse failure than a note.

**View builder.** `api/glass/view.build_view(...)` returns the whole resolved day as one dict:
every block with its times and its plan slice, the resolved current moment, the next Bobcat
Hour, the pane the browser will flip to, events, banner text, short rail tags, and the
collected notes. Every string bound for the screen has already passed through `clamp` at its
field's budget.

**Thin route.** `GET /glass` reads the schedule, reads today's plan, asks the academic calendar
for no-school dates fourteen days out, reads the plan for the next Bobcat Hour after today,
and renders. `?at=<ISO8601>` pins the instant for the whole render and reaches the browser with
ticking suspended; an unparseable value falls back silently to the real clock, because the
page's job is to be on the wall.

**Client runtime.** The entire day is serialised once into `#glass-data`. `runtime.js` ticks
the local clock against that static structure and swaps which block is active, so nothing
fetches, polls, or asks the server to recompute anything at a period boundary. This is what
makes invariant 4 real, and it is also how the screen changes itself between classes and how
the rail updates underneath a running widget. All live state is in memory and is lost on
refresh, deliberately: no endpoint accepts it, and the JS touches no storage API.

### File formats and where they live

Everything Glass reads sits in one folder, `Library/Glass`, and the contracts for all of it are
written out in `api/default_docs/Glass/README (Glass contracts).txt`, which seeds into that
folder. That file is the canonical field-by-field statement for a teacher or an assistant
authoring these files; what follows here is the map, not the spec.

**Bell schedule.** `Library/Glass/*.json`, format `canvasexpert.bell_schedule/1`.
JSON rather than CSV because container blocks nest and nesting is not tabular. A day type is
an ordered list of blocks; a block may carry `sub_blocks` with a mode:

- `sequential` children partition the parent exactly, first child at parent start, last child
  at parent end, no gaps and no overlaps. This is A and B lunch inside a period on a Friday,
  Homeroom First, or Pep Rally day. The validator enforces the partition.
- `concurrent` children all run for the parent's whole span and carry a label and a location.
  This is Bobcat Hour's simultaneous offerings. They partition nothing, and the validator
  rejects a `lunch`-kind child inside a concurrent parent.

`weekday_default` keys are stringified `date.weekday()`, 0 for Monday; a weekday absent from
the map is not a school day. `date_overrides` is the calendar-authored exception list and wins
over the weekday default. Keys beginning with an underscore are inline documentation and are
skipped by the parser, which is why the shipped files can explain themselves.

The folder ships the contracts README, `bell-schedule-template.json`,
`section-map-template.json`, and `Mockingbird-Junior-High-Sample.json`. The sample defines all
four day types
(`bobcat_hour`, `friday`, `homeroom_first`, `pep_rally`), only `bobcat_hour` carries a
`bobcat_hour` block, and its `date_overrides` use 2099 dates so nothing reads as a real
calendar.

**Sample versus real.** `Library/Calendars` globs every CSV, so a shipped sample there is
indistinguishable from real data. For a bell schedule that would put wrong times on a
projector all day, so every shipped file carries `"sample": true`. `discover_bell_schedule()`
prefers a file without it; if only samples exist it loads one, sets `is_sample`, and the page
carries a quiet "Sample schedule" tag in the rail plus a sentence in the notes. Two non-sample
files is a reported error rather than a silent pick. Section-map files sitting in the same
folder are recognised by their format string and skipped.

**Day plan.** `Library/Glass/day-plans/YYYY-MM-DD.json`, format `canvasexpert.day_plan/1`. The
file name is the authority on the date; a plan whose internal `date` disagrees renders with a
note. Three scopes because the content has three authors: `school_wide` (events, Bobcat Hour
offerings), `teacher` (`bobcat_hour_here`, what is happening in this room during that block),
and `sections` (learning goal, success criteria, work, banner). `day_type_override` is the
same-day override, a day-type id that wins over the calendar for this date without the
schedule file changing. It lives on the plan because the plan is the thing being written at
6:55am after the email arrives.

`sections` keys are `block_id`s, not Canvas section ids, so rendering needs no lookup. A block
with no entry renders an empty focus slot, which is the honest answer for a conference or duty
period, not an error.

**Why one folder in the Library.** All of it is teacher-visible content the teacher or the
assistant authors, so it is in the Library beside Calendars where a teacher can find and edit
it. There is no second Glass folder anywhere.

Workspace seeding: `LIBRARY_SUBFOLDERS` includes `"Glass"`, which self-seeds from
`api/default_docs/Glass/`; `_seed_folder_if_missing` walks the source tree, so `day-plans/` and
its contents come along. `ensure_workspace()` also creates `Library/Glass/day-plans`
explicitly, so an empty one exists where git could not have shipped it. The shipped
`day-plan-template.json` and `day-plan-sample.json` sit inside `day-plans/`, which is safe
because `available_plan_dates()` counts only well-formed `YYYY-MM-DD.json` names.

**A naming tension, stated honestly.** The schedule engine is CE-general by locked decision 7,
while its data now sits in a folder named for its first consumer. That is accepted: a second
consumer would read the same file in the same folder rather than getting a folder of its own.

### Character budgets

| Field | Budget |
|---|---|
| `learning_goal` | 90 |
| `success_criteria[]` | 40 |
| `work[].name` | 34 |
| `work[].detail` | 44 |
| offering label (school-wide and teacher) | 30 |
| offering location (school-wide and teacher) | 12 |

Single source: `CHARACTER_BUDGETS` in `api/glass/schema.py`, with named constants read from
that mapping. Both halves of the rule import it and neither retypes a number.
`validate_day_plan` reports every over-budget field with its length and its budget, so the
teacher can shorten their own text at compose time; `clamp` truncates anything that still
arrives long, ending in a single ellipsis character and never returning more characters than
the budget. The renderer clamps and truncates; it never reflows, because a goal that wraps to
three lines pushes everything else off the bottom of a projected screen.

### Registry literals a new surface has to update

Missing any of these fails an existing test, and the list is easy to miss:

1. `api/tests/test_presentation_contracts.py`: the route's row in `EXPECTED_PRESENTATION`
   (now 13 entries, asserted by literal), and its feature stylesheet in the `FEATURE_CSS`
   tuple.
2. `api/tests/test_route_contract.py`: the path and its methods in `EXPECTED`, for example
   `('/glass', ('GET',))`.
3. `api/webui/README.md`: the page-map table row, plus a module-routing section for anything
   split across several files.
4. `api/webui/templates/layouts/_app_header.html`: the nav anchor. Glass renders no header of
   its own but still gets a nav entry so a teacher can find it; the route passes
   `nav_section: "glass"`.
5. `api/webui/workspace.py`: any new Library or `_System` folder name.
6. `api/webui/server.py`: import the router and `include_router` it.

## The widget contract

The contract is the valuable artifact of the touch work, for the same reason the schedule model
is: get it right and every later widget is cheap. It is documented at the top of
`api/webui/static/glass/widgets.js` and that comment block is the canonical statement.

**What a widget declares.**

| Field | Meaning |
|---|---|
| `name` | Short unique id. Also the tray owner key. |
| `launcherLabel` | The words a launcher row would show. No launcher exists yet; declared now so the second widget does not retrofit one. |
| `claimsFocus` | Whether the widget may take over the focus slot. A tray-only widget declares false. |
| `trayStates` | `{ stateKey: elementId }`. Tray markup lives in the page template, one element per state, and the runtime shows exactly one. |
| `defaultTrayState` | Which state key the widget rests in. |
| `buildFocus(ctx)` | Returns the element to place in the focus slot. Called once, lazily, only if the widget ever claims focus. |
| `summon(ctx)` | The widget is now the tray owner. Wire listeners here. |
| `dismiss(ctx)` | No longer the tray owner. Stop everything live and release the focus slot. |
| `onPeriodChange(ctx, period)` | The bell rang underneath it. |

**Summoning and dismissal.** `window.CE_GLASS_WIDGETS` publishes `register`, `summon`,
`dismiss`, `showTray`, `notifyPeriodChange`, `onFocusChange`, `focusOwner`, `trayOwner`,
`launchers`, and `setHost`. Exactly one widget owns the tray at a time; summoning a second one
dismisses the first. That is the seam a launcher row will drive. The runtime summons the first
registered widget once the parser has finished, on `DOMContentLoaded` rather than on a zero
timeout: widget modules load after the runtime, and a timeout can fire between two scripts,
which leaves the tray with no owner and every tap doing nothing.

**Live state.** `ctx.state` is a plain object, created per widget, held in memory, and lost on
refresh. There is no endpoint that accepts it and nothing writes it to disk. `ctx` also exposes
`claimFocus`, `releaseFocus`, `hasFocus`, `showTray`, `trayState`, `goalLine`, and `day`. A
widget that wants to persist something is a stop condition, not a feature request to absorb.

**When the period changes underneath a running widget.** The runtime repaints the rail, the
progress line, the day strip, the panes, and the banner on its own, underneath whatever holds
the focus slot, then calls `onPeriodChange` on every registered widget inside a try block so
one widget cannot stop the clock. The widget decides what to do. The rule for anything that
counts down: keep running, because it counts wall time. A teacher who started ten minutes of
work at 9:15 wants it to finish at 9:25 whether or not a bell rang. An idle widget should
release the focus slot so the new period's learning goal comes back.

**Reach rules.** A teacher standing at a projected image can comfortably reach its lower
portion and not its top, so:

- Everything touchable lives in the tray along the foot of the screen, inside the bottom third.
  No interactive control goes above that band. The page deliberately has no exit or navigation
  link at all, because a link would be an interactive element outside the band, and the teacher
  has a browser.
- No hit target smaller than 9% of screen width. `--glass-touch-min` is declared once at
  `10.5vw` and applied as `min-width`, comfortably above the floor.
- No hover-dependent affordances and no small dismiss buttons.
- Nothing destructive on a single tap. Students will touch this screen.
- **The tray transforms and never changes height.** `--glass-tray-height` is declared once at
  `26vh` and the tray container uses it; the two states are grid siblings in the same cell of
  which exactly one is shown. Starting or stopping a timer cannot move anything above the tray.
  A tray that grew would shove the learning goal around mid-class.

**The one widget: the work timer.** At rest the tray is the timer, so tapping a preset starts
one directly. With a single widget a launcher would be pointless indirection. Presets are 5,
10, 15, and 20 minutes plus Custom, which starts at one minute and is built up with plus one
minute, so there is no keypad on a projected surface. While running the tray becomes pause,
resume, plus one minute, and reset. Reset sits past a flexible spacer, is styled apart with
`--ce-danger`, and arms rather than acts: the first tap changes it to "Tap again to reset" for
four seconds. The timer claims the focus slot while running and the learning goal collapses to
its one-line form, and under two minutes the digits and the filled bars turn `--ce-danger`,
which is the only colour change on the page and therefore only ever means "time is nearly up".

**Only one widget exists on purpose.** The contract is the deliverable; the catalogue is not.
Random student picker, group maker, dice, spinner, scoreboard, noise meter, and drawing or
annotation are all out, however small they look now that the tray exists. A test asserts that
`timer.js` registers exactly once and mentions none of them.

## Open decisions

This section is the one that saves the next person time. Read it before planning anything.

**The real schedule is not authored yet.** Only the blank template and the fictional
Mockingbird Junior High sample are shipped. The teacher's own bell schedule and day-type
calendar have not been written yet; they are workspace files. The page runs on sample data
until they exist and says so quietly in the rail.

**The teacher-run projector day has not happened.** One full Bobcat Hour day on the real
projector in the real room is the brief's manual criterion: correct period and countdown all
day with no intervention, goal and work readable from the back row, the Bobcat Hour pane
flipping from today to tomorrow on its own, and the timer started, paused, and reset by hand
without reaching above shoulder height. It is the only criterion that can fail after the code
is green, and it is still outstanding.

**Events and banner items carry no character budget, and that is now a decision rather than an
omission.** The brief's budget table defines six budgets and does not cover these two, so none
was invented, and the teacher confirmed on 2026-07-29 that they stay unbudgeted for now. They
are bounded structurally instead: events are a single ellipsised line each and whole items are
shed when the rail runs short of room, and the banner is one ellipsised line.

Revisit when the banner is actually wired to the mirror and the vault. That is the point where
unbounded generated text starts arriving instead of hand-written text, and it is the moment to
add budgets to `schema.py` plus validator rows plus clamping in the view. Until then the six
budgeted fields are the whole contract.

**Long lists move; they are not capped and not clipped.** This is a design principle from the
teacher, recorded on 2026-07-29, and it should govern the next such decision too: Glass is not a
static screen, so a list longer than its pane rotates rather than being truncated, bounded by a
schema cap, or given a scrollbar. The Bobcat Hour pane pages through its offerings on a 17
second interval, holding its height constant, with a quiet `1 to 11 of 25` label under the list.
It does not rotate when everything fits, because motion with nothing to reveal is just noise,
and most days fit.

Two supporting details worth keeping. The interval is 17 seconds rather than a rounder number
because 15 and the banner's 12 coincide every 60 seconds, which reads as the whole screen
pulsing in unison. And rotation is suspended under a frozen clock: `?at=` parks the pane on the
first page and never starts the tick, without which the geometry tests measure a moving target
and fail intermittently.

**The shed priority took two fixes, and the first one alone would not have worked.** Worth
reading before touching the rail, because the failure looked like the opposite of its cause.
`shed()` hid trailing items only while *that list* overflowed, so nothing ever asked events to
yield on Bobcat's behalf. But the rail's tracks were `minmax(0, auto) auto minmax(0, 1fr)`, with
the flexible track under **events**, so even once events had shed all six items the freed space
went to a track holding nothing. Events measured 0 of 6 while the Bobcat pane sat at 260.1px of
a 411.0px rail: the yielding was already happening and buying nothing.

Both had to change. `.glass-panes` is now `auto minmax(0, 1fr) auto` so the pane that holds its
ground is the one that grows, and `shedPanes()` is priority-driven, yielding from events then
work while re-measuring against whether Bobcat fits, and never yielding from the Bobcat list at
all. At 24 offerings the pane now shows 11 rows rather than 8, at both viewports.

The trade is real and unchanged from the brief: a day with a long offering list empties the
events pane first, by design. Capacity is measured after shedding, so it tracks actual pressure
rather than being a fixed number; a before-school page with an empty work pane fits 12. The
final page can be short, one row of 25 at full pressure, because remainder paging never repeats
a row. Sliding the last window back to keep every page full is the alternative and was
deliberately not chosen.

**Rendered geometry is measured, not inspected.** `api/tests/glass/test_glass_geometry.py`
drives a real browser through Playwright and measures the page with `getBoundingClientRect()`
at 1280x800 and 1920x1200, both 16:10. It is the repo's first browser-driving test, and it
covers the three criteria that cannot be proven from source text: no element overflows its
container under over-length strings, every interactive element sits inside the bottom third and
is at least 9% of viewport width, and the tray's height is identical across rest, running,
paused, reset-armed, and after-reset.

The tests **skip cleanly** when Playwright's Chromium is absent, following the posture of
`engine/tests/unit/test_physical_html_parity.py`. To enable them:
`py -m playwright install chromium`. A skip is not a pass; if you are relying on these
criteria, check that they actually ran.

Two fixture gotchas are encoded there and are worth knowing before writing a second such test.
Holding `sync_playwright()` open for the whole session leaves an asyncio loop running under the
rest of the suite and breaks unrelated tests in `api/tests/test_api_error_contract.py`, so
Playwright is opened and closed inside each test. And Playwright locates its browsers under
`%LOCALAPPDATA%`, which the session isolation fixture in `api/tests/conftest.py` deliberately
empties, so a session-scoped fixture resolves the executable path before that isolation applies
and each launch is handed the path outright. The isolation fixture is not weakened.

The page is served to the browser as a real subprocess, because the page reads the workspace and
an in-process monkeypatch cannot reach it. The subprocess gets its own `LOCALAPPDATA` and a
machine config written before launch, which supplies `workspace_path` and short-circuits legacy
migration so the real `api/webui/config.json` is never touched. The token half of the onboarding
gate comes from `keyring`, so a fictional keyring backend is installed in that process only; the
real credential store is neither read nor written, and the gate allowlist is unchanged.

**`section-map.json` is written and validated but read by nobody.** It exists so a later batch
can answer "4th period is Canvas section X". Day plan slices are keyed by `block_id` and are
deliberately decoupled from Canvas sections, so nothing reads the section map at render time.
Do not couple them without a decision.

**The Bobcat Hour lunch question is closed.** Bobcat Hour is the lunch hour and has no A and B
split. Students eat, attend tutorials, and go to clubs, largely self-determined and spread
across the building. Its sub-blocks are simultaneous offerings, its `blocks` list is empty in
the schedule file because offerings are day-plan content that changes weekly, and the
validator rejects a lunch split inside it. Do not reopen this.

**Non-goals a future executor will feel pressure to add.** All of these were considered and
declined:

- MCP tools of any kind.
- The morning compose step, and any model call.
- Mirror or vault reads, and real missing-work data. The banner renders hand-written plan text
  only.
- Event or club auto-import from mail. Offerings are hand-written.
- Club sign-up, rosters, capacity, attendance, or any per-student Bobcat Hour assignment. Glass
  lists what is on offer; it does not place anyone.
- QR codes. Everything is in Canvas and students already go there.
- A goal editor, criteria builder, club manager, or any other authoring form.
- Period-boundary recomputation or any freshness machinery.
- Any second widget.
- Phone or second-device control.
- Multi-school or multi-campus support.

**Documentation gap.** `docs/reference/webui-presentation-system.md` still describes three
template families and does not mention `display`. Worth folding in the next time that document
is touched.

## Verification discipline

**Commands.**

- Full gate: `py -m pytest api/tests` from the repo root. Current state is 1747 passed, 0
  failed, 0 skipped.
- This subsystem: `py -m pytest api/tests/schedule api/tests/glass`. 224 tests, 114 in
  `api/tests/schedule/` and 110 in `api/tests/glass/`. Twelve of the glass tests are the
  Playwright geometry pass and will skip rather than fail if Chromium is absent, so check that
  they ran before trusting the geometry criteria.
- Read-only render harness: `py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765
  --lifespan off`, run from `api/`. Then `http://127.0.0.1:8765/glass?at=2099-09-14T11:30:00`
  for any state of any day.
- Shipped-data check: the only schedule content in the repo should be the template and the
  fictional Mockingbird sample.

**How the layers are tested.** The pure engine is unit-tested with no I/O at all: the instant
is a parameter and no-school dates are a frozenset, so every state is reachable without waiting
for 12:13 to come around. Resolver coverage spans all four day types and, for each, the first
block, a mid-block moment, both sides of a passing period, both sides of lunch where defined,
before school, after school, and a weekend or calendar no-school date. `next_occurrence`
coverage includes the Friday case that resolves forward to Monday, a Pep Rally day, and the day
before a no-school date. The route is tested against a frozen clock through `?at=`, which is
the repo's first frozen-clock seam and is deliberately boring: every pure function takes the
instant as a parameter and no module reads the clock internally.

**Hard constraints that existing tests enforce.** These are not Glass-specific, they are
repo-wide, and one of them bit this batch already:

- **No `except ImportError` or `except ModuleNotFoundError` in production code under `api/`.**
  Enforced by AST walk in `api/tests/test_beta075_imports.py`, which also bans flat
  (non-`api.`-prefixed) imports of owned modules. `schedule/calendar.py`, `schedule/loader.py`,
  and `glass/store.py` all import their heavier dependencies function-locally, which is what
  keeps `api/schedule/` and `api/glass/` importable without pulling in `keyring`. Where such an
  import needs a guard at all, it guards on `except Exception` and never on an import-error
  name; `schedule/calendar.py` is the only place that currently does. This is the constraint
  that caught this batch out once: `loader.py` shipped an `except ImportError` fallback around
  `validate`, written while that sibling module did not yet exist, and it failed the sentinel
  the moment both landed. The fallback is gone and the import is direct.
- **No visual literals in feature CSS.** `VISUAL_LITERAL_RE` in
  `api/tests/test_presentation_contracts.py` bans `font-family:`, hex colours, `rgb(`, `hsl(`,
  `border-radius:`, and `box-shadow:` across every file in `FEATURE_CSS`. Use the shared
  tokens; `--ce-danger` and `--ce-attention` already exist and are theme-aware.
- **No static `style="` attribute in any template.** Checked recursively over `templates/`.
  Dynamic sizing is set from JS, which is why the progress fill's width is assigned in
  `runtime.js`.
- **Shared `ce-*` component classes are never JS selectors.** Use an id, a feature class, or
  `data-ce-hook`. Asserted both repo-wide and again over the three Glass JS files.
- **Every rendered `id` attribute on a page must be unique.** Asserted per route against the
  real response text. Easy to break on a page like this one, which renders every element the
  browser will later write into rather than omitting it conditionally.

**Glass-specific structural tests worth knowing about**, all in
`api/tests/glass/test_glass_route.py`: nothing touchable sits outside the tray; the tray height
and the touch floor are each one declared value; reset is set apart and asks a second time; the
under-two-minutes state uses the shared danger token; the widget contract is a registration
seam with exactly one widget on it; the page never polls and never reaches for anything live
(no `fetch`, no `XMLHttpRequest`, no `WebSocket`, no `EventSource`, no URL of any kind in the
JS); live state is never persisted (no storage API, no cookie); and the Python never calls a
model or writes to Canvas.

## Two deviations from the brief and the build spec

Both are the code being right and the plan being incomplete. Describe reality, not the plan.

**`build_view` takes an optional `next_plan`.** The Bobcat Hour pane always shows the next
Bobcat Hour that has not ended yet, so after the block ends it is tomorrow's, and tomorrow's
offerings have to come from tomorrow's plan. Showing today's clubs under tomorrow's heading
would be wrong on the wall all afternoon. The route therefore loads the plan for the next
Bobcat Hour falling after today and passes it in, and the view renders both candidate panes
(`bobcat_hour` and `bobcat_hour_after`) into the blob so the browser can flip on the clock with
no second request. When that plan is not written yet the pane still shows its heading and its
times and says the offerings arrive with that day's plan.

**`NextOccurrence.is_today` means "the first day the search looked at", not "is the calendar
date today".** `next_occurrence` sets it from `offset == 0` of its own search. The follow-up
lookup for the pane the browser flips to is anchored at tomorrow's midnight, so its
`is_today` is true for tomorrow. This already caused one bug, which is why
`view._bobcat_blob` compares `occurrence.on == today` against a date passed in rather than
reading the flag. Anything else consuming `NextOccurrence` should do the same.
