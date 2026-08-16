# Glass instrument-panel presentation

**Status:** READY FOR EXECUTION

**Opened:** 2026-08-15

**Execution model:** One implementation executor. The senior accepts against this brief and
returns ordinary corrections to the same executor/context.

## 1. Objective

Replace Glass's current card-dashboard presentation with the approved classroom instrument
panel: one clinical header line, three unequal columns, cards that alternate between compact and
expanded states, and a footer tool dock. Instruction is the fixed visual center and the largest
column. The page should read as an elegant engineering tool used by professionals, not SaaS.

This is one vertical UI batch for both Glass modes. Preserve the existing resolver and disk-only
projections; make the current information easier to see and the existing Random Name capability
part of a coherent classroom tool dock.

## 2. Teacher-visible outcome

At a class time, a 16:9 projector shows:

```text
DATE | TIME | PERIOD/STATE | COURSE | ENDS/STARTS AT | SIMULATION WHEN ACTIVE

┌─────────────────┬────────────────────────────────┬───────────────────┐
│ class operations│ instruction                    │ whole school      │
│ compact/max cards│ dominant objective            │ compact/max cards │
└─────────────────┴────────────────────────────────┴───────────────────┘

[ RANDOM NAME ] [ TIMER ] [ QUICK NOTE ] [ BLANK ]              STATUS
```

There are no column headings in the rendered page. The labels in the wireframe describe
ownership only.

## 3. Preflight — run before writing

1. Confirm the worktree is on `dev`; preserve unrelated changes.
2. Confirm both routes in `api/webui/routes/glass.py` call
   `glass_board.get_display_context`, and that class mode returns `context`, `board`, and
   `classroom` together.
3. Confirm `api/webui/static/pages/glass.js` still owns one page lifecycle and uses the
   server-provided `context.at` rather than the browser clock.
4. Confirm the existing projections expose only the data named in section 5. In particular,
   there is no agenda/resource payload and no explicit major-grade classification.
5. Confirm no Glass module imports a Canvas client.

If any assumption is false, return RED. Do not repair or expand a backend contract by inference.

## 4. Locked presentation decisions

### 4.1 Frame and hierarchy

- Full-screen Glass remains outside normal app chrome.
- Header is exactly one visual line at the projector target. It contains date, server-derived
  time, current period/state, course or schedule, and the current boundary (`ENDS`, `STARTS`, or
  `RESUMES`). `SIM` is an inline state when `context.simulated` is true; there is no badge row.
- Class mode uses `25% / 48% / 27%` as the starting column proportions: class operations on the
  left, instruction in the middle, whole-school information on the right. Adjust by at most two
  percentage points to prevent real overflow; the middle must remain visibly dominant.
- No column headings, navigation, explanatory copy, onboarding, shadows, pills, gradients, or
  decorative dashboard metrics.
- Use flat opaque surfaces, hairline rules, restrained corners, tabular/monospaced time values,
  and one signal accent. Existing Canvas Expert presentation tokens remain the color/type source.
- At 1280×720 there are no page, column, or card scrollbars. Summarize overflow with `+ N`, caps,
  and ellipsis. Narrow administrative/browser views may stack and page-scroll.

### 4.2 Text and icon law

- Be brutally clinical. Content is preferred over category labels.
- If an icon communicates the category, do not repeat it with a title. The objective uses a target
  icon plus objective text, never “Learning objective.” Calendar content uses a calendar icon,
  never a “Calendar,” “Today,” or “Coming up” heading.
- If text is required to identify a card, omit the decorative icon. “Missing work” earns a title
  because the list is otherwise ambiguous; it has no icon.
- Assignment names, event names, student display names, repair states, and due/boundary times are
  data, not UI chrome, and may use their natural length within truncation rules.
- Empty/error copy is terse and honest: e.g. `NO OBJECTIVE`, `NOTHING DUE`, `SYNC REQUIRED`.
  Independent region degradation remains visible; never blank the whole page for one region.

### 4.3 Motion

- Each eligible column has exactly one expanded card; siblings are compact summary rows. The
  instruction objective remains expanded when it is the only real instructional source.
