# Windows session — naming/path follow-up from the b053071 arc

**Status:** CURRENT direct execution brief
**Executor:** one senior implementation agent, on real Windows
**Branch:** create `fix/windows-naming-followup` off `dev`
**Base:** `dev` at `b0530712db5f06ae953c8aae7151830fecc98d56`

This is the only execution authority in `docs/handoffs/`. Do not split this
across agents or open a second brief. The prior two briefs in this directory
(`windows-path-length-senior-overview.md`, `workspace-v2-restructure-spec.md`)
covered work that is now merged — their durable record is Git history.

## Why this session exists

Three commits landed in one day — Windows path-length recovery
(`8fb781b`/`6a80532`/`7d76c56`), the v2 workspace restructure (`143974a`), and
the naming consolidation (`b053071`). The logic is sound and the suite is green,
**but the suite ran on Linux.** The code that matters most here only executes on
Windows, and it has never done so. This session runs on Windows to close that
gap and fix two concrete defects the review surfaced.

Findings below were verified against the code by a second review pass. Read the
"what's actually true" note on each before acting — the first-pass diagnosis was
wrong on two of them, and acting on the wrong diagnosis wastes the session.

## Locked decisions (do not relitigate)

1. The consolidation itself stays. One shared `safe_filename_component`, one
   `needs_compact_layout` probe, one `run_stamp()`, one
   `quarantine_corrupt_file`/`utc_compact_stamp` — these are correct and reduce
   real drift. This session hardens them; it does not unwind them.
