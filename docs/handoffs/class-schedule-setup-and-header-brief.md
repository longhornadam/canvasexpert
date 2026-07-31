# Brief: header declutter, SmartDeck rail, and a real class-schedule setup surface

Status: **GREEN**, executed 2026-07-31. Authored 2026-07-31.

> **Format note.** `AGENTS.md` prefers one vertical improvement per brief and one executor.
> This brief covers seven bounded units because the user is orchestrating several executors
> outside Claude Code. A senior holding to the one-executor model should split it into three
> briefs at the marked seams: **A** = units 1, 2, 7 (chrome only); **B** = units 3, 4 (schedule
> model plus examples); **C** = units 5, 6 (the Settings surface). Unit 7 depends on 2 and 6,
> so in a three-brief split it moves to the end of C.

## Objective

Three defects reported from the running app:

1. **The header is overcrowded.** `SmartDeck` and `Settings` visibly overlap at 1280px. Root
   cause: `.ce-app-header` declares a four-column grid whose third column
   (`minmax(260px, 1fr)`, reserved for a readiness status strip) is never rendered, so it eats
   the width the nav needs while `Settings` and the theme toggle sit pinned right in
   `.topbar-right`.
2. **SmartDeck's left rail is a paragraph of prose.** No links to the page's own sections, and
   when the page is unconfigured the warning names what is missing but offers nowhere to go.
   Its fallback copy already reads "Please configure your schedules in Settings" while pointing
   at a Settings panel that does not exist. Teacher schedules are hand-edited JSON today, with
   the instructions buried in the file's own `_comment`.
3. **The SmartDeck tagline is marketing copy.** This is a tool for a professional.

Outcome: a header that fits one line, a SmartDeck rail that navigates the page and routes an
unconfigured teacher into a Settings panel that can finish the job, and three honest example
schedule sets in the repo so a teacher starts from a working file instead of a blank template.

## Locked decisions

Confirmed with the user. Do not relitigate.

1. **Add an optional `weekdays` field to a teacher-schedule block.** `[0, 2]` means Monday and
   Wednesday; 0=Mon..6=Sun, the numbering `api/default_docs/Calendars/school-events.json`
   already documents. Absent means "meets every day", so every existing file keeps working and
   no current test changes.
2. **Do not add a `schedules` field.** Considered and cut. Nothing in scope needs it, and its
   values would be filename slugs that break silently on a rename.
3. **Two blocks may share a `name` when their weekday sets are disjoint.** This is what lets a
   slide bound to `"Algebra I"` resolve on both a M/W day and a short Friday. Example 2 depends
   on it. Saving rejects a duplicate name only when the weekday sets actually intersect.
4. **The Settings panel gets a full blocks editor**, including the example-cleanup flow.
5. **Examples ship in the repo and are copied only on explicit request.** Never seeded.
6. **Do not bump `version`.** It stays `"1.0-json"`. The field is additive and `version` is
   never read by any code path.
7. **Nav order** becomes `Home  Create  PowerGrader  CanvasAgent  SmartDeck  More ▾  Settings`
   then the theme toggle, all packed left. `More` holds `Students`, `Seating`, `Automations` in
   that order.

## Non-goals

Explicit. An executor that builds any of these has exceeded scope.

- No file upload, in-app CSV grid, bell-period row editor, day-calendar date picker, per-date
  override UI, generate-a-day-calendar-from-a-range, or paste-CSV box. The Calendars folder is
  already the documented drop zone and it syncs. An upload endpoint buys a second write path
  plus multipart handling and filename sanitization for no capability the folder does not
  already give. (If one of these returns later, it is the day-calendar generator: writing 180
  rows by hand is the real remaining pain, and the examples only postpone it.)
- Do **not** add `/smartdeck` to `EXPECTED_PRESENTATION` in
  `api/tests/test_presentation_contracts.py`. It is absent today and
  `test_registry_is_the_full_program_route_map` asserts exactly 12 routes. No unit here needs
  it.
- Do not remove other pages' `page_header` ledes. Only SmartDeck's tagline goes.
- Do not touch the dead status-strip block or CSS, the unpoliced `smartdeck.css` literals, or
  `list_calendar_files()`. See **Adjacent, deliberately excluded** at the end.
- No migration or back-compat shims beyond "absent `weekdays` means every day". Per
  `docs/reference/project-state.md`, this is pre-launch with a single user.

## Routed references

Read only these, and only the sections named.

| Need | Read |
|---|---|
| Workflow, guardrails, test commands | `AGENTS.md` |
| Scope posture | `docs/reference/project-state.md` |
| Web UI route/page/JS load order | `api/webui/README.md` |
| Template families, CSS ownership, JS-hook rule | `docs/reference/webui-presentation-system.md` §§ Template API, CSS ownership, change propagation |
| SmartDeck ownership, storage layout, schema | `docs/reference/smartdeck-module-map.md` |
| Settings ownership and guardrails | `docs/reference/settings-module-map.md` |

**Guardrail note, important.** `AGENTS.md` guardrail 3 explicitly exempts academic calendars
and bell schedules: they are public information, and the real district times already seeded
under `api/default_docs/Calendars/` are sanctioned and must **not** be "fixed" as a violation.
The requirement here is narrower and different: the three new **examples** must use invented
times so they are unmistakably examples, and so
`test_example_bell_times_do_not_match_the_seeded_district_times` is a meaningful check rather
than a coincidence. Course labels must stay generic subject names; no school name, teacher
name, or district URL enters any example file.

## Hard constraints (every unit)

- No em-dashes in any copy or comment. Calm teacher-facing voice; no ALL-CAPS emphasis, no
  "ENFORCED"/"NEVER" framing, no compliance banners, no taglines.
- No `style="` in any template. `test_all_live_templates_use_layouts_and_no_inline_styles`
  walks every template under `templates/`.
- Files listed in `FEATURE_CSS` may not contain `font-family:`, hex colors, `rgb(`/`hsl(`,
  `border-radius:`, or `box-shadow:`. Tokens only.
- Shared `ce-*` component classes may never appear in a JS selector. Use an `id` or a `data-*`
  attribute.
- Every `id` on a page must stay unique.

## Preflight

Stop and report if any of these is false.

1. `.ce-app-header` at `api/webui/static/ui/layouts.css:1` still declares four grid columns
   while `layouts/_app_header.html` emits three children.
2. `{% block status_strip %}` in `api/webui/templates/base.html` is still overridden by no
   template, and no `_readiness_strip.html` exists.
