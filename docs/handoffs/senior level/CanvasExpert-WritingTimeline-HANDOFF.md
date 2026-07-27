# CanvasExpert / PowerGrader — Assignment Distribution + Writing Timeline

**Handoff document. Design state as of 2026-07-27.**
Carries decisions and their rationale so they don't get re-litigated. No code.

**2026-07-27 decision update:** Microsoft LTI cloud assignments remain rejected.
The teacher explicitly chooses whether every AssignmentForge assignment is **tracked**
or **not tracked**. A tracked assignment is a Canvas File Upload restricted to DOCX;
PowerGrader treats DOCX-only assignments as tracked, including assignments created
outside CanvasExpert.

**2026-07-27 implementation checkpoint — GREEN:** the PowerGrader/privacy vertical is
implemented in the current `dev` worktree. Exact DOCX-only assignment classification,
local OOXML timeline parsing, the all-mode queue view, metadata-only SAFE projection,
and optional teacher-only `writing_process_observations` are in place. The named gate
passed 85 tests with the predeclared Windows-path test deselected. `/powergrader` and a
fictional tracked queue rendered successfully in light and dark themes; the local Open
file control worked and both pages produced zero browser warnings/errors. No live Canvas
or AI call was made.

**2026-07-27 adversarial audit — three defects fixed, one finding downgraded.** The SAFE
boundary itself held: raw Office authors reach the bundle only via `local_attachments`,
which is popped before the SAFE bundle is written, and held students are dropped entirely.
XML entity expansion is rejected by ElementTree. Author matching already failed toward not
accusing (single-token names untrusted, ambiguous aliases collapse to
`unrecognized_author_present`). What was wrong:

1. **Uncapped `blocks` in the SAFE projection.** `largest_insertions` was capped at three;
   the full block array was not. A well-formed 75 KB tracked DOCX measured 60,000 blocks
   and 8.6 MB of outbound JSON per student, billed to the teacher's own AI key, with no
   consumer anywhere — the UI reads only trail/lock/properties/largest, and the counts
   already carry volume. The array is no longer projected at all.
2. **Only one of three `build_students` callers attached timelines.** `pg_start` did;
   `powergrader_late.py` and `routines_powergrader.py` did not. Late submitters on a
   tracked assignment got no timeline and no explanation, indistinguishable from "no
   revision trail". Both paths now attach and set `writing_timeline_tracked`. The late
   gap was live; the routines gap was **latent** — `is_tracked_assignment` requires
   `allowed_extensions == {docx}` while pure-upload autoscore eligibility requires an
   extension in `READABLE_UPLOAD_EXTS`, which excluded `docx`, so scheduled autoscore
   could not reach a tracked assignment. **Superseded the same day** — see the follow-up
   below: that exclusion turned out to be a stale list, not a policy, and the routines
   path is now live.
3. **`writing_timeline_tracked` was written but never read** by any route, template, or
   JS — so the teacher had no way to know an assignment was tracked, and the queue could
   not distinguish "tracked, no trail" from "not tracked". Now surfaced as a topbar badge,
   plus an explicit not-examined state per submission.
4. **The teacher-only observation had no server-side guard.** The contract forbade
   integrity conclusions in prose; `validate_results` only type-checked. A well-formed
   `"This student likely used AI"` would have validated and displayed verbatim.
   `writing_timeline.sanitize_process_observation` now enforces it at `reidentify`, the
   single funnel from model output to teacher-facing row, and fails closed.

Still open, judged not worth changing now: the timeline appends once per response when an
attachment carries no `item_id` (`feedback_artifacts.py`), latent only because the
assignments path builds a single response per student. Revisit if that ever changes.

**2026-07-27 follow-up — tracked assignments now auto-score, and a two-list defect is
closed.** The question was whether a tracked assignment could run the same PowerGrader
content path as any other upload so scheduled auto-score would be available. It already
did: `route_bytes` extracts DOCX text and inline images and marks it `ai_eligible`
(landed 2026-07-14), and the timeline is additive metadata that never gates scoring. The
only blocker was `autoscore_queue.READABLE_UPLOAD_EXTS`, written **2026-07-01** — two
weeks before DOCX extraction existed — and never revisited.

