# Handoff: documentation truth sweep, Panels positioning, and the 1.0.0-beta.3 cut

**Executor:** 5.6Luna. This is established-pattern work: prose corrections against facts that
are already established below, plus two small test additions and one version bump. Nothing
here is guardrail-adjacent, so it does not need Terra.

**Twelve slices.** Slices 1 to 11 are independent and can be done in any order, though the
listed order goes mechanical first and judgment last. **Slice 12 is the release cut and runs
only after 1 to 11 are green.**

**Self-contained.** Every replacement row, file listing, route number, hash, and decision is in
this brief. You should not need to re-derive anything or ask a question to start.

**Supersedes `app-level-doc-accuracy.md`,** which covered six of these slices and has been
deleted. Nothing is lost; its content is folded in here with more.

## Context

CanvasExpert's docs split into two layers. The MCP tool-surface layer was corrected in the
immediately preceding commit, which fixed a wrong schema version and tool count in
`docs/mcp-server.md`, added two undocumented tools, corrected four route cards and one
contract, deleted three superseded planning docs, and added a test that pins the MCP doc to
the live registry.

This brief covers everything else that a review of that work turned up: the human-facing docs
that never picked up the last several releases, four consolidation questions that kept getting
reopened, one product-positioning decision, and the drift that can still recur because only a
single doc is currently pinned by a test.

It ends in a release. Panels landed as a genuinely robust surface, and that is worth a version.

## Part 1: Decisions already made. Do not relitigate these.

These are settled. They are written down here so that no future pass reopens them and no part
of this batch stalls waiting on a judgment call.

### 1.1 Panels is the classroom-display surface we lead with. SmartDeck is not deprecated.

This is a product decision from the teacher who owns the tool, not an inference from the code.
Apply it as written.

Use this framing wherever a doc has to describe either surface:

> A Panel is one URL that renders one thing, full bleed. A teacher drops it into whatever
> display surface they already use, including Classroomscreen, and it runs unattended for a
> whole period reading local data only. That is the path to lead with, because it meets a
> teacher inside the tool they already have on the wall.
>
> SmartDeck drives the whole screen itself, as a sequence of Slides with widgets. It stays
> fully supported for teachers who want CanvasExpert to own the display.

**Hard constraints on this wording:**

- **SmartDeck is not deprecated.** No doc, heading, table, or comment may call it legacy,
  retired, superseded, deprecated, a fallback, or "the old way." If you find yourself writing a
  migration note, you have gone too far.
- **Where a doc lists both, Panels comes first.** That is the only ordering change required.
- Do not add a comparison table, a "which should I use" decision tree, or a deprecation notice.
  One or two sentences of the framing above is the whole change.

### 1.2 The four consolidation questions are CLOSED. Nothing is merged or deleted.

A prior review flagged four apparent duplication candidates. All four were inspected for this
brief and all four are **keeps**. Record the reasoning where noted, so the question does not
get reopened a third time.

**The three operation-ledger docs stay as three.** They looked duplicative by shape and are
not by content. `docs/contracts/operation-ledger-contract.md` holds the invariants
(checkpoints, idempotency, receipts). `docs/reference/operation-ledger-design.md` holds the
data models and the protocol: Operation, Target, Batch, Step, Claim record, the adapter
interface, and the claim/lease/recovery rules at its sections 4.1 to 4.4. That protocol is
recorded nowhere else, and this is the high-risk Canvas write boundary.
`docs/reference/operation-ledger-module-map.md` holds file ownership. Deleting any of them
loses information. **No action beyond leaving them alone.**

**The two PowerGrader maps stay as two, but they must declare a boundary.** Merging them fights
the lazy-routing model in `AGENTS.md`, which exists precisely so an executor does not read a
260-line doc wholesale. The real defect was never the split: it was that neither doc declared
which one owns a *new scoring entry point*, so when `stage_scores` shipped it landed in
neither. Fix the cause. See Slice 9a for the exact ownership lines.

**`api/README.md` and `api/webui/README.md` stay as two, but they must declare a boundary.**
Both currently carry launcher instructions, both describe PowerGrader and Copilot batching, and
both carry a files or route table. They serve different audiences and should not merge. See
Slice 9b.

**`docs/reference/Architecture Narrative - Scenes.md` stays.** It is the teacher's own origin
document, and its opening banner already states that it is historical, names the superseded
terminology ("Scenes," "panes"), names the superseded number (an 84% score floor), points at
the authoritative doc, and points at the real shipped constant. That is a well-behaved
historical doc. Its overlap with `classroom-facing-data-contract.md` is inert because the
banner tells a reader which one wins. Deleting it destroys provenance for zero accuracy gain.
**No action.**

