# Classroomscreen Panel library initiative

**Status:** Batch D accepted GREEN and retired; the Panels initiative is complete

**Last senior review:** 2026-08-01

**Active prerequisite:** the canonical Calendar correction closed GREEN and was retired in commit
`a91182e`. Batches A, B, and C are accepted GREEN. Batch D passed its focused gate (211 passed),
full API suite (1872 passed), v3/MCP closure searches, local browser route/theme checks, and
`git diff --check`; its integration commit is `0dfc9bc`, the current senior checkout.
There is no active direct brief.

**Next batch pointer:** none. Batch D closes the four-row Panels initiative. Do not promote
another handoff from this document without a new senior product decision; any future work
needs a new initiative or an explicitly authored next batch. Outstanding decisions: none
carried from Batch D.

**Batch A timing decision:** the teacher confirmed the 2026-27 Bobcat Hour split as
`bobcat_a` 12:11–12:41 and `bobcat_b` 12:43–13:13. This is the locked seed timing for the
promoted Batch A handoff.

This document is persistent senior context. It does not occupy the single active-handoff slot,
and an executor must not implement directly from it. A senior promotes one batch at a time into
the single direct brief in `docs/handoffs/`, locks its baseline and exact references against the
then-current repository, and gives it to one executor.

## 1. Teacher outcome

Build a useful library of Canvas Expert Panels that the teacher can paste into
Classroomscreen's existing Embed widget. Duplicating a utility that Classroomscreen already has
is acceptable; Canvas Expert is not using novelty as a scope test. The differentiator is that
these Panels can combine the local school calendar, class schedule, Canvas course content, and
classroom-safe roster facts.

The requested library is:

1. What's due.
2. Select random student - independent random selection, repeats allowed.
3. Select random student - no repeats until the teacher resets the completed cycle.
4. Upcoming events.
5. Missing work.
6. Sports results.
7. Birthdays and celebrations.
8. Learning objective, authored by an AI assistant after inspecting Canvas modules,
   assignments, and pages.
9. Bobcat Hour schedule - the day's tutorials and clubs, split into A and B blocks and shown
   only on Bobcat Hour days.

`whats-due` is already shipped. It is the baseline Panel and must remain green; do not rebuild
it or create a second implementation.

## 2. Surface and boundary decisions

These are **Panels**, not new SmartDeck Widget kinds. Each kind remains one allowlisted,
chrome-free `/panels/{kind}` URL rendered inside Classroomscreen, a browser tab, OBS, or another
iframe host. No Classroomscreen API, account connection, automation, or vendor-specific runtime
code is required.

All Panel requests remain local and disk-only:

- no Panel page or data request may call Canvas, an AI provider, a school website, or a sports
  service;
- Canvas-derived data comes only from Course Catalog or typed CanvasMirror reads;
- school-day and public-event data comes only from the canonical Calendar service;
- the app stays on `127.0.0.1:8765`, saved URLs remain readable and durable, and unknown kinds
  still return 404;
- course-bound Panels follow the live Calendar/Teacher Schedule resolver and support only the
  stable `?block=` override. Do not restore raw `?course=` pinning;
- calendar-wide Panels do not invent a course dependency;
- every projected outcome is a calm named state; a broken producer must never become a 500 on
  a classroom wall.

Keep `PANEL_CATALOG` as the one allowlist. Extract the growing pure payload/join logic from
`api/webui/routes/panels.py` into one `api/webui/panel_data.py` owner when the first promoted
batch adds multiple kinds. The route module keeps URL parsing, course/date resolution, catalog
dispatch, and response construction. Do not add a second Panel registry or a general plugin
system.

Every new kind uses the existing Panel CSS/JS kit, theme variables, responsive degradation, and
console builder. A theme changes appearance only, never content or row count. The console is a
builder: each kind gets working options, preview, full URL, and embed copy; it does not become a
marketing page.

## 3. Panel catalog contract

The intended public slugs and sources are locked:

