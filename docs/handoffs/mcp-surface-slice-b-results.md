# MCP surface legibility, slice B: detail moves to the result that needs it

Status: RETIRED, accepted 2026-09-07. The senior accepted the GREEN result against
slice A's three reproducible, out-of-scope baseline failures and authorized slice C.

Do not start this before A is done and its execution result is filled in. A rewrites
all 50 first lines and ratchets `LISTING_BUDGET`, so every figure below moves. B's
preflight re-measures rather than trusting this brief's numbers.

## Objective and boundaries

Slice A made the always-loaded line of each tool a complete sentence. This slice
addresses what sits behind it. Of 11,135 characters of description, 7,718 come after
the first newline, and in a client that renders only the first physical line all of
that is on the wire and never seen. It is paid for on every connection and read by
some clients only.

Most of it should not be in a description at all. It is either a restatement of what
the result already contains, or instructions for what to do once the result is in
hand. Results are unbudgeted: `get_product_guide(topic="full")` is already 25,838
characters, larger than the entire tool listing, and costs nothing until something
calls it.

The exemplar is already in this repository. `get_authoring_contract` has the leanest
description of all fifty, 52 characters, and its result carries the whole envelope
contract, the Inbox path, and the marker-file procedure. A PowerGrader session never
pays for QuizForge's schema. That is the shape every fat tool should take.

No tool is added, removed, renamed, or resignatured. `TOOL_SCHEMA_VERSION` stays at
36: the frozen contract records input property types and required lists, and neither
moves here. Unlike slice A, this slice does change some result payloads, which is the
main risk and is bounded below.

Work on dev; preserve unrelated changes; do not commit, push, install, change client
configuration, start tunnels, contact Canvas, or read real student data.

## Correction to the target figure

Earlier planning named 14,000 characters as the goal. That was wrong and this brief
supersedes it. The listing has a floor that no description work can touch:

```
input schemas       7,998
tool names          1,126
JSON scaffolding    2,345
                   ------
floor              11,469
```

Reaching 14,000 would leave 2,531 characters for 50 descriptions, about 51 each, which
cannot hold a complete identity sentence plus a safety clause. The honest target is the
floor plus roughly 6,500 of description, so **about 18,000, a cut near 4,600 from
22,604**. Anything below 17,000 should be treated as suspicious rather than excellent:
check what fact went missing.

## The rule

Apply this to every sentence after line one, in all 50 descriptions. The material
change lands in about fifteen tools; the rest will already comply.

1. **Does an agent need it before calling, to decide whether this is the right tool or
   to build its arguments?** It stays in the description. Argument formats, defaults
   that are not in the schema, which of two similar tools to reach for, and anything
   about consequence. Before the call is the only moment this text helps.

2. **Does the result already show it?** Delete it. Field names are the documentation.
   A description that enumerates its own return keys pays for them on every connection
   so that an agent can read them a second time.

3. **Is it what to do with the result once you have it?** Move it into the result.
   Paging advice, coordinate handoffs, next-tool routing.

Where a sentence is genuinely two of these, split it rather than compromising.

## The consequence and procedure split

This is how B stays consistent with A rather than undoing it. Slice A put consequence
in line one because a client may deliver no instruction block and no second line. That
does not change.

- **Consequence stays before the call.** This writes. This reaches the live Canvas
  gradebook. This is the frozen review, not current staging. Students arrive as
  stand-ins.
- **Procedure moves after the call.** Summarize the preview to the teacher and get
  confirmation. Pass `base_revision` back as `expected_revision`. Use
  `include_context=false` on later pages.

An agent that reads only line one still cannot call a write blindly. An agent that has
called and is holding a result now gets the procedure exactly where it applies, and it
reaches clients that never render a second line at all.

## Locked decisions

1. **One new advisory key, `next`, for relocated procedure only.** The codebase already
   carries `problems` (25 uses), `state` (23), `attention` (3), `warnings` (2), and a
   conditional `stale_note` (tools.py 823, 868). Overloading `problems` with things
   that are not problems is worse than adding a key, and inventing a general-purpose
   fifth advisory channel is worse than a specific one. `next` is a plain string, holds
   procedure only, never student data, and never a condition or an error. Consolidating
   the existing four is a separate cleanup and is out of scope.