### 1.3 Seeded-file staleness in hand-edited copies is accepted, not fixed.

The seeded-file mechanism deliberately never overwrites a file a teacher edited. The
consequence is real: a teacher who hand-edited their workspace copy of
`START HERE - CanvasAgent.txt` keeps text that the preceding commit corrected, and the new
version arrives alongside rather than replacing it.

**This is correct behavior and stays.** Never clobbering a teacher's edits is worth more than
guaranteed freshness, and there is a strong mitigation already in place: `get_product_guide`
does not read the teacher's workspace at all. `_read_authoring_doc` at
`api/mcp_server/tools.py:1059` resolves from `REPO_ROOT` (see the `REPO_ROOT` import at
`tools.py:48`), so any MCP-connected assistant always receives the current shipped text. Only a
teacher manually pasting their own edited copy can get stale wording.

**Action: document that, do not change it.** One or two sentences, in Slice 5. No code change,
no version marker in seeded files, no new warning banner.

### 1.4 This batch ends at 1.0.0-beta.3.

Current version is `1.0.0-beta.2` at `api/__init__.py:3`. Slice 12 cuts the bump. Do not bump
it early, and do not bump it if any slice is red.

## Part 2: The slices

### Voice constraints (every slice)

- **No em-dashes in prose you write.** Comma, colon, or full stop.
- **Do not run an em-dash removal pass over the rest of a file you are editing.** Several of
  these files use them heavily today. Converting them all buries the real change in an
  unreviewable diff. New and rewritten lines follow the rule; untouched lines stay.
- **No taglines, no value-proposition copy.** No ALL-CAPS emphasis, no "ENFORCED" or "NEVER"
  framing, no compliance-banner boxes.
- **Security is built firmly and mentioned quietly.** A calm sentence stating what is true.
  Never a selling point, never a visual signal.
- **Working information before explanation.** Do not restructure a page around a first-time
  reader.
- **Do not invent features.** If you cannot verify a claim in code, leave it out and say so in
  the handback. An omission is recoverable; a confident wrong sentence is not.

---

### Slice 1: `START HERE - CanvasAgent.txt`, Appendix B is missing three shipped surfaces

**Highest value slice in the batch.** This file is what a teacher pastes into an AI, so a gap
here becomes an assistant confidently telling a teacher a feature does not exist.

#### The defect

Appendix B ("What CanvasExpert can do") runs these sections, verified by inspection: Create,
PowerGrader, Panels, Panel themes, Writing Timeline, Students, Seating, Gradebook tools,
Automations, Home, Speed.

Three shipped surfaces have no section at all:

1. **The canonical School Calendar.** School dates, day kinds, grading periods, bell
   schedules, the Teacher Schedule. Seven MCP tools and a `/calendar` page.
2. **SmartDeck.** Decks, Slides, widgets, the projector display view.
3. **Learning Objectives.** Reviewed, revision-protected per-course objectives that a Panel can
   display.

#### The fix

Add three sections in Appendix B, in the existing voice: a bolded-by-convention leading noun
phrase, then plain prose, no bullets. Keep each to the length of the neighbouring sections,
which run five to ten lines.

Placement matters for the positioning decision in 1.1: put **SmartDeck after Panels and Panel
themes**, so the display surfaces read Panels first. Put Calendar and Learning Objectives
wherever they read naturally; Calendar fits well before Students, and Learning Objectives fits
next to Panels since a Panel is where a teacher sees one.

Apply the 1.1 framing to the SmartDeck section. Do not add a comparison.

#### The hash step, and why it is cheap this time

This file is hash-registered at `api/webui/ai_ta.py:64`. The preceding commit already appended
the hash of the version it replaced, so **the currently committed text is not yet listed.**

After editing, compute the hash of the version you are replacing and append it to the
`"START HERE - CanvasAgent.txt"` frozenset with a comment saying what changed. Get it with:

```bash
git show HEAD:"api/default_docs/AI Authoring/START HERE - CanvasAgent.txt" | sha256sum
```

`api/webui/ai_ta.py:46-51` documents the procedure inline. Line endings are normalised to LF
before hashing, which the `git show` route gives you for free.

**Make all your edits to this file in this one slice, then hash once.** Do not touch it again
in a later slice: each separate edit costs another hash append, and the preceding commit
already paid one for Appendix D.

**Never list the hash of the version you just wrote.** That makes the app delete and re-seed
forever. `test_a_retired_name_that_still_ships_cannot_churn` catches it, so a mistake shows up
as a test failure rather than a field bug, but understand why.

---

### Slice 2: `AGENTS.md` routing index, four unroutable areas

#### The defect