| Slug | Title | Scope | Local producer | Interaction |
|---|---|---|---|---|
| `whats-due` | What's due | Current course | Course Catalog assignments | Rotating list; shipped baseline |
| `random-student` | Random student | Current course | CanvasMirror private roster | Pick again; independent draws |
| `random-student-no-repeats` | Random student - no repeats | Current course | CanvasMirror private roster | Pick next; reset cycle |
| `upcoming-events` | Upcoming events | Calendar-wide | Canonical Calendar projection | Rotating list |
| `missing-work` | Missing work | Current course | CanvasMirror roster, assignments, submissions | Rotating list |
| `sports-results` | Sports results | Calendar-wide | Canonical Calendar `game` events with results | Rotating list |
| `birthdays-celebrations` | Birthdays & celebrations | Current course | CanvasMirror roster plus Roster classroom profiles | Rotating list |
| `learning-objective` | Learning objective | Current course | Reviewed local Learning Objectives document | Static text |
| `bobcat-hour` | Bobcat Hour | Calendar-wide | Canonical Calendar plus Bobcat Hour Bell Schedule | A/B lists; current block highlight |

The catalog may gain only the small metadata immediately consumed by the builder and dispatcher,
such as `scope`, supported options, and template name. It does not become a free-form rendering
schema.

Default windows:

- `upcoming-events`: today plus 14 calendar days; clamp hand-edited URLs to 60 days;
- `sports-results`: today and the previous 14 calendar days; clamp to 90 days;
- `birthdays-celebrations`: today plus 7 calendar days;
- `bobcat-hour`: today only;
- preserve the existing What's due window and ordering contract.

## 4. Bobcat Hour and Calendar model

### 4.1 Bell Schedule

The repository already ships `api/default_docs/Calendars/Bell Schedule - Bobcat Hour.csv`.
Today it models Bobcat Hour as one `bobcat` meeting from `12:11` to `13:13`. Replace that single
meeting with two stable periods:

```csv
bobcat_a,12:11,12:41
bobcat_b,12:43,13:13
```

Keep periods 1-7 and their existing times unchanged unless the then-current official Bell
Schedule says otherwise. This is a seed-file edit consumed by the ordinary data-driven loader;
do not hardcode Berry Miller, Pearland ISD, or Bobcat Hour branches in Python.

The A/B timing is supported by Berry Miller's published 2025-26 Tutorial & Club Schedule. The
current 2026-27 Bell Schedule confirms the outer `12:11-1:13` Bobcat Hour window but does not
publish the internal split. Before promotion, the senior must confirm with the user or a current
official source that `12:11-12:41` and `12:43-1:13` still apply. A Luna executor does not choose
new times.

Official public references:

- `https://berry-miller.pearlandisd.org/bobcat-hour`
- `https://resources.finalsite.net/images/v1767999956/pearlandisdorg/pearlandisdorg/oua6u8kx5p6pchry2kor/TutorialandClubSchedule.pdf`
- `https://resources.finalsite.net/images/v1754520153/pearlandisdorg/noazezurlx2hdw3gjlsf/BellSchedules.pdf`

### 4.2 Which dates are Bobcat Hour days

The canonical `School Calendar.json` remains the only date authority. A date is a Bobcat Hour
day only when it is `instructional` and names `bell_schedule_bobcat_hour`. Neither weekdays nor
the presence of tutorial/club events may infer that day type.

The `bobcat-hour` Panel returns `not_bobcat_hour_day` on any otherwise valid instructional date
using another Bell Schedule. It preserves the Calendar's existing unconfigured, invalid,
outside-coverage, no-school, no-regular-classes, and unknown-schedule states. It never displays
an old schedule merely because today has no answer.

### 4.3 Tutorials and clubs

Do not create `Bobcat Hour Schedule.json`. Tutorials and clubs are public school events already
owned by the canonical Calendar. Represent each activity with the existing `tutorial` or `club`
kind, weekday recurrence plus effective date bounds, A/B `from` and `to` times, and a short
`detail` such as room/location. The Panel selects only today's matching events whose time fits
exactly in `bobcat_a` or `bobcat_b`, groups them by A/B and tutorial/club, and sorts each group by
label then detail.

Add the missing teacher-facing Calendar UI and MCP preview/apply path for creating, editing, and
removing public events. It must mutate the `events` array through the Calendar's existing whole-
document validation, revision, digest, and atomic-write authority. It may not add a second event
file, direct-write endpoint, or apply-without-preview path. The editor is generic for every
accepted event kind; Bobcat Hour is a real use of the generic event model, not a district branch.

Do not copy the published 2025-26 tutorial/club roster into repository defaults. Staff names and
room assignments change and some names are teacher contact information. The teacher supplies the
current schedule through Calendar UI or a reviewed MCP change.

### 4.4 Sports results

Calendar remains the source of truth for public games. Extend a `game` event with one optional,
plain-text `result` field, maximum 160 characters. It is valid only for `kind: "game"`; unknown
or cross-kind use is rejected. A short string is intentional because sports results can be a
score, placement, aggregate meet result, or A/B-team summary. Do not force every sport into a
home-score/away-score schema.

