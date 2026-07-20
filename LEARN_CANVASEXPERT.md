# LEARN_CANVASEXPERT.md

*Paste this whole file into a chatbot (ChatGPT, Claude, whatever you use) and ask it anything about CanvasExpert. Everything below is accurate as of this writing — the chatbot should answer from this, not guess.*

## What CanvasExpert is

CanvasExpert is a free tool one teacher built for their own classroom, then shared. It runs as a small program on a teacher's own Windows computer and talks to Canvas using that teacher's own login. It is not a company, not a subscription, and not hosted anywhere else. When the teacher closes it, it stops running. When they're not using it, it holds no data anywhere except on that one computer.

It doesn't replace Canvas. It sits next to it and handles the repetitive parts.

## Creating and pushing coursework

A teacher writes a quiz, assignment, page, or rubric as a plain text file (often with help from an AI chatbot, since the format is simple enough for one to draft). CanvasExpert checks the file for common mistakes, things like a multiple-choice question missing its correct answer, or answer choices that give away the answer by being longer than the others, before anything reaches Canvas. Once it looks right, one click pushes it live to one course or several at once, with due dates, grading category, and publish state all set together instead of one at a time.

It can also generate a printable PDF or an editable Word document of the same quiz automatically, useful for a student who's absent or for a paper backup.

Assignments can be pushed in different versions for different groups of students (differentiated or scaffolded versions of the same assignment, matched to a class's tiers or Canvas groups), so a teacher isn't manually re-creating three versions of the same assignment by hand.

## Grading

CanvasExpert has its own grading screen, separate from Canvas's own SpeedGrader, built to be moved through quickly with just a keyboard. A teacher can go student to student without repeatedly clicking back into Canvas's own interface.

## Roster and accommodations

A teacher can manage tiers, groups, and accommodation flags (like extended-time status) for a class inside CanvasExpert. Canvas itself stays the source of truth for who's actually in which group; CanvasExpert just makes it faster to see and adjust. Flagging a student as extended-time isn't just a label, it actually changes how other automated features (like late-work sweeps) treat that student, so accommodations are respected automatically instead of the teacher having to remember every time.

## Gradebook tools

Curving a low-scoring assignment, sweeping a course for late submissions, and granting a due-date extension are each one action instead of a multi-step process in Canvas's own gradebook.

## Automating routine tasks

A teacher can turn on "Routines": small automations that run on their own computer on a schedule (or whenever they open the app). Examples: automatically download new student submissions as they come in, automatically flag late work, automatically curve an assignment once grading is done, or keep a running report of what still needs grading and how overdue it is. These run locally, on that one computer, on purpose, because most school-issued computers don't allow background cloud services or scheduled tasks that IT hasn't approved.

## Dashboards and reports

A home screen rolls up what needs attention, grading debt, late work, students who need a check-in, across every course a teacher teaches, in one place. There are also clean, printable reports for a single student's work over time (useful for parent conferences or documentation).

## Speed, even on bad school wifi

CanvasExpert keeps a private local copy of a teacher's course data (roster, assignments, submissions), refreshed automatically in the background. Most screens load from that local copy instantly instead of waiting on Canvas's servers on every click, and the tool always shows how current that local copy is. If Canvas or the school's internet is slow, most of the app still works.

## Optional AI features

A few features can use an AI model to draft a first-pass grade and comment for a teacher to review, edit, or reject before anything is posted. This is turned off unless a teacher deliberately turns it on, and even then, it never posts a grade by itself except two very narrow, off-by-default settings a teacher has to opt into individually.

Before anything is sent to an AI model, student names and ID numbers are swapped for made-up placeholders (a fake name standing in for the real one), and the real identities are only reattached afterward, on the teacher's own computer. This is called pseudonymization. It's a strong privacy safeguard, but it's honest to say what it isn't: if a student happens to type their own name or other personal details into a free-response answer, that text isn't independently scrubbed, so this is not an absolute guarantee that no personal information could ever reach an AI model, and a teacher should still use judgment before sending sensitive student work anywhere. It is not a certified "FERPA-safe" stamp, it's a strong, honest safeguard.

Using the AI option also requires the teacher to set up their own account with an outside AI provider (OpenRouter), which is separate from CanvasExpert itself and may have its own cost depending on use. Nothing about the rest of the tool requires this.

## Privacy and trust, plainly

- CanvasExpert runs on the teacher's own computer. There is no CanvasExpert server anywhere holding student data.
- The teacher's Canvas login (a Personal Access Token, not their password) is stored the same secure way Windows stores other saved passwords, never in a plain file, never emailed, never uploaded anywhere.
- Nothing is ever pushed to Canvas, or posted as a grade, without the teacher clicking to approve it first (aside from the two narrow AI opt-ins mentioned above, which a teacher has to turn on deliberately).
- Installing and running it never requires admin rights or an IT ticket.
- The code itself is open source under the MIT license. Anyone can read exactly what it does; nothing is hidden.

## Setup and requirements

- Currently built for **Windows**. (Not Mac or Chromebook at this time.)
- No admin rights needed to install or run it. It installs entirely inside the teacher's own user folder.
- The first time it runs, if the computer doesn't already have Python installed, it walks the teacher through a one-time, no-admin, per-user install of it, then finishes setting itself up automatically.
- After that first run, opening it is a single double-click.

## Common questions

**Does this replace Canvas?** No. It's a companion that saves time on things a teacher would otherwise do inside Canvas by hand.

**Do I have to use the AI parts?** No. Every other feature works completely on its own. AI is off unless a teacher turns it on.

**Is my students' data safe?** It never leaves the teacher's computer except when the teacher deliberately pushes something to Canvas, or opts into an AI-assisted feature (and even then, real names are swapped out first).

**Does my school's IT department need to approve it?** No admin rights are required to install or run it.

**What does it cost?** CanvasExpert itself is free. The optional AI features require the teacher's own account with an outside AI provider, which may have its own separate cost.

**Do I need to know how to code?** No. Everyday use is point-and-click through a web page in the teacher's own browser.

**Can it mess up my gradebook or Canvas course?** Every push to Canvas requires the teacher's explicit confirmation first, and the tool is built so an interrupted push (like a computer restart mid-action) can't leave Canvas half-done or duplicated.

**Does it work on a Mac or Chromebook?** Not currently. It's built for Windows.

**What if my school's internet is slow?** Most screens still work, since CanvasExpert keeps its own local copy of course data.

**Who do I ask if something breaks?** Ask the teacher who built and shares this tool.

## What it isn't

- Not a Canvas replacement.
- Not a grading autopilot. AI-assisted grades are drafts for a teacher to review, not final answers, outside two narrow opt-in exceptions the teacher controls.
- Not a certified "anonymous" or "FERPA-safe" system. It's built with strong, honest privacy habits, not a compliance stamp.
- Not cross-platform yet. Windows only, for now.

## How this was built

CanvasExpert's code was written with AI assistance, directed and reviewed by the teacher who built it at every step, not generated and shipped unsupervised. Decisions about what to build, what to cut, and what's safe were made by a person, not an algorithm.

This matters for the same reason pseudonymization does: never send anyone's personally identifiable information to an AI service. Doing so can violate federal student-privacy law (FERPA). CanvasExpert's own AI features are built around that rule, and anyone extending or modifying this code should hold to it too.