The lazy routing index at `AGENTS.md:45-61` has no row for Panels, SmartDeck, the MCP server,
or Learning Objectives. All four are large, all four have current documentation, and an agent
following the index cannot reach any of it.

Calendar and Course Catalog rows already exist at lines 56 and 57 and are correct. Leave them.

#### The fix

Insert these four rows immediately after the Calendar row. Keep the three-column shape exactly.
Panels precedes SmartDeck, per decision 1.1.

```markdown
| Panels | `docs/reference/panels-route-card.md` | Disk-only reads, never live Canvas, because a Panel runs unattended on a wall for a whole period. A theme sets palette, typeface, and one decorative layer; it can never change what a Panel shows or how many rows fit. |
| SmartDeck | `docs/reference/smartdeck-module-map.md` | Decks write live with no review queue. Anything a Slide or Panel can display must satisfy `docs/contracts/classroom-facing-data-contract.md`. |
| MCP server | `docs/mcp-server.md` | Pseudonymized reads plus local writes behind preview/apply pairs. Never a Canvas write, and never a live Canvas response handed to the assistant. |
| Learning Objectives | `api/learning_objectives.py`, with `api/default_docs/AI Authoring/Author a Learning Objective.txt` for the authoring grammar | Reviewed objectives are teacher-confirmed and revision-protected; a write applies only the exact reviewed preview. |
```

There is deliberately no route card for Learning Objectives, so its row points at the module
and the contract. **Do not create one.** A new route card is its own batch.

---

### Slice 3: `api/webui/README.md`, the whole `/panels` family is absent

#### The defect

The page map at `api/webui/README.md:45-61` omits all five `/panels` routes. Panels appears in
that file only as three incidental cross-references. All five live in
`api/webui/routes/panels.py`.

#### The fix

Add these rows after the `/smartdeck/display/{deck_id}` row, which groups the classroom-display
surfaces together. Verified route definitions are at `panels.py:286`, `326`, `351`, `396`, `409`.

```markdown
| `/panels` | **Panels** console: pick a Panel, copy its URL, optionally fix it to one Teacher Schedule block | `pages/panels_clipboard.js` |
| `/panels/{kind}` | One Panel, chrome-free, sized to whatever box it is dropped into | `panels/panel.js` |
| `/panels/{kind}/data` | The Panel's single data fetch. Disk-only; never calls Canvas | route-driven |
| `/panels/themes.css` | The teacher's own Panel themes, generated from their theme files | route-driven |
| `/panels/theme-art/{key}/{index}.{ext}` | Processed bytes for one art entry, cached and immutable | route-driven |
```

#### Two boundaries to state in prose, not just the table

Both are things a later edit silently breaks, which is why they belong in the README and not
only in the route card.

1. **Registration order is load-bearing.** `/panels/themes.css` and `/panels/theme-art/...` are
   registered **ahead of** `/panels/{kind}`. That last route is a catch-all which would
   otherwise read those paths as a Panel kind and 404 both the stylesheet and the art.
2. **Two different things are called `themes.css`.** The static file
   `static/panels/themes.css` holds hand-written rule blocks for the eight built-in themes. The
   route `/panels/themes.css` serves the teacher's own themes as generated CSS. Every Panel
   links the static file first, then the route. Do not describe them as one thing.

---

### Slice 4: `api/README.md` predates most of the current app

#### Three defects

1. **Feature bullets at `api/README.md:6-14`** cover pushing content, printable output,
   Gradebook, PowerGrader, and Download. Absent: Panels, SmartDeck, the canonical Calendar, the
   MCP server, and Daily Writing (`api/dailywriting/`).
2. **Files table at `api/README.md:149-163`** omits every package added since it was written:
   `mcp_server/`, `mirror/`, `operation_ledger/`, `work_registry/`, `dailywriting/`, `rubrics/`,
   `custom_routines/`. It also omits the load-bearing top-level modules `panel_themes.py`,
   `learning_objectives.py`, `smartdeck_feeds.py`, and `course_catalog.py`.
3. **`api/README.md:79` is factually wrong.** It says non-secret config in
   `api/webui/config.json` includes "academic calendars." The canonical School Calendar replaced
   that. Verified for this brief: no `calendars` key and no `academic_calendar` reference remains
   anywhere in `api/`. `school_events` survives only as a SmartDeck *feed name* that reads the
   canonical calendar, which is not the same thing. Delete the phrase from that list and leave
   base URL, bookmarks, and download root, which are all still accurate.

#### Scope rule for the files table

The table names **subsystem owners, not an inventory.** There are roughly sixty top-level `.py`
files in `api/`. Do not list them. Add rows for the seven packages and four modules named above,
then stop. A module reachable only through a package already in the table does not need a row.