- Eligibility is computed from the current rendered payload, not from a fixed card list:
  - a ready region with zero meaningful items is omitted entirely;
  - content that is fully communicated by its compact row remains compact and never enters the
    rotation;
  - a card is expansion/rotation eligible only when it has meaningful detail that is hidden in
    compact form;
  - unavailable, stale, or repair-required states are not “empty” and remain visible as concise,
    static repair rows.
- A column with fewer than two expansion-eligible cards does not cycle. Its sole eligible card, if
  any, remains expanded. A page with no rotating column creates no presentation interval.
- Recompute eligibility after every data render and mode/course change. Removing a card must also
  remove it from the rotation sequence immediately; never rotate into a blank or stale DOM slot.
- One page-level motion controller advances one eligible column at a time on an approximately
  eight-second cadence. Do not create an interval per card or per list.
- Expansion/collapse uses restrained 350–550 ms geometry/content transitions. No bounce, pulse,
  parallax, or decorative entrance animation.
- A slow horizontal school-information ticker may run only when its content overflows. Do not
  scroll objective, student, due, or repair text.
- Hover/focus pauses the affected motion. Opening a tool pauses all presentation motion. A manual
  card selection remains in place for at least 20 seconds before automatic rotation resumes.
- `prefers-reduced-motion: reduce` disables automatic card rotation, ticker motion, and animated
  transitions while leaving every item readable and every manual control usable.
- Page visibility changes and repeated `/glass/data` renders must not accumulate intervals,
  listeners, or stale transitions.

## 5. Fixed data-to-region mapping

Use the current payload only. Do not add a registry or generic card framework.

### Class mode

| Location | Source | Rendering rule |
|---|---|---|
| Header | `context` + `classroom.period` | One line; boundary derives from the existing server clock contract. |
| Left | `classroom.missing` | Named `MISSING WORK`; expanded list is capped and compact state shows counts. |
| Left | `classroom.due.assignments` | First item is next due; remaining items are upcoming. Show assignment names and times directly, without redundant card titles. |
| Left | `classroom.celebrations` | Conditional content card only when non-empty; never place student celebrations in the whole-school column. |
| Middle | `classroom.objective` | Target icon plus objective text. It owns the largest uninterrupted area. |
| Right | `board.today_events`, `forward_events`, `academic_dates` | One calendar family; combine and cap in the browser without changing the projection. |
| Right | `board.bobcat`, `sports_results`, `grading_period` | Conditional school cards using direct content and compact summaries. |
| Footer | `classroom.random_name.names` | Enables Random Name only in class mode when names exist. |

The approved visual mockup used illustrative lesson steps, resources, and “major grade” examples.
Those are not current product data. Do not ship static examples, infer an agenda, classify a major
grade from points/group names, or add an authoring convention. Until an explicit source exists,
the center contains the objective and only real future instructional sources may add siblings.

Card presence is day-specific. `no_missing_work`, `nothing_due`, `nothing_to_celebrate`, an empty
event window, no sports results, an inactive Bobcat Hour region, or no active grading period do not
reserve blank cards or motion slots. If one upcoming assignment or school item fits completely in
its compact row, show that row without expanding it merely to fill space. The layout absorbs the
freed space; it does not manufacture placeholders.

### Board mode

- Keep the same single-line header and footer language.
- Do not render empty class/instruction columns. Distribute the existing public board regions
  across all three columns using the same compact/expanded behavior.
- Random Name is absent when no class roster is in scope. Timer, Quick Note, and Blank remain.
- Board mode remains student-free. No browser state from a prior class render may leave a student
  name visible after mode changes.

## 6. Footer tools

Tools are fixed code-owned controls, not an authoring or plugin surface. Opening one tool closes
the previous one; `Escape` closes the active tool or overlay.

1. **Random Name** — reuse `classroom.random_name.names`; repeat-allowed selection remains the
   current contract. Show the selected shortened classroom name in a focused overlay. Clear it on
   course/mode change.
2. **Timer** — local-only 5/10/15-minute presets with start, pause, and reset. Show a running value
   in the footer and a large value in its overlay. A `/glass/data` refresh must not reset it; a full
   page reload may. No sound or notification work.
3. **Quick Note** — ephemeral browser text with `SHOW`/`HIDE`; shown text uses a large classroom
   overlay. It is not persisted, synced, or sent to the server.