2. **`next` goes on a bounded list of tools:** `get_scoring_packet` and
   `start_scoring_session` for paging and routing, and the nine `preview_*` tools for
   the confirm-then-apply handoff and its coordinates. Do not add it anywhere else in
   this slice.

3. **`get_product_guide` is slice C's, not this slice's.** Its description
   (450 characters) enumerates topics that every response already returns in `topics`,
   and the description even says so, so it is pure duplication and an obvious target.
   Leave it alone anyway: C is redesigning that envelope and two people editing the
   same tool is how a merge goes wrong. Record the saving, do not take it.

4. **Worked examples.** These four are the analysis, not illustrations. Apply the same
   treatment to the rest.

   **`get_scoring_packet`, 562 characters.** Identity sentence stays. "Returns items
   (prompts, deduplicated) and students (responses, text-only, no media)" is rule 2,
   delete. The paging gotcha, that a multi-item quiz gives one student several rows and
   `total` counts rows while `students_total` counts people, is rule 3: move to the
   result beside those two counts, where the numbers that confuse an agent are sitting.
   "Set include_context=false on later pages" is rule 3, move to `next`. "Projected
   payload is returned as estimated_tokens; refuses over 25,000 tokens with a workable
   smaller limit" is rule 2 twice over: `estimated_tokens` is a returned field, and
   `PacketTooLarge` already carries the workable retry in the message that
   `{"ok": False, "error": str(e)}` hands back (scoring_packet.py 22-25, tools.py
   2773). Keep "Course-gated." Keep the untrusted-content clause slice A added; it is
   consequence. Target near 180.

   **`preview_school_calendar_replacement`, 518.** Identity and the semantics of what
   every date in coverage becomes stay: an agent needs both before it calls. "Returns
   the base revision (0 for a first-ever calendar), current vs. proposed school year
   and coverage, and material change counts" is rule 2, delete. "Summarize this to the
   teacher and get their confirmation before calling apply_school_calendar_replacement
   with its base_revision as expected_revision" is the model case for rule 3: it is
   useless before the call and essential after it, and moving it to `next` puts it next
   to the revision it names. Target near 230.

   **`get_day_schedule`, 409.** Identity stays and `date is YYYY-MM-DD` stays. The
   seven-value resolution enum is rule 2: the result returns the state. The block field
   list `{name, label, start, end, raw_periods, schedule_id, period_ids, segments,
   seq}` is rule 2 at its most literal. "Repeated blocks produce one entry per
   consecutive meeting run" stays: it is a semantic property of the data that no field
   name reveals. Target near 140.

   **`get_writing_history`, 557.** Identity stays. The returned-field list is rule 2,
   delete. "Writing Record does not score, coach, or judge work" stays, it is scope.
   `since`/`until` formats and the `include_text` semantics stay, rule 1. "No
   course_id" can compress to a short phrase since the absence is visible in the
   schema. The closing "Call get_product_guide(topic=\"writing_record\") first if
   unsure this exists" is slice C's to resolve; leave it. Target near 300.

5. **Ratchet both guards.** `LISTING_BUDGET` drops to the achieved figure. Add a
   per-description maximum set to the achieved longest description, so the fat tail
   cannot regrow one tool at a time. Slice A's first-line test stays exactly as it is
   and must still pass: shortening a description must not break its first sentence.

6. **`next` never carries student data and is asserted so.** It is a static or
   near-static string. Add it to the tests that walk every registered tool, and confirm
   the final response gate is unaffected: `_STUDENT_RESULT_KEYS` (tools.py 142-146) does
   not contain `next`, so a plain advisory string passes the structural gate. Do not
   add `next` to any result that already carries student rows unless the gate is
   re-checked for that tool specifically.

## Risk: result-shape changes

This is the one thing in the slice that can break something outside its own files.
A handful of tests assert exact result equality or exact key sets:

- `api/tests/mcp_server/test_tools.py:137` and `:147` (`list_courses`), `:565`
  (`get_authoring_contract`)
- `api/tests/mcp_server/test_standards_profile.py:46`
- `set(result)` assertions at `test_tools.py:1113`, `:1283`, `:1289`, `:1347`

None of those are tools that gain `next` under decision 2, so the expectation is that
none of them move. If one does, that is a signal the key went somewhere it was not
authorized, not a reason to edit the test.