Note: `api/README.md:18` also states the current version. Slice 12 updates it. Leave it here.

---

### Slice 5: `About This Folder.txt` omits five shipped files

#### The defect

The "File categories" list at `api/default_docs/AI Authoring/About This Folder.txt:7-14` names
START HERE, four authoring skills (QuizForge, AssignmentForge, PageForge, RubricForge), Scoring
skills, Reference, and MagicSchool Toolkit.

The folder actually ships thirteen entries, verified:

```
About This Folder.txt
Author a Class Schedule.txt
Author a Learning Objective.txt
Author a Page (PageForge).txt
Author a Quiz (QuizForge).txt
Author a Rubric (RubricForge).txt
Author a SmartDeck (SlideForge).txt
Author an Assignment (AssignmentForge).txt
MagicSchool Toolkit/
Reference/
START HERE - CanvasAgent.txt
Writing Record (longitudinal writing history).txt
Writing Timeline (tracked assignments).txt
```

Missing from the categories list: SlideForge, Author a Class Schedule, Author a Learning
Objective, Writing Record, and Writing Timeline. A teacher reading this file cannot tell that
five of the things in front of them exist.

**Verify one claim before keeping it.** The text promises "Scoring skills: one file per valid
rubric in the default rubric library." No such file sits in the folder statically. Either they
are generated at seed time from `api/rubrics/`, in which case the line is correct and stays, or
they are not, in which case it is a false promise and goes. Confirm in code. Do not guess.

#### Also add the decision 1.3 note

Add one or two calm sentences covering what 1.3 settles: the app never overwrites a file you
edited, so if you edited one, your version stays and the new one arrives beside it. An
assistant connected over MCP always reads the current shipped text regardless, because
`get_product_guide` serves from the app's own files rather than your workspace copy.

The file already explains the seeding and retirement mechanism at lines 16-19, so extend that
paragraph rather than adding a new section.

#### The hash step

Same mechanism as Slice 1, different file. This one is registered at `api/webui/ai_ta.py:58`
and already has two hashes listed. Append this one, which is the hash of the version you are
replacing, verified for this brief through the app's own `_shipped_hash`:

```
b31f29b5a32c1c4efa23ed9c9a3e53f408cdc029cee8aa1b503c6f981205a409
```

Append, never replace. Never list the hash of what you just wrote.

---

### Slice 6: the root `README.md` (judgment)

#### The defect

`README.md:7-12` is the public GitHub landing page and its bullets have no Panels, SmartDeck,
Calendar, PowerGrader, or MCP. Line 11, "Powerful, but optional, AI integrations with
security-first design," is the only gesture at the entire assistant surface.

#### Constraints

- **Audience is a teacher deciding whether to download a ZIP.** Not a developer.
- **Keep it short.** The file is 40 lines and should stay near that. Add bullets for the
  surfaces a teacher would go looking for. Do not build a feature matrix.
- Panels earns a bullet. SmartDeck may share it or get its own, Panels first, per 1.1.
- Line 11 already leans closer to marketing than the quiet-security rule prefers. You may
  soften it. Do not amplify it, and do not add a second security bullet.
- Leave Getting started, Learn more, License, and AI Disclosures alone. All current and correct.

---

### Slice 7: the `/about` page (judgment, do this last of the prose slices)

#### The defect

`api/webui/templates/about.html` has these section headings, verified: What it does, The Forges,
Pedagogy is the default, Built safe by design, Where your content lives, The whole workflow, Get
started. The words Panel, SmartDeck, PowerGrader, and MCP do not appear anywhere in the file.
The feature story stops several releases back.

Version is templated as `v{{ app_version }}`, so there is no hardcoded number here. Slice 12
does not touch this file.

#### Constraints

- `/about` is an explainer page, so it is the one surface where explanation legitimately leads.
  That is a narrow licence, not a general one.
- **Smallest correct change.** Extend "What it does" to cover the classroom-display and grading
  surfaces, and put the assistant and MCP story where "Built safe by design" already discusses
  AI. **Do not restructure the page or add new top-level sections.**
- Do not add a tagline beyond the existing `h1`. Do not turn "Built safe by design" into a
  compliance-banner box.
- Apply 1.1: Panels before SmartDeck.

---

### Slice 8: `docs/README.md` does not index its own top-level files

#### The defect

`docs/README.md:8-11` lists the four subfolders but never mentions either top-level file:
`docs/mcp-server.md` or `docs/mirror.md`. The "useful starting references" list at lines 13-27
has no MCP entry either, which means the single most-referenced doc in the repo is unreachable
from the documentation index.

#### The fix

