# Brief: named events from the school calendar

**Scoped 2026-07-29. Not started.** One vertical slice. Route card for the consuming surface is
`docs/reference/glass-module-map.md`; read it and the Glass foundation brief's locked decisions
before starting.

The school calendar already knows that November 26th is a no-school day. It also knows the day
is called Thanksgiving Break, and it knows when report cards go home. Both of those are thrown
away at parse time and again at storage time, so Glass cannot show a named event and the teacher
retypes "Picture day" into a day plan every week.

This slice makes the calendar hand Glass named events and real deadlines, without touching the
one thing nine call sites depend on.

---

## 1. Why the obvious approach is wrong

The instinct is to enrich `_parse_calendar_csv` so it keeps holiday names and
`report_issue_date`. That alone accomplishes nothing, and understanding why shapes the whole
slice.

Calendars are parsed **once, at import**, and the result is persisted into the synced
`settings.json` under `calendars`. `set_calendar` (`api/webui/config/calendars.py:12`) writes
only `{label, no_count_dates, grading_periods}`. So the loss happens twice: the parser drops
the fields, and the storage layer would drop them even if the parser kept them.

That means an enriched parser helps nobody who has already imported a calendar. It would need
either a re-import by every teacher or a migration that re-reads CSVs, plus a schema change to a
file that syncs across machines. All of that is risk in exchange for nothing a simpler design
cannot deliver.

## 2. Locked decisions

1. **`_parse_calendar_csv` and `no_count_dates` are not touched.** Nine call sites read
   `no_count_dates` for late-work math: `work_registry/providers/late_work.py`,
   `operation_ledger/adapters/sweep.py`, `webui/gradebook_service.py`,
   `webui/routes/gradebook_extensions.py`, `webui/routes/powergrader_late.py`,
   `webui/routes/routines_builtin.py` (twice), `webui/routes/pages.py`, and
   `api/schedule/calendar.py`. Their behaviour must be provably identical afterward. This is the
   blast radius and it is the reason this is a deliberate slice rather than a quick edit.
2. **No change to the `settings.json` schema, and no re-import.** A teacher who has already
   loaded their calendar gets named events with no action. If the design starts to require a
   stored-schema change, that is a stop (§8).
3. **Storage says which calendars the teacher chose; the CSV supplies the detail.** The stored
   keys are the record of teacher intent. A new reader maps each stored key back to its file in
   `Library/Calendars` and re-reads that file for the rich fields. This is the central design
   decision and §3 explains what it buys.
4. **This is a read. Nothing writes to the calendar, ever.** No editor, no import wizard, no
   normalisation pass that rewrites the teacher's CSV.
5. **The calendar is public information.** It is district configuration, not sensitive data. It
   stays out of the repo for the same reason a base URL does: another district could run this.
   Do not add privacy machinery, redaction, or pseudonymisation anywhere in this slice.
6. **Hand-written plan events stay.** The calendar cannot know about picture day or a field trip.
   Calendar events are an additional source, not a replacement.

## 3. Why "storage names the file, the file carries the detail"

Two simpler designs both fail, and the failures are instructive.

**Re-reading every CSV in the folder** fails on the sample problem. `list_calendar_files()`
globs every `*.csv`, so the shipped fictional `Summer_Session_Sample.csv` and the blank template
are both in that folder on every machine. A reader that globs would put fictional events on a
real projector. This is the same gap the Glass bell schedule had to solve with a `sample: true`
marker, and here there is no marker to lean on.

**Enriching storage** fails on §2 as described in §1.

Reading the CSVs *that storage already names* avoids both. The teacher explicitly chose to load
a calendar; that choice is durable in `settings.json`; the file it came from is still on disk. So:

- `config.get_calendars()` gives the chosen keys.
- `_file_key(filename)` (`api/webui/routes/calendar.py:28`) already maps a filename to its
  storage key, so the same function maps back by scanning the folder.
- Each matched file is re-read with a **new, separate** parser that returns rich events.
- `no_count_dates` continues to come from storage, untouched.

