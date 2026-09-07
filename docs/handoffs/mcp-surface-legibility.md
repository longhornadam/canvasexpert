# MCP surface legibility, slice A: line one carries the tool

Status: RETIRED, accepted 2026-09-07. The senior accepted the three reproducible,
out-of-scope full-suite failures below as the baseline exception and authorized slice B.

This is the first of three planned slices. A is this brief: make the always-loaded
line of every tool a real sentence, and fix the code defects two probes found. B
(`mcp-surface-slice-b-results.md`, queued and blocked on this one) moves the workflow
detail that currently sits after each description's first newline into the results that
need it, targeting a listing near 18,000 characters. C gives `get_product_guide` an
annotated table of contents, a topic that inventories every tool, and an inward pointer
instead of one aimed at `docs/mcp-server.md`. B and C are not authority yet and are not
to be started from here.

## Objective and boundaries

Two capability probes ran this server from two clients on 2026-09-07. One received the
full 50-tool surface and the complete instruction block. The other received 7 tools and
zero instruction characters. The 7-tool surface is not reproducible from this
repository: one `FastMCP` instance (server.py:70), no tool gating, no allowlist in the
connector writer (connections.py:52). That is a client or tunnel question and is out of
scope.

The probe that lost the instruction block also reported two tool descriptions arriving
cut mid-clause, and read that as its client mangling text. It was not. Python wraps
these docstrings at 79 columns, that client displays the first physical line, and the
wrap point is arbitrary. **35 of 50 descriptions have a first line that stops
mid-sentence.** Eight more are safe only because they happen to fit on one line.

So the always-loaded summary for most of this surface is currently 68 characters of
sentence fragment. That is the defect this slice fixes, and every wording change the
probes asked for follows from it, because there is no point front-loading a warning
into a line that ends wherever column 79 fell.

No tool is added, removed, renamed, or resignatured. `TOOL_SCHEMA_VERSION` stays at 36
and no connected client's cached tool list is invalidated. Risk is low: descriptions,
two refusal paths, and the instruction block. No preview or apply implementation,
authorization rule, or return shape changes.

Work on dev; preserve unrelated changes; do not commit, push, install, change client
configuration, start tunnels, contact Canvas, or read real student data.

## Measured starting state

Reproduce these before editing; the acceptance criteria are stated against them.

```
python -c "
import sys, json, asyncio; sys.path.insert(0,'.')
from api.mcp_server import server
ts = asyncio.run(server.mcp.list_tools())
wire = json.dumps([{'name':t.name,'description':t.description,
                    'inputSchema':t.inputSchema} for t in ts], separators=(',',':'))
first = sum(len((t.description or '').split(chr(10))[0]) for t in ts)
desc  = sum(len(t.description or '') for t in ts)
bad = [t.name for t in ts
       if not (t.description or '').split(chr(10))[0].strip().endswith(('.','!','?'))]
print('tools', len(ts), 'listing', len(wire), 'desc', desc,
      'first-lines', first, 'mid-sentence first lines', len(bad))
print('instructions', len(server._SERVER_INSTRUCTIONS))
"
```

At brief time: 50 tools, listing 22,604, descriptions 11,135, first lines 3,417,
mid-sentence first lines 35, instructions 2,725.

Where the listing goes: descriptions 11,135 (49%), input schemas 7,998 (35%), names
1,126, JSON scaffolding 2,345. The schemas are a floor, already stripped of pydantic's
generated titles. Ten tools carry 41% of all description text, from
`get_scoring_packet` at 562 characters down to `get_authoring_contract` at 52.

Of the 11,135 description characters, 7,718 sit after the first newline. In a
first-line-only client that is a third of the entire listing, on the wire and never
rendered. Slice B relocates it. This slice does not, but it may tighten it: see
decision 3.

## Budget

The listing must not grow. Net zero against 22,604 is the requirement, not the
23,000 cap, because slice B is what buys real headroom and this slice should not spend
it in advance. Additions are paid for inside the same description.