2. The 230-char teacher-visible budget and the `\\?\` fallback policy from the
   path-recovery brief remain in force. Do not lower thresholds or return
   `\\?\` values in API/UI payloads.
3. "Clean break, no migration" for the v2 tree was a deliberate product call.
   This session does **not** add a migration engine. It only answers what
   happens to already-synced evidence (task 3) and adds cleanup only if that
   investigation proves it necessary.

## Tasks, in priority order

### Task 1 — Run the Windows-only suite for real (primary objective)

The whole point of being on Windows. These tests are `skipif(os.name != "nt")`
and have never executed:

- `api/tests/test_workspace.py:200` — `extended_path` `\\?\` and UNC prefixing.
- `api/tests/test_powergrader_packet.py:63` — MAX_PATH (260) boundary behavior.

Steps:
1. Run the full suite on Windows. Confirm these two files' cases actually
   execute (not skip) and pass.
2. Exercise `workspace.extended_path()` against a genuinely deep path
   (long OneDrive root + long course/assignment names) and confirm
   `open()`/`makedirs` succeed where an unprefixed call raises
   `FileNotFoundError [Errno 2]`.
3. Exercise the UNC branch (`\\server\share\...` → `\\?\UNC\...`) against a real
   or simulated UNC path. This branch has zero real-platform coverage.
4. Walk the teacher-facing PowerGrader packet end to end in Explorer and a file
   picker: create a packet with long fictional course/assignment labels, open
   each returned folder via `/api/open-path`, and confirm every path is
   ≤230 and openable. Confirm the compact fallback (`needs_compact_layout` →
   `teacher_visible_path` compact form) triggers and produces distinct,
   openable paths.

Deliverable: a short results note appended to this brief (or a reply) stating
which Windows cases now genuinely ran, plus any real-platform failure and its
fix. Do not report "green" from a Linux run again.

### Task 2 — Fix reserved-device-name extension mangling in `safe_filename_component`

**File:** `engine/utils/text_utils.py` (`safe_filename_component`).

**What's actually true (corrected from first-pass review):**
- The bug is **pre-existing** — the old `api/webui/workspace.py:safe_component`
  did the identical `text += "_"` after the extension; `b053071` extracted it
  verbatim. It is not new to the refactor.
- It is **narrow**: it only bites when the sanitized value is a real
  `filename.ext` **and** its stem is a reserved Windows device name
  (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`9`, `LPT1`–`9`). Then `CON.pdf` becomes
  `CON.pdf_`, which Windows/Explorer won't open as a PDF.
- **It does NOT affect** `folder_creator.sanitize_filename`, `ai_ta`,
  `feedback_contract._safe`, `portfolio._safe`. Those sanitize **titles/names**,
  not `filename.ext`; the caller appends the extension afterward
  (`f"{sanitize_filename(quiz.title)}_QTI.zip"`). A quiz titled "CON" correctly
  becomes `CON_`. Do not "fix" these — they are working as intended.
- The real filename call sites are `workspace.safe_component(filename, 150)` as
  used by `managed_evidence_path` and the fallback branch in
  `new_quiz_fetch.py` (~line 748). Note `b053071` already added
  `os.path.splitext` there to preserve extensions for *normal* files — only the
  reserved-name case slips through.

**Fix:** in `safe_filename_component`, when the stem is a reserved name, insert
the `_` **before** the extension, not after it: `CON.pdf` → `CON_.pdf`. Splitext
first, guard the stem, reassemble. Add unit cases in
`engine/tests/unit/test_text_utils.py`:
- `safe_filename_component("CON.pdf") == "CON_.pdf"`
- `safe_filename_component("AUX.docx") == "AUX_.docx"`
- `safe_filename_component("nul") == "nul_"` (no extension — unchanged)
- title-style callers unaffected (add one asserting `sanitize_filename("CON")`
  still yields `"CON_"`).

Then verify the managed-evidence and new-quiz fallback paths produce
`CON_.pdf`-style names on Windows.

### Task 3 — Answer what happens to already-synced evidence after the v2 restructure

**What's actually true (corrected from first-pass review):**
The first-pass claim was "every teacher re-downloads their entire history
because stored `local_path` no longer matches how new paths are generated."
**That mechanism is wrong.** Reuse does not regenerate paths. `_existing_records`
(`api/powergrader/assignment_refresh.py:51`) reads a manifest `relative_path`,
joins it to the current root, and gates on `os.path.isfile`. The
`<id> — <file>` → `<file> — <id>` rename is irrelevant to reuse.

So the real, open question is a **product/data** one, not a code bug:
1. Does the v2 restructure physically relocate previously-downloaded evidence,
   or does "no migration" leave old files sitting at their old relative paths
   under the same workspace root?
2. If old files stay put: reuse still hits (`isfile` True), but new writes go to
   the new tree — a split-brain where a teacher sees both old and new layouts.
   Decide whether that is acceptable or needs a one-time relocation/cleanup.
3. If old files are effectively orphaned (root moved, or old relative paths no
   longer resolve): reuse misses and re-downloads from Canvas — fail-safe, but
   potentially a large silent re-fetch and orphaned old-tree files.

Deliverable: reproduce the upgrade on Windows with a pre-restructure workspace
snapshot, observe which of (2)/(3) actually happens, and record the finding.
Only add cleanup/migration code if the observed behavior warrants it — and if it
does, that is a **new** brief, not a bolt-on here.

### Task 4 — Leading-underscore collision for blank-title exports

`sanitize_filename("")` returns `""`, so a whitespace-only quiz title yields
`_QTI.zip` / `_RATIONALE.docx` (`engine/packagers/canvas_handler.py:41`,
`physical_handler.py:193`). This repo treats leading-`_` names as internal/hidden
(`api/webui/routes/pages.py:47`, `routines_custom.py:47`), so these exports could
be filtered out of listings. Give `sanitize_filename` a non-empty fallback for
the blank case at the export call sites (the packagers already do
`or "Untitled_Quiz"` for folders — apply the same to the `_QTI`/`_RATIONALE`
filename stems). Add a test.

### Task 5 — Minor: git identity (optional, do last)

Commits across this arc alternate `longhornadam <adambeckham@gmail.com>` and
`WorldForge Developer <adambeckham@live.com>` — same person, two machine
configs. Not a code issue; align the Windows machine's `git config user.*`
before committing so this session's history is consistent.

## Out of scope

- Unwinding any of the b053071 consolidation.
- A general workspace migration engine (unless Task 3 proves it necessary — then
  it is a separate brief).
- Touching the title-sanitizing call sites for the reserved-name fix (Task 2) —
  they are correct.
- Lowering the 230 budget or changing `extended_path`'s threshold.

## Definition of done

- Windows-only tests demonstrably executed (not skipped) and green on Windows,
  with the deep-path, UNC, and end-to-end packet checks done by hand.
- Reserved-device-named uploads produce `CON_.pdf`-style names; new tests cover
  it; title call sites confirmed unaffected.
- Task 3's data question answered with an observed result recorded here.
- Blank-title exports no longer produce leading-`_` filenames.
- Full suite green **on Windows**, results noted in this brief.