Also check `api/tests/mcp_server/test_server_instructions.py`'s registry-driven
synthetic tests, which stub all 50 delegates and assert one gated text block per tool.
Those should be indifferent to payload keys, and if they are not, say so rather than
loosening them.

## Required references and insertion points

Read AGENTS.md and docs/reference/project-state.md, then slice A's execution result for
the post-A figures. Then only:

- api/mcp_server/server.py: the 50 wrapper docstrings. Line one of each is slice A's
  work and is not to be rewritten here beyond what shortening the remainder requires.
  `_SERVER_INSTRUCTIONS` is not touched in this slice.
- api/mcp_server/tools.py: the result builders for the eleven tools in decision 2, and
  the paging counts in `get_scoring_packet`. No changes to gating, pseudonymization, or
  the final response gate.
- api/tests/mcp_server/test_server_instructions.py: both ratchets and the `next`
  assertions.
- api/tests/mcp_server/test_tools.py and the per-feature test modules for the eleven
  tools whose results change.
- docs/mcp-server.md: every row whose description text changes, pinned by
  `test_beta075_mcp.py::test_mcp_server_doc_matches_the_live_registry`.

Do not touch: `get_product_guide`'s description, topics, or bodies (slice C); the
existing `problems`/`state`/`attention`/`warnings`/`stale_note` keys; any preview or
apply implementation or authorization rule; `contract.py`; any `tool_schema_vN.json`;
`api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`.

## Preflight

Re-run slice A's measurement block and record the post-A figures: tool count, listing,
description total, first-line total, longest description, and the ratcheted
`LISTING_BUDGET`. Run `api/tests/mcp_server` and `api/tests/test_beta075_mcp.py` green
first.

## Acceptance criteria and named gate

- 50 tools, `TOOL_SCHEMA_VERSION` 36, every `tool_schema_vN.json` unchanged.
- Listing at or below 18,000 characters and not below 17,000 without an explanation of
  what was removed. Report the achieved figure and ratchet `LISTING_BUDGET` to it.
- Zero mid-sentence first lines: slice A's test still passes unchanged.
- A per-description maximum test exists, set to the achieved longest description.
- `next` appears only on the eleven tools in decision 2, is a plain string, and carries
  no student data.
- No description enumerates its own return field names. Spot-check the ten formerly
  fattest by reading them.
- The four exact-equality and four key-set assertions listed under Risk are unchanged.
- Full api test suite green. No Canvas call, no student data read, no client
  configuration touched, no tunnel started.

Named gate: trace the three teacher jobs on paper using only each tool's first line
plus the schema to make the first call, then only the returned payload to decide the
second. Score a stack of writing, create a page, straighten next week's schedule. If a
job needs a fact that is now in neither place, the relocation went too far and that
fact comes back to the description. This is the same trace both probes ran, so their
reports are the comparison.

## Stop conditions

- The listing cannot reach 18,000 without deleting a fact rule 1 protects: report the
  figure reached and stop.
- Adding `next` changes a result that one of the listed tests asserts exactly.
- A relocation would put consequence after the call rather than before it: that
  inverts slice A and is not a judgment call to make here.
- Slice C's territory starts to look necessary, in `get_product_guide` or the guide
  bodies: stop and report.
- The final response gate needs any change to accommodate `next`.

## Out of scope, recorded

- Slice C: `get_product_guide`'s table of contents. `topics` returns ten bare slugs
  with no hint that the tool inventory lives under `connected` (6,409 characters, names
  37 tools) or `full` (25,838, names 40), while the default `overview` (5,819) names 6.
  Both tool-bearing topics point at `docs/mcp-server.md`, which no MCP client can open.
  C also inherits `get_product_guide`'s own 450-character description and
  `get_writing_history`'s closing pointer.
- Consolidating `problems`, `state`, `attention`, `warnings` and `stale_note` into a
  coherent advisory convention. Worth doing, not here.
- Renaming the two writing previews, gated on the first live New Quiz finalization.
- `ToolAnnotations`. After this slice the listing should have room that it does not
  have today: all fifty minimally annotated cost 1,800 characters when measured against
  the pre-A listing. Re-measure and re-decide once B has landed, remembering that the
  SDK documents annotations as hints a client should not base tool-use decisions on.
