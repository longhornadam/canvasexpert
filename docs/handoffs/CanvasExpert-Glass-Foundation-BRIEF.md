# Brief — Glass, a screen that knows what day it is

**Active execution brief. Written 2026-07-28.** One vertical batch. First batch of a new
subsystem, so there is no route card to read yet; writing one is an acceptance criterion
of this batch (§8.8).

Glass is a classroom projector display: an always-on screen at the front of the room showing
the period and countdown, the day's learning goal, today's work, what is on offer during
Bobcat Hour, upcoming events, and a rotating missing-work banner. It is driven by a **day
plan** the assistant composes each morning, and at runtime it is a dumb player of that plan.

The room's projectors are touch-aware, so Glass is also an interactive surface. It carries
**widgets** the teacher operates with a finger, starting with a work timer.

---

## 1. The shape of the whole thing

> Pull information in, standardise its formatting, then let AI assistants do interesting
> things with it.

That is the project, and it is why this batch builds a data model and a renderer and no
intelligence at all. The valuable artifact here is not the screen. It is the **standardised
format**: a schedule the machine can resolve, and a day plan with known fields and known
budgets. Once those exist, composing a good screen each morning is something an assistant is
already good at, and so is everything nobody has thought of yet.

An executor working this brief will repeatedly feel the pull to add a form, a picker, or a
derived value. Resist it. Every field the schema pins down is leverage; every editor built
around a field the assistant should fill is a liability.

## 2. Objective

Put a correct, legible Glass screen on a real projector for a full school day, driven by the
real Berry Miller bell schedule and a hand-written day plan.

Nothing in this batch calls a model, reads the Canvas mirror, or exposes an MCP tool. Those
are well-understood and low-risk. The two genuinely unknown things are whether the layout is
readable from the back of the room and whether the schedule model survives contact with four
real day types, and both are answerable without any of that plumbing. Build the part that can
be wrong first.

## 3. Where this lands, and why

**Glass is a CanvasExpert surface, not a separate project.** This reverses an earlier
recommendation made in design conversation; the reversal is deliberate and the reasoning is
recorded here so it is not relitigated.

Glass has no independent existence. It needs the mirror, the pseudonym vault, the workspace,
the MCP server, and the WebUI shell. It is structurally identical to PowerGrader and
SpeedGrader: a page under `api/webui`, state in the workspace, tools on the existing MCP
server. The earlier argument for separation rested on Glass having a different runtime
profile that had to be independently bulletproof. That evaporated when Glass became a player
of a prebuilt file: it now has *no* runtime Canvas dependency at all, which makes it less
demanding than the surfaces already shipping, not more.

The decisive detail is §"Academic calendars" in `api/webui/README.md:171`. CE already models
a district academic calendar, already loads it from a workspace folder, and already ships no
district data in the repo. Glass's bell schedule is the same kind of object with the same
privacy posture. Extending that subsystem is right; building a parallel one next door is not.

## 4. Locked decisions

1. **Two layers, split by whether they need human review.** The **day plan** is composed once
   each morning, reviewed by the teacher, and durable for the day. **Live state** (timer
   running, which state is on screen) is transient, unreviewed, and lost on restart. Only the
   plan is persisted.
2. **The runtime is dumb.** Glass renders a plan and resolves a clock against a schedule. It
   contains no scoring, no derivation, no Canvas calls, no model calls. Every judgement that
   requires intelligence happens at compose time, outside this batch.
3. **The intelligence is the assistant, not a form.** There is no goal-authoring UI, no
   criteria builder, no assignment picker, no club manager. The assistant reads the week's
   module and writes the goal. Corrections happen by the teacher telling the assistant, not by
   a settings page. Do not build editors for fields the assistant fills.
4. **Staleness within a day is acceptable and must not be engineered against.** No
   period-boundary recomputation, no polling, no cache invalidation. A plan composed at 7:15
   is correct enough at 3:00. This is a product decision from the teacher, not an oversight.
5. **The repo ships no district data.** Bell schedules, the day-type calendar, and Bobcat Hour
   offerings follow the `Library/Calendars` precedent exactly: a blank template plus one
   fictional sample in the repo, real data only in the workspace. Berry Miller's actual bell
   times, calendar, club lists, and section-to-period mapping are workspace files and must
   never be committed.
