# Canonical School Calendar contract

**Status:** accepted target design · **Owner:** Calendar domain

Canvas Expert has one school-calendar authority. It answers, for any covered date, whether
regular classes meet, which named bell schedule applies, which grading period contains the
date, and which public school events belong on teacher-facing surfaces. Every feature and
every AI tool reads and writes that same authority.

This is a teacher-maintained operational record, not a passive import. A principal can email
a change, the teacher can paste the relevant public schedule facts into an MCP-connected
assistant, and the assistant can preview and apply the same structured change the Calendar UI
would make.

## 1. Domain boundary

The Calendar domain owns four related artifacts from one top-level `/calendar` surface:

1. the canonical date record described below;
2. reusable Bell Schedule definitions (period IDs and clock times);
3. the Teacher Schedule (stable block names mapped to period IDs and Current Canvas courses);
4. public school events such as assemblies, performances, tutorials, and spirit weeks.

Only the first item decides what kind of day a date is and which Bell Schedule it uses. Bell
Schedules and the Teacher Schedule remain separately validated, reusable definitions because
copying either into every date would create a second truth. The Calendar page is their common
editor and readiness surface.

Canvas assignment due dates, Canvas course-calendar events, student schedules, grades, and
roster facts are outside this domain. Pasted email text is input to the assistant, never stored
in the calendar. Persist only the short public label and structured change the teacher intends.

## 2. Canonical storage

The one active document is:

```text
<workspace>/Library/Calendars/School Calendar.json
```

It is a closed, versioned JSON document:

```json
{
  "version": "1.0-json",
  "type": "SCHOOL_CALENDAR",
  "revision": 12,
  "school_year": "2026-27",
  "coverage": {"start": "2026-07-01", "end": "2027-06-30"},
  "days": {
    "2026-08-19": {
      "kind": "instructional",
      "schedule_id": "bell_schedule_bobcat_hour",
      "label": "First day"
    },
    "2026-09-07": {
      "kind": "no_school",
      "schedule_id": null,
      "label": "Labor Day"
    },
    "2026-10-16": {
      "kind": "no_regular_classes",
      "schedule_id": null,
      "label": "Field day"
    }
  },
  "grading_periods": [
    {
      "code": "T1",
      "name": "Term 1",
      "start": "2026-08-19",
      "end": "2026-10-09",
      "report_issue_date": "2026-10-16"
    }
  ],
  "events": [
    {
      "id": "fall-concert",
      "kind": "performance",
      "label": "Fall concert",
      "shape": "date",
      "date": "2026-10-22",
      "detail": "6:30 PM",
      "from": "6:30 PM",
      "to": "8:00 PM",
      "result": ""
    }
  ]
}
```

Bell Schedule definitions are teacher-authored CSV files in the same `Calendars` folder,
with the header `period_id,start,end,label`. `start` and `end` are local wall-clock values
written as `h:mm AM` or `h:mm PM` (for example, `8:35 AM` and `3:55 PM`). Public event
`from` and `to` values use the same format. Dates remain exact ISO dates; no timezone or
date rollover is implied by a clock value.

That 12-hour spelling is the authored and displayed form, and reads tolerate one alternative:
a 24-hour value whose hour is two digits, such as `08:35` or `13:13`. It is parsed and rendered
in the 12-hour form, so a file a teacher already had is not refused over spelling and never
displays in two clock conventions at once. Tolerance stops where the value stops being
unambiguous: a single-digit hour with no meridiem, such as `1:15`, is invalid rather than
resolved, because reading it as 01:15 would move an afternoon class to the middle of the night
without ever looking wrong. Invalid clock values are reported against their period and never
guessed.

`revision` starts at 1 on the first successful creation and increases by one for every
successful write after that, including complete-school-year replacement. A replacement never
resets revision numbering. Writes validate the whole next document and replace the file
atomically. Unknown keys are rejected at every level. API and MCP responses never expose an
absolute path.

