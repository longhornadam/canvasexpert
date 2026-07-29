Glass contracts
===============

This folder holds every file the Glass projector display reads: your bell
schedule, your section map, and one day plan per teaching day. It is written for
two readers. If you are a teacher, it tells you what to put where. If you are an
AI assistant working on a teacher's behalf, it is a complete specification: you
should be able to write a valid file from this document alone, without reading
any source code.

The one rule for the whole folder
--------------------------------

A file here is data that the teacher or the assistant authors. Glass only reads
it. Glass never writes back to these files, never writes anything to Canvas, and
has no editing surface on the screen. If you want the display to say something
different, change a file in this folder. There is no other route in.

That also means the folder is yours to organise. Nothing is generated, nothing is
overwritten, and a file you leave here that Glass does not recognise is skipped
with a note rather than removed.

What lives here
---------------

  README (Glass contracts).txt        this file
  bell-schedule-template.json         blank bell schedule to copy
  Mockingbird-Junior-High-Sample.json a complete fictional schedule
  section-map-template.json           blank section map to copy
  day-plans/
    day-plan-template.json            blank day plan to copy
    day-plan-sample.json              a complete fictional day plan
    YYYY-MM-DD.json                   your real plans, one per date

The templates and the samples all carry a "sample": true line. Real files leave
that line out. More on that below.

The times, rooms, clubs, and school name in every shipped file are invented. They
belong to a school that does not exist. Your own schedule and plans stay in this
workspace folder and are never part of the app.


1. Bell schedule
================

What it is for
--------------

The bell schedule answers two questions all day: which kind of day is today, and
which block is running right now. Glass resolves the clock against it to paint
the period name, the countdown, and the day strip. Everything else on the screen
hangs off that answer.

Where it lives
--------------

Any ".json" file at the top level of this folder whose format is
"canvasexpert.bell_schedule/1". The file name is up to you; something like
"our-bells.json" is fine. Files inside day-plans/ are not considered.

Shape
-----

Top level fields:

  format            string, required. Exactly "canvasexpert.bell_schedule/1".
  sample            boolean, optional. See "Sample versus real" below.
  school            string, optional. Used only to tell one file from another.
  timezone          string, optional. An IANA name such as "America/Chicago".
                    Nothing reads it today: the clock works in the local time of
                    whatever machine the screen is running on, which is the right
                    answer for one school in one time zone. Worth filling in
                    anyway, since it is the field a later slice would use.
  day_types         object, required in practice. One entry per kind of day.
  weekday_default   object, optional. Which day type each weekday normally gets.
  date_overrides    object, optional. Single dates that use a different day type.

Any key beginning with an underscore is treated as inline documentation and
skipped. That is how the shipped files explain themselves. You can add your own
"_note" keys anywhere and nothing will read them.

day_types is keyed by a short id you choose, for example "bobcat_hour". Each
value is:

  label   string, optional. Falls back to the id.
  blocks  list, required. The day's blocks in the order they run.

A block is:

  id          string, required. Short and unique within its day type, for
              example "p1". This is the key day plans use, so keep it stable.
  kind        string, optional, defaults to "class". One of: class, homeroom,
              bobcat_hour, lunch, advisory, assembly, other.
  label       string, optional. Falls back to the id. This is the text on the
              rail, so "1st Period" reads better than "p1".
  start       string, required. "HH:MM" on a 24 hour clock. Afternoon times count
              on past 12, so 1:05pm is "13:05".
  end         string, required. Same format. Must be after start.
  location    string, optional. Only meaningful on a concurrent child.
  sub_blocks  object, optional. See below. Only allowed one level deep.

Passing periods are not blocks. They are the gaps between blocks, and Glass works
them out on its own.

Container blocks
----------------

A block may carry sub_blocks:

  mode    string, required. Either "sequential" or "concurrent".
  blocks  list, required. Child blocks, same shape as above, except that a child
          may not carry sub_blocks of its own.

The two modes behave differently and the difference matters:

  sequential   The children partition the parent exactly. The first child starts
               when the parent starts, the last child ends when the parent ends,
               and there are no gaps and no overlaps in between. This is A and B
               lunch inside a period on a day with no separate lunch hour.

  concurrent   The children all run for the parent's whole span, and each carries
               a label and a location. They partition nothing. This is a lunch
               and tutorials hour with several things on offer at once.

Bobcat Hour is the lunch hour and has no A and B split. Students eat, go to
tutorials, and go to clubs, spread across the building. So a bobcat_hour block is
a concurrent container, never a sequential one, and a child of kind "lunch"
inside a concurrent block is reported as a mistake.

