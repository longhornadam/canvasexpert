# Brief — Canonical Calendar foundation and first consumer cutover

**Status:** ready for execution · **Author:** Codex senior, 2026-08-01
· **Executor:** one Terra-class or external architecture-capable executor
· **Lane:** one cross-cutting vertical batch · **Branch:** `dev`

## Teacher-visible outcome

Canvas Expert gains a primary **Calendar** page where the teacher can see whether the current
school year is healthy, correct one date or a flexible date range, maintain the Teacher
Schedule, and inspect the Bell Schedules that SmartDeck and Panels use. An MCP-connected
assistant can preview and apply the same structured change after the teacher pastes a public
schedule announcement.

After this batch, every current calendar consumer reads one `School Calendar.json`. A broken or
expired calendar stops dependent behavior with a concise repair link instead of producing a
confident wrong answer. Panels follows the live clock by default, supports a stable fixed-block
override, respects Current courses, and keeps due-today work visible all day.

## Required context — read only this

1. `AGENTS.md`, including **Repository boundary**, **Web UI / teacher surfaces**, **Execution
   model**, **Risk and verification**, and **Handoff and document hygiene**.
2. `docs/reference/project-state.md` — all sections. This is a clean replacement with no
   migration or compatibility layer.
3. `docs/contracts/canonical-school-calendar-contract.md` — all sections; this brief implements
   them for the consumers explicitly named below.
4. `docs/reference/settings-module-map.md` — **Ownership**, **Browser Routing**, **Backend
   Routing**, and **Guardrails**.
5. `docs/reference/smartdeck-module-map.md` — **Data flow**, **Current ownership**, **Storage
   layout**, **MCP tools**, and **Feed system**.
6. `docs/reference/panels-route-card.md` — **Two contracts that are easy to break by accident**,
   **Panel catalog**, **whats-due**, **Following the schedule**, **Correcting today**, **The
   console**, and **Verification gate**.
7. `docs/contracts/course-catalog-contract.md` — **Location and identity** and the HTTP
   Current-course boundary in **Acquisition and writes**.
8. `docs/reference/webui-presentation-system.md` — **Template API**, **Who these pages are for**,
   **Page conventions**, **CSS ownership**, and **Change propagation**.
9. `api/webui/README.md` — **Rendered verification**, **Page map**, **Settings page**, and
   **Settings module routing** only.
10. `docs/mcp-server.md` — **Tools** and **Token-lean results** only.

Do not read the historical SmartDeck design, archived handoffs, or a whole architecture vision.
The contract above supersedes their day-calendar decisions for this batch.

## Current repository truth and preflight

At authoring, `HEAD == origin/dev == a9c602003611e88b513f0c669ab5fcb9a909d91f` and
`origin/main == c75b6f5a088b0ba3ccf1b9398c39fb4fbdd1aa3a`. The only pre-existing worktree item is
the user-owned untracked `api/webui/static/scratch/`; do not add, alter, or delete it.
The planning-session baseline at that exact commit was `py -m pytest api/tests -q` →
`1792 passed in 64.50s`.

Before writing:

1. Fetch and compare `dev` with both remotes. A newer clean `dev` is acceptable after inspecting
   the intervening diff for these seams; a divergent branch or overlapping calendar work is RED.
2. Run `py -m pytest api/tests -q` once and record the exact baseline. This is a genuinely
   cross-cutting batch, so a failing baseline is RED unless the failure is clearly environment-
   only and independently reproducible.
3. Run the inventory commands in **Consumer closure**. Any additional runtime calendar owner is
   RED until the senior adds it to scope; do not leave a parallel source behind.

## Locked decisions

1. Implement the contract's canonical storage, date model, mutation semantics, consumer rule,
   and first Calendar surface: one active `Library/Calendars/School Calendar.json`, complete
   date coverage, revisioned atomic writes, explicit day kinds, and no legacy read/write path.
2. Reuse Bell Schedule CSVs and `Library/SmartDecks/Teacher Schedule.json` as referenced
   definitions. They are edited/reached from Calendar; they are not copied into the date map.
3. Absorb public school events into the canonical document and remove live
   `school-events.json` ownership. Academic CSVs remain import inputs only.
4. `/calendar` is a `workspace/left-main` page and a primary-nav peer. Put **Calendar** after
   **Panels** and before **Settings**. Preserve Panels in primary navigation and verify header
   behavior rather than changing another item's rank to make room.
5. Date/range rules materialize exact dates. There is no runtime weekday/override precedence.
6. UI and MCP share the same create, preview, apply, validation, and atomic-write functions.
   Apply requires the preview's `expected_revision`.