There is no live `config.calendars` copy, `Day Calendar*.csv`, `Day Overrides.csv`, or
`school-events.json`. Academic CSVs and other public files may remain as import/seed inputs,
but they are not read at runtime after import. Pre-launch means this is a clean replacement:
there is no dual read, migration, backup-renaming protocol, or compatibility API.
Retired Calendar files are removed from repository seeds. Existing copies already present in a
teacher's workspace are ignored and left untouched; Canvas Expert does not silently delete or
archive user files.

## 3. Date model and validation

`coverage.start` and `coverage.end` are exact ISO dates and `start <= end`. `days` contains
exactly one entry for every calendar date in that inclusive range, including weekends. A
missing day is invalid rather than an implied weekend or instructional day. Keys outside the
range are invalid.

Each day has one of three kinds:

| Kind | Meaning | `schedule_id` | Label |
|---|---|---|---|
| `instructional` | Regular classes meet | required and must name a loaded Bell Schedule | optional |
| `no_regular_classes` | Students may be present, but ordinary class blocks do not meet | must be null | required |
| `no_school` | Students do not attend | must be null | required except generated weekends may use `Weekend` |

Both non-instructional kinds are excluded from class-meeting and instructional-day arithmetic.
They remain distinct in UI and classroom messages: a field day is not called a holiday.

Grading-period codes are unique. Period bounds are exact ISO dates, ordered, and inside
coverage; `report_issue_date` is optional. Overlapping grading periods are invalid because a
consumer must never choose one by list order.

Public event kinds remain the closed classroom-safe set: `game`, `dance`, `assembly`,
`performance`, `spirit`, `tutorial`, `club`, `library`, and `other`. Event IDs are unique and
stable. An event has exactly one shape: one `date`, an inclusive `start`/`end` span, or a
`weekdays` recurrence with an optional effective range. Shared optional fields are `detail`,
`from`, and `to`. Only `game` events may carry an optional plain-text `result` of at most 160
characters; an empty result is allowed. Events can inform a display but never silently change
a day's kind or schedule. A pep-rally event and a pep-rally Bell Schedule are two explicit
facts.

## 4. Resolution and failure semantics

One service owns document parsing, validation, range projection, mutation, and schedule
resolution. Existing feature facades may call it, but no consumer parses the file or retains a
second calendar projection.

Date resolution has explicit states:

- `unconfigured`: no canonical document;
- `invalid_calendar`: the document cannot be parsed or validated;
- `outside_coverage`: the requested date is not covered;
- `no_school`;
- `no_regular_classes`;
- `unknown_schedule`: an instructional day names a missing/invalid Bell Schedule;
- `ready`: the date and its Bell Schedule are valid.

Teacher-Schedule validation and the ordinary `between_blocks`, `day_over`, and
`block_without_course` states remain downstream schedule outcomes. Missing, expired, or broken
calendar state never degrades to “weekends only,” “nothing scheduled,” or a guessed weekday
schedule. A feature that needs instructional-day math or a current class blocks elegantly and
links to `/calendar`.

A fixed teacher-block override is the one intentional bypass: a Panel URL may use
`?block=<stable-teacher-block-name>` to display that block regardless of the live date or clock.
It still resolves the block through the Teacher Schedule and still enforces the Current-course
boundary. Raw `?course=` pinning is replaced, not retained as a second override contract.

## 5. Editing operations

The UI and MCP call the same application service and validators. There are three operation
families:

- create/replace a complete school year from coverage, weekday defaults, optional imported
  academic-calendar facts, grading periods, and events;
- preview/apply a day change to either an explicit date list or an inclusive date range plus
  optional weekday subset;
- edit Bell Schedule, Teacher Schedule, grading-period, and public-event definitions.