Investigating it surfaced a worse defect in the opposite direction. The gate and the
router were independent hand-maintained lists that had never agreed:

- The gate promised scheduled auto-score for **20 extensions** `route_bytes` refuses to
  send (`.java`, `.ts`, `.sql`, `.cpp`, `.go`, `.rs`, `.ipynb`, `.yml`, `.xml`, `.tsv`,
  …). Such an assignment was queued and a session created, then every student was held
  with nothing scorable — the exact outcome the Stage 1 design forbade: "Do not silently
  charge the teacher for an assignment where most work cannot be read."
- It excluded `.docx` and `.markdown`, which the router extracts in full.

Fixed at the root: `student_attachments.AI_TEXT_EXTS` is now the single source of truth
for readable student work, and `READABLE_UPLOAD_EXTS` is derived from it. Tracked
assignments became autoscore-eligible as a consequence rather than as a special case, so
the routines timeline attach is now live and covered end to end by
`test_scheduled_routine_attaches_timelines_for_tracked_assignment`. The narrowing is a
bug fix, not a policy change: those code-extension assignments never produced a scored
result. They now classify `needs_attention` for teacher review.

**Current next-batch pointer:** CanvasAgent/Create tracked intent and handout preparation.
Required context is this document §5 **Template**, **Authoring and distribution flow**,
and §11 **Appendix G structure**, plus
`docs/reference/course-expert-module-map.md` **Browser Routing**, **Backend Routing**,
and **Guardrails**. The batch must add the required tracked/not-tracked authoring choice,
teacher review override, standard student notice, and a non-destructive path that turns
either authored content or a teacher-selected source DOCX into a new tracking-enabled,
tracking-locked derivative. Distribution/idempotency may join the same batch only if the
senior can lock its exact local-workspace boundaries before delegation.

---

## 0. How to use this document

Sections 5 and 6 are the important ones. Section 5 is what's settled; Section 6 is
what was considered and rejected, and *why* — several of the rejected options look
obviously correct on first inspection and are not. Read 6 before proposing an
alternative architecture.

Section 7 holds vendor-documented facts that were verified during design. Don't
re-derive them; several are counterintuitive.

---

## 1. The system this plugs into

CanvasExpert (CE) is an existing local app. Relevant properties:

- Windows only. Python 3.13+. Runs entirely in the teacher's user folder — no admin
  rights, no IT ticket, no installer. Console window + local web UI on
  `127.0.0.1:8765`.
- Talks to Canvas with a Personal Access Token in the Windows credential store.
- Keeps a local mirror of course data; most screens serve from it.
- MIT licensed, open source.
- Existing surfaces: **Create** (author quiz/assignment/page/rubric, validate, push),
  **PowerGrader** (grading queue), **Students** (tiers, groups, accommodation flags),
  **Seating**, **Gradebook tools**, **Automations** (local scheduled jobs — already
  downloads new submissions), **Home** (roll-up).
- PowerGrader's three modes, named as teachers see them: *Score myself* /
  *Score with AI chat* / *Auto-score with AI*.
- Ships with `START HERE - CanvasAgent.txt`, a paste-into-any-AI briefing document.
  CORE block + appendices A–F.

### Invariants (do not violate)

1. The assistant **never writes to Canvas**. It stages drafts; the teacher pushes.
2. The assistant **never writes to a student's live folder**. *(New — add to CORE.)*
3. Student data reaching any model is **pseudonymized**; real identities are
   reattached locally.
4. Unmapped author strings stay local. Teacher clicks through to see them.
5. Output is **observations, never scores or likelihoods**. No integrity percentage,
   ever. See §8.
6. Staging uses the existing `.txt` + `.txt.done` byte-count gate. Measure the file
   on disk after writing; a text-mode write can double line endings and the mismatch
   holds the draft back on purpose.

### The one place being agreeable does harm