The Sports results Panel displays only game events with a nonempty result whose effective date
falls in the requested lookback, newest first. It shows date, label, and result. Manual entry or
a teacher-directed MCP Calendar edit is v1. Automatic scraping, school-site ingestion, vendor
credentials, and background web polling are non-goals.

### 4.5 Upcoming events

Upcoming events are the classroom-safe union of:

- canonical public events touching the window; and
- structural academic dates synthesized from Calendar day kinds and grading periods:
  no-school dates, no-regular-classes dates (emitted as the already-classified `day_type`
  display kind), grading-period ends, and report-card dates.

Tag from the source kind, filter through `api.audience.classroom_only()`, strip the internal
audience field, sort chronologically with deterministic ties, and never accept an audience value
claimed by stored input. A game may appear here before it is played and later in Sports results
after a result is recorded; that is two views over one Calendar event, not duplicate data.
Canvas assignment dates remain in What's due. Canvas course-calendar events are outside this v1
Panel because they have no accepted disk-only producer in the current architecture.

## 5. Roster-backed Panels

### 5.1 Privacy and freshness

Names, birthdays, celebrations, submissions, and missing status are private local student data
even though the accepted classroom-facing contract allows the selected facts on a wall. They
never enter source, fixtures with real values, generic logs, support output, MCP results, or an
external AI request.

All roster-backed payloads use `api.mirror.read_service` with `LOCAL_DISPLAY`. They never use
`mirror_reads.*_or_live` and never fall back to Canvas. Require the needed scopes to be exactly
current before showing student facts:

- random selectors: `private.roster`;
- missing work: `private.roster`, `private.assignments`, and `private.submissions`;
- birthdays/celebrations: `private.roster` plus local Roster classroom profiles.

Unavailable, stale, incomplete, or internally inconsistent data returns
`mirror_needs_attention`, with no student rows and a short instruction to use **Sync now** in
Canvas Expert. This deliberately fails closed: an obsolete roster can select a withdrawn
student, and stale missing status can embarrass a student in front of classmates.

Every emitted fact is stamped and filtered in code:

- selector entries: `student_name`;
- missing entries: `missing_work`;
- birthday entries: `birthday`;
- teacher-entered positive items: `achievement`.

The final Panel JSON omits Canvas user IDs, SIS IDs, section IDs/names, submission IDs, scores,
accommodations, monitoring state, notes, and the internal audience tag.

### 5.2 Classroom display names

Derive display names only from the current mirrored roster. Default to first name plus last
initial, matching `docs/contracts/classroom-facing-data-contract.md`. If that form collides
within the resolved course, expand only the colliding students to their full Canvas display
name. The resulting strings must be nonempty and unique before they reach a selector. Do not
send an identifier to the browser to solve collisions.

### 5.3 Random student semantics

`random-student` performs an independent uniform draw on every teacher click. Repeats are
allowed, including consecutive repeats. It does not pretend to track participation.

`random-student-no-repeats` is a shuffle bag:

- each current display name appears once per cycle;
- state is stored only in browser `localStorage` at the localhost origin;
- the state contains display names, never Canvas IDs;
- the storage key uses the resolved Teacher Schedule block, with the URL block and then
  `follow` as fallbacks, so separate follow-mode blocks have separate cycles;
- a roster refresh keeps only names still present in the current display-name set;
- after the final name, show **Everyone has been selected** and require an explicit **Reset**;
  do not silently start another cycle;
- ordinary reloads and Classroomscreen iframe remounts preserve the cycle.

Randomness may use the browser crypto API. Tests inject/stub the choice source; they must not
make probabilistic assertions.

### 5.4 Missing work semantics

Join current mirrored assignments and submissions by stable IDs, then roster by user ID entirely
on the server. A row is missing only when Canvas's normalized submission has `missing: true` and
`excused` is not true, and the joined assignment still exists and is published. Do not infer
missing from a blank score, `workflow_state`, lateness, or the current clock.

Return one classroom-safe row per student with display name, missing count, and assignment titles
ordered by due date then title. Sort students by missing count descending then display name. Wide
Panels may show titles; narrow tiers drop titles before shrinking the name/count below the
legibility floor. Zero-count students are omitted; an empty roster remains **No students in the
current roster**, while an otherwise complete roster with no rows says **No missing work** and
makes no integrity judgment.