Initial creation and complete-year replacement use an explicit preview/apply pair. The first
apply expects base revision 0 and writes revision 1. A replacement preview names the current and
proposed school year and coverage, summarizes day/grading-period/event changes and validation
conflicts, and records the current revision. Replacement apply requires that exact revision and
writes `revision + 1`; it never performs a one-click overwrite. The UI uses an inline staged
preview with an explicit Create or Replace action, not a generic browser confirmation dialog.

Range and weekday rules are authoring conveniences only. A change such as “use Friday Schedule
Monday through Friday for the next two weeks” materializes those ten exact dates. No recurring
schedule rule survives beside the day records, so runtime precedence is impossible to hide.
One-offs and changes used two or three times per year use the same operation with a smaller
selection.

Every date change is previewable. Preview returns the base revision, affected dates, before and
after values, conflicts, and validation problems. Apply requires that `expected_revision`; a
stale preview is refused. A no-op is successful without incrementing the revision. The UI shows
the preview before Apply. MCP exposes separate read, preview, and apply tools, and its authoring
contract instructs the assistant to summarize the preview before applying it.

Public events use the same preview/apply boundary. An event change is either an `upsert` of one
complete event by its stable `id`, or a `delete` by `event_id`. Its preview returns
`operation: "event_change"`, the base revision, normalized mutation, before/after event values,
conflicts, and a deterministic `preview_digest`. Apply requires the expected revision and exact
digest, re-derives the candidate `events` array from the normalized mutation, validates the
complete next document, and refuses altered before/after projections. Replacing an equivalent
event or deleting a missing event is a no-op and does not increment revision.

Apply never trusts client-supplied `before`, `after`, or affected-date projections as write
authority. It re-derives and validates the proposed result from the normalized mutation carried
by the preview and refuses a preview whose revision or canonical preview digest no longer
matches. This is a local correctness boundary against stale or accidentally altered preview
payloads, not an authentication mechanism.

## 6. Calendar surface

`/calendar` is a primary-nav working surface, not a Settings subsection. Its title and nav label
are both **Calendar**. Panels remains in primary navigation.

The first screenful contains:

- a compact readiness line for the active school year and coverage;
- today and the upcoming dates, with the resolved day kind and Bell Schedule visibly named;
- the date/range change control.

The same page owns the Teacher Schedule editor, Bell Schedule definitions, academic-calendar
import, grading periods, and public events. Settings removes its Class schedule and Academic
calendars editors and links to Calendar only where calendar readiness is relevant. Other
features link directly to the exact Calendar section that resolves their gate.

Every create/replace input the service accepts is reachable from the page, not only from MCP:
coverage, the default Bell Schedule, a per-weekday Bell Schedule override for Monday through
Friday, no-school dates, and grading periods. Grading periods are directly editable there and are
not import-only. Because replacement rewrites the whole document, the page prefills that editor
from the active calendar, so a teacher who replaces a year without opening it carries the existing
periods forward instead of dropping them.

Creating a year is an assistant-first task, and the Create/replace surface says so before it
shows a field. Districts publish academic calendars as PDFs and web pages, so the realistic first
step is handing that source to an assistant, not retyping it. The surface therefore leads with the
`Author an Academic Calendar` guide — downloadable and copyable, the same bytes MCP serves — and
names the two outcomes honestly: a connected assistant previews and writes the year through the
MCP operations and the teacher never opens the form; a chat-only assistant returns a CSV for the
paste box. The manual form remains complete and unhidden, because it is both the no-assistant path
and the surface where a CSV lands for review. Nothing about this ordering lets a preview skip
review or an apply skip its expected revision.

Academic import accepts both the canonical eight-column format and the advertised Simple
four-column format. The canonical header is
`school_year,row_type,code,name,start_date,end_date,report_issue_date,basis`; `basis` is an
optional source note and is not stored. The Simple header is
`Category,Name,Start Date,End Date`. Dates accept ISO `YYYY-MM-DD` or source-calendar
`MM/DD/YYYY` on import and are stored canonically as ISO dates. When an academic period has no
explicit code in either format, import derives a deterministic, unique, stable code from its name
before canonical validation; the teacher is not sent from a successful import into an impossible
Create/Replace operation.