Appendix E is the project's honesty document. It currently promises names and IDs
are swapped before anything reaches a model, and explicitly states that free-response
bodies are *not* scrubbed. **Document metadata is a third category that Appendix E
does not currently cover.** Shipping timeline-to-AI before updating E makes the most
honest document in the project inaccurate. That is the actual failure mode here —
treat the E rewrite as a release gate, not documentation cleanup.

---

## 2. The feature, in one paragraph

Teacher describes an assignment in an AI chat session. The AI authors one envelope
that produces both a Canvas assignment (File Upload, `docx` only, rich formatted
prompt) and a handout `.docx` built from a tracking-locked template. Teacher reviews
and pushes; CE distributes the handout into per-student OneDrive folders the teacher
owns. Students write in that file and submit through Canvas. Automations download
submissions; a **Writing Timeline** parser reads the submitted `.docx` internals and
produces a pseudonymized report of how the text arrived — incremental typing vs.
bulk insertion, revision trail present or absent, template descent, unrecognized
authors. Canvas remains authoritative for submission time and grade.

---

## 3. Canonical example (use this as the acceptance walkthrough)

ELA7, extended constructed response on Katniss cutting down the tracker jacker nest.

1. **Canvas assignment** "Tracker Jacker ECR" — Submission Type: File Upload,
   Restrict Upload File Types: `docx`. Prompt, ECR scaffolding, and links live in the
   Canvas description as formatted HTML.
2. **Handout** `Tracker Jacker ECR.docx` lands in
   `Students/Lastname_Firstname/Unit N - Name/`. Track Changes on and locked. Name
   and title stamped at top by the distribute step. A parent who hates computers can
   print it and the kid handwrites — see paper accommodation, §5.
3. **Student submits** the `.docx` to Canvas by the due date.
4. **CE/PG pulls** when the teacher opens the grading queue, pseudonymizes, runs the
   timeline, and does normal PowerGrader work.

---

## 4. Folder structure (decided: A+C)

```
ELA7 Library/                         ← shared read-only with all students
  readings, notes, reference material

Students/
  Lastname_Firstname/                 ← shared individually; student EDIT, parents VIEW
    Unit 1 - Name/
      <handout>.docx
    Unit 2 - Argument/
      <handout>.docx
```

Rationale: distributed material lives outside student folders, so there is no
"is this file student work or something I handed out?" exclusion logic and no
duplicating readings across 30 folders. Unit subfolders keep prompt and response
adjacent and stop a year of ELA7 becoming 60 files in one flat list.

A **manifest** records what was distributed where and when. Its original job —
identifying which file is the student's response — is gone, because responses now
arrive through Canvas. It remains useful for redistribution and template-descent
checks. Not load-bearing.

**Multi-machine:** teacher works across several machines synced via OneDrive. Store
manifest paths **relative to the workspace root** and resolve at runtime; absolute
paths break because the user folder and tenant folder name differ per machine. Keep
the manifest in the workspace so it syncs, expect conflict copies, and make sure a
folder scan can rebuild it. Manifest = fast path, scan = fallback.

---

## 5. Locked decisions

### Sharing and setup (once per year, by hand)

- Folder per student, shared **individually**. Never share the parent folder —
  that exposes every student's work to every student. FERPA, not just untidy.
- Student gets **edit**. Parents get **view**.
- Teacher accepts that edit access permits delete, rename, and re-share (see §7).
  Deletions land in the teacher's recycle bin and are recoverable; version history
  and the recycle bin make this low-stakes.
- `ELA7 Library/` shared read-only.
- Refuse to generate a share worklist for any folder containing more than one
  student's files. Five-line guard, sharpest FERPA edge in the design.

### Template

- **Authoring order matters:** write prompt and header into the doc **first**, then
  turn Track Changes on, then Lock Tracking with a password, then save. Reverse the
  order and the teacher's own prompt text becomes a tracked insertion sitting in all
  30 copies — noise in every timeline and it muddies template-descent checks.