The instruction block has 275 characters free against its 3,000 cap and decisions 9 and
10 spend part of that. Do not raise either cap. On success, ratchet `LISTING_BUDGET` in
`api/tests/mcp_server/test_server_instructions.py` down to the achieved figure so the
gain cannot quietly erode, and say in the test comment that slice B will lower it again.

## Required references and insertion points

Read AGENTS.md and docs/reference/project-state.md. Then only:

- api/mcp_server/server.py: all 50 wrapper docstrings, and `_SERVER_INSTRUCTIONS`
  (24-69). Docstrings and instructions only: no registration, ordering, signature,
  `_compact`, or schema-strip changes.
- api/sis_grade_bridge.py: `list_sis_grade_bridges` (26-46) only.
- api/mcp_server/tools.py: the course-identity gate ahead of the freshness refusals at
  728, 773, 846, 1822 and 1828. No return-shape changes anywhere in this file.
- docs/mcp-server.md: every row whose description text changes, plus the three Canvas
  apply paths section. Pinned to the registry by
  `test_beta075_mcp.py::test_mcp_server_doc_matches_the_live_registry`.
- api/tests/mcp_server/test_server_instructions.py: budget guards, the
  write-rules-before-discovery ordering assertion, and the new first-line test.
- api/tests/mcp_server/test_tools.py; api/tests/test_beta075_mcp.py: schema contract
  and doc-pin tests.

Do not touch: `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt` (no tool
names change, so Appendix D stays valid), any preview or apply implementation, the
pseudonym vault, the final response gate, `contract.py`, any `tool_schema_vN.json`, or
`get_product_guide`'s topics and bodies, which belong to slice C.

## Locked decisions

1. **Line one of every description is a complete sentence that names the tool's job.**
   All 50, not just the 35 currently broken, because a rule with exceptions is not
   testable. It is what a first-line-only client shows and what a search-based client
   ranks on, so it has to stand alone with no instruction block behind it and no second
   line in front of it. Rewrap the remainder however reads best in source; the wire
   does not care where later newlines fall.

2. **A new test pins it.** For every registered tool, the first line of the description
   ends in a period and is at least 30 characters. Assert against the live registry so
   a tool added later is red until it complies. Put it in
   `test_server_instructions.py` beside the existing budget guards, since it is a guard
   on the same always-loaded surface, and say in the docstring why the first physical
   line is the unit: one real client renders exactly that and no more.