3. `api/webui/deps.py:93` `load_bell_schedules()` still returns `({}, [])` with no problem
   string when zero `Bell Schedule*.csv` files exist.
4. `api/webui/routes/smartdeck.py:157` `smartdeck_readiness()` still calls only the three
   loaders and never `resolve_day`.
5. `api/webui/templates/ui/_macros.html` `panel()` still takes no `id`.
6. `Examples` is still absent from `LIBRARY_SUBFOLDERS` in `api/webui/workspace.py:43`.
7. Baseline: `py -m pytest api/tests` is green at the starting commit. Record the count.

## Findings that correct common assumptions

- `resolve_day` problems never reach `/smartdeck/api/readiness`. "Period not in schedule" noise
  lands in per-deck notes, the display payload, and MCP `get_day_schedule().problems`.
- **Existing bug to fix in unit 5:** with a teacher schedule and a day calendar but zero bell
  schedules, readiness returns `{ready: false, missing: []}` and the UI falls through to
  generic copy. Fix in the new composer, not in `deps.load_bell_schedules`: that loader also
  feeds `resolve_schedule_for`, and a new string there would double up with
  `schedule '<id>' not found for <date>`.
- `.callout` / `.warn` at `settings.html:437` have **no CSS anywhere**. Do not reuse them; use
  `ce-notice`.
- `.ce-app-nav .ce-app-nav--active` (layouts.css:7) never matched the Settings link, because
  the link lives outside `.ce-app-nav`. The active page gets `aria-current` but no visible
  highlight. Unit 1 fixes this incidentally.

---

# Unit 1: header nav, `More` menu, Settings inline

**Independent. No backend. Parallel-safe with units 2 and 3.** Everything is in
`api/webui/templates/layouts/_app_header.html` (18 lines, the whole header) and the first 12
lines of `api/webui/static/ui/layouts.css`.

1. Delete the `Students`, `Seating`, `Automations` links from `.ce-app-nav`. Add a `<details>`
   after `SmartDeck`:
   ```html
   <details class="ce-nav-more" id="ce-nav-more">
     <summary class="{% if nav_section in ['manage', 'seating', 'automate'] %}ce-app-nav--active{% endif %}">More <span class="ce-nav-more__caret">▾</span></summary>
     <div class="ce-nav-more__pop"> ...the three links... </div>
   </details>
   ```
   `/seating` sets `nav_section: "seating"` (`routes/pages.py:175`) while the header currently
   path-matches it. Use `nav_section` for consistency and verify the highlight on `/seating`.
2. **Move the `Settings` link inside `.ce-app-nav`**, after the `More` block. Drop the
   `ce-app-settings` class and let `.ce-app-nav a` style it. Grep `ce-app-settings` across
   `static/`, `templates/`, `docs/`, `api/tests/` before removing.
3. Remove the `.topbar-right` wrapper; leave `<button class="theme-toggle" id="theme-toggle">`
   as a direct header child. **Keep the `theme-toggle` id**
   (`webui-presentation-system.md` pins it as preserved chrome; `base.html:29` binds it). Grep
   `topbar-right` before deleting its rule.
4. **`.ce-app-header` becomes flex, not grid.** Replace
   `display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(260px, 1fr) auto` with
   `display: flex; flex-wrap: wrap; align-items: center`. This is what removes the dead third
   column. Brand, nav, and toggle now pack left with empty space on the right, which is what
   was asked for: no right-side justify.
5. `.ce-nav-more` CSS in `ui/layouts.css`, modeled on the existing `.ce-course-picker` /
   `.ce-picker-pop` pattern at `api/webui/static/pages/course_expert.css:14-24` (tokens only):
   `.ce-nav-more { position: relative }`; `.ce-nav-more summary` matching `.ce-app-nav a`
   (padding `7px 9px`, `list-style: none`, default marker hidden);
   `.ce-nav-more__pop { position: absolute; z-index: 20; left: 0; ... }`.
6. Responsive: rewrite the `.ce-app-header` rules in the `1180px` and `760px` blocks for flex.
   At `760px`, `.ce-app-nav { order: 3; flex-basis: 100%; overflow-x: auto }` preserves today's
   horizontal-scroll behavior. Leave the `.ce-status-strip` rules alone.
7. Small IIFE in `base.html` beside the theme-toggle script (inline is the convention for
   header chrome): close `#ce-nav-more` on outside click and on Escape. `<details>` handles
   click-to-open and keyboard activation natively.

**Acceptance.** Header renders on one line at 1280px with no overlap. `More` opens; closes on
outside click and on Escape. `/roster`, `/seating`, `/routines` each highlight `More`.
`/settings` highlights `Settings` visibly, not just via `aria-current`. Suite green.

---

# Unit 2: shared rail navigation

**Independent. Pure extraction, zero behavior change. Parallel-safe with units 1 and 3.**

`api/webui/static/settings/rail_nav.js` is a working in-page section highlighter, but its
selectors are Settings-specific and its coverage map is hardcoded. Generalize it so unit 7
reuses it instead of growing a second copy. This follows the approved shared-partials
direction in `webui-presentation-system.md`.

1. New `api/webui/static/ui/rail_nav.js`, moved from `settings/rail_nav.js`. Change the
   selector from `.ce-settings-index__links a[data-rail-link]` to `[data-rail-link]` (a bare
   attribute selector, which satisfies the no-shared-class-as-JS-hook contract). Replace the
   hardcoded `extraCoverage` object with a `data-rail-covered-by="<link-target-id>"` attribute
   read off the covered sections, so the shared file carries no page-specific knowledge.
2. New shared classes in `ui/components.css`: `.ce-rail-nav`, `.ce-rail-nav__group`,
   `.ce-rail-nav__kicker`, `.ce-rail-nav__links`, `.ce-rail-nav__links a.is-active`. Port the
   values from `.ce-settings-index__*` in `api/webui/static/pages/settings.css:2-9`.
3. Migrate `settings.html:10-50` to the shared classes; add
   `data-rail-covered-by="current-courses-card"` to `#previous-courses-card` and
   `#add-courses-card`; point the script tag at the new path; delete the
   `.ce-settings-index__*` rules and the old JS file.
4. Extend the `panel` macro in `ui/_macros.html:6` to `{% macro panel(title='', id='') %}`,
   emitting `id` only when given. Additive and backwards-compatible; unit 7 needs it to anchor
   SmartDeck's panels. `base.html:42-49` already smooth-scrolls to `location.hash`, so anchors
   need no extra JS.