Degradation is graceful and must be tested. A calendar loaded via `POST /api/calendar/set` has
the key `custom` and no backing file, so it yields no named events. A teacher who deleted their
CSV after loading it yields no named events. In both cases `no_count_dates` still works from
storage and nothing crashes.

## 4. Scope

### 4.1 A new rich reader

New module, next to but not inside `calendar_csv.py`, because that file is load-bearing for late
work and should stay boring. Pure stdlib, no app imports, same posture as its neighbour.

It parses both formats the existing parser accepts. The canonical 7 column format is
`school_year,row_type,code,name,start_date,end_date,report_issue_date,basis`; the simple format
is `Category,Name,Start Date,End Date`, which also carries a name.

Three event kinds come out:

| Kind | Source | Carries |
|---|---|---|
| `no_school` | `row_type` in Holiday, No School for Students, Holiday for Students/Teachers; or Category matching "day off" / "no school" | name, start date, end date, subtype |
| `grading_period_end` | `Academic Period` rows | name, code, end date |
| `report_card` | `report_issue_date` on `Academic Period` rows | name, code, date |

Notes that matter:

- **Preserve the no-school subtype in the data even though the display collapses it.** All three
  mean "no school" to a student, so the wall reads the same. But a staff development day and
  Christmas are genuinely different facts and the vocabulary already distinguishes them. Keep it
  in the data; a later consumer will want it. Do not let it change `no_count_dates`.
- `report_issue_date` is currently parsed by nothing anywhere in the repo. It appears once, as a
  literal inside a fallback header string at `api/webui/routes/calendar.py:81`. This slice is the
  first thing to read it, so expect the real files to have it filled in inconsistently and treat
  a missing or unparseable value as absent rather than an error.
- A no-school span is one event, not one event per day. The existing parser expands ranges to
  individual dates because late-work math needs a set; an events pane needs "Spring Break, March
  9 to 13" as a single line.
- Grading period **starts** are deliberately not events. Nobody needs them on a wall.

### 4.2 A range query

One function answering "what named events fall in this window", mirroring the shape of
`get_combined_calendar_for_range` so it reads familiarly: takes a date range, merges across all
chosen calendars, returns events sorted by date. Overlapping spans from two loaded calendars
dedupe on name and date range.

Look-ahead default: **14 days**. It matches the resolver's existing `search_days` default and
keeps the pane useful without turning into a term overview. Put it in one named constant.

### 4.3 Glass consumes it

The events pane merges calendar events with the day plan's hand-written events, sorted by date,
deduped on date plus case-folded label so a teacher who also typed "Spring Break" does not see it
twice. Plan events win on a tie, since the teacher's wording is deliberate.

Two consequences to handle rather than discover:

- **Event text is no longer teacher-controlled.** The Glass foundation batch left events
  deliberately unbudgeted because they were hand-written and short. District names are neither:
  "Holiday for Students/Teachers - Staff Development Day" is plausible. Structural bounding
  (single ellipsised line, whole-item shedding) already exists and may be enough. Measure it at
  the real aspect before deciding whether a budget is now warranted, and report the numbers
  rather than adding a budget on instinct.
