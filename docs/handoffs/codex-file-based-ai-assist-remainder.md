# Codex handoff: finish the file-based AI assist work

**Repo:** CanvasExpert, branch `dev`. **Baseline for this work:** `10de84a`.

**Read this first, then read** `docs/handoffs/senior/copilot-file-based-ai-assist-trace.md` for the
reasoning behind every item. That trace is the authority on *why*; this document is the authority on
*what is left* and *what not to touch*.

---

## 1. Context in one paragraph

An in-tenant AI chat app with a strong model, free to teachers, is becoming the default assistant in
this district. It takes files in and gives files out, and it has **no MCP**. So CanvasExpert's
file-and-clipboard paths (PowerGrader's "Score with AI chat" packet mode, and Create's Forge
copy/paste/upload round trip) are now the main line rather than the fallback behind the MCP lane. A
trace of both surfaces found eight defects. Five are fixed and committed. Three remain, and one of
those is a decision rather than a task.

---

## 2. What already landed (do not redo)

Five commits, each verified green in an isolated worktree.

| Commit | What landed |
| --- | --- |
| `28ef33c` | Zero-result AI imports fail closed instead of reporting success; parser widened to five more reply shapes; `parsed_count` added to the payload |
| `3e55deb` | Vendor-neutral naming across the packet flow (19 teacher-facing strings, the on-disk folder, the readme); batch cards accept a result file |
| `833c283` | AI helper file downloads carry their real filenames (Content-Disposition on both routes) |
| `a0b481e` | `/ai-expert` scoring skills retired including their second surface on Create; binary-upload guard in the Forge parsers and temp-upload; file lane named before paste lane |
| `10de84a` | Trace doc updated with execution state and two new findings |

---

## 3. Test gate

```bash
py -m pytest api/tests -q -p no:randomly --tb=short
```

**Expected at `10de84a`: 1 failed, 2226 passed.**

The single failure is
`api/tests/test_presentation_contracts.py::test_migrated_feature_css_consumes_shared_visual_tokens`,
a `calendar.css` token check. **It fails at `1847615` too**, so it predates all of this work. Leave it
failing. Do not "fix" it as part of these items.

If you see a higher passed count, that is the uncommitted work in section 4 contributing its own
tests. That is expected and is not a problem.

---

## 4. The hazard: do not commit the working tree wholesale

At `10de84a` the working tree carries roughly 40 uncommitted files that are **not part of this work**:
an in-flight "assistant staged scores" feature (spanning `api/webui/routes/powergrader.py`,
`api/powergrader/session_actions.py`, `api/feedback_contract.py`, and the MCP server and tools), plus
separate Panels, Calendar, and school-calendar work.

`git add -A` will sweep all of it into your commit. Stage explicit paths instead.

Two files have finished work from this initiative interleaved with that in-flight feature, so if you
need to touch them, stage at hunk level:

- `api/webui/static/powergrader/queue_import.js` (the staged-scores hunks are the ones mentioning
  `pollStagedStatus`, `stagedStatus`, `loadStagedScores`, `lastStagedAt`)
- `api/tests/test_route_contract.py`
- `api/webui/static/powergrader/queue_core.js` and `api/webui/templates/powergrader_queue.html` are
  also modified by that feature, which matters for item 5.2 below

---

## 5. Remaining work

### 5.1 Decision needed before code: writing-timeline data in the batch path

**Status: open decision. Do not implement without an answer.** Trace sections 4.8 and 8.4.

**The verified facts.** The SAFE bundle carries writing-timeline data per response
(`api/feedback_artifacts.py:305-307` sets `response["writing_timeline"]` via
`writing_timeline.safe_projection`). The flat packet dumps the whole bundle into
`Student Responses.json` (`api/powergrader/packet.py:184`) so it travels there, and the flat packet's
`START HERE` documents `writing_process_observations` with explicit guardrails
(`api/feedback_contract.py:91`).

The batch path does neither. `_student_blocks` (`api/powergrader/copilot_packet.py:40-65`) builds
`03-work.md` from only `pseudonym`, `item_id`, `possible`, and the response text, and file 02's
contract (`rubric_persona_text` in `api/powergrader/copilot_packet_support.py`) never mentions
`writing_process_observations`. So in packet mode the AI is never given the data and never asked for
the field.

**Correction to an earlier framing, important.** An earlier draft of trace section 4.8 implied the
queue's "Tracked DOCX, Writing Timeline" badge promises something packet mode cannot deliver, and a
first instinct was to hide the badge in packet mode. **Do not do that.** The timeline strip renders
from local session data (`queue_writing_timeline.js:56` reads
`students[].attachments[].writing_timeline`), not from the AI. Packet mode therefore gives the
teacher the full working timeline view: signals, sparkline, and navigation. The badge is accurate.
Hiding it would remove a feature that works.

What is genuinely absent in packet mode is only the AI's teacher-only `writing_process_observations`
note. Nothing in the UI currently promises that note, so nothing is currently lying.

**The three options, for the product owner to pick:**

1. **Leave it out, and write it down.** Treat writing-process observations as an API-lane and
   MCP-lane capability. Change no behavior; document the difference so it stops being rediscovered.
   Smallest, and honest.
