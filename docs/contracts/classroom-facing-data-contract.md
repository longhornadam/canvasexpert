# Classroom-facing data contract

The authority for which facts a classroom screen may show and which stay with the teacher.
`api/audience.py` is the enforcement; this document is the decision. When the two disagree,
this document is wrong or the code is -- fix them together, never one alone.

## The split is not "student data versus not"

Schools put birthdays and full names on signage outside the building. They announce
outstanding achievements -- a 5 on an AP exam, the all-A list, STAAR Masters -- over the
intercom and in newsletters. Treating every student-linked fact as restricted would describe
a school that does not exist, and would make a classroom screen useless for the things it is
actually for.

The real line is **classroom-facing versus teacher-facing**, and the teacher owns where it
falls.

## Classroom-facing

May be shown on a projector, wall display, or any student-visible surface.

| Group | Facts |
|---|---|
| The school day | bell schedule, day types, blocks, school schedule |
| District calendar | no-school days, grading period ends, report card dates |
| School events | games, dances, assemblies, performances, spirit weeks, picture day, library hours, tutorial schedules, club schedules |
| Names | student names, teacher names |
| Per-student, publicly celebrated | birthdays, missing assignments, numeric scores **at or above 90%** (4+/5 and equivalent), positive achievements, STAAR Masters |
| Reviewed course context | teacher-reviewed learning objectives |

## Teacher-facing only

Never reaches a student-visible surface.

| Fact | Note |
|---|---|
| Scores **below 90%** (<4/5) | The floor is the whole point: a low score is private, a high one is a celebration |
| Behavioral punishment | |
| **Special Ed and 504 designations** | The one item here that actually generates challenges and lawsuits. Least negotiable entry in this document |
| Social security number | |
| Address, phone numbers, parent email | |
| Student ID number | |
| Economic designations | |
| STAAR below Masters | |

## The posture

Four rules that decide the cases the lists do not name.

1. **Offer caution, ask, and defer.** The app is not a FERPA oracle and must not act like
   one. Where a fact is genuinely ambiguous, surface the question to the teacher and accept
   the answer.
2. **Never self-lock.** Nothing is treated as restricted unless it is on the teacher-facing
   list or the teacher put it there. An assistant or a surface deciding on its own that
   something feels sensitive is a bug, not caution.
3. **Assume opt-in.** Absent teacher direction, classroom-facing facts are shown. It is the
   teacher's responsibility to say otherwise, and the app's responsibility to make that easy.
4. **Fail closed on the unclassified.** An unrecognised kind is not a classroom-facing kind
   missing from the list; it is a fact nobody has classified. `classroom_safe()` returns
  False for it. This is not in tension with rule 2 -- rule 2 governs known facts, this
   governs unknown ones.

## The assistant gets the contract, not the roster

- An assistant is off the machine by definition. So it gets the contract, not the roster --
  regardless of surface, this can never change.
- A classroom-facing surface is structured data (a fixed layout: heading, body text, or a
  bulleted list) rendered by a small set of built-in templates, not arbitrary HTML/CSS/JS.
  There is no user-authored code execution surface for a classroom-facing surface to have in
  the first place -- a stronger property than sandboxing it. (An earlier, deleted feature took
  the opposite approach: an AI authored arbitrary HTML/CSS/JS, run in an iframe with
  `sandbox="allow-scripts"`, an opaque origin, `no-referrer`, and an inline CSP blocking every
  outbound route. That mechanism no longer exists in this codebase and must not be resurrected
  as a shortcut to letting a classroom-facing surface run authored code again -- if a future
  design ever needs to render something more dynamic than the fixed layouts above, it should
  get there without arbitrary script, not by rebuilding that sandbox.)

## Enforcement

- Every item a day context emits carries an `audience`, stamped from the kind by
  `api.audience.tag()` -- not copied from whatever the source claimed, so a source cannot
  promote its own fact to the wall.
- Classroom-facing surfaces filter with `api.audience.classroom_only()` rather than trusting
  their input.
- `SCORE_FLOOR_PERCENT = 90` lives in `api/audience.py` and is stated here. A score below it
  can never be tagged classroom-facing, whatever a classroom-facing surface asks for.
- Per `docs/reference/project-state.md`, a model instruction is not an enforcement boundary.
  None of the above may be relocated into prompt text, a classroom-facing surface's source,
  or an authoring contract.

## Open teacher decisions

Defaulted per rule 3 so work can proceed. Each is a one-line change.

| Decision | Default |
|---|---|
| Birthday display name | First name plus last initial |
| Missing assignments by name on a wall | Shown. The most likely item to be re-scoped later |
| Report card dates on a classroom screen | Shown; students care when grades go home |