6. **Glass reads; it does not write to Canvas.** It consumes the mirror (in a later batch) and
   writes only its own display state. It never touches the operation ledger. If a future slice
   wants a Canvas mutation, that is a RED stop and an architecture conversation.
7. **The schedule engine is CE-general, not Glass-specific.** It goes in `api/` as its own
   module with no import from Glass, because "which section is in the room right now" is
   useful to CE proper. Glass is its first consumer, not its owner.
8. **Identity is per-widget, not per-app.** The data layer must be able to return either the
   real name or the vault pseudonym, and each widget declares which it wants. Real names for
   seating and turn-taking, pseudonyms for anything score-adjacent or attributed. Wiring this
   is a later batch, but the plan schema must not foreclose it.
9. **Nothing on the glass is addressed to one student by name.** The display is public. The
   banner uses vault pseudonyms; no panel resolves a real student to a place, a score, or an
   obligation. This is a hard boundary, not a default.
10. **Touch changes live state only.** A finger can start a timer; it cannot edit the day
    plan, the schedule, or anything durable. If a widget appears to need a persisted setting,
    that is a compose-time field, not a touch affordance. This is what keeps the review gate
    meaningful: everything reachable by hand is transient and self-evidently visible.

## 5. Scope

### 5.1 Schedule engine (`api/schedule/`, new)

Pure functions, no I/O, fully unit-testable.

- **Day types** from the real bell schedule: `bobcat_hour` (Mon–Thur), `friday`,
  `homeroom_first`, `pep_rally`. Each is an ordered list of blocks with start and end times.
  Only `bobcat_hour` days contain a Bobcat Hour block; the other three do not, and the model
  must not assume every day has one.
- **Container blocks.** A block may hold sub-blocks. Two distinct uses, one mechanism:
  - *Sequential:* Friday, Homeroom First, and Pep Rally each split a period into A and B
    lunch. These are sub-blocks of the parent period, not peers, and they partition the
    parent's time.
  - *Concurrent:* **Bobcat Hour is the lunch hour** on Mon–Thur and does not split into A and
    B. Students eat, attend tutorials, and go to clubs, largely self-determined and spread
    across the building. Its sub-blocks are simultaneous offerings carrying a label and a
    location, and they do not partition the parent's time. Do not model an internal lunch
    split for Bobcat Hour; there isn't one.
- **Resolver:** given a datetime, return the day type, current block (or passing period, or
  before/after school, or not-a-school-day), elapsed and remaining minutes, percent complete,
  and the next block.
- **Next-occurrence lookup:** given a datetime and a block kind, return the next occurrence of
  that block that has not yet ended, with its date. Used by the Bobcat Hour panel (§5.4). Must
  skip day types that lack the block, and skip no-school dates from the academic calendar.
- **Calendar:** date to day type. Reuses the existing academic calendar for no-school dates
  rather than duplicating that logic.
- **Override:** a same-day "today is actually a Pep Rally day" that takes effect without
  editing the calendar, because real schedule changes arrive by email at 6:50am.

### 5.2 Day plan schema

The most important artifact in this batch. Three scopes, because content has three different
audiences and three different authors:

| Scope | Holds | Changes |
|---|---|---|
| School-wide | Events, Bobcat Hour offerings | Weekly-ish, same for every class |
| Teacher | What is happening in *this* room during Bobcat Hour | Daily |
| Per-section | Learning goal, success criteria, today's work, banner items | Daily, differs by period |

Glass selects the right per-section slice automatically from the resolver, so one plan file
covers the whole teaching day and the screen changes itself between classes.

Character budgets are part of the schema, not the renderer's problem: learning goal 90,
success criterion 40, assignment name 34, assignment detail 44, offering label 30, offering
location 12. Enforced at compose time; the renderer clamps and truncates rather than
reflowing.

### 5.3 Workspace data

- Bell schedule definitions and the day-type calendar, in the Library-side workspace folder
  alongside Calendars. Blank template plus one fictional sample shipped; real file authored
  locally.
- Section-to-period mapping, so Glass knows 4th period is a particular Canvas section.
- Day plans, on the private side of the workspace wall, since they will eventually carry
  pseudonymised missing-work content.