2. **Include it, gated.** Carry the safe projection into `03-work.md` and add
   `writing_process_observations` to file 02's contract, behind the acknowledgement packet mode
   already requires. Most capable, most exposure.
3. **Include only the aggregate.** Author count and revision-span summary, never per-document
   detail. Probably enough for the coaching use the feature was built for.

**Why this is a decision and not a fix:** writing-timeline data describes authorship and revision
behavior. `safe_projection` and `sanitize_process_observation` were built to guard a payload going
out over the API lane. Putting the same data into a `.md` file a teacher hands to a chat app by hand
is a different exposure, and the teacher chooses the destination.

If option 2 or 3 is chosen, do item 5.3 in the same pass, because the contract text becomes
load-bearing.

### 5.2 Batch packaging: one ZIP per batch, and a return lane for the whole-class ZIP

**Status: ready, but gated on a manual test that has not been run.** Trace sections 4.3, 4.4, 4.5.

**Run the gate first.** In the actual chat app the teacher will use, confirm by hand: that a `.zip`
attachment is read and its contents enumerated; that every file inside is actually attended to rather
than the first few; and that `.md` and `.json` attachments work. The vendor's self-report says all of
this works, but that is a self-report, not a test. **If a ZIP is read but only partly attended to, stop
and report rather than shipping the repackaging**, because partial attention produces silent
under-scoring, which is the exact failure class `28ef33c` was written to close.

If the gate passes:

- **One ZIP per batch.** Batches currently ship three loose `.md` files
  (`01-info.md`, `02-rubric.md`, `03-work.md`) written by `build_copilot_batches` in
  `api/powergrader/copilot_packet.py`. One ZIP per batch is a better artifact for any chat: one
  attachment, no chance of attaching 01 and 03 but forgetting 02, and the readme travels with it.
  Keep the loose files on disk as well; teachers browse that folder.
- **A return lane for the whole-class ZIP.** `queue_import.js:63` always offers "Download packet ZIP",
  and it is the most clickable artifact in the strip, but when batches exist line 66 hides
  `legacyImportBox`, which holds the only whole-class textarea. A whole-class result pasted into a
  batch box fails validation against that batch's `expected_results`. So either give the whole-class
  ZIP a working return lane or stop offering it in batch mode. Do not leave it as a dead end.
- **Path budget.** These paths are length-constrained against `workspace.TEACHER_VISIBLE_BUDGET`.
  `_needs_compact_layout` projects the deepest expected child; if you add a `.zip` per batch, update
  that projection to match or the budget check tests the wrong string.

**Do not change** `DEFAULT_COPILOT_CONTEXT_TOKENS = 128_000` as part of this. Batching exists because
of the context window, not because of attachment limits, so a large class still needs splitting no
matter how few files it arrives in. Whether that number becomes configurable is trace section 8.3, a
separate open decision.

### 5.3 Consolidate the output contract, which is written four times

**Status: ready, lowest risk, lowest urgency.** Trace section 4.7.

The same scoring output contract is stated independently in four places:

- `build_contract_text` in `api/feedback_contract.py` (the flat packet's `START HERE`)
- `paste_format_text` in `api/powergrader/packet.py` (the flat packet's paste-back format file)
- `rubric_persona_text` in `api/powergrader/copilot_packet_support.py` (the "Required JSON Output"
  block inside batch file 02)
- `batch_prompt` in the same module (the copy button and the readme)

They have already drifted: `build_contract_text` documents `writing_process_observations` and
`rubric_persona_text` does not. That drift is item 5.1's other half. Render all four from one source
so the model reads the same contract whichever file the teacher happens to attach.

Do this **after** 5.1, since the answer there changes what the shared contract has to say.

---

## 6. House rules

These are settled and non-negotiable in this repo.

- **No em-dashes anywhere.** Not in code, comments, commit messages, or UI copy. Use commas, colons,
  or parentheses.
- **Vendor neutrality.** CanvasExpert names no preferred AI chat. Naming several as examples in one
  breath is fine; singling one out is not. `3e55deb` established "AI chat" and "your AI chat" as the
  neutral phrasing. Match it. Internal identifiers (`copilot_packet.py`, the `copilot_packet` session
  key, `batch_id`) deliberately keep the old name: churning them adds risk without changing anything
  a teacher sees.
- **Calm teacher-facing voice.** No ALL-CAPS, no ENFORCED or NEVER framing, no compliance-banner
  boxes. This is a working tool, not a SaaS product. Error messages should say what to do next.
- **Match surrounding code.** `queue_import.js` is plain ES5-style IIFE code with no framework.
- **Commit only when asked**, and never `git add -A` in this tree (section 4).
- **No synthetic Canvas data**, and no real district data, tokens, or student PII in the repo.

---

## 7. Sequencing

1. Ask the product owner item 5.1's question. It gates 5.3 and shapes nothing else.
2. Run item 5.2's manual attach gate. If it fails, stop and report; that changes the plan.
3. Implement whichever of 5.1 and 5.2 are cleared, in either order. They touch different files.
4. Implement 5.3 last.

Each step should land as its own commit, green against the section 3 gate, with the pre-existing
failure still failing and nothing from section 4 swept in.