Leave a bobcat_hour block's concurrent blocks list empty in the bell schedule.
What is on offer changes week to week, so the offerings are day plan content and
the schedule only needs to know when the hour runs.

Which day type a date gets
--------------------------

weekday_default is keyed by the weekday number written as text, the same numbering
Python's date.weekday() uses:

  "0" Monday   "1" Tuesday   "2" Wednesday   "3" Thursday
  "4" Friday   "5" Saturday  "6" Sunday

A weekday you leave out of the map is not a school day. That is how weekends work:
you simply do not mention "5" and "6".

date_overrides is keyed by a single date in "YYYY-MM-DD" form and wins over the
weekday default. It is for facts you know in advance, such as an early release day
or a scheduled assembly.

For "the 6:50am email says today is a pep rally", do not edit this file. Use
day_type_override in today's day plan instead, described in section 3.

Sample versus real
------------------

Every file shipped with the app carries "sample": true. A real file omits the line
entirely.

Glass prefers a real file over a sample. If it can only find samples it loads one,
shows a quiet "Sample schedule" tag on the rail, and says so in the notes, because
sample times on a projector all day would be worse than saying nothing. If it finds
two files with no sample marker it will not choose between them: it reports both
file names and shows no schedule. Keep the one you use and move the others out of
this folder.

A section map sitting in the same folder is recognised by its format string and
skipped, not mistaken for a schedule.

What will reject a file
-----------------------

These stop the file from loading. Glass shows a note naming the day type and the
block to go look at, and the display keeps working with whatever it can read.

  - The format field is missing or is not "canvasexpert.bell_schedule/1".
  - The file is not valid JSON. A missing comma or a stray quote is the usual cause.
  - A block has no id.
  - A block has no start or no end, or a time that is not "HH:MM".
  - A sub-block carries sub_blocks of its own.
  - sub_blocks has a mode other than "sequential" or "concurrent".
  - A weekday_default key is not a number from 0 to 6, or its value is empty.
  - A date_overrides key is not a "YYYY-MM-DD" date, or its value is empty.

What will be reported but still displayed
-----------------------------------------

These load and run. Glass lists them in the notes so you can fix them, because a
schedule with a quiet mistake in it puts the wrong times on a wall for a whole day.

  - weekday_default or date_overrides names a day type that is not defined.
  - A day type has no blocks.
  - The same block id appears twice inside one day type.
  - A block's end is not after its start.
  - Two blocks in a day overlap, or are listed out of chronological order.
  - Sequential children do not fill their parent exactly, or leave a gap, or overlap.
  - A concurrent child runs outside its parent's span.
  - A concurrent child has kind "lunch".

Worked example
--------------

A complete, valid file with one day type. Save it as something like
"our-bells.json" in this folder.

{
  "format": "canvasexpert.bell_schedule/1",
  "school": "Mockingbird Junior High",
  "timezone": "America/Chicago",
  "day_types": {
    "bobcat_hour": {
      "label": "Bobcat Hour Day",
      "blocks": [
        { "id": "p1", "kind": "class", "label": "1st Period",
          "start": "08:30", "end": "09:19" },
        { "id": "p2", "kind": "class", "label": "2nd Period",
          "start": "09:25", "end": "10:14" },
        { "id": "bobcat", "kind": "bobcat_hour", "label": "Bobcat Hour",
          "start": "11:15", "end": "12:15",
          "sub_blocks": { "mode": "concurrent", "blocks": [] } },
        { "id": "p4", "kind": "class", "label": "4th Period",
          "start": "12:21", "end": "13:10" }
      ]
    },
    "friday": {
      "label": "Friday",
      "blocks": [
        { "id": "p1", "kind": "class", "label": "1st Period",
          "start": "08:30", "end": "09:24" },
        { "id": "p4", "kind": "class", "label": "4th Period",
          "start": "11:30", "end": "13:00",
          "sub_blocks": {
            "mode": "sequential",
            "blocks": [
              { "id": "p4a", "kind": "lunch", "label": "4th Period / A Lunch",
                "start": "11:30", "end": "12:15" },
              { "id": "p4b", "kind": "lunch", "label": "4th Period / B Lunch",
                "start": "12:15", "end": "13:00" }
            ]
          } }
      ]
    }
  },
  "weekday_default": {
    "0": "bobcat_hour",
    "1": "bobcat_hour",
    "2": "bobcat_hour",
    "3": "bobcat_hour",
    "4": "friday"
  },
  "date_overrides": {
    "2099-09-08": "bobcat_hour"
  }
}