### 5.5 Birthdays and celebrations source

Extend the existing course-scoped `roster_student_settings` record with one validated
`classroom_profile` object:

```json
{
  "birthday": "MM-DD",
  "celebrations": [
    {
      "id": "teacher-stable-id",
      "label": "Published in the school literary magazine",
      "start": "2026-09-08",
      "end": "2026-09-12"
    }
  ]
}
```

`birthday` is empty or a real month/day; never store birth year or age. A celebration is plain
text with a stable ID and an ordered inclusive date span. Reject unknown keys, HTML, invalid
dates, duplicate IDs, and overlong labels. Use the existing Roster one-student update path and
local Roster UI; do not add a second student-profile store.

The Panel repeats birthdays annually, shows the friendly date, and combines them with active or
upcoming celebrations in the configured window. It never displays a birthday year or computes
an age. Default display remains first name plus last initial, with the collision rule above.

**Section 5.5 amendment (Batch 3):** the roster profile now has a narrow, pseudonym-first MCP
mutation surface for teacher-directed local settings. This reverses the original prohibition on
an MCP mutation surface, while preserving the classroom-facing privacy rules above. MCP exposes
additive nickname writes only; it cannot read or replace the stored nickname list, and all writes
reuse the existing Roster update path with preview/apply or digest-protected clear semantics.

## 6. Learning objective

### 6.1 Authorship model

The API does not contain an autonomous objective-writing model and the Panel GET never invokes
AI. An MCP-connected assistant is the AI author:

1. read current local course modules, assignments, and published pages;
2. propose one concise objective grounded in those sources;
3. show the teacher a preview naming the source titles and effective dates;
4. apply only after the teacher confirms;
5. the Panel later renders the reviewed local record from disk.

Course content is student-free, but sending it to an assistant is still a teacher-directed
external transmission. Never include roster, submissions, grades, comments, or student names in
this workflow.

### 6.2 Course Catalog page scope

The current Course Catalog has assignments and module/item titles but no page bodies. The same
promoted batch that adds the Learning objective Panel must add published Canvas pages as an
immediate consumer-driven scope; do not land an unused pages framework first.

Use Canvas's paginated `GET /api/v1/courses/{course_id}/pages` with `include[]=body`. Persist only
an allowlisted, student-free projection: stable page ID, normalized title, normalized plain-text
body, `published`, `front_page`, and `updated_at`. Raw HTML, Canvas URLs/slugs, editor identity,
editing roles, lock explanations, block-editor JSON, and arbitrary Canvas fields remain
forbidden. A page whose body cannot be safely normalized makes the page scope incomplete; raw
content is never retained as fallback.

This is a real schema change. Promote it as **Course Catalog v3**, using `catalog.v3.json` and
`catalog.v3.previous.json`. Per the pre-launch clean-break rule, do not migrate, dual-read, or
preserve v2 compatibility. Existing catalogs are disposable caches and are rebuilt by refresh.
Update every current Catalog reader/test/contract in the same batch; do not leave v2 and v3 as
parallel authorities.

Add a disk-only MCP `get_course_pages` read tool with bounded preview text by default and an
explicit full-text option. Keep `get_modules(include_items=true)` and
`get_course_assignments(full_descriptions=true)` as the other evidence reads. The MCP tool never
performs its own Canvas fallback.

### 6.3 Reviewed Learning Objectives document

Create one canonical local document at:

```text
<workspace>/Library/Panels/Learning Objectives.json
```

It is a closed, versioned, revisioned document keyed by Current Canvas course ID. Each entry has
exactly:

- `objective`: one plain-text sentence, 1-240 characters;
- inclusive `effective_start` and `effective_end` ISO dates;
- `source_refs`: one or more `{kind, id, title}` entries, where kind is `module`, `assignment`,
  or `page`;
- `source_digest` over the exact normalized source records, plus `catalog_updated_at` captured
  from the evidence read;
- `authored_at`.

The stored record has no AI rationale, prompt, chat transcript, HTML, student data, URL, or model
vendor metadata. Validation resolves every source ref against the then-current local v3 Catalog.

Expose paired MCP preview/apply tools. Preview normalizes and validates the objective, effective
dates, Current-course gate, source references, and current Catalog generation, computes the
exact-source digest, then returns a deterministic preview digest and the human-readable source
titles. Apply requires the exact preview, digest, expected document revision, and unchanged
Catalog generation; it atomically writes revision + 1. There is no direct save tool and no apply
from text the teacher has not previewed.