- The 7-tool client surface, and the unread `get_product_guide(topic="full")`.
- `get_assessment_grouping_proposal`'s 25-student ceiling and the missing MCP path to
  refresh the Course Catalog. Product decisions.

## Execution result

**Traffic light: GREEN against the accepted slice-A baseline.** Every slice-B behavior
and named gate is green, and the full API run has exactly the same three accepted,
out-of-scope failures as slice A with no new failure.

Preflight at `2de2b5bc93480561c1442eba02476b41656219ea` on `dev`:

- 50 tools; listing 22,478 characters; descriptions 11,020; first lines 3,499;
  zero mid-sentence first lines; longest description 502 (`get_writing_history`);
  instructions 2,806; `LISTING_BUDGET` 22,478.
- `py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py -p no:randomly`
  -> 196 passed before slice-B edits.

Achieved state:

- 50 tools; schema version 36; listing 17,978 characters; descriptions 6,600;
  first lines still 3,499; zero mid-sentence first lines; instructions still 2,806.
- `LISTING_BUDGET` ratcheted to 17,978. The new per-description maximum is 343,
  achieved by slice-C-owned `get_product_guide`, whose description and result bodies
  were not changed in this slice.
- Static plain-string `next` procedures appear on successful results from exactly the
  eleven authorized tools. Refusals do not gain `next`; the result allowlist is checked
  against all 50 registered tools, and every advisory passes the unchanged final
  structural response gate.
- The formerly fattest descriptions were read after shortening. Return-field
  inventories are gone; argument formats, selection facts, consequences, and the
  untrusted-response boundary remain before the call.
- No tool, name, signature, input schema, schema snapshot, contract version,
  instruction block, product-guide topic/body, CanvasAgent source, preview/apply
  authorization, pseudonymization path, or final response gate changed.

Changed files for slice B:

- `api/mcp_server/server.py`
- `api/mcp_server/tools.py`
- `api/tests/mcp_server/test_server_instructions.py`
- `api/tests/mcp_server/test_tools.py`
- `api/tests/mcp_server/test_start_scoring_session.py`
- `api/tests/mcp_server/test_sis_grade_bridge_tools.py`
- `api/tests/mcp_server/test_new_quiz_scoring_tools.py`
- `api/tests/test_scoring_packet_mcp.py`
- `api/tests/test_learning_objectives.py`
- `api/tests/test_roster_mcp_write.py`
- `docs/mcp-server.md`
- this brief, plus the slice-A status transition to retired/accepted

Verification:

- Focused result/listing/schema/doc gate: `py -m pytest api/tests/mcp_server
  api/tests/test_beta075_mcp.py api/tests/test_scoring_packet_mcp.py
  api/tests/test_learning_objectives.py api/tests/test_roster_mcp_write.py
  -p no:randomly` -> 260 passed.
- Full checkpoint: `py -m pytest api/tests -p no:randomly` -> 2,374 passed,
  3 failed. The failures are exactly slice A's accepted baseline:
  - `api/tests/dailywriting/test_dw_canvas_ingest.py::test_scrub_bypass_would_be_caught_by_the_storage_leak_guard`
  - `api/tests/test_canvasagent_instructions.py::test_it_does_not_claim_python_installs_itself`
  - `api/tests/test_roster_routes.py::test_private_group_snapshot_round_trip_has_only_allowlisted_fields`
- `git diff --check` passed (line-ending warnings only). `contract.py` and
  `tool_schema_v36.json` have no diff. No commit or push was made.

Named gate: all three paper traces close using the intended information boundary.
Scoring starts from the first line/schema, then the session result routes to the first
packet; packet `next` explains row/person counts, context-free paging, and staging.
Page creation starts from `get_authoring_contract` and its returned envelope/staging
procedure. A next-week schedule read starts from the Calendar/day schemas; a needed
change reaches a pure preview whose result supplies the confirm-then-apply coordinates.
No required fact was lost between first call and returned payload.

Implementation note, not a deviation: the initial result change exposed an exact-equality
test for `start_scoring_session` that the brief's risk list omitted; it was updated to the
authorized shape. Independent review also caught that learning-objective previews return
`current_revision`, not `base_revision`, so the advisory uses the real coordinate.