- Lock Tracking is **required**, not optional. It's the only thing preventing the
  most likely destruction of the data: a student looking at a page of colored
  underlines clicks Accept All to make their paper look like a paper. With tracking
  on, every word they typed is a tracked insertion, so Accept All erases the entire
  timeline. Locking also blocks accept/reject, which closes that path.
- **Name is stamped by distribution, not typed by the student.** Consistent string,
  the scrub knows exactly what to remove, no nicknames or misspellings to guess at.
- Students are taught the markup **display toggle** on day one. Hiding markup only
  changes the view, not the record. This is what keeps them from reaching for
  Accept All, and it removes most of the complaining. Ninety seconds of instruction.

### Submission and timing

- **Canvas submission is authoritative** for both grade and late status. Do not
  rebuild late logic; PowerGrader's existing late policies apply.
- **Grade the Canvas attachment, never the OneDrive file.** The live file keeps
  moving after submission.
- The forgotten-submission case (finished Tuesday, forgot to click) is handled
  **manually**: the OneDrive file still has its revision trail, so the teacher can
  see the work was done on time and remedy it. Judgment over automation. Don't let
  the late flag be the last word.
- No-trail submissions are **accepted and flagged**, never rejected.

### Timeline behavior

- Parses the **downloaded Canvas attachment**. Does not touch OneDrive.
- Derives: trail present/absent, insertion blocks (size + timestamp), template
  descent (is the protection element present — did this descend from the handout),
  editing time, unrecognized author strings.
- **Assignment intent is portable Canvas state:** an assignment whose only accepted
  upload extension is `docx` is tracked. PowerGrader applies Writing Timeline
  automatically, including to DOCX-only assignments created manually outside CE.
- PowerGrader surfaces large single insertion blocks prominently, with their size and
  timestamp. It still calls them **insertions**, never pastes; OOXML cannot prove how
  the text entered the document.
- Reports **observations with innocent explanations attached**. Never a score,
  percentage, or likelihood. A number would get quoted in a disciplinary meeting as
  though it meant something.
- Vocabulary: **"insertions,"** not "pastes." See §8.
- **Paper accommodation flag** in Students: handwriting submissions are a legitimate
  no-trail case. Timeline skips flagged students rather than flagging them.
- Feature is named **Writing Timeline** (or Draft History). Not Integrity Checker.
- Writing Timeline is embedded in PowerGrader's existing modes; it does not rename
  them: *Score myself* / *Score with AI chat* / *Auto-score with AI*.

### Pseudonymization (the release gate)

Repository truth as of 2026-07-27: ordinary DOCX visible-body extraction already routes
through the roster-aware text scrub and SAFE-artifact verification before it can reach
an AI mode. Appendix E is stale when it says free-response bodies are not scrubbed.
Do not build a second body-scrub path.

Extend the existing stack to tracked-change metadata and document internals:

- `docProps/core.xml` — `dc:creator`, `cp:lastModifiedBy`
- `docProps/app.xml` — `TotalTime`, `Revision`
- `word/document.xml` — every `w:author` on `w:ins` / `w:del`
- `word/header1.xml` — if the template puts the name line in a header it is **not**
  in `document.xml`
- **Whole body** name scrub. Norms are name at top, sign-off at bottom.

The AI-safe projection never needs raw Office author strings. Normalize authors before
packet creation:

- an author matching the submitting student → `submission_author`
- an author matching another roster member → `other_roster_author`
- an author that cannot be matched safely → `unrecognized_author_present`

The local teacher view may reveal the raw author string on click-through. SAFE packets
carry only the category and counts/times/block sizes, not the raw string or another
student's pseudonym. Apply the same normalization to creator/last-modified-by values.

AI modes may return an optional teacher-only `writing_process_observations` field.
It is displayed locally in PowerGrader, never copied into student-facing feedback,
never posted to Canvas, and never consumed by score calculation, automatic-post
eligibility, or an automatic consequence. The model contract permits observations
only: no integrity conclusion, likelihood, or recommended penalty.

Two hazards:

1. **Author strings are free text**, sourced from the local Office user profile —
   could be a provisioned display name, `jsmith`, or a shared lab machine's generic
   profile. This is a name→pseudonym *match*, not an ID lookup. Strings that match
   nobody are simultaneously the best signal and the thing that can't be
   pseudonymized. They stay local; teacher clicks through.