The Panel resolves the current course, selects the single objective covering today, and shows
the objective plus a compact course/block label. Overlapping effective ranges for one course are
invalid. Missing, expired, changed-source, or broken records return a named state with no
fabricated objective. An unrelated Catalog refresh does not invalidate the objective: the Panel
re-resolves only `source_refs` and displays **Objective needs review** only when a referenced
record is missing or its normalized content no longer matches `source_digest`. It may not
silently regenerate.

Add `learning_objective` to the classroom-facing data contract and `api/audience.py` in the same
batch. The code classification, not MCP prompt text, authorizes it for projection.

## 7. Promotion order and batch boundaries

Each row becomes one future direct brief only after the previous row is accepted GREEN. A senior
may combine adjacent rows only after showing that the resulting vertical batch still fits the
repository's half-day-to-two-day norm and has one coherent verification gate.

### Batch A - Calendar public-event authoring and Bobcat Hour model

Deliver the A/B Bell Schedule seed, generic revision-safe public-event UI/MCP preview/apply, the
optional game `result` contract, and the Calendar tests/docs needed to make those facts writable.
No Panel kind is added yet; the immediate consumer is the already-shipped Calendar surface and
MCP Calendar workflow.

Likely owners: canonical Calendar contract; `api/webui/school_calendar.py`;
`api/webui/routes/calendar.py`; Calendar template/JS; the Bobcat Hour Bell Schedule seed; MCP
Calendar tools/current schema; Calendar/schedule/MCP/presentation tests.

Promotion gate must include the then-current Calendar focused gate, event validation and stale-
preview cases, rendered `/calendar` desktop/mobile checks, full API suite because a public
Calendar/MCP contract changes, `git diff --check`, and proof that no real workspace file was
written.

### Batch B - Public Calendar Panels

Add `upcoming-events`, `sports-results`, and `bobcat-hour`; extract `panel_data.py`; extend the
console builder; preserve What's due. Bobcat Hour must be observed on a Bobcat day and a non-
Bobcat instructional day.

Likely owners: `api/webui/routes/panels.py`; new `api/webui/panel_data.py`; Panel templates;
Panel console and page CSS/JS; `api/audience.py` only if a source kind is missing; Panel tests;
route card.

Named gate: `py -m pytest api/tests/test_panels.py api/tests/test_school_calendar.py
api/tests/test_calendar_events.py api/tests/test_presentation_contracts.py
api/tests/test_route_contract.py -q`, followed by the required responsive sweep for every new
kind/theme/state and the rendered `/panels` console. The promoting senior updates filenames if
the Calendar correction lands different owners.

### Batch C - Roster-backed Panels

Add the two random selectors, Missing work, Roster classroom-profile editing, and Birthdays &
celebrations as one privacy-coherent vertical batch. Do not split the classroom-name/privacy
projection across separate competing helpers.

Likely owners: `api/webui/panel_data.py`; Panel routes/templates/console; `api/webui/config/roster.py`;
Roster route/update/template/JS owners named by `docs/reference/roster-module-map.md`;
`api/audience.py`; focused Panel/Roster/Mirror tests; both route cards/contracts.

Named gate: focused Panel, Roster, Mirror read-service, presentation, and route-contract tests;
then `py -m pytest api/tests -q` because student-data projection is high risk. Render `/roster`,
`/panels`, and every student-backed Panel in ready/empty/stale/collision/narrow states. Inspect
browser storage for the no-repeat Panel and confirm it contains no Canvas IDs or non-display
student facts.

### Batch D - Learning objective authoring and Panel

Deliver Course Catalog v3 pages, the disk-only MCP pages read, reviewed Learning Objectives
preview/apply storage, the `learning-objective` Panel, and all clean-break/documentation closure
in one batch. Do not land page acquisition without the objective consumer.

Likely owners: Course Catalog contract and implementation/routes/tests; CanvasMirror typed
catalog read service; MCP server/tools/current schema/docs; new Learning Objectives store/service;
Panel data/route/template/console; classroom-facing data contract and `api/audience.py`.

Named gate: focused Course Catalog, MCP, Panel, audience, presentation, and route-contract tests;
then `py -m pytest api/tests -q` because the batch changes shared catalog and MCP contracts.
Render `/panels` and the objective Panel in ready/missing/expired/changed-source/narrow states.
Closure searches must prove no current `catalog.v2` authority remains and no Panel/AI path can
receive student data.

## 8. Initiative acceptance criteria