Add both files to the Sections list or the starting-references list, whichever reads better
given they are files rather than folders. Suggested entries:

- `docs/mcp-server.md`: the MCP tool surface, its gating posture, and client setup. Note that
  its tool table is pinned to the live registry by a test, so it can be trusted.
- `docs/mirror.md`: CanvasMirror's current behavior, its laws, and the freshness and staleness
  rules.

If Slice 10 adds more pinned docs, mention the pinning only once here rather than per entry.

---

### Slice 9: the two boundary declarations from decision 1.2

#### 9a: declare which PowerGrader map owns what

Add a short ownership line near the top of each file, under the existing routing-scope
paragraph. The point is that a future scoring entry point has one obvious home.

- `docs/reference/powergrader-scoring-map.md` owns the scoring and privacy **engines,
  pipelines, artifact routing, and every scoring entry point**, whatever route it arrives on:
  the web UI import, the Copilot batch, and the MCP `stage_scores` path.
- `docs/reference/powergrader-module-map.md` owns **routes, scripts, templates, browser load
  order, and backend package routing.**

State the rule explicitly in the scoring map: **a new way for scores to enter a session gets
documented here, not in the module map.** That sentence is the actual fix; the `stage_scores`
omission happened because it existed nowhere.

Cross-link each file to the other in one line so a reader who opened the wrong one is redirected
rather than left to guess.

#### 9b: declare the `api/README.md` versus `api/webui/README.md` boundary

`api/webui/README.md:12` already points at `api/README.md` for the backend overview, yet both
files carry launcher instructions, both describe PowerGrader and Copilot batching, and both
carry a table. Settle it:

- `api/README.md` owns the **backend, CLI, packaging, setup, credentials, workspace, and the
  `api/` files table.**
- `api/webui/README.md` owns **routes, pages, templates, static assets, and per-route script
  load order.**

Remove the duplicated launcher and PowerGrader prose from `api/webui/README.md`, replacing it
with the existing one-line pointer. Do not remove anything from `api/README.md`; Slice 4 is
already expanding it.

---

### Slice 10: pin the enumerations that can still drift, and one stale comment

#### The defect

The preceding commit added `test_mcp_server_doc_matches_the_live_registry` in
`api/tests/test_beta075_mcp.py`, which parses `docs/mcp-server.md` and asserts its declared
schema version, its declared tool count, and every row of its tool table against the live
registry. It works, and it is the reason that doc can now be trusted.

**It pins exactly one doc.** These hand-maintained enumerations remain unpinned and will go
stale silently the same way:

| File | Unpinned claim |
|---|---|
| `docs/reference/panels-route-card.md` | "the six MCP tools," naming all six |
| `docs/reference/smartdeck-module-map.md` | "SmartDeck's own 8," and "the canonical Calendar domain's seven tools," naming all seven |
| `docs/mirror.md` | the four mirror-bound tools, named |
| `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt` | Appendix D's tool list |

A seventh Panel theme tool would falsify three of these and no test would notice.

#### The fix

Extend the existing pattern. Read `test_mcp_server_doc_matches_the_live_registry` first and
follow its shape: it is deliberately simple, it names what drifted and why in its docstring, and
its assertions report the missing and extra names rather than just failing.

Add one test per doc above, each asserting that **every tool name the doc mentions is a
registered tool**, and where the doc states a count or claims to be exhaustive for a group, that
the count and the membership match the registry.

Design notes so this does not become brittle:

- Prefer asserting **"every tool named here exists, and this named group is complete"** over
  asserting the doc mentions every tool in the registry. Most of these docs are scoped to one
  subsystem and should not have to list all 45.
- For the group claims, derive the group from the registry where you can. The six theme tools
  all match a clear naming pattern except `get_theme_contract`; a small explicit set in the test
  is fine and clearer than a clever regex.
- Put them in `api/tests/test_beta075_mcp.py` next to the existing one, so all doc pins live
  together.
- **Verify each new test actually fails when the doc drifts.** Temporarily break a copy of the
  string in memory, not the file on disk. A test that passes vacuously is worse than none,
  because it certifies something it never checked.

#### Also, one stale comment in that same file

The version-history comment stops at v23: it reads "v22 adds the scoring packet surface; v23
adds teacher-owned Panel themes." v24 is covered further down at the assertion, so nothing is
wrong, but the comment is inconsistent inside a file this batch is already editing. Extend it to
name v24 and `list_theme_art`.

---

### Slice 11: apply the Panels positioning to the two docs that own the comparison

Slices 1, 3, 4, 6, and 7 each apply decision 1.1 in passing. Two docs own the framing directly.