**Acceptance.** `/settings` looks and behaves exactly as before, including scroll-driven
highlight and the Courses-group coverage. Suite green.

**Verification caveat.** The in-app Browser pane has no compositing, so `IntersectionObserver`
never fires there. Verify the highlight in a real browser, or verify structurally (links
present, every href resolves to an existing id) and confirm the highlight by hand.

---

# Unit 3: `weekdays` in the resolver

**Independent Python, no UI. Parallel-safe with units 1 and 2.** All in
`api/webui/deck_schedule.py` (pure stdlib, no IO) and its test file.

**Weekday is derivable in place.** `resolve_day` already receives `date` as `YYYY-MM-DD` and
`_parse_date` (`deck_schedule.py:245`) is in the same module. No signature change, no caller
churn.

New helpers:
```python
def _weekday_set(block, name) -> tuple[set | None, list]   # None means no restriction
def _block_meets(block, name, weekday) -> tuple[bool, list]
def effective_weekdays(block) -> set                        # {0..6} when unrestricted
def validate_teacher_schedule(data: dict) -> list           # problem strings, for the save path
```

In `resolve_day` (`deck_schedule.py:143`):
- Before the block loop: `parsed = _parse_date(date)`,
  `weekday = parsed.weekday() if parsed else None`. Code defensively; skip the weekday test
  when `None`.
- Inside the loop, **after** the `raw_periods` validation (structural problems are
  date-independent and must not be hideable by a weekday field) and **before** the
  `missing_ids` check: call `_block_meets`, extend `problems`, `continue` when it does not meet.
- After the existing `blocks.sort(...)`: append
  `block '<name>' resolved twice for <date>; a deck will only use the later one in the day`
  for a repeated resolved name.

`_block_meets` rules, all **fail-open**. A malformed field is reported then ignored; failing
closed would make a block vanish from every day, which is the failure this unit exists to
eliminate.

| Condition | Result |
|---|---|
| `weekdays` absent | meets |
| `weekdays` not a list, or an entry is not an `int` in 0..6, or an entry is a `bool` | problem `block '<name>': weekdays must be a list of numbers, 0 for Monday through 6 for Sunday`; field ignored, block meets |
| valid, and today's weekday is not in it | does not meet, **no problem string** |
| `weekday is None` | test skipped |

Unchanged and still firing: `no schedule for {date}`,
`schedule '{id}' not found for {date}`, `block '<name>' has no raw_periods`, and
`block '<name>' omitted: periods [...] not in schedule '<id>'` for a block that **does** meet
today. That last message is the reason not to take the no-schema-change route: it is the only
signal for a genuine typo (`raw_periods: [8]` in a seven-period school, or a CSV that lost a
row), and after this change it is unambiguous instead of also meaning "not today, on purpose".

`validate_teacher_schedule` is **strict** because it gates saves, while `resolve_day` stays
permissive: `blocks` a list; each block a dict with a non-empty string `name`; `raw_periods` a
non-empty list of ints or non-empty strings; `weekdays` as above but blocking; `label` a string
when present; duplicate `name` a problem **only when two blocks' `effective_weekdays()`
intersect**, message
`block '<name>' is listed more than once for the same weekday; give one a different name or narrow its weekdays`.
`version` is not validated. Unknown top-level and per-block keys are never problems.

**Do not add `weekdays` to the resolved block output.** Keeping the output keys at
`{name, label, start, end, raw_periods, schedule_id}` means zero churn in
`api/smartdeck_feeds.py:80` `_bell_schedule_feed`, `_resolve_slides`, `display.js`, and
`slide_select.js`.

Downstream, verified as needing no code change: `parse_teacher_schedule` (docstring only),
`deps.load_teacher_schedule`, MCP `get_teacher_schedule` (returns the dict verbatim, so
`weekdays` reaches the assistant for free) and `get_day_schedule`, the MCP tool schema JSONs,
`sf.py`.

Docs in this unit:
- `api/default_docs/SmartDecks/Teacher Schedule.template.json`: document `weekdays` in
  `_comment`, add one block using it.
- `api/default_docs/AI Authoring/Author a SmartDeck (SlideForge).txt` near line 53: one
  sentence saying a block may meet only on some days, so call `get_day_schedule` for the deck's
  own date rather than assuming every block from `get_teacher_schedule` exists on it.
- `docs/reference/smartdeck-module-map.md`: the optional field in the schema section.

**Tests** appended to `api/tests/test_deck_schedule.py` (pytest, class-grouped, inline JSON/CSV
string literals, no fixture files). **No existing test changes.**

`class TestResolveDayWeekdays`: `test_block_without_weekdays_meets_every_day`,
`test_block_meets_only_on_listed_weekdays`,
`test_block_omitted_on_unlisted_weekday_is_silent`, `test_weekday_zero_is_monday`,
`test_missing_period_still_reports_for_a_meeting_block`,
`test_missing_period_is_silent_for_a_non_meeting_block`,
`test_malformed_weekdays_reports_and_block_still_meets`,
`test_weekday_out_of_range_reports_and_block_still_meets`,
`test_boolean_weekday_entry_is_rejected`,
`test_no_raw_periods_reports_even_on_a_non_meeting_weekday`,
`test_same_name_on_disjoint_weekdays_resolves_to_one_block_per_day`,
`test_duplicate_resolved_name_reports_once`.

`class TestValidateTeacherSchedule`: `test_valid_schedule_has_no_problems`,
`test_blocks_must_be_a_list`, `test_block_needs_a_name`, `test_block_needs_raw_periods`,
`test_duplicate_name_on_overlapping_weekdays_is_rejected`,
`test_duplicate_name_on_disjoint_weekdays_is_allowed`,
`test_duplicate_name_is_rejected_when_one_block_has_no_weekdays`,
`test_weekdays_must_be_numbers_zero_through_six`,
`test_unknown_top_level_keys_are_not_problems`, `test_version_is_not_validated`.

**Gate.** `py -m pytest api/tests/test_deck_schedule.py api/tests/test_smartdeck_display.py api/tests/test_smartdeck_feeds.py api/tests/test_smartdeck_routes.py`

---

# Unit 4: three example schedule sets

**Depends on unit 3** (example 2 uses `weekdays`).

Location: `api/default_docs/Examples/Class Schedules/<slug>/`.