2. **Short and common names.** A student named Will, Grace, Mark, or Hope gets their
   essay quietly mangled by a naive replace. Word-boundary match on full name and
   roster first/last; when a name collides with a common word, **flag for teacher
   review rather than scrubbing silently.**

### Authoring and distribution flow

- Standalone **distributable contract kind** for documents. Required regardless,
  because readings and notes have no Canvas assignment at all.
- The **assignment envelope can reference** a distributable. One push produces both
  artifacts, so the prompt in Canvas and the prompt in the doc cannot drift.
- Every AssignmentForge envelope carries a required explicit assignment intent:
  **tracked** or **not tracked**. There is no default and the AI assistant must ask
  rather than infer.
- The existing assignment contract already carries submission type and allowed
  extensions. For tracked intent, validation requires `online_upload` as the only
  submission type and `docx` as the only allowed extension. Not-tracked assignments
  keep the normal Canvas submission choices, including `online_text_entry` for a
  daily quickwrite.
- A tracked assignment may use either (a) a CE-authored distributable created in the
  same AI session or (b) an existing teacher-selected DOCX. For an existing DOCX, CE
  creates a new tracking-enabled, tracking-locked derivative and leaves the teacher's
  source file untouched. The derived copy, not the source, is reviewed and distributed.
- Create shows a prominent **Tracked / Not tracked** control during review. The
  teacher may override the assistant's choice. Switching to tracked is blocked until
  a valid locked handout is selected; switching to not tracked removes the DOCX-only
  constraint after confirmation.
- A tracked assignment automatically adds a short student-facing notice to the Canvas
  description: write in the provided Word document, submit the DOCX, and understand
  that the document records when text is added and revised.
- **Push stays a teacher click. Distribute stays a teacher click.** Publishing fires
  notifications to 30 students and populates To-Do lists; distribution writes into
  folders students may already have open. Neither undoes cleanly, and the
  "don't edit a published assignment" problem is exactly what a review gate prevents.
  Cost: one click. Benefit: a gate at the moment things become irreversible.
- **Distribution must be idempotent.** Re-running cannot overwrite a student's
  in-progress work. Get this right before anything else in the distribute path.
- **Distribute before you publish.** Files in folders first, then the Canvas
  assignment goes live. Reverse it and you get thirty emails.

### Rollout

- The timeline is **announced to students**, not secret. Announced, it does most of
  the deterrent work it was built for; unannounced it reads as a trap when used, and
  the consequence lands on a 12-year-old.
- Student briefing is accurate and unexciting: the document remembers when text was
  added, so writing here shows your work, and adding a large block shows up as a
  large block. True, deterrent, doesn't overclaim.
- **Throwaway first assignment** whose only job is confirming every student can find
  their file, work in it, and submit it. Expect a wave of no-trail submissions in
  September from kids who never opened the handout. Moves those flags out of the
  graded set.

---

## 6. Rejected alternatives — read before proposing changes

**Microsoft Cloud Assignments / External Tool submission type.** Looks like exactly
this feature, built by Microsoft — distributes a per-student copy, no
download-then-upload step. **Fatal:** Instructure documents that submitted cloud
assignments are *converted to PDF* at submission time. Both the classic Office 365
and the new Microsoft Education generations. A PDF has no tracked changes, no core
properties, no editing time, no author strings — the parser gets nothing. Second
problem: adding a Microsoft Education assignment *overwrites the title and
description*, which destroys the formatted Canvas prompt in step 1 of §3.