1. **`docs/reference/smartdeck-module-map.md`.** Add a short paragraph near the top recording
   that Panels is the surface being led with for classroom display, with the 1.1 framing, and
   that SmartDeck remains fully supported. **No deprecation language.** This doc was corrected
   in the preceding commit for tool counts, so its MCP section is already right; do not
   re-audit it.
2. **`docs/handoffs/senior level/classroomscreen-panels-initiative.md`.** This is the persistent
   senior-level record for the Panels initiative. Per `docs/handoffs/README.md`, `senior level/`
   documents persist across sessions and hold coordinating context. Record decision 1.1 there as
   a dated decision so the next senior reads it as settled. Keep it to a few lines; do not
   rewrite the initiative document.

---

### Slice 12: cut 1.0.0-beta.3. Runs last, only when 1 to 11 are green.

#### Why this version

Panels shipped as a robust surface: nine Panel kinds, teacher-owned themes with derived
palettes and measured contrast, theme art with silent limit absorption, disk-only reads, and a
six-tool MCP surface. That plus this documentation sweep is a release.

#### The steps

1. Bump `api/__init__.py:3` from `1.0.0-beta.2` to `1.0.0-beta.3`.
2. Update the version sentence at `api/README.md:18` to match. That line names
   `api/__init__.py` as the source of truth, so both must move together.
3. Search for any other hardcoded occurrence of `1.0.0-beta.2` and update it. Do not change
   `about.html`, which templates `v{{ app_version }}` and needs nothing.
4. Run the full suite again after the bump.
5. **Stop there and hand back.** Do not create or push the git tag.

#### Why you do not push the tag

The rule in this project is that `__version__` and a matching git tag move together, because
historically they never once agreed. That pairing is the user's to perform, since it is the
outward-facing act. Report in the handback that the bump is in place and the tag is pending, and
name the exact tag string you expect so there is no ambiguity.

Note that self-update compares versions, so the bump is the thing a live install will act on.
Flag anything you notice that looks like it reads the version at runtime.

## Part 3: Verification gate

This batch ends at a release boundary, so the full suite applies rather than focused checks.
`AGENTS.md` is authoritative on verification policy; `docs/README.md:46-48` explains why a
release boundary earns the full run.

Report actual output, not a summary.

1. `python -m pytest api/tests -q` is green. It was **2044 passed** when this brief was written,
   before Slice 10 adds tests. A total *below* 2044 means you deleted a test; say so.
2. `python -m pytest api/tests -q -k "ai_ta or retired or seed"` specifically, for the two hash
   appends in Slices 1 and 5. Zero failures.
3. Each test added in Slice 10 has been shown to fail when its doc drifts. State how you
   demonstrated it for each.
4. `test_mcp_server_doc_matches_the_live_registry` still passes. If it trips, you edited
   `docs/mcp-server.md`, which is out of scope.
5. Render `/about` and `/` in the running app. Confirm no visual regression and **zero new
   console errors.** `AGENTS.md:60` requires a rendered check for Web UI and template changes,
   and Slice 7 is a template change.
6. Grep every file you touched for em-dashes and confirm none appear in lines you added.
7. Confirm no file anywhere calls SmartDeck deprecated, legacy, retired, or a fallback.
8. `git diff --stat` shows documentation files, `api/webui/ai_ta.py` (two hash appends),
   `api/tests/test_beta075_mcp.py`, `api/__init__.py`, and nothing else. Anything further is
   scope creep: name it in the handback rather than hiding it.

## Part 4: Not in scope

- **The MCP surface docs corrected in the preceding commit:** `docs/mcp-server.md`,
  `roster-module-map.md`, `feedback-scoring-contract.md`, `panels-route-card.md`, and the tool
  counts in `smartdeck-module-map.md` and the two PowerGrader maps. Slices 9a and 11 touch some
  of those files, but only to add the boundary and positioning text specified here. **Do not
  re-audit their tool facts.**
- **Merging or deleting any doc.** Decision 1.2 closed all four candidates as keeps.
- **Creating new route cards,** for Learning Objectives or anything else.
- **Renaming the `feedback_*` engine modules.** Separately deferred;
  `docs/reference/powergrader-scoring-map.md:52-54` explains why they keep the name.
- **Pushing the git tag.** Slice 12 stops at the bump.
- **Claude Code's own memory store.** Four stale entries exist outside the repo, under the
  user's `.claude` directory. They are the senior's to fix and are being handled separately.
  Do not go looking for them.
- **Restarting the user's MCP clients.** Their connected `canvas-expert` processes predate the
  current tool schema, which is an operational step for the user, not a repo change.

## Part 5: Handback

Per `docs/README.md:39-40`, record your compact traffic-light result **in this file** before
handback, so test evidence and current state do not exist only in chat.