4. **Blank** — neutral full-display cover with a visible return control. Timer state may continue
   underneath. Do not use browser fullscreen APIs.

Tool buttons use concise visible text and no duplicate icons.

## 7. Acceptance criteria

1. Class mode renders the single-line header, left/center/right order, dominant center width, and
   footer dock exactly as sections 4–6 define.
2. Board mode uses the same instrument language, fills the three-column content area with public
   school information, and exposes no class/student residue.
3. No rendered column heading exists. Objective and calendar cards obey the icon/title law;
   Missing Work uses text and no icon.
4. Every visible content item comes from the current payload. There are no example lesson steps,
   static resources, major-grade inference, or district-specific classification strings.
5. Compact cards retain a useful content summary. Exactly one card per eligible column is expanded;
   manual and automatic changes never cause layout overflow.
6. Empty-ready regions render no card. Compact-complete regions never expand or enter rotation.
   Columns with zero or one expansion-eligible card create no local cycle, and the page creates no
   presentation interval when no column can rotate. Repair/stale states remain concise and visible.
7. Automatic emphasis advances one eligible column at a time. Eligibility updates after each data
   render and mode/course change. Reduced-motion mode is static. Ticker content remains readable
   when motion is disabled.
8. Random Name, Timer, Quick Note, and Blank satisfy section 6 with keyboard and pointer input.
   Data refreshes do not duplicate handlers or reset the timer/note.
9. `?at=` controls header time, due labels, objective date selection, events, celebrations, and
   boundary countdown together. No Glass JavaScript reads `Date.now()` or constructs a real
   browser “now.”
10. A stale/unavailable private region degrades independently and preserves its `as_of`/repair
   meaning in concise form. No new Canvas client import or live call exists.
11. At 1280×720, both a class render and board render have zero horizontal/vertical page overflow,
    no card scrollbars, a single-line header, working footer tools, and zero browser console errors.
12. The Glass section of `api/webui/README.md` records the settled instrument-panel hierarchy,
    fixed tool set, content-driven card eligibility, motion/reduced-motion rule, and no-inference
    data rule so these decisions survive retirement of this brief.

## 8. Scope and insertion points

Expected changes:

- `api/webui/templates/glass.html` — fixed semantic shell, class/board card ownership, tool overlays.
- `api/webui/static/pages/glass.css` — instrument hierarchy, max/min geometry, projector and narrow
  behavior, reduced motion.
- `api/webui/static/pages/glass.js` — rendering, one motion controller, tool state, refresh/mode
  cleanup, server-clock preservation.
- `api/tests/webui/routes/test_glass.py` — one route/template example and the existing browser-clock
  law; do not prove runtime behavior with source-text assertions.
- `api/webui/README.md` — durable Glass presentation contract.
- This brief's `Execution result`.

Read-only references unless preflight proves a contradiction:

- `docs/reference/project-state.md` — whole short document.
- `api/webui/README.md` — `Glass module routing` only before implementation.
- `api/webui/routes/glass.py` — both route functions.
- `api/webui/glass.py` — `get_current_context`, `normalize_at`.
- `api/webui/glass_board.py` — `get_display_context` and returned board keys.
- `api/webui/glass_class.py` — `get_class_context`, `_due_region`, `_period_region`, and `_public_*`.
- `api/tests/webui/test_glass.py`, `test_glass_class.py`, `test_glass_board.py`, and
  `routes/test_glass.py` — existing Glass law/contract/example coverage.

Do not change backend projections, route URLs, calendar contracts, mirror services, Learning
Objectives, audience/privacy helpers, or MCP tools in this slice.

## 9. Explicit non-goals

- No card registry, widget/plugin model, authoring, drag/drop, saved layout, theme editor, or user
  personalization.
- No placeholder, empty, or artificially expanded card merely to balance a column or keep motion
  active.
- No new persistence, local storage, cookies, server settings, database tables, or migration code.
- No agenda/resource source, Canvas Page convention, major-grade classifier, assignment-group
  configuration, or additional mirror field.
- No live Canvas call, refresh control, Canvas write, external service, audio, notification, or
  browser fullscreen integration.
- No change to resolver states, class/board mode selection, privacy projection, row caps at the
  backend, or the Random Name repeat policy.