- **The pane's shed order is already load-bearing.** Events shed first and the Bobcat Hour pane
  never shrinks, and that priority took two fixes to get right (see the route card, "The shed
  priority took two fixes"). Adding automatic events increases how often shedding actually
  fires. Do not change the priority; do verify it still holds with a realistic calendar loaded.

## 5. Non-goals

Explicitly out, and not to be added opportunistically:

- Any change to `_parse_calendar_csv`, `no_count_dates`, or the `settings.json` calendar schema.
- A calendar editor, import wizard, or event authoring form.
- Event import from email or mail, which is where real single-day events like picture day
  actually arrive. Still hand-written after this slice.
- MCP tools. This is the natural follow-on, since an assistant that can read named events could
  compose a better day plan, but it is a separate slice and depends on this one landing first.
- Canvas assignment deadlines. Those come from the mirror, not the calendar, and are a different
  slice with different privacy handling.
- Early release, late start, exam windows, or any concept the CSV does not already carry.
- Surfacing Glass bell-schedule `date_overrides` (pep rally, homeroom first) as events. Adjacent,
  cheap, genuinely useful, and deliberately not bundled here so this slice stays about the
  calendar. Worth its own small follow-on.
- Retroactively re-importing or migrating anyone's stored calendar.

## 6. Preflight

Verify before writing. Stop if an assumption is false.

1. Confirm `_file_key` round-trips: for every CSV in a populated `Library/Calendars`, the key it
   produces matches the key `load-builtin` stored. If the mapping is not reliable, the whole
   design in §3 is void and this becomes a storage-schema conversation instead.
2. Confirm that `POST /api/calendar/set` really does store under the literal key `custom`, so the
   no-backing-file path is a known case rather than a surprise.
3. Confirm the shipped fictional sample and the blank template are both present in a freshly
   seeded workspace, since they are the reason globbing is unsafe.
4. Read the Glass events pane and its shed logic before changing what feeds it.

## 7. Acceptance criteria

1. **A golden test pins `_parse_calendar_csv`.** Its output is asserted byte-identical for the
   shipped template, the shipped sample, both header formats, and a few malformed rows. The
   simplest way to pass this is not to touch the file, which is the intent.
2. The full suite is green with no change to any existing assertion about `no_count_dates` or
   late-work behaviour.
3. The rich reader returns correct named events for both header formats, including a multi-day
   span as one event and a report card date from `report_issue_date`.
4. A missing, empty, or unparseable `report_issue_date` yields no `report_card` event and no
   error.
5. **A CSV sitting in the folder but not loaded into storage produces no events.** This is the
   test that proves the fictional sample cannot reach a real projector, and it is the most
   important one in the slice.
6. A stored calendar whose file has been deleted, and a `custom` calendar with no file at all,
   both yield no named events, no crash, and unchanged `no_count_dates`.
7. Glass renders merged calendar and plan events in date order, deduped, within the look-ahead
   window, against a frozen clock via `?at=`.
8. Measured at 1280x800 and 1920x1200 with a realistic calendar loaded and long district event
   names: no element overflows, the events pane still sheds before the Bobcat Hour pane, and the
   tray height is unchanged. Extend the existing Playwright geometry tests rather than writing a
   parallel mechanism.
9. `git grep` finds no real district calendar dates, holiday names, or school names in the repo.
   The fictional sample may gain named holidays and a report card date to exercise the new
   reader, and stays fictional.
10. The route card is updated: the new module in the table, the event taxonomy, and the §3
    design decision recorded so nobody later "simplifies" it into globbing the folder.

## 8. Verification gate

Full `py -m pytest api/tests`. Current baseline is 1747 passed, 0 failed, 0 skipped. Report
counts as numbers. Confirm the Playwright geometry tests actually ran rather than skipped; a skip
is not a pass.

## 9. Stop conditions

Stop and report rather than working around, when:

- `no_count_dates` output changes for any input, or any late-work test needs adjusting.
- The design starts to need a `settings.json` schema change, a migration, or a teacher re-import.
- `_file_key` does not reliably map files to stored keys (§6.1).
- Reading named events requires globbing the Calendars folder, which would let the fictional
  sample reach a real screen.
- Long district event names cannot be made to fit without changing the pane's design rather than
  its numbers. Report what does not fit; do not redesign the rail.
- Anything here wants to write to the calendar, call a model, read the mirror, or touch Canvas.

## 10. Open questions for the teacher

None are blocking; defaults are chosen and stated so work can proceed.

1. **Look-ahead window.** Defaulting to 14 days (§4.2). A term-long view is a different product.
2. **Report cards on a student-facing screen.** Assuming yes, since students care when grades go
   home. Say so if that should be teacher-facing only.
3. **No-school subtype on the wall.** Assuming all three read the same to a student ("No school
   Monday") while the distinction is preserved in the data. A staff development day could read
   differently if that is worth saying out loud.

## 11. Execution result

_Not started._