The initiative is complete only when all of the following hold:

1. The Panel console offers exactly the nine requested kinds, with What's due still using its
   accepted behavior and every saved URL remaining localhost/readable.
2. No Panel request performs network IO. Tests fail if Canvas, AI, school-site, or sports-service
   transport is reachable from a Panel payload.
3. Calendar identifies Bobcat Hour dates solely through `schedule_id`, and the Bobcat Panel never
   appears on a different schedule or invalid day.
4. The Bobcat Hour seed exposes A and B as distinct periods; current tutorial/club entries are
   teacher-maintained canonical events, not a copied stale staff schedule.
5. Upcoming events and Sports results are two filtered views over one canonical Calendar event
   collection. A game result is previewed/revision-safe and no scraper is required.
6. Random selection is uniform with repeats in one kind and a persistent, explicit-reset shuffle
   bag in the other. Neither exposes or stores Canvas student IDs in the browser.
7. Student-backed Panels refuse stale/incomplete Mirror state, output only code-classified
   classroom-safe facts, and never log or fixture real student data.
8. Missing work follows Canvas's explicit `missing` and `excused` flags and never infers guilt,
   lateness, or integrity from a blank/low score.
9. Birthday storage contains no year/age; celebrations are date-bounded positive facts edited
   through Roster's existing mutation path.
10. Learning objectives are grounded in current local module/assignment/page evidence, previewed
    for teacher review, revision-safe, and generated nowhere in the display request path.
11. Course Catalog has one current v3 authority with normalized page text and no v2 dual-read,
    raw HTML, URLs, editor identity, or student data.
12. Every kind passes its focused behavior tests, all affected rendered routes, the full
    responsive shape/theme/state sweep, contrast/legibility requirements, and zero new browser
    console errors or document overflow.

## 9. Explicit non-goals

- No timer, stopwatch, groups, seating, poll, noise meter, or other unrequested Panel in this
  initiative.
- No SmartDeck feed binding or new SmartDeck Widget kind.
- No Classroomscreen API integration, account automation, or cloud hosting.
- No live Canvas fallback from any Panel.
- No AI call during refresh/render and no unattended AI overwrite of an objective.
- No automatic sports scraping, vendor API, credentials, browser automation, or scheduled web
  ingestion.
- No import of the published 2025-26 Bobcat Hour staff/activity matrix as a default.
- No student IDs, scores, sections, accommodations, monitoring state, behavior, notes, birthday
  years, or ages on a Panel.
- No migration/compatibility shim for Bell Schedule period IDs, Course Catalog v2, or new local
  profile schemas. This is pre-launch; take the clean break and update current fixtures. Existing
  shipped Panel slugs remain durable public URLs.
- No arbitrary AI-authored HTML/CSS/JavaScript. Every Panel remains a built-in template.

## 10. Stop and senior-review conditions

Stop before promotion or return RED during execution if:

- the active Calendar correction is not GREEN/retired or changed a named seam materially;
- `12:11-12:41` and `12:43-1:13` cannot be confirmed for the intended school year;
- Bobcat Hour activities cannot be represented by canonical public events without a second
  schedule artifact;
- a requested Panel would require live network IO to render;
- a student-backed payload cannot remove teacher-only fields before reaching the template;
- a stale Mirror would have to be treated as current to make a Panel useful;
- page bodies cannot be normalized without retaining raw HTML/block-editor data;
- the objective can be applied without teacher preview, or needs student data to be useful;
- a current public contract outside Calendar, Course Catalog, MCP, Roster, Panels, or the
  classroom-facing classification must expand;
- unrelated user-owned work overlaps a promoted batch.

## 11. Senior promotion checklist

Before converting one batch into the direct handoff:

1. Fetch and compare `dev` with `origin/dev` and `main` with `origin/main`; record the exact
   baseline and preserve user-owned changes.
2. Read the final result of the Calendar correction and current route cards; remove obsolete
   assumptions from the promoted brief rather than asking Luna to reconcile them.
3. For Batch A, resolve the one outstanding timing confirmation. The other product decisions in
   this initiative are locked unless the user changes direction.
4. Name exact files/symbols and exact numbered sections from this initiative; do not route the
   executor through the whole repository or archived handoffs.
5. Pre-author slice-specific acceptance criteria, the named gate, rendered states, stop
   conditions, and the required compact Execution result block.
6. Keep only that one promoted brief in `docs/handoffs/` and use one executor. GREEN closure
   retires it before the next row is promoted.