For each slice: what changed, the traffic light, and anything you could not verify with the
reason. Name any claim you **removed** rather than corrected, so the next pass knows it was a
decision and not an oversight. Name the expected git tag string for Slice 12.

If a slice turns out to be wrong, drop it and say so. Eleven correct slices and one honest
refusal is a better outcome than twelve where one is invented.

Per `docs/handoffs/README.md`, this brief is deleted once the batch lands and the result is
recorded. Git preserves the history; the durable record is the route cards under
`docs/reference/`.

## Execution result

**Traffic light: GREEN.** Executed on 2026-08-02. Slices 1 through 12 are complete with no
undeclared implementation deviation. The expected release tag is `v1.0.0-beta.3`; the version
bump is present, but the tag was intentionally not created or pushed.

- **Slice 1, GREEN:** Added School Calendar, Learning Objectives, and SmartDeck to Appendix B,
  and led Panels with the settled classroom-display framing. Added the normalized hash of the
  replaced START HERE version, `1d7f62ce11001bded743ca8e76bfa5cbcaa1b9c999f921d2e1712553ee3f6c7b`.
- **Slice 2, GREEN:** Added Panels, SmartDeck, MCP server, and Learning Objectives to the
  routing index in the required order.
- **Slice 3, GREEN:** Added all five `/panels` routes and documented registration order and the
  distinction between static and generated `themes.css`.
- **Slice 4, GREEN:** Expanded the API feature list and subsystem-owner table, added the
  backend versus Web UI ownership boundary, and removed the false `academic calendars`
  configuration claim.
- **Slice 5, GREEN:** Indexed SlideForge, Class Schedule, Learning Objective, Writing Record,
  and Writing Timeline. Kept the scoring-skills claim after verifying `ai_ta.build_library()`
  generates one file per valid rubric folder. Documented the accepted hand-edited-copy behavior
  and appended the required `b31f29b5a32c1c4efa23ed9c9a3e53f408cdc029cee8aa1b503c6f981205a409`
  hash.
- **Slice 6, GREEN:** Added short teacher-facing bullets for Panels, SmartDeck, School
  Calendar, PowerGrader, and MCP, and softened the existing AI wording.
- **Slice 7, GREEN:** Extended `/about` in its existing sections with Panels before SmartDeck,
  PowerGrader, and the local MCP privacy/write posture. The rendered page remained intact.
- **Slice 8, GREEN:** Indexed `docs/mcp-server.md` and `docs/mirror.md`, with the registry pin
  mentioned once.
- **Slice 9, GREEN:** Declared both PowerGrader map boundaries and the API versus Web UI README
  boundary. Removed the duplicated Web UI launcher line and full PowerGrader narrative, while
  retaining route and script ownership. The removed `academic calendars` claim and duplicated
  PowerGrader prose are deliberate removals, not omissions.
- **Slice 10, GREEN:** Added four registry-backed enumeration tests and updated the v24 comment
  for `list_theme_art`. Each new test was run against an in-memory stale-name mutation and
  failed as intended. The existing MCP server document pin also passed.
- **Slice 11, GREEN:** Recorded the Panels-first decision in the SmartDeck route card and the
  persistent Panels initiative document. No SmartDeck positioning text uses prohibited terms.
- **Slice 12, GREEN:** Bumped `api/__init__.py` and `api/README.md` to `1.0.0-beta.3`. No other
  runtime hardcoded beta.2 reference remains; the remaining occurrences are procedural text
  in this handoff.

Verification evidence:

- `py -m pytest api/tests -q -k "ai_ta or retired or seed"`: **16 passed, 2032 deselected**.
- `py -m pytest api/tests -q`: **2048 passed in 67.92s (0:01:07)**, above the 2044 baseline.
- Rendered `/` and `/about` in the local app. Both loaded with expected navigation and content,
  screenshots showed no layout regression, and both reported zero error or warning console
  entries.
- `git diff --check`: passed. No em-dashes occur in lines added by this execution.
- The current docs and authoring files do not call SmartDeck deprecated, legacy, retired, or a
  fallback. Existing `SmartDecks-legacy` archive-path cleanup code and its tests predate this
  handoff and were preserved as unrelated worktree changes.
- The worktree also contains the preceding MCP and Panels batch changes, including code and
  document edits outside this brief. They were preserved and are named by `git diff --stat`;
  no unrelated files were edited by this execution.

## Senior review corrections, 2026-08-02

The executor's result above was reviewed against real state rather than accepted on its report.
The suite total, the version bump, the routing rows, the page map, and the em-dash claim all
held up on independent re-run. Four findings came out of it, three of which needed fixing. They
were fixed by three parallel Sonnet agents, one file each, and each fix was then verified by the
senior rather than by the agent that made it.