7. Missing/invalid/out-of-coverage state blocks any consumer that needs calendar facts. No
   weekend-only fallback and no guessed schedule.
8. Move the existing Teacher Schedule editor and academic-calendar import out of Settings.
   Calendar shows the Bell Schedule definitions and the existing safe “Open Calendars folder”
   action. Full in-browser Bell Schedule row editing and full public-event CRUD are deferred;
   do not invent either editor in this batch.
9. Panels keeps live-clock preview and gains stable `?block=<teacher-block-name>` override.
   Delete generated/raw `?course=` pinning; there is no pre-launch URL compatibility burden.
10. What's due uses Current courses only, includes earlier-due-today work until local midnight,
    covers through local `today + 7`, and orders future items before earlier-today items.
11. The projected Panel shows calendar/schedule repair states. The builder links to Calendar.
12. Clipboard success is truthful; use a selected temporary control for the fallback and report
    failure when neither mechanism copies.
13. Remove feature-local `skip_weekends`, `holidays`, and “additional no-count days” controls
    and persisted settings. Calendar day kinds are the sole input to instructional-day math;
    student accommodations remain separate.

## Implementation boundary and insertion points

### A. Canonical service and clean storage cutover

Create `api/webui/school_calendar.py` as the single pure/application owner for the closed
schema, parsing, whole-document validation, range projection, readiness, create, preview,
apply, and atomic persistence. Keep filesystem discovery at the existing workspace boundary;
do not introduce a repository, adapter registry, database, or cache.

Change the schedule seam so `api/webui/deps.py:resolve_schedule_for()` obtains the date's
`schedule_id` only from this service, then uses the existing Bell Schedule and Teacher Schedule
parsers. Retain the useful pure Bell/Teacher validation in `deck_schedule.py`; delete its Day
Calendar parser and every loader/override path that is no longer live.

Delete live ownership from:

- `api/webui/config/calendars.py` and its `config/__init__.py` exports;
- `deps.load_day_calendar`, `DAY_OVERRIDE_FILENAME`, and Day Calendar discovery;
- `schedule_setup.save_day_calendar`, day-override functions, backup/overlap helpers, and their
  old API routes;
- `api/webui/school_events.py` and the seeded `school-events.json`;
- seeded `Day Calendar*.csv` files.

Keep academic CSV parsing only as an import helper. Import/create must produce a complete,
validated canonical document, not save a second projection.

### B. Calendar page and APIs

Replace the old calendar route surface in `api/webui/routes/calendar.py` with:

- `GET /calendar` — left-main working page;
- `GET /api/calendar` — compact canonical document/readiness projection, Bell definitions,
  Teacher Schedule blocks, Current-course choices, and upcoming date rows;
- `POST /api/calendar/create` — complete school-year creation/replacement;
- `POST /api/calendar/change/preview` and `/apply` — the revision-checked date mutation;
- narrowly named import/grading-period/event endpoints only where the moved existing academic
  import requires them.

The date mutation accepts either explicit dates or an inclusive range with an optional weekday
subset, never both. It accepts the three day kinds and validates schedule IDs. The initial
create accepts coverage plus weekday defaults, materializes every date, and can apply a parsed
academic CSV's no-school days and grading periods before the first write.

Build `templates/calendar.html`, a page-owned stylesheet, and bounded browser code. The first
screenful is readiness, today/upcoming dates, and the preview/apply control. Move the existing
Teacher Schedule editor and academic import behavior here; do not duplicate it. Show Bell
Schedule definitions with names, period rows, validation state, and Open Folder. Use exact
section anchors so repair links can target date setup, Bell Schedules, or Teacher Schedule.

Remove the two editors and their browser owners from Settings. Replace only genuinely relevant
Settings copy with a terse link to `/calendar`; Calendar does not become a generic Settings
subpage. Update all existing feature links that currently target `/settings#cal` or
`/settings#class-schedule-card`.

Add the Calendar router/page to `server.py`, the header, presentation registry, route contract,
and WebUI page map. Preserve the app's setup allowlist behavior deliberately: Calendar requires
a configured workspace and is not a first-run bypass.

### C. Consumer closure and gates

Replace every direct academic/day-calendar read in these owners with the canonical service:

- `api/smartdeck_feeds.py`;
- `api/work_registry/providers/late_work.py`;
- `api/operation_ledger/adapters/sweep.py`;
- `api/webui/gradebook_service.py`;
- `api/webui/routes/gradebook_extensions.py`;
- `api/webui/routes/powergrader_late.py`;
- `api/webui/routes/routines_builtin.py`;
- `api/webui/routes/routines_custom.py`;
- `api/webui/routes/pages.py`, including Settings and Gradebook calendar projections;
- `api/webui/routes/gradebook_sweep.py`, `api/webui/config/gradebook.py`, and the Gradebook
  template/browser inputs that currently collect local weekend/holiday overrides;