Mockingbird-Junior-High-Sample.json in this folder is a fuller version of the
same thing, with all four day types the real schedule uses: bobcat_hour, friday,
homeroom_first, and pep_rally. Only bobcat_hour carries a bobcat_hour block. The
other three do not, so nothing should assume every day has one.


2. Section map
==============

What it is for
--------------

The section map records which Canvas section meets in which block, so a later
feature can answer "4th period is Canvas section X" without anyone retyping it.

Be aware that nothing reads this file today. Day plans are keyed by block id and
are deliberately not coupled to Canvas sections, so writing a section map changes
nothing on the screen. It is here so the format is settled and so the information
is not lost, and it is validated when loaded so a file you write now will still be
good when something does read it.

Where it lives
--------------

"section-map.json" at the top level of this folder. Copy section-map-template.json
and remove the "sample": true line.

Shape
-----

  format    string, required. Exactly "canvasexpert.section_map/1".
  sample    boolean, optional.
  sections  object, optional. Keyed by a block id from your bell schedule.

Each entry is:

  course_id     string, optional. The Canvas course id, written as text.
  section_name  string, optional. What that section is called in Canvas.

Underscore keys are skipped, as everywhere else. Leave out any block you do not
teach.

What will reject a file
-----------------------

  - The format field is not "canvasexpert.section_map/1".
  - The file is not valid JSON.
  - A sections entry is not an object with fields in it.

Worked example
--------------

{
  "format": "canvasexpert.section_map/1",
  "sections": {
    "p1": { "course_id": "10412", "section_name": "Grade 7 English - Period 1" },
    "p4": { "course_id": "10412", "section_name": "Grade 7 English - Period 4" }
  }
}


3. Day plan
===========

What it is for
--------------

The day plan is the day's content: the learning goal and today's work for each
class, what is on offer during Bobcat Hour, what is happening in this teacher's
own room during that hour, school-wide reminders, and the banner text. It is
written once in the morning, reviewed, and then durable for the day. Glass reads
it and renders it, and nothing recomputes it as the day goes on.

Where it lives
--------------

"day-plans/YYYY-MM-DD.json", one file per teaching day. The file name is the
authority on which date the plan is for. If the date field inside disagrees with
the file name, Glass goes by the file name and shows a note asking you to rename
one of the two.

Only well formed "YYYY-MM-DD.json" names are treated as plans. That is why
day-plan-template.json and day-plan-sample.json can sit in the same folder without
ever being mistaken for a real day.

Three scopes
------------

The plan has three top-level content sections because the content has three
different authors and audiences.

  school_wide   The same for every class in the building. Events and the Bobcat
                Hour offerings that anyone might attend.
  teacher       This one teacher's own room during Bobcat Hour. It is what a
                student standing in this doorway needs to know, which is a
                different question from what the whole school is offering.
  sections      Per block. The learning goal, success criteria, today's work, and
                the banner, which differ from one class to the next.

Shape
-----

Top level:

  format             string, required. Exactly "canvasexpert.day_plan/1".
  sample             boolean, optional.
  date               string, required. "YYYY-MM-DD", matching the file name.
  day_type_override  string or null, optional. See below.
  school_wide        object, optional.
  teacher            object, optional.
  sections           object, optional. Keyed by block id.

day_type_override is the same-day override. When the 6:50am email says today is a
pep rally, set this to the matching day type id from your bell schedule, for
example "pep_rally". It applies to this date only and takes effect without editing
the bell schedule at all, which is the point: an override written into the schedule
file would still be there tomorrow. Normally it is null.

school_wide holds two lists:

  events                   list, optional. Each entry:
                             label  string, required.
                             when   string, optional. Whatever reads well: a
                                    weekday, a time, "after 6th".
  bobcat_hour_offerings    list, optional. Each entry:
                             label     string, required.
                             location  string, optional.

teacher holds one entry:

  bobcat_hour_here   object, optional:
                       label     string. Leave it empty when the answer is
                                 nothing happening in this room today.
                       location  string, optional.

sections is keyed by block id. The keys are block_id values from your bell
schedule, not Canvas section names and not Canvas section ids. That is what lets
Glass pick the right slice on its own as the clock moves, with no lookup. A block
with no entry is normal rather than an error: a conference period or a duty period
simply shows an empty focus area, and the clock and the period name keep working.

Each section entry is:

  learning_goal      string, optional. One sentence.
  success_criteria   list of strings, optional. Two or three is usual.
  work               list, optional. Each entry:
                       name    string, required.
                       detail  string, optional.
  banner             list of strings, optional. Short reminders that rotate along
                     the bottom for this class.

Character budgets
-----------------