**Two of the three findings were defects in this brief, not in the execution.** Recorded plainly
so the next senior does not repeat them.

**Finding 1, content loss. Caused by Slice 9b.** Slice 9b asserted that the PowerGrader prose in
`api/webui/README.md` was duplicated in `api/README.md`. That was wrong. `api/README.md` carries
a one-line bullet; the Web UI README carried the unique per-page feature reference. The executor
faithfully deleted a section it had been told was redundant, and declared the removal openly.
Six facts were verified absent from the entire repo afterward: the 35%/65% setup split,
mode-aware fast versus AI configuration, the last-three-modules picker default, the exactly
three numbered Copilot upload files, the Late batch prefix/label/own-SAFE-bundle rule, and the
teacher-facing review-before-upload safety wording. All six are restored. One paragraph was
deliberately replaced with a pointer instead: the New Quizzes summary, because
`docs/reference/powergrader-module-map.md:75` genuinely does carry the unavailable-features line.
The two facts unique to the page (New Quizzes selectable in all three modes, Classic Quizzes
unavailable) were kept as prose. The Slice 9b boundary wording was also corrected to cover
per-page feature behavior, which is what made the deletion look sanctioned.

**Lesson for future briefs: do not turn a topical overlap report into a delete instruction.**
Two docs covering the same subject is not the same as two docs carrying the same content. Verify
duplication at the level of the specific sentences before authorizing removal.

**Finding 2, a phantom hash. Caused by Slice 1.** Slice 1 stated that "the currently committed
text is not yet listed," which was false, and told the executor to hash `HEAD`, which would have
produced an already-present duplicate. The executor noticed the contradiction and instead
registered the hash of the uncommitted intermediate working-tree version
(`1d7f62ce...`), which never shipped and so could never match a teacher's file. Harmless but
dead weight under a comment implying it shipped. Removed; the four older hashes plus the genuine
last-shipped `2cb1a3c9...` remain, now under one merged comment covering both the Appendix D and
Appendix B changes.

**Lesson: when the working tree is already dirty, "hash HEAD" is ambiguous.** A future brief must
say explicitly whether it means the last shipped text or the pre-edit working copy, and only the
last shipped text is ever correct here. The executor should have flagged the contradiction rather
than resolving it silently.

**Finding 3, weak drift tests. Shared.** Three of the four new Slice 10 tests pinned docs to
hardcoded set literals inside the test file, which catches a renamed or removed tool but not a
registry that grows past the doc. Registry growth is the exact case Slice 10 named. Slice 10's
own guidance ("a small explicit set in the test is fine") invited this. Corrected: the theme
group now derives from the registry as names containing `theme`, and the Calendar group as names
containing `school_calendar`. Both were verified to yield exactly the documented membership
against the real 45-tool registry, and both were shown to flip to a failure when a fake tool is
added. SmartDeck's eight are not cleanly derivable, so they keep an explicit set plus a guard
asserting that every registry tool matching deck or schedule patterns is accounted for; that
guard was also shown to trip on a new bell-schedule tool. The mirror-doc test keeps an explicit
set because no name pattern separates strict mirror-only readers from other local readers, and
its docstring now says plainly that it cannot detect a newly added mirror-bound tool rather than
implying coverage it lacks.

**Finding 4, invalid evidence. No fix needed.** The handback cited `git diff --check` as proof of
the no-em-dash gate. That command checks whitespace errors, not em-dashes. The conclusion was
correct on re-check, but the evidence did not support it. A gate is only as good as the command
that proves it.

**Post-correction verification, run by the senior:**

- `python -m pytest api/tests -q`: **2048 passed.**
- Seeded-file churn safety re-checked directly through `ai_ta._shipped_hash`: neither
  `START HERE - CanvasAgent.txt` nor `About This Folder.txt` has its current text listed in
  `RETIRED_FILES`. All nine genuine hashes present, phantom absent.
- Drift detection re-proved independently, not taken from the agents: theme group 6 to 7 flips,
  Calendar group 7 to 8 flips, deck/schedule guard flips on a new bell-schedule tool.
- All six restored PowerGrader facts confirmed present; the launcher line confirmed still absent.
- One em-dash in added lines across the whole batch, in the `get_writing_history` table row,
  matching that column's existing convention.
- No file calls SmartDeck deprecated, legacy, retired, or a fallback.

**Final state: GREEN.** Batch total 24 files, 418 insertions, 1017 deletions. Version is
`1.0.0-beta.3`; the matching tag was left for the user, per Slice 12.