- `api/webui/schooldays.py` and the public routine/operation call shapes that currently accept
  `skip_weekends` or caller-supplied holiday lists;
- Welcome's optional multi-calendar activation step in `templates/welcome.html` and
  `static/welcome.js`;
- SmartDeck routes/display and Panels through the schedule resolver;
- MCP reads/writes.

Before and after implementation, run:

```powershell
rg -n 'get_combined_calendar_for_range|config\.get_calendars|load_day_calendar|Day Calendar|Day Overrides|school-events\.json|save_day_calendar|skip_weekends|additional no-count|settings\.get\("holidays"|params\.get\("holidays"' api docs --glob '!docs/handoffs/canonical-calendar-foundation.md'
```

Afterward, runtime/source references must be gone. Remaining references are allowed only in
tests that assert rejection/removal or in this contract's explicit historical replacement
statement. Do not mechanically change Canvas's own calendar terminology.

Each operation that currently computes holidays/instructional days must receive an explicit
configured/range-valid result. If invalid, its existing plan/readiness endpoint must refuse the
operation with a stable, student-free reason and `/calendar` repair target. Do not let a lower
helper turn the gate into an exception or empty holiday set.

Delete the Gradebook/Late Work `skip_weekends` and additional-no-count-day inputs and the
corresponding persisted sweep-setting keys. The operation ledger and built-in/custom routine
interfaces no longer accept caller-supplied school-calendar exceptions. Refactor the pure
school-day helper so its callers provide a validated canonical day projection (or an equivalent
set derived only from that projection), not a preference plus parallel holiday list.

Custom routines' `combined_calendar` input may change shape in this clean break so it carries
readiness plus `no_count_dates`, grading periods, and events. Update its authoring contract and
tests in the same batch. Its calendar-aware school-day helper no longer asks routine authors to
pass weekend or holiday policy.

Welcome must stop activating any number of independent calendars. Remove that optional
multi-calendar editor/step. Once workspace/account setup is complete, its completion state may
link to `/calendar`; actual calendar creation remains in the one Calendar surface.

### D. MCP and AI authoring

Replace `save_day_calendar` with token-lean tools named:

- `get_school_calendar(date_from, date_to)`;
- `create_school_calendar(...)`;
- `preview_school_calendar_change(...)`;
- `apply_school_calendar_change(..., expected_revision)`.

Wire server wrappers, tool schema, registrations, docs, and `Author a Class Schedule.txt` in
one schema-version bump. Existing `get_bell_schedule`, `get_day_schedule`,
`get_teacher_schedule`, and `save_teacher_schedule` use the new authority/shared validators.
Tool results return revision, readiness, counts, dates, labels, and problems only — no absolute
paths or full document unless the bounded range was requested.

The authoring contract should tell an assistant to translate pasted public schedule facts into
a preview, summarize affected dates and conflicts, and apply only after the teacher accepts that
summary. Do not build email ingestion, an LLM call, or a free-text parser inside Canvas Expert.

### E. Panels correction while its resolver changes

In `routes/panels.py`, the builder template, and the panel template:

- populate selectable blocks/courses through the Teacher Schedule and
  `config.active_courses()` only;
- replace raw course query generation/resolution with the stable block override;
- show the canonical Calendar failure states on the projected surface, while fixed block
  bypasses only date/clock resolution;
- implement the local-calendar-day due window and future-first ordering in the contract;
- preserve catalog staleness as a separate visible fact;
- make copy feedback depend on actual Clipboard API/fallback success.

Do not add a manual preview day, time, or period selector. Do not add another Panel kind, retune
themes, or fix the open long-title responsive defect in this batch.

### F. Durable documentation at handback

Update, do not append history to:

- `docs/reference/settings-module-map.md` — remove Calendar ownership and stale guardrails;
- `docs/reference/smartdeck-module-map.md` — canonical resolver/storage/MCP facts;
- `docs/reference/panels-route-card.md` — block override, Calendar states, due semantics, and
  removal of the Panels “Correcting today” owner;
- `api/webui/README.md` and `docs/mcp-server.md`;
- the applicable route/tool contract docs and AI authoring file.

The canonical contract remains authority. Do not duplicate its schema into each route card.

## Acceptance criteria

1. There is exactly one active school-date document and no runtime legacy calendar store,
   day-calendar/override reader, or separate school-event file.
2. A complete year can be created from UI and MCP inputs; every covered date validates and the
   resulting file is atomically written with revision 1.