Import expresses exactly two facts: no-school dates and grading periods. It cannot express an
instructional day, a Bell Schedule, `no_regular_classes`, or a public event. Its accepted
vocabulary is closed and named here so an authoring tool does not have to guess it. In the
canonical format `row_type` matches exactly one of `Holiday`, `No School for Students`,
`Holiday for Students/Teachers`, or `Academic Period`. In the Simple format `Category` matches by
substring on `holiday`, `day off`, `no school`, or `academic period`. Column names are compared
case-insensitively and with surrounding whitespace trimmed, in both formats.

Import never silently discards a row. A row whose type matches no accepted value, or whose dates
are missing or unreadable, is skipped and reported as a note naming its source row number and the
unusable value. Import remains successful when it produces nothing, because an empty result is a
defect in the source file rather than a fact about the school year; the notes are what tell the
teacher which. The Calendar page shows them with the parsed counts.

The page follows the WebUI presentation contract: controls before explanation, no sales copy,
no permanent onboarding tour. Readiness is calm but unmissable. It becomes
`needs_attention` when no valid calendar exists, today is outside coverage, an instructional
date references an unknown Bell Schedule, or fewer than 30 calendar days remain in coverage.
Warnings name the concrete repair and take the teacher to its control.

## 7. Panels contract carried by Calendar

Panels normally mirror the live local date and clock. The builder does not gain a fake day,
period, or clock preview. A fixed-block URL is a deliberate display override, not a preview
mode, and the builder offers it by teacher-block label.

If live resolution fails, the projected Panel shows the schedule/calendar problem rather than
quietly behaving like an empty day. Its action text is brief (for example, “Calendar needs
attention. Open Calendar in Canvas Expert.”). The builder provides the clickable repair link.

The What's due panel:

- reads only a Current course, including when reached through a teacher block;
- includes every due-today assignment through the end of the local calendar day, even after
  its due time;
- includes dates through `today + 7 calendar days` (today plus the next seven named dates);
- orders future/upcoming items first, then earlier-today items; ties are chronological and
  deterministic;
- describes an earlier-today item neutrally, never as missing or late;
- shows a Previous-course mapping as “This class is no longer current. Update its Canvas
  course in Calendar.”

Copy controls report success only when the Clipboard API or a selected-text fallback actually
copies. Failure leaves the full address visible and says to select and copy it.

## 8. Consumer rule

All current consumers must use the canonical service in the cutover batch: Panels and its
feeds, Panels, Late Work Sweep, Gradebook date arithmetic, Extensions, PowerGrader late work,
built-in and custom routines, operation-ledger sweep planning, and MCP schedule/calendar reads.
No consumer may import `config.calendars`, parse an academic/day-calendar file, or silently
invent weekend-only behavior.

Consumers also stop accepting their own `skip_weekends`, `holidays`, or “additional no-count
days” calendar overrides. An exceptional school day is edited once in Calendar, then every
instructional-day calculation sees it. Student-specific extra-time accommodations remain a
separate roster fact and are not calendar overrides.

Existence of a valid document is not sufficient for instructional-day arithmetic. Before a
consumer calculates lateness or adds school days, the Calendar service must confirm that every
date the calculation can inspect is inside coverage and that instructional dates in that range
resolve to loaded Bell Schedules. Unconfigured, invalid, out-of-coverage, and unknown-schedule
states fail closed with the shared Calendar repair target. A bounded range projection never
silently clips the caller's requested dates.

## 9. Privacy and locality

The calendar is public, student-free school configuration. It may contain public district
dates and bell times under the repository guardrail for seed files. It must not contain student
data, teacher contact details, email bodies, Canvas credentials, private workspace paths, or
Canvas transport data. Everything remains local to the token-holding app and MCP server.