**Why that path, and why never seeded.** `ensure_workspace()` (`api/webui/workspace.py:726`)
seeds by iterating `LIBRARY_SUBFOLDERS` (`workspace.py:43`) and calling
`_seed_folder_if_missing`. `Examples` is not in that list, so a top-level
`default_docs/Examples/` is inert by construction. That is the reason for the parent directory:
not tidiness, a guarantee. Seeding these would be corruption, not clutter:
`load_day_calendar()` **merges every** matching CSV in `Calendars`, so three fake date maps
would union into the teacher's real one; `load_bell_schedules()` picks up any file starting
with "bell schedule"; and a seeded `Teacher Schedule.json` would make readiness report
**ready** on a fresh workspace, putting invented periods on a classroom projector.

## Shared date span, weekdays verified

All three use **2026-08-17 through 2026-09-11**, weekdays independently confirmed:

| Date | Day | Date | Day |
|---|---|---|---|
| 2026-08-17 | Mon | 2026-08-31 | Mon |
| 2026-08-18 | Tue | 2026-09-01 | Tue |
| 2026-08-19 | Wed | 2026-09-02 | Wed |
| 2026-08-20 | Thu | 2026-09-03 | Thu |
| 2026-08-21 | Fri | 2026-09-04 | Fri |
| 2026-08-24 | Mon | 2026-09-08 | Tue |
| 2026-08-25 | Tue | 2026-09-09 | Wed |
| 2026-08-26 | Wed | 2026-09-10 | Thu |
| 2026-08-27 | Thu | 2026-09-11 | Fri |
| 2026-08-28 | Fri | | |

19 dates. **2026-09-07 is deliberately absent**: it is the first Monday in September, and its
omission demonstrates that a no-school day is expressed by leaving the date out of the day
calendar. Same span in all three, so a teacher comparing them is comparing schedules, not
dates.

Each `Day Calendar - *.csv` has header `date,schedule_id` and exactly those 19 rows.
`schedule_id` is the bell-schedule filename slug produced by `_file_key()`
(`api/webui/routes/calendar.py:28`, `re.sub(r'[^a-z0-9]+', '_', stem.lower()).strip('_')`).

Each directory also gets `manifest.json`
(`{"format": "canvasexpert.schedule_example/1", "slug", "name", "summary", "demonstrates", "teacher_schedule", "bell_schedules": [...], "day_calendar", "check_dates": [...]}`)
and a short `README.md`. **Neither is ever copied into a workspace.**

## Example 1: `seven-single-periods/`

`Bell Schedule - Example Seven Period Day.csv` (`bell_schedule_example_seven_period_day`),
header `period_id,start,end`:
`1,07:55,08:45` / `2,08:50,09:40` / `3,09:45,10:35` / `4,10:40,11:30` /
`lunch,11:30,12:05` / `5,12:10,13:00` / `6,13:05,13:55` / `7,14:00,14:50`

`Teacher Schedule.json`: seven blocks, no `weekdays` on any, named `1st Period` .. `7th Period`
with `raw_periods` `[1]`..`[7]` and labels `Reading Workshop`, `Reading Workshop`, `Planning`,
`Writing Workshop`, `Writing Workshop`, `Reading Workshop`, `Study Skills`. `_comment`: the
same seven single periods every school day; no block sets `weekdays`; the `lunch` row is not a
block, because a period nothing refers to is simply ignored.

Day calendar: all 19 dates to `bell_schedule_example_seven_period_day`.
`check_dates`: `2026-08-17`, `2026-09-11`.

## Example 2: `alternating-day-split/`

The point of this one: **the weekday split lives entirely in the teacher schedule, and the bell
schedules only describe day types.** Those two axes compose instead of multiplying.

`Bell Schedule - Example Split Day.csv` (`bell_schedule_example_split_day`):
`1,08:15,09:45` / `2,09:50,11:20` / `lunch,11:20,11:55` / `3,12:00,13:30` / `4,13:35,15:05`

`Bell Schedule - Example Split Friday.csv` (`bell_schedule_example_split_friday`):
`1,08:15,08:55` / `2,09:00,09:40` / `3,09:45,10:25` / `4,10:30,11:10` /
`lunch,11:10,11:45` / `5,11:50,12:30` / `6,12:35,13:15` / `advisory,13:20,15:05`

`Bell Schedule - Example Split Assembly.csv` (`bell_schedule_example_split_assembly`):
`1,08:15,09:25` / `2,09:30,10:40` / `assembly,10:45,11:35` / `lunch,11:35,12:10` /
`3,12:15,13:25` / `4,13:30,15:05`

`Teacher Schedule.json` blocks, in this order:

| name | raw_periods | weekdays | label |
|---|---|---|---|
| Algebra Foundations | [1] | [0, 2] | Algebra Foundations |
| Geometry Basics | [2] | [0, 2] | Geometry Basics |
| Math Lab | [3] | [0, 2] | Math Lab |
| Pre-Algebra | [1] | [1, 3] | Pre-Algebra |
| Algebra I | [2] | [1, 3] | Algebra I |
| Study Skills | [3] | [1, 3] | Study Skills |
| Planning | [4] | [0, 1, 2, 3] | Planning period |
| Algebra Foundations | [1] | [4] | Algebra Foundations |
| Geometry Basics | [2] | [4] | Geometry Basics |
| Math Lab | [3] | [4] | Math Lab |
| Pre-Algebra | [4] | [4] | Pre-Algebra |
| Algebra I | [5] | [4] | Algebra I |
| Study Skills | [6] | [4] | Study Skills |

`_comment`: Monday and Wednesday carry one set of classes, Tuesday and Thursday another, and
Friday is a short day where every class meets once; `weekdays` counts 0 for Monday through 6
for Sunday, the same numbering the school events file uses; a block with no `weekdays` meets
every day; two blocks may share a name when their days do not overlap, which is how Algebra
Foundations is first period on Monday and Wednesday and still Algebra Foundations on the Friday
schedule, so a slide bound to that name works on both.

Day calendar: Fridays (08-21, 08-28, 09-04, 09-11) to `..._split_friday`; 2026-09-02 to
`..._split_assembly`; the other 14 dates to `..._split_day`.

Worked resolution, zero problems on every date:

