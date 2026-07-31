# Brief — Guard the retired paths so a resurrection cannot pass green

**Status:** current, awaiting execution · **Author:** Claude Code (session of 2026-07-31)
· **Executor:** external · **Lane:** one vertical improvement · **Branch:** `dev`

## Why this exists

On 2026-07-31 a `git pull` on `dev` brought in merge `95a54ed`, which joined this repository's
**old parallel lineage** (root `0508fbd`) back into the working lineage (root `85d6067`). Git merged
cleanly file-wise, but it resurrected 35 deliberately retired files and turned the architecture
guards red: 20 failures across `test_beta075_imports`, `test_canvas_mutation_ownership`,
`test_transport_ownership`, `test_presentation_contracts`, and the NoteForge suite, which calls
`html_renderer` with `variant="note"` against a renderer that only accepts `quiz` and `key`.

That is already fixed and pushed. Commit `4b13898` re-retired 34 of the 35 (plus one orphan),
`28889f2` removed an em-dash from teacher-facing copy, and the suite is back to
**1924 passed, 1 skipped, 0 failed** with all 71 GET routes returning no 5xx.

What is *not* fixed is that the suite could not see most of the resurrection.

## The actual defect

Restoring three retired files and running the full suite produced this:

| Resurrected file | Suite result |
|---|---|
| `api/webui/templates/push_quiz.html` | caught by the inline-style scan |
| `api/webui/config.py` | **passed silently** |
| `engine/orchestrator.py` | **passed silently** |

Two of three slipped through. `api/webui/config.py` is the worst case: `api/webui/config/` is a
package and shadows the module, so a duplicate config module can sit in the tree indefinitely with
nothing importing it and nothing complaining. The NoteForge detection was also **accidental**, not
designed. It only went red because the tests came back alongside the code; resurrect
`note_adapter.py` on its own and the suite stays green.

So the exposure is not merge-specific. A revert, a cherry-pick, or an agent re-adding a file it saw
referenced in an old document all land the same way, quietly.

## What does not need fixing

The lineage-welding failure mode is closed, and this was verified rather than assumed. The
resurrection happened because the two lineages had **no common ancestor**, so git had no merge base
for those paths, every side's files looked like additions, and nothing looked like a deletion. Merge
`95a54ed` gave the histories a common base. Branching from the pre-deletion tip `1f86843` (which
still carried all 35 files), committing simulated unpushed work, and merging current `dev` in leaves
all 35 **deleted**. Do not build a merge-policing hook; it would guard a door that is already shut.

## Locked decisions

Decided by the user this session. Do not relitigate.

| # | Decision |
|---|---|
| D1 | MCP tools may force a mirror refresh for **any saved course**, Current or Previous. The gate removal in `1f86843` stands. Student-data reads (`get_roster`, `get_submissions`, `get_gradebook_snapshot`, `get_seating_context`) keep their gate. |
| D2 | No em-dashes in **teacher-facing or student-facing** writing. Python docstrings and code comments are out of scope. `&mdash;` in a template or a JS string counts. |
| D3 | Re-retire the resurrected code rather than relaxing the contracts to accept it. Done in `4b13898`. |
| D4 | `docs/reference/smartdeck-design.md` is **kept**. It has no retirement commit and carries the PII execution model and the district data guardrail carve-out. It was the one old-lineage file not removed. |

## First, on this machine

The work moved physical locations mid-session. Before anything else:

1. `git fetch && git status`. `dev` should be at `28889f2` or a fast-forward of it. It will
   fast-forward cleanly; no merge is needed, because `origin/dev` already contains both lineages.
2. Set `git config --global pull.ff only`. Git for Windows ships `pull.rebase=false` in its
   **system** config (`C:/Program Files/Git/etc/gitconfig`), so a diverged `git pull` silently
   creates a merge commit. That is what produced both
   `Merge branch 'dev' of https://github.com/longhornadam/canvasexpert into dev` commits
   (`0dbbee2` and `95a54ed`). With `pull.ff only` a diverged pull aborts and the choice becomes
   deliberate. This is hygiene now rather than a fix, but it costs one command.
3. Confirm the baseline before changing anything: `python -m pytest -q` should report
   **1924 passed, 1 skipped**. If it does not, stop and report what differs.

## Step 1 — the retired-path guard

Add one test asserting that no retired path exists in the tree. Follow the repository's existing
idiom, do not invent a new one: `api/tests/test_repo_privacy_scan.py` is the suite gate with
`.githooks/pre-commit` as the fast backstop, and `ai_ta.RETIRED_FILES` is already a precedent for a
central retired list.

Put it where a future reader will look for it. `api/tests/test_retired_paths.py` is a reasonable
home; if an existing module is a more natural owner, use that instead and say why.

Carry the retirement commit per entry, so the next person can see *why* each path is retired without
excavating history. Entries marked `(none)` existed only on the old lineage and were removed by
judgment call, not by a prior retirement commit; label them as such rather than inventing a citation.