3. Previewing and applying a one-off, a sparse weekday range, and a two-week Monday-Friday
   “Friday Schedule” change produces the exact dates expected. A stale revision is refused and
   a no-op does not increment revision.
4. An instructional day cannot name an unknown Bell Schedule. Missing, malformed, expired, and
   out-of-range calendars produce distinct stable states.
5. Calendar is in primary navigation, the header remains usable at supported widths, and the
   Calendar page puts readiness/today/range editing first. Settings contains no duplicate
   Class Schedule or Academic Calendar editor.
6. SmartDeck and Panels resolve the same date to the same Bell Schedule and class blocks. A
   one-off/range edit is reflected by both without another file or override.
7. Every listed instructional-day consumer blocks with a Calendar repair target when its
   requested dates are not validly covered; none silently assumes weekends-only.
8. MCP read/preview/apply and the UI exercise the same service. The old `save_day_calendar`
   registration/schema/docs are absent, and token-lean results expose no private path.
9. A projected default Panel visibly reports Calendar trouble. A generated `?block=` URL shows
   that Current block even when the calendar is broken. A block mapped to a Previous course
   shows the exact Current-course repair state and never reads its catalog.
10. At one minute after an assignment's due time, that due-today assignment remains present.
    Future items precede earlier-today items, and an item due on local `today + 7` is included
    while `today + 8` is excluded.
11. Copy reports “Copied” only after demonstrated success; its fallback selects the address.
12. Gradebook, operation-ledger, routine, and saved sweep settings contain no independent
    weekend/holiday override. A changed exceptional date affects each through Calendar alone.
13. Welcome no longer creates or activates parallel calendars and its completion path reaches
    the canonical Calendar page.
14. The focused tests, full API gate, browser routes, consumer-closure search, and
    `git diff --check` all pass with no undeclared deviation.

## Explicit non-goals

- Automatic email access, inbox monitoring, natural-language parsing inside CE, or an external
  AI call. The connected host assistant interprets pasted text.
- Canvas Calendar event synchronization or any Canvas write.
- In-browser Bell Schedule row authoring or full public-event CRUD. Calendar shows these
  artifacts/readiness and keeps safe existing file access; a later batch may add editors.
- Multi-school, multiple teacher profiles, timezone configuration, or recurrence storage for
  schedule changes.
- New Panel kinds, SmartDeck feed authoring/display integration, theme work, or the known Panel
  long-title sizing repair.
- Migration, compatibility aliases, backup files, dual reads, or preservation of `?course=`.

## Named verification gate

This batch is deliberately cross-cutting, so the slice gate is:

```powershell
py -m pytest api/tests -q
```

Add focused coverage at minimum for the schema/service, Calendar routes, Calendar browser
operations, schedule resolution, each gated consumer, MCP tools/schema, Panels, route contract,
and presentation contract. Pure browser behavior should have a direct JS test where the current
harness permits it; source-text assertions do not prove clipboard or layout behavior.

Then run a rendered browser matrix against the local app:

- `/calendar` at desktop, 760px transition, and narrow mobile width: create/preview/apply,
  readiness states, moved Teacher Schedule editor, Bell list, and academic import;
- `/settings`: no duplicate editors and a correct Calendar link;
- `/panels` and a projected What's due route: live-clock state, broken-calendar state, fixed
  block, Previous-course gate, and real copy success/failure;
- `/smartdeck` plus one display data route after changing a date;
- one representative Gradebook/Extensions or Late Work surface showing its Calendar gate;
- header/navigation on every affected route, required globals/state present, zero new console
  errors.

For any changed Panel layout, also run the route card's full responsive shape sweep. Record exact
commands, counts, and browser observations. Finish with the consumer-closure `rg`,
`git diff --check`, and `git status --short`.

## Stop conditions

Return RED without widening scope if:

- current code reveals another live calendar authority/consumer not named in Consumer closure;
- a clean cutover would require preserving real user state (repository state says none exists);
- the canonical schema cannot represent a discovered current behavior without a product choice;
- a consumer cannot expose a Calendar gate without changing a public operation contract not
  named here;
- Bell Schedule editing, event CRUD, email/AI ingestion, Canvas access, student data, or a new
  persistence/registry layer becomes necessary;
- the header cannot hold the locked primary items at supported widths without a navigation
  design decision;
- baseline or implementation exposes an unrelated regression.

## Execution result

**Traffic light:** not started

**Commit:** none

**Changed files:** none

**Evidence:** none

**Deviations:** none

**Unresolved decisions:** none at handoff

The executor writes the compact result here and in chat. GREEN closure accepts the batch and
deletes this brief in the same commit; Git is the execution record.