| Date | Weekday | `.weekday()` | schedule_id | Resolves |
|---|---|---|---|---|
| 2026-08-17 | Mon | 0 | split_day | Algebra Foundations 08:15-09:45, Geometry Basics 09:50-11:20, Math Lab 12:00-13:30, Planning 13:35-15:05 |
| 2026-08-18 | Tue | 1 | split_day | Pre-Algebra, Algebra I, Study Skills at the same four slots, plus Planning |
| 2026-08-19 | Wed | 2 | split_day | same four as Monday |
| 2026-08-20 | Thu | 3 | split_day | same four as Tuesday |
| 2026-08-21 | Fri | 4 | split_friday | all six courses at 08:15-08:55 / 09:00-09:40 / 09:45-10:25 / 10:30-11:10 / 11:50-12:30 / 12:35-13:15. Planning excluded (weekdays 0-3). |
| 2026-09-02 | Wed | 2 | split_assembly | same four names as Monday, at 08:15-09:25 / 09:30-10:40 / 12:15-13:25 / 13:30-15:05 |

The nine non-meeting blocks on a Monday are silently absent, not nine warnings. The assembly
row shows the two axes composing: the weekday picks which classes, the bell schedule picks the
clock.

`check_dates`: `2026-08-17`, `2026-08-18`, `2026-08-19`, `2026-08-20`, `2026-08-21`,
`2026-09-02`.

## Example 3: `double-block-mixed/`

`Bell Schedule - Example Double Block Day.csv` (`bell_schedule_example_double_block_day`):
`1,08:20,09:10` / `2,09:14,10:04` / `3,10:08,10:58` / `4,11:02,11:52` /
`lunch,11:52,12:27` / `5,12:31,13:21` / `6,13:25,14:15` / `7,14:19,15:09`

`Bell Schedule - Example Double Block Early Release.csv`
(`bell_schedule_example_double_block_early_release`):
`1,08:20,08:55` / `2,08:59,09:34` / `3,09:38,10:13` / `4,10:17,10:52` / `5,10:56,11:31` /
`6,11:35,12:10` / `7,12:14,12:49`

`Teacher Schedule.json`, no `weekdays` on any block: `1st/2nd` `[1,2]` Intensive Reading;
`3rd Period` `[3]` English I; `4th Period` `[4]` English I; `5th/6th` `[5,6]` Intensive
Reading; `7th Period` `[7]` Planning. `_comment`: a block covering two periods lists both
numbers in order and runs from the first period's start to the last period's end; the early
release day uses the same block names at shorter times, which is why slides bind to a name and
never to a clock time.

Day calendar: 2026-08-28 to `..._early_release`; the other 18 to `..._day`.

Resolution: on 2026-08-17, `1st/2nd` = 08:20-10:04 and `5th/6th` = 12:31-14:15. On 2026-08-28,
the same names give 08:20-09:34 and 10:56-12:10. Zero problems on both.
`check_dates`: `2026-08-17`, `2026-08-28`.

## Parent README

`api/default_docs/Examples/Class Schedules/README.md`: three complete class schedule sets, kept
here so the app can show a teacher a working example; nothing in this folder is copied into a
workspace on first run; Settings copies one set on request, under "Class schedule examples";
every course name, bell time, and date here is invented. Add one line explaining that the
seeded schedules in `api/default_docs/Calendars` are real, sanctioned public district times,
and that these examples stay invented so the two sets are never confused.

## Tests: new `api/tests/test_schedule_examples.py`

This is the file that keeps the examples honest. Reuse the `isolated_workspace` fixture pattern
from `api/tests/test_smartdeck_display.py:21`. The root `api/tests/conftest.py` unsets
`OneDrive`, so `workspace_root()` is `None` unless `workspace.library_folder` is monkeypatched.