| Path | Retired by | Commit subject |
|---|---|---|
| `CLAUDE.md` | `bfe1877` | Add TAForge and canonical agent guidance |
| `api/default_docs/AI Authoring/NoteForge_Base.md` | (none) | old-lineage only; NoteForge leaves no other trace on this lineage |
| `api/downloader.py` | `f8a8f22` | Retire duplicate Download Work workflow |
| `api/tests/test_downloader.py` | `f8a8f22` | Retire duplicate Download Work workflow |
| `api/tests/test_noteforge_physical_routes.py` | `926b4f2` | Modularize live-fire workflows |
| `api/webui/activity.py` | `6110c48` | Complete 0.75beta local hardening and MCP support |
| `api/webui/config.py` | `87b2a80` | Refactor web UI modules and document next slices |
| `api/webui/push_service.py` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/static/style.css` | `1c2d9f7` | Complete WebUI presentation migration |
| `api/webui/templates/_course_picker.html` | `1c2d9f7` | Complete WebUI presentation migration |
| `api/webui/templates/download_work.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/templates/feedback_expert.html` | `f53394e` | Complete local-first Luna 5-7 surfaces |
| `api/webui/templates/name_manager.html` | `1c2d9f7` | Complete WebUI presentation migration |
| `api/webui/templates/push_assignment.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/templates/push_note.html` | `926b4f2` | Modularize live-fire workflows |
| `api/webui/templates/push_page.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/templates/push_quick.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/templates/push_quiz.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `api/webui/templates/push_rubric.html` | `cbd6738` | Cleanup legacy Course Expert standalone push surfaces |
| `docs/handoffs/smartdeck-slice1-schedules.md` | (none) | old-lineage only; completed slice handoff |
| `docs/handoffs/smartdeck-slice2-contract-and-writes.md` | (none) | old-lineage only; completed slice handoff |
| `docs/handoffs/smartdeck-slice3-management-ui.md` | (none) | old-lineage only; completed slice handoff |
| `docs/handoffs/smartdeck-slice4-display-and-timer.md` | (none) | old-lineage only; completed slice handoff |
| `engine/dev/test_cases/test_orchestrator_manual.py` | (none) | orphaned by `a405b24`; imported the retired `engine.orchestrator` |
| `engine/orchestrator.py` | `a405b24` | cruft-removal audit: retire dead code |
| `engine/packagers/note_handler.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/rendering/physical/note_adapter.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/rendering/physical/note_spike.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/rendering/physical/templates/note.html.j2` | `926b4f2` | Modularize live-fire workflows |
| `engine/tests/integration/test_backwards_compatibility.py` | `a405b24` | cruft-removal audit: retire dead code |
| `engine/tests/integration/test_orchestrator.py` | `a405b24` | cruft-removal audit: retire dead code |
| `engine/tests/unit/test_noteforge_cornell.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/tests/unit/test_noteforge_frayer.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/tests/unit/test_noteforge_guided_cloze.py` | `926b4f2` | Modularize live-fire workflows |
| `engine/tests/unit/test_noteforge_live_handler.py` | `926b4f2` | Modularize live-fire workflows |

Two requirements on the test itself:

- **Fail with the path and the reason**, not a bare `assert not exists`. The failure message is the
  whole point; someone will hit this months from now with no context.
- **Prove it can fail.** Before committing, restore `api/webui/config.py` from `1f86843`, confirm the
  new test goes red, then remove it again. A guard nobody has seen fail is a guard nobody should
  trust. `git checkout 1f86843 -- api/webui/config.py` stages it, so undo with
  `git reset HEAD -- api/webui/config.py` followed by deleting the file.

## Step 2 — mirror it into the pre-commit hook (optional)

`.githooks/pre-commit` already blocks tokens and PII at commit time as a fast backstop to
`test_repo_privacy_scan.py`. Adding a retired-path check there follows the same shape and blocks a
resurrection before it reaches history. Skip this if it makes the hook slow; the suite gate in
step 1 is the requirement, this is convenience.

Note `core.hooksPath` is already set to `.githooks` in this clone. A fresh clone needs
`git config core.hooksPath .githooks`, as the hook's own header says.

## Step 3 — the dead `var(--line)` token

Separate small defect found while verifying the deletions, pre-existing and unrelated to the merge.

`var(--line)` is referenced by three files but `--line` is defined nowhere. It existed only in
`api/webui/static/style.css`, which `1c2d9f7` removed without migrating these call sites, so these
borders have been rendering with no color since that commit:

- `api/webui/static/gradebook/curves.js` (1 use, around line 264)
- `api/webui/static/powergrader/queue_import.js` (1 use)
- `api/webui/static/settings/calendars.js` (2 uses)

The current system defines `--ce-rule` and `--ce-rule-strong` in `api/webui/static/ui/tokens.css`.
Use `var(--ce-rule)` unless the surrounding visual clearly wants the heavier divider; compare against
what `api/webui/static/ui/components.css` uses for equivalent dividers.

`test_presentation_contracts.py` runs a `VISUAL_LITERAL_RE` check and a `FORBIDDEN_JS_SELECTORS`
check over JS files, so do not introduce a raw hex color or a forbidden selector while fixing this.

## Known defect, explicitly not in this batch

Teacher-facing em-dashes, roughly 290 occurrences across about 30 files under
`api/webui/templates/` and `api/webui/static/`. Retiring the legacy templates in `4b13898` took this
from 415 down to 290. Per D2 these should go, but a 290-occurrence sweep is its own batch and would
bury this one. Fix them opportunistically in files you are already editing. Do not open the sweep
here.

## Verification

- `python -m pytest -q` reports **0 failures**. The count rises by the tests added in step 1.
- The step 1 guard has been observed failing on a deliberately restored file, then passing again.
- `git status` is clean and no file from the table above exists in the tree.

## Retiring this brief

Per `AGENTS.md`, close GREEN work by accepting it and retiring this brief in the same batch. Git
history is its record. If any step lands RED or YELLOW, leave the brief current and record the
status in it.