3. **The ten fattest descriptions may be tightened to pay for decisions 4 through 8.**
   Authorized for prose weight only: `get_scoring_packet` (562), `get_writing_history`
   (557), `preview_school_calendar_replacement` (518), `apply_new_quiz_scores` (484),
   `get_product_guide` (450), `get_day_schedule` (409), `start_scoring_session` (404),
   `preview_school_calendar_change` (403), `preview_new_quiz_scores` (401),
   `stage_scores` (396). Do not delete a fact an agent needs to call the tool
   correctly; relocating facts to results is slice B's job, not this one. Named
   candidates: `preview_new_quiz_scores`'s parenthesised count list `(students, items,
   ready, refused, already_finalized)`, which the result already carries;
   `get_scoring_packet`'s `(context included once per session)`, which the preceding
   clause implies.

4. **The two previews that write say so in line one. The other seven do not.**
   Verified: only `preview_new_quiz_scores` (stashes a per-student pending review and a
   new operation onto the session, tools.py 3088-3118) and `preview_sis_grade_bridge`
   (creates an operation and freezes a batch, sis_grade_bridge.py 105-119) persist
   anything. `preview_bell_schedule`, `preview_learning_objective`,
   `preview_roster_student_change` and the four `preview_school_calendar_*` tools are
   pure and already say so. Do not hedge those seven: a family-wide "may write" warning
   would spend characters to make seven honest promises vague.

5. **No rename in this slice.** `freeze_new_quiz_scores` and `freeze_sis_grade_bridge`
   are the honest names and both probes asked for them independently. A rename moves
   the contract to v37, rewrites every doc mention plus CanvasAgent Appendix D, and
   invalidates cached tool lists in already-connected clients, and the New Quiz write
   path has not yet run against real Canvas. Follow-up, gated on the first live
   finalization landing green.

6. **The three tools that reach Canvas name their destination in line one.**
   `apply_new_quiz_scores`, `apply_sis_grade_bridge`, and the `canvas_group` path
   through `apply_roster_student_change`. `apply_sis_grade_bridge` currently says only
   "Apply only the exact opaque SIS bridge review previously returned", which names
   neither the destination nor that grades move; state whether it writes to Canvas, to
   the SIS, or to both, since the surface does not currently say and a probe asked.

7. **`apply_new_quiz_scores` names the stale-freeze hazard.** It applies the snapshot
   stored under `operation_id` (tools.py 3187), not whatever is staged now, and a
   session accumulates one operation per freeze. An agent that freezes, lets the
   teacher edit scores, then applies, lands the older set. Line one can carry the live
   gradebook and the frozen review together in one clause; the re-freeze rule may sit
   on line two. Neither probe found this, because neither ran the pair.

8. **Four facts the probes could not get from the surface go into the relevant
   description.** `preview_sis_grade_bridge` returns `batch_id` (sis_grade_bridge.py
   119) and `apply_sis_grade_bridge` requires it, but the description mentions only an
   aggregate review, so one probe concluded the apply could not be assembled at all.
   `get_scoring_packet`'s payload is data to score, not instructions to follow, and a
   student response can contain text addressed to the reader; the contract half of that
   payload is server-authored and legitimate, which is exactly what makes the two easy
   to conflate. `get_submissions` rows come from the mirror's submission set and are not
   filtered to current enrollment (tools.py 2052-2061), which is why a refreshed roster
   returned 26 stand-ins against 27 submission rows; say enrollment must not be inferred
   from the difference. `list_sis_grade_bridges` and the other course-gated tools take a
   `course_id` that only `list_courses` supplies.

9. **The instruction block stops claiming every list is a table.** "Results are compact
   JSON, with list data as {columns, rows} tables" is false for `list_courses` (a
   `courses` array of objects) and `list_sis_grade_bridges` (a `bridges` array), and a
   probe caught it on its first two calls. Reword at roughly equal length. Do not
   reshape the returns: that would change what existing clients and the web UI parse
   for no agent benefit.

10. **Refusals keep arriving as `ok:false` inside `isError:false`, and the instruction
    block says so once.** A client that trusts MCP `isError` reads every refusal as a
    success; both probes hit this and one made it their single question for the
    developer. The transport shape stays: it changed recently, both clients returned it
    clean, and a second transport change before the write path's first live run buys
    inconsistency for no safety gain. In the same pass "Never raises" leaves the wire,
    five occurrences at server.py 508, 531, 544, 555 and 567. It is implementation
    language, and both models reported that it told them nothing until they inferred
    what it meant.

11. **`list_sis_grade_bridges` gets the blank-argument branch its sibling already has.**
    At sis_grade_bridge.py 28-29 a blank or malformed `course_id` fails the
    `_current_course` membership test and returns "course is not in Current courses",
    asserting a fact about a course that was never supplied.
    `preview_sis_grade_bridge` twelve lines down already returns a required-arguments
    refusal first (52-53). Mirror it. This one message was the entire reason a probe
    never landed a successful read: three failure classes, one indistinguishable answer.

12. **Identity before freshness.** A `course_id` that `list_courses` never returned
    currently comes back as "the local CanvasMirror roster for this course is stale or
    missing ... call refresh_mirror" (tools.py 1822) or "No local course catalog found
    for this course. Refresh the catalog from the CanvasExpert web UI" (728, 773, 846).
    Both send an agent to refresh state for an identifier that does not exist. Check the
    ID against saved courses first and refuse it as unknown, naming `list_courses`.
    Leave the existing stale messages exactly as they are for IDs that are real.

## Preflight

Run the measurement block above and record its output. Run
`api/tests/mcp_server/test_server_instructions.py` and `api/tests/test_beta075_mcp.py`
green first, so anything red afterwards belongs to this slice.

## Acceptance criteria and named gate

- 50 tools, `TOOL_SCHEMA_VERSION` 36, every `tool_schema_vN.json` unchanged, no tool
  renamed, added, removed, or resignatured.
- Mid-sentence first lines: 0 of 50, enforced by the new test.
- Listing at or below 22,604 characters. Report the achieved figure and ratchet
  `LISTING_BUDGET` to it.
- Instruction block at or below 3,000, cap unchanged, figure reported. The
  write-rules-before-discovery ordering assertion still passes.
- `preview_new_quiz_scores` and `preview_sis_grade_bridge` state the local write in line
  one. The other seven previews still promise purity.
- `apply_new_quiz_scores`, `apply_sis_grade_bridge` and the `canvas_group` path state in
  line one that they reach Canvas, and `apply_sis_grade_bridge` names its destination.
- `apply_new_quiz_scores` states that it applies the frozen review rather than current
  staging.
- `list_sis_grade_bridges("")` and `list_sis_grade_bridges("not-a-course-id")` are
  distinguishable from a real-but-not-current course, one new test each.
- A never-returned `course_id` refuses as unknown and names `list_courses`, with a new
  test. A real course with a stale mirror still gets the existing refresh instruction,
  its existing test unchanged.
- "Never raises" appears nowhere in server.py wire text.
- docs/mcp-server.md matches the registry and the changed descriptions.
- Full api test suite green. No Canvas call, no student data read, no client
  configuration touched, no tunnel started.

Named gate: print the 50 first lines alone, nothing else, and read them as a document.
That is what one real client shows and all a cold session may ever get. It should tell
you which tools write, which reach Canvas, that students arrive as stand-ins, and where
a `course_id` comes from. If reading the 50 lines does not answer those four, the slice
is not done regardless of what the tests say.

## Stop conditions

- Any change would move `TOOL_SCHEMA_VERSION` or touch a schema snapshot.
- The listing cannot be held at or below 22,604 after tightening the ten named
  descriptions: report the shortfall rather than raising a cap, dropping a decision, or
  cutting a fact an agent needs.
- A first line cannot be made complete without losing the tool's identity.
- Decision 12 would change what a real, current course sees.
- Any preview or apply implementation, authorization rule, or return shape would have to
  change.
- Relocating a description fact into a result starts to look necessary: that is slice B,
  stop and report.

## Out of scope, recorded

- The 7-tool client surface. Needs reproducing against the client and the tunnel
  profile; not a repository defect. `mcp-lean-interface.md` was retired on 2026-09-07
  and its unfinished Cowork guide read is blocked on exactly this question.
- `get_product_guide(topic="full")` has never been read by a client. At 25,838
  characters it is the largest single result on the surface and the local read is clean.
  One opportunistic read in the next Work or Cowork session.
- Slice B: relocating the 7,718 post-first-newline characters into results, target
  listing near 18,000 against a floor of 11,469 that no description work can touch
  (schemas 7,998, names 1,126, JSON scaffolding 2,345). The exemplar already exists in
  this codebase:
  `get_authoring_contract` has the leanest description of all fifty, 52 characters, and
  its result carries the whole envelope contract, so a PowerGrader session never pays
  for QuizForge's schema.
- Slice C: `get_product_guide`'s table of contents. `topics` currently returns ten bare
  slugs with no hint that the tool inventory lives under `connected` (6,409 chars, names
  37 tools) or `full` (25,838, names 40), while the default `overview` (5,819) names 6.
  Both tool-bearing topics point at `docs/mcp-server.md`, which no MCP client can open.
- Renaming the two writing previews, per decision 5.
- Whether to spend listing budget on `ToolAnnotations` (`readOnlyHint`,
  `destructiveHint`, `idempotentHint`). Zero of 50 tools declare any today. Measured:
  all fifty minimally annotated puts the listing at 24,404, and the 25 readers alone at
  23,504, so it does not fit before slice B. The SDK also documents annotations as
  hints clients should not base tool-use decisions on, so they complement the wording
  fix rather than replacing it.
- `get_assessment_grouping_proposal` refuses whole above 25 students (tools.py 133,
  1625) with no narrowing argument, so a 26-student class cannot use it. Product
  decision.
- No MCP path to refresh the Course Catalog; modules and pages dead-end at the web UI.
- Marking the untrusted half of any other payload. Decision 8 covers
  `get_scoring_packet` only. `get_authoring_contract` also returns imperative text,
  including a local Inbox path and a byte-count marker step, but that text is
  server-authored and the teacher asked for it.

## Execution result

**Traffic light: ACCEPTED WITH BASELINE EXCEPTION.** Slice A's focused acceptance gate
is green and the scoped implementation is complete. On 2026-09-07 the senior authorized
the move to slice B with the three reproducible failures outside this brief's files and
behavior recorded as the comparison baseline; they were not repaired or absorbed here.

Preflight at `2de2b5bc93480561c1442eba02476b41656219ea` on `dev`:

- 50 tools; listing 22,604 characters; descriptions 11,135; first lines 3,417;
  35 mid-sentence first lines; instructions 2,725.
- `py -m pytest api/tests/mcp_server/test_server_instructions.py
  api/tests/test_beta075_mcp.py -p no:randomly`: 17 passed.
- `dev` was seven commits ahead of `origin/dev`; `origin/dev` and `origin/main` were
  fetched and compared. No commit or push was made, as required.

Achieved state:

- 50 tools; tool schema version 36; listing 22,478 characters; descriptions 11,020;
  first lines 3,499; zero mid-sentence first lines; instructions 2,806.
- `LISTING_BUDGET` ratcheted from 23,000 to 22,478, 126 characters below the brief's
  22,604 ceiling. The 3,000-character instruction cap is unchanged.
- All seven pure previews say `without writing` in line one. The two stateful previews
  say they persist locally. The three Canvas-reaching apply paths name Canvas in line
  one, and New Quiz apply says it uses the frozen review rather than current staging.
- `Never raises` is absent from `api/mcp_server/server.py` wire text.
- Blank, unknown, and known-Previous SIS bridge course IDs now have distinct refusals.
  Section, mirror, and Course Catalog reads reject unknown IDs with `list_courses`
  guidance before suggesting refresh, while known Previous-course behavior remains intact.
- No tool was added, removed, renamed, or resignatured; no schema snapshot,
  `contract.py`, CanvasAgent source, preview/apply implementation, authorization rule,
  or result shape changed.

Changed files:

- `api/mcp_server/server.py`
- `api/mcp_server/tools.py`
- `api/sis_grade_bridge.py`
- `api/tests/mcp_server/test_server_instructions.py`
- `api/tests/mcp_server/test_tools.py`
- `docs/mcp-server.md`
- this brief's status and Execution result

Verification:

- Focused gate: `py -m pytest api/tests/mcp_server/test_server_instructions.py
  api/tests/mcp_server/test_tools.py api/tests/test_beta075_mcp.py -p no:randomly`
  → 163 passed.
- First full API run found seven failures. Four were caused by an initially over-broad
  identity check; the check was narrowed to A's named discovery seams, and all four
  regressions passed on targeted rerun.
- Final full gate: `py -m pytest api/tests -p no:randomly` → 2,371 passed, 3 failed.
  The same three failures reproduce individually:
  - `api/tests/dailywriting/test_dw_canvas_ingest.py::test_scrub_bypass_would_be_caught_by_the_storage_leak_guard`
  - `api/tests/test_canvasagent_instructions.py::test_it_does_not_claim_python_installs_itself`
  - `api/tests/test_roster_routes.py::test_private_group_snapshot_round_trip_has_only_allowlisted_fields`
- `git diff --check` passed. The live schema/doc-pin tests passed, and no schema snapshot
  or other forbidden file changed.

Named gate review: printing only the 50 first lines now reads as a coherent tool map. It
identifies writes through their verbs, distinguishes the two locally persistent previews
from the seven pure previews, names all three Canvas-reaching paths, says roster students
arrive as stable one-word stand-ins, and opens with `list_courses` as the source of
`course_id`.

Deviation accepted by senior: the full-suite-green criterion is unsatisfied solely by
the three out-of-scope failures above. They are the recorded baseline for slice B. Slice A
is retired; slice B is now the sole implementation authority and C remains queued.