The screen is read from the back of a classroom, and text that wraps to a third
line pushes everything else off the bottom. So six fields have a budget:

  Field                                    Budget
  ---------------------------------------  ------
  learning_goal                                90
  each entry in success_criteria                40
  work[].name                                   34
  work[].detail                                 44
  offering label (school_wide and teacher)      30
  offering location (school_wide and teacher)   12

When a field is over budget, two things happen. At compose time the validator
reports the field by name with its actual length and its budget, so the text can
be shortened by the person who wrote it. At render time anything still too long is
trimmed to exactly the budget, ending in a single ellipsis character. It is never
wrapped and never reflowed. Writing inside the budget is always better than being
trimmed, so treat the numbers as a drafting constraint rather than a safety net.

Events and banner items deliberately carry no budget for now. They are bounded by
the layout instead: each event is a single trimmed line, whole events are dropped
when the rail runs short of room, and the banner is one trimmed line. If a future
version starts generating that text rather than having it hand-written, budgets
will be added.

What will reject a file
-----------------------

  - The format field is missing or is not "canvasexpert.day_plan/1".
  - The file is not valid JSON.
  - date is missing, or is not a "YYYY-MM-DD" date.
  - sections is present but is not an object keyed by block id.
  - A section entry is not an object with fields in it.
  - success_criteria or banner is present but is not a list.
  - work is present but is not a list, or a work item has no name.
  - school_wide is present but is not an object, or its events or
    bobcat_hour_offerings is not a list.
  - An event has no label, or a Bobcat Hour offering has no label.
  - teacher is present but is not an object.

A rejected plan is a note, not a crash. Glass keeps showing the clock, the day
type, and the day strip, and leaves the focus area empty. A morning where nobody
had time to write a plan should still give a working screen.

Worked example
--------------

Save this as "day-plans/2099-09-14.json".

{
  "format": "canvasexpert.day_plan/1",
  "date": "2099-09-14",
  "day_type_override": null,
  "school_wide": {
    "events": [
      { "label": "Yearbook photos in the gym", "when": "Tue" },
      { "label": "Band trip leaves after 6th", "when": "Thu" }
    ],
    "bobcat_hour_offerings": [
      { "label": "Robotics Club", "location": "Rm 214" },
      { "label": "Math tutoring", "location": "Rm 122" },
      { "label": "Quiet study", "location": "Library" }
    ]
  },
  "teacher": {
    "bobcat_hour_here": { "label": "Essay retakes", "location": "Rm 108" }
  },
  "sections": {
    "p1": {
      "learning_goal": "Explain how point of view shapes what a reader knows",
      "success_criteria": [
        "Name the narrator's point of view",
        "Quote one line that proves it"
      ],
      "work": [
        { "name": "Point of view sort", "detail": "Finish page 2 before you leave" }
      ],
      "banner": [ "Signed forms are due Friday" ]
    },
    "p2": {
      "learning_goal": "Trace a central idea across two short paragraphs",
      "success_criteria": [ "Underline the central idea" ],
      "work": [
        { "name": "Central idea notes", "detail": "Front side only" }
      ],
      "banner": []
    }
  }
}

Note that block "p4" is absent. That is a normal plan, not an incomplete one.


4. School calendar
==================

The school calendar is not a Glass file and does not live in this folder. It is
the existing Calendars subsystem, in "Library/Calendars", where each calendar is a
CSV the teacher imports or edits. That subsystem has its own template and its own
page in the app, and it is already used for grading periods and for the late-work
features, so it is not documented again here and it is not something to change on
Glass's behalf.

Glass uses it for exactly one thing, read only: it asks the academic calendar for
the non-instructional dates in the next two weeks and treats those dates as no
school, which is why a holiday shows as no school without appearing in your bell
schedule at all. If no calendar has been imported, Glass assumes no known
no-school dates and the weekly pattern in weekday_default is the whole answer.


5. Event and tutoring schedules
===============================

These are not implemented. There is no file format, no parser, and nothing that
reads one. Writing an event schedule or a tutoring schedule file into this folder
today has no effect: Glass would skip it with a note about an unrecognised format.

The idea, recorded so it is not reinvented from scratch, is that a school-wide
event schedule would carry dated entries with a label, a time or window, and
perhaps a location, covering the term rather than one day, so that the events pane
could fill itself instead of the day plan repeating the same reminders every
morning. A tutoring schedule would carry recurring offerings by weekday, so that
"Math tutoring in Rm 122 on Tuesdays and Thursdays" would only be written once
rather than copied into every day plan.

Until something reads them, the day plan is the only route in. Put events in
school_wide.events and tutorials in school_wide.bobcat_hour_offerings.