**Confirm the literal v2 workspace paths before writing.** This brief names intent, not
paths; the workspace layout owner is authority. If the intended split does not exist as
described, stop (§10).

### 5.4 The Bobcat Hour panel

Bobcat Hour is lunch plus tutorials plus clubs, so it is the one block whose *contents* are
worth displaying. It gets its own pane in the right rail.

**It always shows the next Bobcat Hour that has not ended yet, and derives its own heading
from that date.** In the morning that reads "Today during Bobcat Hour". After the block ends
it becomes "Tomorrow during Bobcat Hour" without anything being switched. On a Friday, or a
Homeroom First or Pep Rally day, there is no Bobcat Hour at all, so it resolves forward and
reads "Monday during Bobcat Hour".

Express this as one rule over the next-occurrence lookup, not as a morning mode and an
afternoon mode. Two hardcoded states would show an empty panel every Friday.

The panel lists offerings as label plus location, nothing more. It never says where a
particular student should go (locked decision 9).

### 5.5 The `/glass` page

Register in the page map (`api/webui/README.md:43`) following the existing surface pattern.

- **Top rail:** school, day-type pill, current period with time remaining, wall clock.
- **Full-width period progress line** directly under the rail.
- **Focus slot**, holding exactly one large thing: the learning goal with success criteria at
  rest, the timer when one is running, the countdown during a passing period.
- **Right rail, three panes:** today's work, then Bobcat Hour, then upcoming events. If
  vertical space is tight, **events shed items first**; the Bobcat Hour pane does not shrink.
- **Day strip:** all blocks of the day, current one lit.
- **Rotating banner:** cycles plan-supplied items on a fixed interval.

The reference mockup is **directional, not binding**. It is a useful starting point for type
scale, hierarchy, and colour, and it predates both the Bobcat Hour pane and the widget tray.
Where it conflicts with this brief, the brief wins. Matching it pixel for pixel is not a goal
and is not worth stopping over.

In this batch the banner renders **text supplied by the hand-written plan**. It is not yet
wired to the mirror or the vault. The slot exists so the layout is proven at real size.

### 5.6 Touch, and the widget contract

The projectors are touch-aware, so Glass is an interactive surface and not only a display.
This does not disturb the two-layer split: **touch mutates live state, never the plan**
(locked decision 10).

**Reach governs the layout.** A teacher standing at a projected image can comfortably reach
its lower portion and not its top. So:

- Everything large and readable lives high: rail, focus slot, panes.
- Everything touchable lives in the **bottom third**, in a tray along the foot of the screen.
- No interactive control goes above that band, however convenient the spot looks.

Targets are finger-sized on an imprecise surface: no hit target smaller than 9% of screen
width, generous spacing between them, no hover-dependent affordances, no small dismiss
buttons. Students will touch this thing, so nothing destructive happens on a single tap.

**Define the widget contract, then ship one widget.** The contract is the valuable artifact
here, for the same reason the schedule model is: what a widget declares (name, launcher
label, whether it claims the focus slot), how it is summoned and dismissed from the tray, how
it reads and writes live state, and what happens when the period changes underneath a running
widget. Get that right and every later widget is cheap.

The one widget in this batch is the **work timer**, because it is asked for and it is the one
that runs constantly:

- Duration presets as large tap targets, plus a plus-one-minute control.
- Pause, resume, reset.
- Claims the focus slot while running; the learning goal collapses to its one-line form.
- Under two minutes the digits and bars go red.
- Reset takes a confirm, because a stray hand must not wipe a running timer.

No second widget is built this batch, and the tray shows exactly one launcher.

## 6. Non-goals

Explicitly out, and not to be added opportunistically:

- MCP tools of any kind.
- The morning compose step, and any model call.
- Mirror or vault reads; real missing-work data.
- Event or club auto-import from mail. Offerings are hand-written this batch.
- Club sign-up, rosters, capacity, attendance, or any per-student Bobcat Hour assignment.
  Glass lists what is on offer; it does not place anyone.
- QR codes. Considered and declined: everything is in Canvas and students already go there.
- A goal editor, criteria builder, club manager, or any authoring form (locked decision 3).
- Period-boundary recomputation or freshness machinery (locked decision 4).
- **Any widget other than the timer.** The contract is the deliverable; the catalogue is not.
  Random student picker, group maker, dice, spinner, scoreboard, noise meter, and drawing or
  annotation are all out, however small they look once the tray exists.