`test_every_example_directory_has_a_manifest`, `test_every_manifest_file_exists_on_disk`,
`test_every_example_teacher_schedule_validates`,
`test_every_example_resolves_with_zero_problems` (parametrized over every `(slug, date)` in
each manifest's `check_dates`), `test_every_example_resolves_at_least_one_block`,
`test_split_example_resolves_a_different_block_set_on_each_weekday_family`,
`test_split_example_resolves_the_same_block_names_on_monday_and_friday`,
`test_double_block_example_spans_two_periods`,
`test_examples_are_not_seeded_into_a_new_workspace` (run `ensure_workspace()` on `tmp_path`,
assert no `Example` file in `Library/Calendars` and no `Library/SmartDecks/Teacher Schedule.json`),
`test_example_bell_schedule_filenames_are_discoverable`,
`test_example_day_calendar_filenames_are_not_mistaken_for_bell_schedules`,
`test_example_day_calendar_schedule_ids_match_its_bell_schedule_slugs` (via
`routes.calendar._file_key`; catches a rename),
`test_example_day_calendar_dates_match_the_weekday_pattern_in_its_manifest`,
`test_example_bell_times_do_not_match_the_seeded_district_times` (compare start-time sets
against every `api/default_docs/Calendars/Bell Schedule - *.csv`).

**Gate.** `py -m pytest api/tests/test_schedule_examples.py api/tests/test_deck_schedule.py api/tests/test_workspace.py`

---

# Unit 5: `schedule_setup.py` and the schedule routes

**Depends on units 3 and 4.**

New `api/webui/schedule_setup.py`, above `deps.py` and below the routers. One source of truth
for readiness, the `Teacher Schedule.json` read/write, and the example catalog. **Do not put
this in `api/webui/readiness.py`**: that is a cached, network-probing surface with a
process-global `_LAST_PROBE` and a 5-second HTTP timeout. Different lifecycle.

```python
EXAMPLES_DIR: str   # api/default_docs/Examples/Class Schedules

def readiness() -> dict                                      # {"ready", "missing", "pieces"}
def teacher_schedule_path() -> str | None
def load_blocks() -> tuple[list, list]                       # (blocks_as_written, problems)
def save_blocks(blocks: list) -> tuple[dict | None, list]
def list_examples() -> list[dict]                            # manifest + {"slug", "dir", "loaded"}
def load_example(slug, overwrite=False) -> tuple[dict | None, list]
def remove_example(slug) -> tuple[dict | None, list]
```

`readiness()` composes the three loaders and **appends `no bell schedules found`** when
`bell_schedules` is empty. `smartdeck_readiness` (`routes/smartdeck.py:157`) becomes a
delegating one-liner that keeps `ok`, `ready`, `missing` (so `smartdeck.js` and both existing
route tests keep passing) and **adds** `pieces`. Purely additive.

New `api/webui/routes/schedule.py`, registered in `api/webui/server.py` alongside
`_calendar_router`. **Not an extension of `routes/calendar.py`**: those five routes all write
`config.set_calendar()` for the gradebook sweep, a different feature that happens to read the
same folder. Form-encoded bodies with a JSON string for structured data, matching
`/api/calendar/set` and `/api/tier-tags`. House style: HTTP 200 with
`{"ok": false, "problems": [...]}` on failure.

**`GET /api/schedule`** returns everything the panel needs in one request: `ok`, `ready`,
`missing`, `pieces` (per-part `present` / counts / `path` / `problems`; `bell_schedules.found`
with `name`, `label`, `schedule_id`, `period_count`; `day_calendar` with `date_count`, `first`,
`last`, `files`, `schedule_ids`, **`unknown_schedule_ids`**), `blocks` (**the raw array as
written in the file**, keys and order untouched, so the editor can round-trip unknown per-block
keys), `folders`, `examples`.

`unknown_schedule_ids` is new: a day-calendar row naming a bell schedule that does not exist
currently surfaces only as a per-date resolve failure, so a CSV rename goes unnoticed until the
day it bites.

**`POST /api/schedule/teacher`** — `blocks` (Form, JSON array string) to
`{"ok": true, "count", "path"}`.

Preservation rules, all load-bearing:
- Read the existing file; **every top-level key is preserved verbatim**, including `_comment`.
  Only `blocks` is replaced.
- `version` is written as `"1.0-json"` **only when absent**. An existing value is never
  touched.
- `blocks` is written in the order received, **never sorted**. `resolve_day` sorts by start
  time at render, and `raw_periods` order is semantically meaningful: it picks the first
  period's start and the last period's end.
- Unknown per-block keys survive because the browser holds the whole block object from
  `GET /api/schedule` and mutates only the known fields; the server writes extras through and
  validates only what it knows. A deleted block loses its extras, which is correct.
- The editor renders Mon-Fri checkboxes only. When writing `weekdays` it posts the checked
  Mon-Fri values **plus any 5 or 6 already present in that block**, so a hand-written weekend
  entry is not silently dropped.
- Atomic write mirroring `deck_store.save_deck` (`api/webui/deck_store.py:169`):
  `tempfile.mkstemp` in the target directory, `os.fdopen`, `flush`, `fsync`, `os.replace`.
  **Do not pass `sort_keys=True`** the way `deck_store` does; this file is hand-edited, and
  `json.dump(data, f, indent=2)` over a `json.loads` dict preserves insertion order so
  `_comment` stays where the teacher left it.
- On any validation problem, nothing is written.

**`POST /api/schedule/examples/load`** — `slug`, optional `overwrite`, to
`{"ok", "slug", "written", "skipped", "moved_aside", "day_calendar_overlap", "problems"}`.
- `Teacher Schedule.json` exists and no `overwrite`: refuse the whole load, write nothing,
  return `{"ok": false, "conflict": "teacher_schedule", ...}`.
- With `overwrite`: **move** the existing file to
  `Teacher Schedule (replaced YYYY-MM-DD HHMM).json`, never unlink. This is the codebase's own
  moves-never-deletes rule (`deck_store.delete_deck`, `migrate_legacy_glass_folders`).
- CSVs that already exist by name are skipped and reported, unless `overwrite`, in which case
  they are moved aside the same way.
- `day_calendar_overlap` counts dates the teacher's existing day calendar already covers,
  because `load_day_calendar()` merges every matching CSV and an example can shadow real dates
  (last file wins by sorted filename). The count drives the warning copy.
- `manifest.json` and `README.md` are never copied. Unknown slug returns a problem.

**`POST /api/schedule/examples/remove`** — `slug`, to `{"ok", "moved", "kept", "problems"}`.
Moves the example's files to `_System/Archive/Class Schedule Examples/<slug>/`, **but only when
a file's bytes still match the shipped copy**. An edited file is left in place and reported in
`kept`, so `Teacher Schedule.json` is normally kept, which is right. Without this endpoint,
trying an example is a one-way door that permanently pollutes day-calendar resolution.

**Tests: new `api/tests/test_schedule_routes.py`** —
`test_get_api_schedule_on_empty_workspace_reports_all_three_missing`,
`test_get_api_schedule_reports_missing_bell_schedules_explicitly`,
`test_get_api_schedule_reports_unknown_schedule_ids_in_the_day_calendar`,
`test_get_api_schedule_returns_blocks_verbatim_including_unknown_keys`,
`test_post_schedule_teacher_writes_blocks`,
`test_post_schedule_teacher_creates_the_file_when_absent`,
`test_post_schedule_teacher_preserves_unknown_top_level_keys`,
`test_post_schedule_teacher_sets_version_only_when_absent`,
`test_post_schedule_teacher_keeps_block_order`,
`test_post_schedule_teacher_refuses_invalid_blocks_and_leaves_the_file_unchanged`,
`test_load_example_writes_every_manifest_file`,
`test_load_example_does_not_write_the_manifest_or_readme`,
`test_load_example_refuses_to_clobber_an_existing_teacher_schedule`,
`test_load_example_with_overwrite_moves_the_old_file_aside`,
`test_load_example_skips_csvs_that_already_exist`,
`test_load_example_reports_day_calendar_overlap`,
`test_load_example_rejects_an_unknown_slug`, `test_loaded_example_makes_readiness_ready`,
`test_remove_example_moves_unmodified_files_to_the_system_archive`,
`test_remove_example_keeps_a_file_the_teacher_edited`.

Appended to `api/tests/test_smartdeck_routes.py`:
`test_smartdeck_readiness_keeps_ready_and_missing_keys`,
`test_smartdeck_readiness_adds_pieces`,
`test_smartdeck_readiness_names_the_missing_bell_schedules`.

**Gate.** `py -m pytest api/tests/test_schedule_routes.py api/tests/test_schedule_examples.py api/tests/test_smartdeck_routes.py api/tests/test_route_contract.py`

---

# Unit 6: the Settings panels

**Depends on units 2 and 5.**

Two sections in `api/webui/templates/settings.html`, inserted **immediately before**
`<section ... id="cal">` (line 414), so they sit under the existing "Files & calendars" rail
group. Class schedule goes first because it is the one with a readiness gate; the academic
calendar is a sweep input, a different concern that happens to share a folder.

- `<section class="ce-panel ce-settings-panel" id="class-schedule-card">` heading
  **Class schedule**, with `<small class="lbl-hint">(used by SmartDeck)</small>`
- `<section class="ce-panel ce-settings-panel" id="class-schedule-examples-card" data-rail-covered-by="class-schedule-card">`
  heading **Class schedule examples**

**One rail link, not two.** Add
`<a href="#class-schedule-card" data-rail-link>Class schedule</a>` before the Academic
calendars link (`settings.html:40`); the examples panel borrows its highlight via the
`data-rail-covered-by` mechanism from unit 2, the same precedent as Previous courses and Add
courses.

**Render client-side.** New `api/webui/static/settings/class_schedule.js` fetches
`GET /api/schedule` on load. Two reasons: readiness parses every CSV in the Calendars folder,
too much work for every `/settings` render on an already heavy page; and `_configure_fictional`
at `api/tests/test_presentation_contracts.py:68` monkeypatches a fixed list of `pages.*`
attributes, so a server-side call would force that fixture to grow. **Nothing is added to
`pages.py`'s `/settings` context.**

Panel contents: readiness rows for the three parts; the blocks editor (rows of name / periods /
Mon-Fri checkboxes / label, plus Add a block, Remove, Save blocks); Open the Calendars folder
and Open the SmartDecks folder via the existing `POST /api/open-path`; and the examples panel
with Load and Remove per example.

Markup and CSS: new rules in `api/webui/static/pages/settings.css` (in `FEATURE_CSS`, so tokens
only: `--ce-space-*`, `--ce-rule`, `--ce-rule-strong`, `--ce-surface-soft`, `--ce-ink`,
`--ce-ink-muted`, `--ce-ok`, `--ce-danger`). JS hooks: container `id="class-schedule-blocks"`,
generated rows carry `data-ce-hook="block-row"`. Use `ce-notice` / `ce-notice--ok`, **not**
`callout warn`.

## Copy (use verbatim; no em-dashes)

Panel intro:
> Your class schedule is what SmartDeck uses to turn a block name like 4th/5th into today's real start and end time. It has three parts, all kept as plain files in your workspace, so you can edit any of them by hand at any time.

Readiness rows:
> **Your blocks.** Found 5 blocks in Teacher Schedule.json.
> **Your blocks.** No Teacher Schedule.json yet. Add your blocks below, or load an example set.
> **Bell schedules.** Found 2: Example Split Day, Example Split Friday.
> **Bell schedules.** No Bell Schedule files in your Calendars folder yet.
> **Day calendar.** Found 19 dates, 2026-08-17 through 2026-09-11.
> **Day calendar.** No day calendar in your Calendars folder yet. A day calendar says which bell schedule each date uses.
> SmartDeck has everything it needs.
> SmartDeck needs all three parts before it can show a deck.

Blocks editor:
> A block is one of your classes as it sits in the day. Give it a short name you will recognize on a slide, the bell periods it covers in order, and an optional label. A block that runs two periods back to back gets both period numbers.
> Leave the days blank if this block meets every school day. Otherwise check the days it meets.
> Two blocks can share a name as long as their days do not overlap. That is how one class can be first period on Monday and Wednesday and fifth period on the Friday schedule, with your slides still finding it by the same name.
> Save blocks / Add a block / Remove
> Saved 5 blocks to Teacher Schedule.json.
> Nothing was saved. Fix these first:
> Open the Calendars folder / Open the SmartDecks folder
> Bell schedules and day calendars are CSV files you keep in your Calendars folder. Drop a new one in and it shows up here.

Examples panel:
> Three complete example sets ship with the app. Loading one writes its files into your workspace so you can see how the three parts fit together, then edit them into your own. The course names, bell times, and dates are all invented.
> Load this example / Remove this example

Confirms and warnings:
> You already have a Teacher Schedule.json. Loading this example moves your current one aside as "Teacher Schedule (replaced 2026-07-31 1412).json" and writes the example in its place. Continue?
> Loaded. 4 files written. 1 was already there and was left alone: Bell Schedule - Example Split Day.csv.
> This example's day calendar covers 6 dates that your own day calendar already covers. On those dates the example may win. Remove the example when you are done looking at it.
> Move this example's files out of your workspace? They go to _System/Archive/Class Schedule Examples, and nothing is deleted. Files you have edited stay where they are.

Appended to `api/tests/test_presentation_contracts.py`:
`test_settings_has_a_class_schedule_panel_and_rail_link` (both `id="class-schedule-card"` and
`href="#class-schedule-card"` present; the existing unique-id assertion covers collisions for
free).

Also update `docs/reference/settings-module-map.md`: ownership, browser routing, backend
routing, and a guardrail line saying example schedule sets are copied on explicit request and
never seeded.

**Gate.** `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_schedule_routes.py api/tests/test_route_contract.py`

---

# Unit 7: SmartDeck page

**Depends on units 2 and 6.** All in `api/webui/templates/smartdeck.html` plus a little CSS.

1. **Remove the tagline.** Line 14 becomes `{{ page_header('SmartDeck') }}`. The macro already
   guards on `{% if lede %}`. Grep the tagline string across `api/tests/` first.
2. **Rail section links.** Add a `.ce-rail-nav` (unit 2) above the existing blurb with four
   `data-rail-link` anchors: Active, Templates, Archived, Widgets. Give each `panel()` call its
   matching `id` via the extended macro (`smartdeck-active`, `smartdeck-templates`,
   `smartdeck-archived`, `smartdeck-widgets`). Load `/static/ui/rail_nav.js` in
   `workspace_scripts`.
   - Keep the existing blurb, moved below the links. It describes the surface rather than
     selling it, so it stays. Drop it only if it visibly crowds the rail.
3. **Route the unconfigured notice to Settings.** Add a static link inside
   `#smartdeck-unconfigured` (static markup, not JS-injected, so it is always right):
   > SmartDeck needs your class schedule before it can show a deck. Set it up in Settings.

   linking `/settings#class-schedule-card`. Keep `#smartdeck-unconfigured-detail` for the
   specific missing list. Replace the generic fallback string at
   `api/webui/static/smartdeck/smartdeck.js:23` so it no longer says "Please configure your
   schedules in Settings" in prose the teacher cannot click.

**Acceptance.** No tagline. The rail lists all four sections and clicking each scrolls to it.
With an unconfigured workspace the notice names what is missing and links into the new Settings
panel. With an example loaded the notice is gone.

---

# Acceptance criteria (whole brief)

Independently checkable, authored before execution.

1. At 1280px, the header occupies one line and no two nav items overlap.
2. `More` opens on click, closes on outside click and on Escape, and holds exactly Students,
   Seating, Automations.
3. Visiting `/roster`, `/seating`, `/routines` highlights `More`; visiting `/settings`
   highlights `Settings` with the underline, not only `aria-current`.
4. `/smartdeck` shows no tagline and four working rail section links.
5. `/settings` still highlights its rail sections on scroll, exactly as before unit 2.
6. On an empty workspace, `GET /api/schedule` reports all three parts missing, and the missing
   list names the absent bell schedules rather than returning an empty list.
7. Loading `alternating-day-split` writes its 5 files, flips all three readiness rows, and
   shows 13 blocks in the editor with the correct Mon-Fri boxes checked.
8. `resolve_day` for 2026-08-17 and 2026-08-21 in that example returns different block sets,
   resolves the shared names on both dates, and returns **zero** problems on both.
9. Saving an edited block leaves `_comment`, `version`, and block order intact on disk, and
   changes only `blocks`.
10. Removing the example moves the CSVs to `_System/Archive/Class Schedule Examples/` and keeps
    an edited `Teacher Schedule.json` in place.
11. `test_examples_are_not_seeded_into_a_new_workspace` passes: `ensure_workspace()` on a fresh
    tmp path produces no example file and no `Teacher Schedule.json`.
12. No existing test was modified to pass. Every change to a test file is an addition.

# Verification gate

Per unit, run that unit's named focused gate. At the end of the batch, one integration run:

```powershell
py -m pytest api/tests
```

Then, in the running app (`cd api; py qf_ui.py`, http://127.0.0.1:8765):

1. `/` — header on one line, `More` behavior, active highlights on the four routes.
2. `/smartdeck` with an unconfigured workspace — no tagline, four rail links, notice names what
   is missing and links to `/settings#class-schedule-card`.
3. Follow that link — Class schedule panel reports all three parts missing, with a real reason
   for zero bell schedules.
4. Load `alternating-day-split` — files land in `Library/Calendars` and `Library/SmartDecks`,
   readiness rows flip, editor shows 13 blocks.
5. Edit a block name and save — **diff `Teacher Schedule.json` on disk yourself.** Confirm
   `_comment` and block order survived and only `blocks` changed. Do not accept an executor's
   claim that nothing else was touched.
6. MCP `get_day_schedule` for `2026-08-17` and `2026-08-21` — Monday and Friday sets differ,
   shared names resolve on both, `problems` empty on both. This is the check that proves the
   weekday model works through the whole stack.
7. Remove the example — CSVs archived, edited `Teacher Schedule.json` kept.

**Two verification caveats.** The in-app Browser pane has no compositing, so
`IntersectionObserver` never fires there: the rail's active-section highlight can only be
confirmed in a real browser. And the root `api/tests/conftest.py` unsets `OneDrive` so
`workspace_root()` is `None` by default; any new schedule test must monkeypatch
`workspace.library_folder` the way `api/tests/test_smartdeck_display.py:27` does, or it will
silently test the empty-workspace path and pass for the wrong reason.

# Stop conditions

Stop and report rather than guessing when:

- Any preflight item is false.
- A test that existed before this brief needs editing to pass.
- The `panel()` macro change breaks a page other than SmartDeck and Settings.
- `weekdays` turns out to need a `resolve_day` signature change, or a consumer not listed in
  unit 3's downstream table needs a code change.
- The Settings panel would need anything added to `pages.py`'s `/settings` context.
- Any unit would require a new write path to the Calendars folder beyond the two example
  endpoints.

# Adjacent, deliberately excluded

Named so a later agent does not mistake them for oversights. Separate commits, or not at all.

- **Dead status strip.** `{% block status_strip %}` (`base.html:24`) is overridden by no
  template and no `_readiness_strip.html` exists, yet `.ce-app-header .ce-status-strip` /
  `.ce-status-item` / `.ce-readiness-*` occupy `layouts.css:8-11` plus responsive rules at :35
  and :43. Unit 1 leaves them alone on purpose: they are inert under flex, and
  `api/webui/readiness.py` suggests a strip was or is intended somewhere. Removing them is a
  real cruft win but needs its own decision about whether the strip is coming back.
- **Unpoliced SmartDeck CSS.** `static/smartdeck/smartdeck.css` is not in `FEATURE_CSS`, and it
  shows: a raw `border-radius: 4px` at :22 and `var(--ce-text-secondary)` at :37 and :79, a
  token `tokens.css` does not define (the real one is `--ce-ink-muted`, so that color is
  currently falling back). Fixing the token and adding the file to `FEATURE_CSS` is a tidy
  standalone change.
- **`list_calendar_files()` shows every CSV**, including bell schedules, so the Academic
  calendars panel already renders useless buttons like "Load Bell Schedule Bobcat Hour" on a
  fresh workspace. Loading an example adds more. Cheap fix: skip files whose header identifies
  them as a bell schedule or a day calendar. Pre-existing and adjacent.

# Execution result

Traffic light: **GREEN**

Commits, in slice order:

- `d611af8` Declutter app header navigation
- `3403b79` Share rail navigation behavior
- `d2d5f92` Support weekday-specific teacher schedule blocks
- `8e9399a` Ship class schedule example sets
- `dd78219` Add class schedule setup routes
- `f3b089e` Add class schedule Settings panels
- `ed3bc78` Add SmartDeck section navigation

Changed surfaces: header navigation and menu behavior; shared rail navigation; weekday-aware
schedule resolution and validation; three example schedule sets; schedule setup/readiness
routes; Settings panels and editor; SmartDeck rail and setup notice; routed tests and module
documentation.

Verification:

- Starting baseline: `py -m pytest api/tests` passed 1678 tests.
- Focused gates passed: 99 schedule/resolver tests, 96 example tests, 55 route-contract tests,
  31 Settings tests, and 23 SmartDeck presentation tests.
- Final integration gate: `py -m pytest api/tests` passed 1748 tests in 63.30 seconds.
- `git diff --check` passed.
- In-app Browser checks at 1280px confirmed a one-line header, More open/Escape/outside-close
  behavior, route highlights, four SmartDeck rail links, working section anchors, Settings rail
  targets, the unconfigured notice link, and no browser warnings or errors.

Deviations: the user-directed assertion update changed the shared-rail token assertion and the
Settings rail test now follows the moved shared script. The live configured workspace was not
modified for example load/save/remove verification; those write, preservation, overlap, and
archive paths passed their focused route tests. The in-app Browser cannot fire
`IntersectionObserver`, so scroll-driven active highlighting was verified structurally and the
anchor clicks were exercised directly.

Unresolved decisions: none.