**Microsoft Graph API** for folder creation, distribution, or snapshots. Needs an
Azure AD app registration; `Files.ReadWrite.All` is not a permission most school
tenants let a teacher self-consent to. That's a ticket, and for many teachers a dead
end — it breaks the no-admin-no-ticket install story. Unnecessary anyway: the sync
client puts everything at `%USERPROFILE%\OneDrive - <Tenant>\`, so distribution and
parsing are plain local file operations. The *only* thing Graph is needed for is
granting a student access to a folder, and that is a once-per-year manual step.

**Teams Assignments.** Would do template distribution natively. Disabled by this
district's admin (confirmed in course settings). Not available.

**Teacher-side deadline snapshot / pull.** Earlier design: script copies files out of
student folders at the due date to freeze state. Obviated once Canvas submission
became authoritative — the submission *is* the frozen artifact, timestamped by
Canvas rather than by the teacher. Deletes snapshot copies, Files On-Demand
hydration states, hash + capture time, and the multi-machine lock. If this comes
back, note: *copy* creates a new driveItem with fresh version history; only *move*
re-parents and preserves it, and move takes the file from the student.

**File mtime as turn-in time.** Touched by Word autosave, sync client operations,
and — critically — the teacher opening the file to read it. Grade a paper and you
stamp yourself as the turn-in time. If a local timestamp is ever needed again, use
the last tracked-change timestamp authored by that student.

**Bare Canvas submission purely as an "I'm done" declaration** (while grading the
OneDrive file). Rejected as fraught: it punishes the student who finished on time and
forgot to click. Note this is *different* from the current design, where the Canvas
submission is the actual deliverable.

**"Can review" sharing permission.** Enforces tracked changes server-side and can't
be stripped by unzipping the file — genuinely stronger than the template password.
Rejected because plain edit access was accepted, and because folder-level edit
rights override it: Microsoft documents that if a user already has edit permission,
selecting Can review won't apply and the document opens in edit mode. Would have
required sharing folders as view-only and each file as Can review. Available if the
lock ever proves insufficient.

**Cloud version history as an evidence source.** Doesn't survive a download — it
lives in OneDrive/SharePoint, not in the file. Teacher-side only, reviewed in the
browser, never sent to a model.

---

## 7. Verified vendor facts

Confirmed against vendor documentation during design. Don't re-derive.

| Fact | Source |
|---|---|
| Cloud assignment submissions are converted to PDF at submission; students must resubmit for changes to appear in SpeedGrader. True for both Office 365 and Microsoft Education LTI. | Instructure KB 660702, 664418 |
| Adding a Microsoft Education/Office 365 assignment overwrites the assignment title and description. | Instructure KB 664418 |
| Rubrics must be added *before* setting submission type to External Tool. Same for moderated grading. | Instructure KB 664418 |
| Office 365 files can't be used in an external tool for group assignments. | Instructure KB 664418 |
| Files picked from OneDrive on a **File Upload** assignment behave like any other file upload and land in the student's Canvas submissions folder — a real file copy, **not** a PDF conversion. | Instructure KB 661225 |
| Lock Tracking can only be *set* in desktop Word (not web, not mobile). Word for the web **respects** an existing lock without showing the UI; the lock also survives into the desktop app. | Microsoft Support; WiseChecker |
| While tracking is locked, tracking cannot be turned off **and** changes cannot be accepted or rejected. | Microsoft Support |
| Documented bypass: copy content into a new document. Produces a file with no revision trail, fresh creation date, trivial editing time, and no protection element — i.e. self-flagging, not a clean pass. | Microsoft/WordTips |
| A user with **edit** permission on a shared folder can copy, move, edit, rename, share, and delete anything in it. | Microsoft Support |
| Classic OneDrive / Teams Assignments / OneNote / Reflect LTI apps sunset **2026-09-17**. Not a problem here — this tenant is on the new Microsoft 365 LTI. | Microsoft Learn |
| OOXML has **no paste flag.** Word records no attribute distinguishing pasted from typed text. | OOXML structure |

---

## 8. Honest limits — must be reflected in UI copy

**There is no paste detection.** What exists is inference: Word coalesces contiguous
same-author insertions and stamps them to the minute, so 600 words arriving as one
insertion at one timestamp is a bulk insert, while typing produces many insertions
across many timestamps. `app.xml` editing time corroborates. The UI must say
*"inserted as a single block at 10:47"* and never *"pasted."*

**Initial controlled Word calibration (fictional content, 2026-07-27):** one fast
contiguous 33-word text-entry action became one 210-character `w:ins`; one 161-word
clipboard insertion became one 1,017-character `w:ins`; three text-entry actions
separated by two-second pauses became two `w:ins` blocks (13 and 10 words). Word can
coalesce separate entry actions, and ordinary contiguous entry can also be one block.
This validates listing the three largest blocks but does **not** justify a warning
threshold. Human-speed samples are still needed before emphasizing any size.

**Track changes records typing, not authorship.** A student who retypes AI output
instead of pasting produces a flawless organic-looking trail. Pasting is what gets
caught, and pasting is the lazy version. A clean revision history is not proof of
anything — it is evidence about process, not about who thought of it.

**The teacher's own framing, and it's the right one:** a fence isn't meant to stop
every attempt. It makes the alternative difficult, annoying, and obvious enough not
to be worth it. Build to that standard and don't oversell past it.

**No-trail does not imply tampering.** The most likely cause is a kid who opened
blank Word and never touched the handout. Disorganization, not evasion. Flag copy
should read *"no revision history — did you write this in the file in your folder?"*

**Filename changes are not evidence.** OneDrive sync clients and mobile apps generate
renames and conflict copies on their own. Deliberate settings-tampering is fair to
act on; filename weirdness alone is not.

---

## 9. What needs building

**New machinery**

- **Distribution.** Resolve student folder, create unit subfolder, copy handout in.
  Idempotent — must never overwrite in-progress work.
- **Roster ↔ folder map.** Canvas pseudonym → real name → folder path. Everything
  depends on this join. Needs a repair UI for nicknames, hyphenated names, mid-year
  transfers.
- **Handout generation.** Authored content + locked template + stamped name/title
  header. Protection element must survive intact.
- **Timeline parser.** A `.docx` is a zip; `zipfile` + stdlib XML, no new dependency.
  Reads core properties, editing time, insertion/deletion tuples (author, timestamp,
  type, character count), protection element presence.

**Extensions to existing surfaces**

- Pseudonymization stack → tracked-change authors, document properties, headers, and
  timeline SAFE projection, reusing the existing whole-body scrub. **Gate.**
- Automations → add parse step to the existing submission download.
- PowerGrader queue → flags carrying reasons; missing-file items carrying a reason
  (never created / present but unsynced / renamed-so-unmatched) so the teacher isn't
  hand-checking placeholders.
- PowerGrader modes → Writing Timeline is available in all three teacher-facing modes:
  *Score myself* renders only locally; *Score with AI chat* adds a pseudonymized
  timeline to the SAFE packet; *Auto-score with AI* receives the same safe projection.
  Neither AI mode may turn timeline observations into an integrity score, conclusion,
  or automatic penalty.
- Students → paper-submission accommodation flag.
- Create → distributable kind; assignment envelope references it.
- MCP → read timeline reports, stage drafts. Distribution stays a teacher click.
- Settings/Home → token expiry checker (see §10).

**Documentation**

- **Appendix E rewrite** — document metadata as a third category. Release gate.
- **Appendix G** — the durable checklist (§11).
- **CORE** — two lines: hard line extends to student live folders; distribution
  follows stage-then-teacher-acts.
- **Appendix F** — token expiry troubleshooting.

---

## 10. Build order

The ladder is structural, not advisory — the risky mode cannot ship early because
the gate sits below it.

1. **Distribution.** Local file copies into unit subfolders. No AI, no PII, no
   pseudonymization dependency. Useful the day it works and it's most of the value.
2. **Timeline, teacher-only.** Parse the downloaded attachment, render the revision
   table locally. Still no PII leaving the machine. → adds timeline to *Score myself*.
3. **Pseudonymization extension** for tracked-change authors/properties/headers and
   timeline projections, reusing the existing DOCX body scrub, plus an Appendix E
   rewrite that accurately describes both. **Gate.**
4. **Timeline packet for AI chat.** Opens only after 3. → adds timeline to
   *Score with AI chat*.
5. **Auto-score timeline context.** Reuses the same gated SAFE projection; it never
   creates an integrity judgment or automatic consequence.

Smallest useful first build: distribution + roster map.

There is no date pressure on this ladder. Student testing is unavailable before day
one, and the teacher has more than three weeks. Prefer offline synthetic-DOCX fixtures,
focused privacy gates, and explicit later live-student validation over compressing the
sequence.

---

## 11. Appendix G structure (the durable checklist)

Written as checklists an AI walks the teacher through, not prose. Four blocks:

- **Once per year** — folders created and shared individually (student edit, parents
  view); Library shared read-only; template with tracking on and locked; student
  briefing (name at top, sign at bottom, display toggle, never Accept All).
- **Per assignment** — distribute handout into `Unit N - Name/`; Canvas assignment set
  to File Upload restricted to `docx`; due date. Three items, same three every time.
  *This block is the answer to "I can't remember all the little switches and dials."*
- **At scoring** — Automations pull; timeline parses the Canvas attachment; grade the
  attachment not the OneDrive file; check the OneDrive revision trail before
  finalizing a late mark.
- **Invariants** — the list in §1.

---

## 12. This teacher's environment (confirmed from screenshots)

- **Microsoft Education / Microsoft 365 LTI present** in the external tool list.
  Not affected by the 2026-09-17 classic sunset.
- Course-level Dashboard Apps enabled: **OneDrive, Class Notebook, Reflect,
  Reading Coach**. **Teams is disabled by the district admin.**
- A legacy `Office365 Prod Iad` authorization still exists, last used Sept 2023.
  Harmless; build against Microsoft Education.
- OneDrive picker works from inside Canvas, with New folder and Upload available.
- **Token hygiene:** an approved integration labeled `CE` **expired 2026-07-24**
  (last used 07-23). Another, `CDDesk`, runs to July 2027. If CE stopped reaching
  Canvas last week, that's why. Build a specific 401 handler: tell the teacher the
  token expired and walk them to Settings → Approved Integrations → New Access
  Token, rather than failing generically. Recurring support question; Appendix F
  doesn't cover it yet.
- ELA7, 7th graders, ~30 per period. Teacher works across multiple machines synced
  via OneDrive.
- Scope: personal tool, shared with local colleagues. Not a SaaS product. Other
  districts' admin configurations are a footnote, not a requirement.

**Note:** the uploaded screenshots contain the teacher's legible name and several
staff folder names. Scrub before reusing them in a README — precisely the kind of
thing Appendix E would want caught.

---

## 13. Open questions

1. **Highlight passes** — shading bulk insertions in the document, and whether a
   model does out-of-voice analysis at all. Same precision caveat: you can shade
   insertions, not "pastes."
2. **Large-insertion presentation threshold** — the first UI lists the three largest
   insertion blocks without attaching a warning threshold. Calibrate a later emphasis
   threshold from controlled, fictional Word samples that compare ordinary typing and
   bulk insertion. Do not invent the threshold before observing Word's real grouping.
   This changes presentation only; it must not become an integrity score.
3. **Year-end handback** — returning copies so students keep their own writing.
4. **OneDrive submission tab availability to students.** Not a blocker: both paths
   (download-then-attach, and the OneDrive picker) produce a real `.docx` upload, so
   the architecture is identical either way. It's a student-instruction detail. Canvas
   Student View likely can't test it — the Test Student has no Microsoft identity to
   authenticate the picker. Enroll a colleague in a sandbox course, or find out in
   week one.

---

## 14. Footguns

- Never edit a published cloud assignment — *not applicable here* (no cloud
  assignments), but the same class of problem is why push is gated.
- Distribute before publish, or thirty emails.
- Files On-Demand: a file may be a cloud placeholder. A failed read is **not** a
  missing submission. If local reads ever return, report "not yet synced" as its own
  state.
- Conflict copies: `(conflicted copy)`, duplicate suffixes. Expect them in the
  workspace and in the manifest.
- Template authoring order (§5) — easy to get wrong, invisible until every timeline
  is noisy.
- Short-name scrub collisions (§5) — silently corrupts student essays.