- Touch controls that edit the plan, the schedule, or the offering list (locked decision 10).
- Phone or second-device control.
- Multi-school or multi-campus support.

## 7. Preflight

Verify before writing. Stop if an assumption is false.

1. **Touch must be proven before anything is built on it.** The projectors are touch-aware,
   but it is unknown whether a finger press reaches the browser as an ordinary pointer event
   or requires vendor drivers or a whiteboard overlay app. Before building the widget layer,
   put a trivial page with one large button on the real projector and confirm a press fires a
   click at the correct coordinates. If it does not, stop (§10): the widget scope is void and
   this batch reverts to display-only.
2. Confirm the v2 workspace paths for Library-side and private-side data (§5.3).
3. Confirm how the existing academic calendar exposes no-school dates, and consume it rather
   than reimplementing.
4. Confirm the WebUI surface registration pattern from an existing page.

Bobcat Hour's lunch question is **closed**: it is the lunch hour and has no A/B split (§5.1).
Do not reopen it.

## 8. Acceptance criteria

1. Resolver unit tests cover all four day types, and for each: first block, a mid-block
   moment, both sides of a passing period, both sides of lunch where defined, before school,
   after school, and a weekend or calendar no-school date.
2. The same-day override changes the resolved day type without the calendar file changing.
3. Next-occurrence returns the correct Bobcat Hour and date from each of: Wednesday morning
   (today), Wednesday after 1:13pm (tomorrow), **Friday any time (the following Monday)**, a
   Pep Rally day, and the day before a calendar no-school date.
4. The Bobcat Hour pane's heading is derived from the resolved date in every case above, not
   selected from a fixed set of strings.
5. `/glass` renders all states against a frozen clock and produces the correct period label,
   countdown, progress percentage, and day-strip highlight for each.
6. Every character budget in §5.2 clamps rather than reflows, verified at the real 16:10
   aspect with over-length strings. No element overflows its container in any state, including
   a Bobcat Hour pane at maximum offering count.
7. **Every interactive element sits inside the bottom third of the screen and is at least 9%
   of screen width**, verified by measuring the rendered geometry, not by inspection.
8. The timer widget supports presets, plus-one-minute, pause, resume, and a reset that takes
   a confirm. It claims the focus slot while running, collapses the goal to one line, and
   turns red under two minutes.
9. A running widget survives a period change without crashing or wedging, and the rail and
   day strip update underneath it.
10. `git grep` finds no Berry Miller bell times, calendar dates, club or tutorial names,
    section names, or student data anywhere in the repo. Only the template and the fictional
    sample.
11. `docs/reference/glass-module-map.md` exists and carries the subsystem's durable state:
    invariants, this batch, the widget contract, open decisions, and verification discipline.

**Manual, teacher-run, not automatable:** one full Bobcat Hour day on the real projector in
the real room. The screen shows the correct period and countdown all day with no
intervention, the goal and work are readable from the back row, the Bobcat Hour pane flips
from today to tomorrow on its own when the block ends, and the timer can be started, paused,
and reset by hand without the teacher reaching above shoulder height. Report this separately
from the gate; it is the only criterion that can fail after the code is green.

## 9. Verification gate

The full `api` suite, plus the new `api/tests/schedule/` module. No new failures, no skips
introduced. Report counts, not adjectives.

## 10. Stop conditions

Stop and return YELLOW or RED rather than guessing when:

- A named workspace path or calendar seam does not exist as §7 describes.
- The academic calendar cannot answer no-school dates without being modified. Modifying a
  shipping subsystem is out of scope for this batch.
- Rendering the agreed layout at real size requires changing the design rather than the
  numbers. Report what does not fit; do not redesign.
- Touch does not reach the browser as pointer events (§7.1). The widget scope is void; report
  what the projector actually delivers and revert to display-only rather than shimming.
- A widget wants to persist something, or a second widget starts to look necessary to prove
  the contract. One widget is the scope; report the pressure instead of absorbing it.
- Any part of this appears to want a Canvas write, the operation ledger, or a model call.
- A Bobcat Hour feature would require knowing which student goes where.
- Real district or student data would have to enter the repo to make a test pass.

## 11. Execution result

_Not started._