## 10. Risk, verification, and named gate

**Risk:** Medium. This is a browser presentation/lifecycle rewrite over an existing
classroom-only student-name surface; it does not create a new data or external boundary.

Named focused gate:

```powershell
py -m pytest api/tests/webui/test_glass.py api/tests/webui/test_glass_class.py api/tests/webui/test_glass_board.py api/tests/webui/routes/test_glass.py api/tests/test_route_contract.py -p no:randomly -q
```

Also run `git diff --check`.

Rendered acceptance per `api/webui/README.md`:

- Class: `/glass?at=2026-09-02T11:30:00-05:00`
- Board: `/glass?at=2026-09-02T12:15:00-05:00`
- Primary viewport: 1280×720. Also inspect 1024×768 and a narrow 360 px browser view.
- Exercise automatic/manual card emphasis, every footer tool, mode transition, a data refresh while
  the timer runs, and reduced-motion emulation.
- Exercise three content-shape probes: all optional regions empty; exactly one compact-complete
  item in a column; and two cards with hidden detail. Record card presence and whether the single
  page-level rotation interval exists/advances only in the third case.
- Record status code, overflow measurements, required page globals, tool outcomes, and console
  errors. Screenshots are verification evidence, not repository artifacts.

Do not run the full API suite unless focused failures reveal unexpected coupling.

## 11. Stop conditions

Return RED before implementation if the class payload is absent from the route, a requested region
requires a new backend/public contract, an agenda or major-grade rule would need to be guessed, or
the current clock/privacy boundary differs from this brief. Return YELLOW if the local app cannot
render either named simulated state or reduced-motion/browser verification is unavailable.

## 12. Execution result

**Traffic light: YELLOW** — the implementation and focused gate are complete, but the named live
class route could not be rendered in this workspace because no `Teacher Schedule.json` is
configured, so the simulated timestamps resolve to board mode. Reduced-motion emulation and the
three payload-shape probes were not available in the connected browser surface.

**Commit:** none (working tree preserved; the pre-existing deletion of
`docs/handoffs/glass-classroom-display-initiative.md` was not touched).

**Changed files:**

- `api/webui/templates/glass.html` — shared three-column shell, semantic card regions, footer
  tools, Timer/Quick Note/Blank overlays, and Random Name overlay.
- `api/webui/static/pages/glass.css` — instrument hierarchy, 25/48/27 columns, compact/expanded
  geometry, responsive stacking, projector overflow rules, and reduced-motion CSS.
- `api/webui/static/pages/glass.js` — one page controller, payload-driven class/board cards,
  eligibility/expansion reconciliation, one rotation interval, server-clock refresh, tool state,
  manual pause, and mode/course cleanup.
- `api/tests/webui/routes/test_glass.py` — route/template contract checks for the fixed shell/tools.
- `api/webui/README.md` — durable Glass presentation contract.

**Verification:**

- `py -m pytest api/tests/webui/test_glass.py api/tests/webui/test_glass_class.py api/tests/webui/test_glass_board.py api/tests/webui/routes/test_glass.py api/tests/test_route_contract.py -p no:randomly -q` — **21 passed**.
- `node --check api/webui/static/pages/glass.js` — passed.
- `git diff --check` — passed.
- In-app browser board render at 1280×720 (`/glass?at=2026-09-02T12:15:00-05:00`): status 200, zero page overflow, zero rendered headings, zero console errors; compact grading card retained its summary.
- In-app browser footer checks: Timer preset/start, Quick Note SHOW/HIDE, and Blank RETURN all passed; Random Name was correctly disabled in board mode.
- In-app browser responsive checks at 1024×768 and 360×720: zero horizontal/vertical overflow and visible footer controls; narrow screenshot captured.
- Preflight confirmed both routes call `get_display_context`, class payload shape is `context`/`board`/`classroom`, client clock derives from `context.at`, and no Glass module imports a Canvas client.

**Deviations / unresolved decisions:** live class-mode browser evidence, reduced-motion emulation,
refresh-preservation exercise, mode transition, and the three content-shape probes remain for the
next verification pass after a local Teacher Schedule is available or an approved browser fixture
surface exists. No backend projection or public contract was expanded.
