# MCP surface legibility, slice C: the guide becomes a table of contents

Status: GREEN against the accepted A/B baseline, implemented 2026-09-07; awaiting
senior acceptance. The same three reproducible, out-of-scope full-suite failures remain
the comparison baseline.

Do not start before B's execution result is filled in. B lowers the listing and
ratchets `LISTING_BUDGET`; two of C's decisions lower it again from B's figure, so C
re-measures rather than trusting anything written here.

## Objective and boundaries

Slices A and B fixed the always-loaded layer. This one fixes the layer an agent reaches
next, and it closes the question that started this arc: is there one place an agent can
go to learn there are 50 tools and where to find out more?

Today, almost. `get_product_guide` already self-advertises: every response returns a
`topics` list, and the tool's own description says so, which means an agent that has
only its tool list can still find the guide without the instruction block. That is the
right architecture and it survives the client that dropped everything else. Three
things are missing from it.

**The table of contents has no contents.** `topics` is `list(_GUIDE_FILES)`
(tools.py:1124), ten bare slugs. Nothing tells an agent that the tool inventory lives
under `connected` rather than `overview` or `full`. It has to guess or fetch all ten.

**No topic inventories the tools.** `connected` names 37 of 50, `full` names 40, and
the default `overview` names 6. There is no complete list anywhere an agent can reach.

**The deepest layer points out of the protocol.** Appendix D line 246 reads "The full
tool list is in docs/mcp-server.md." That file is the genuine per-tool reference and is
pinned to the registry by a test, and no MCP client can open a file in this repository.
The probe that followed the trail said so: it was told where the full tool list was, and
that was the one place it was not allowed to look.

No tool is added, removed, renamed, or resignatured. `TOOL_SCHEMA_VERSION` stays at 36.
One topic is added, one result field changes shape, one appendix sentence changes, and
two descriptions shrink.

Work on dev; preserve unrelated changes; do not commit, push, install, change client
configuration, start tunnels, contact Canvas, or read real student data.

## Locked decisions

1. **A new topic, `tools`, that inventories all 50 by job, generated rather than
   written.** Hand-maintained inventories drift, and this one already has:
   Appendix D names 37 tools and its test
   (`test_beta075_mcp.py::test_canvasagent_appendix_d_tools_match_the_live_registry`)
   asserts only that the names it mentions still exist, not that it mentions them all,
   so it can silently fall behind and has.

2. **Generate it from the frozen contract, not from the live registry object.**
   `tools.py` imports neither `server` nor `contract` today, and `contract.py` imports
   only `json` and `pathlib`, so `from . import contract` in `tools.py` is safe.
   Importing `server` would be circular, since `server` imports `tools`. Use
   `contract.load_contract()`, which is already guaranteed to match the live registry by
   `test_beta075_mcp.py::test_live_mcp_schema_matches_versioned_contract`, so reading the
   snapshot is equivalent to reading the registry and cannot drift from it.

3. **The inventory carries names grouped by job, not descriptions.** Two reasons. The
   descriptions live in `server.py` docstrings, which `tools.py` cannot reach without
   the circular import above. More importantly, the agent already has every description
   in its tool list, and after slice A each one opens with a complete sentence. What an
   agent lacks is the map, so the map is what this topic supplies. Do not restate a
   description here, in either direction.

4. **The grouping table is pinned for completeness.** Assert that the union of the
   groups equals the contract's tool names exactly, with no tool in two groups and none
   missing. A tool added later is then red until someone places it. This is the guard
   Appendix D never had, and it is the whole reason this decision is worth its code.

5. **Group names reuse Appendix B's surface vocabulary wherever a surface has tools.**
   Appendix B already names the surfaces a teacher sees in the UI: Create and Forge,
   PowerGrader, SIS Grade Bridges, Learning Objectives, School Calendar, Writing
   Timeline, Writing Record, Students, Seating, Assessments and DataForge. Reuse those
   names rather than inventing a parallel taxonomy for agents, so the inventory and the
   guide describe the product the same way. Appendix B's remaining surfaces (Home,
   Speed, Routines, Gradebook tools, Privacy) have no MCP tools and get no group. Course
   discovery and the catalog reads have no Appendix B surface of their own and need one
   group that Appendix B does not name; name it plainly and note the exception in the
   code comment so it does not read as an oversight.

6. **`topics` becomes annotated.** Replace the bare slug list with a compact object
   mapping each topic to a one-line summary of what is in it, so the reader can pick a
   topic without fetching it. Use an object rather than a list of two-key objects: this
   ships on every guide response and the object form is materially smaller. Order is the
   declaration order of `_GUIDE_FILES`, which is deliberate; preserve it.

   Exactly one test reads the current shape, `test_tools.py:594`
   (`assert result["topics"] == list(tools._GUIDE_FILES)`). Update it to assert the new
   shape and the completeness of the summaries. Do not loosen it to a membership check.

7. **The unknown-topic refusal stays consistent with the list.** It already enumerates
   every topic (tools.py 1108-1112) and is therefore a second table of contents. It
   should not disagree with the annotated one about what exists.

8. **The outward pointer turns inward.** Appendix D line 246 stops naming
   `docs/mcp-server.md` and names `get_product_guide(topic="tools")` instead.
   `docs/mcp-server.md` stays exactly as it is and stays pinned: it remains the
   reference for people reading this repository. It just stops being what an agent is
   told to open.

   Editing Appendix D is low risk. The guide text is read verbatim from
   `api/default_docs/AI Authoring/` in the repository at tools.py:1012, not from a copy
   seeded into a teacher's workspace, so there is no seeded-file hash to update for this
   read path. The appendix extraction laws still apply: heading order and spelling are
   load-bearing, so change prose inside Appendix D and leave its heading alone.

9. **Two descriptions deferred from slice B come due here.**
   `get_product_guide`'s own description is 450 characters and spends most of them
   enumerating topics that every response already returns, which the description itself
   admits ("Every response lists all available topics"). With decision 6 in place that
   enumeration is pure duplication: cut it, keep the identity sentence and the default
   behaviour, target near 150. `get_writing_history` closes with "Call
   get_product_guide(topic=\"writing_record\") first if unsure this exists", roughly 70
   characters that exist only because the table of contents was unreadable; once
   `writing_record` carries a summary, delete it.

10. **Ratchet the listing guard again.** Decision 9 lowers the listing below B's
    achieved figure. Report the new number and lower `LISTING_BUDGET` to it. Slice A's
    first-line test and B's per-description maximum both stay and must still pass:
    shortening `get_product_guide` must not break its opening sentence.

## Risk

The topic count goes from ten to eleven. No test hardcodes ten, verified against
`test_tools.py`, `test_server_instructions.py` and `test_beta075_mcp.py`, so the count
itself should break nothing.

`_GUIDE_FILES` currently maps a topic to a filename, and `tools` has no file. Do not
give it a placeholder filename to keep the shape uniform. Make the topic registry's
value a source that is either a file or the generated inventory, and say so where it is
declared, so nobody later reads a fake path as real.

The appendix extraction path (`_read_canvasagent_topic`) rejects missing, duplicate and
out-of-order headings by design. Prose edits inside Appendix D are safe; anything that
touches a heading is not.

## Required references and insertion points

Read AGENTS.md and docs/reference/project-state.md, then slices A and B's execution
results for the current figures. Then only:

- api/mcp_server/tools.py: `_GUIDE_FILES` (980), `_DEFAULT_GUIDE_TOPIC` (992),
  `get_product_guide` (1098-1124) including its refusal branch, and the new grouping
  table and inventory builder. No changes to `_read_authoring_doc`,
  `_read_canvasagent_topic`, gating, pseudonymization, or the final response gate.
- api/mcp_server/server.py: the `get_product_guide` and `get_writing_history` wrapper
  docstrings only. Line one of each is slice A's and stays intact.
- api/mcp_server/contract.py: read-only. Import it; do not change it.
- api/default_docs/AI Authoring/START HERE - CanvasAgent.txt: Appendix D prose only,
  line 246 and its immediate context. Do not touch any Appendix heading, and do not
  touch Appendices A, B, C, E, F or G.
- api/tests/mcp_server/test_tools.py: the `topics` assertion at 594 and the guide tests
  around 587-697.
- api/tests/mcp_server/test_server_instructions.py: the listing ratchet.
- api/tests/test_beta075_mcp.py: the Appendix D tool-name test and the schema contract
  test.
- docs/mcp-server.md: rows for the two changed descriptions, and the guide section if it
  describes the topic list.

Do not touch: `_SERVER_INSTRUCTIONS`; any other tool description; any preview or apply
implementation; any `tool_schema_vN.json`; the web UI download route, which shares the
same source file and must keep serving it unchanged.

## Preflight

Re-run slice A's measurement block and record post-B figures. Record the current topic
list and the count of tools named in `connected`, `full` and `overview` (37, 40 and 6 at
brief time) so the inventory's improvement is measurable. Run `api/tests/mcp_server` and
`api/tests/test_beta075_mcp.py` green first.

## Acceptance criteria and named gate

- 50 tools, `TOOL_SCHEMA_VERSION` 36, every `tool_schema_vN.json` unchanged.
- Eleven topics. `topics` returns a summary for every one of them, and the unknown-topic
  refusal agrees with that list.
- `topic="tools"` names all 50 tools, each in exactly one group, and the completeness
  test from decision 4 fails when a tool is added without a group. Prove it by
  temporarily registering a throwaway tool in a test, not by editing the registry.
- No group is empty, and no group name conflicts with an Appendix B surface that has no
  tools.
- Neither the inventory nor any description points at `docs/mcp-server.md` or any other
  repository path. Grep for it.
- Listing below B's achieved figure; report and ratchet `LISTING_BUDGET`. Slice A's
  first-line test and B's per-description maximum still pass unchanged.
- `docs/mcp-server.md` still matches the registry.
- Full api test suite green. No Canvas call, no student data read, no client
  configuration touched, no tunnel started.

Named gate: run the trail a cold session actually has to run, with the instruction block
assumed absent. From the tool list alone, reach `get_product_guide`; call it bare; from
the annotated `topics` alone, work out that an inventory exists and which topic holds
it; call that topic; from the group names alone, land on the right tools for scoring a
stack of writing. Then confirm the same session never had to load QuizForge's authoring
contract to get there. If any step needs a fact that lives only in the instruction block
or only in this repository, the slice is not done.

## Stop conditions

- Making the inventory complete would require importing `server` into `tools`, or any
  other circular import.
- The grouping cannot cover all 50 tools without a group that means nothing to a
  teacher: report the leftovers rather than inventing a bucket.
- An Appendix heading would have to change, or the extraction laws reject the edited
  appendix.
- `topics`' new shape breaks more than the one test named in decision 6.
- The web UI download of the same source file changes in any way.
- The listing cannot be held below B's achieved figure.

## Out of scope, recorded

- Consolidating `problems`, `state`, `attention`, `warnings` and `stale_note` into one
  advisory convention, carried from slice B.
- `ToolAnnotations`. This is the right moment to re-decide, since A, B and C together
  should leave real headroom where none existed: all fifty minimally annotated cost
  1,800 characters measured against the pre-A listing. Re-measure after C and treat it
  as its own decision, remembering the SDK documents annotations as hints a client
  should not base tool-use decisions on.
- Renaming the two writing previews, gated on the first live New Quiz finalization.
- The 7-tool client surface, and the still-unread
  `get_product_guide(topic="full")` at 25,838 characters.
- `get_assessment_grouping_proposal`'s 25-student ceiling, and the missing MCP path to
  refresh the Course Catalog. Product decisions, both recorded since the probes.
- Whether `overview` should itself change. It is Appendix B, 5,819 characters, and it
  reads as product surfaces rather than as a tool map. With `tools` carrying the map,
  leaving `overview` alone is the point, not an omission.

## Execution result

**Traffic light: GREEN against the accepted A/B baseline.** C's guide contract,
generated inventory, inward pointer, and listing ratchet are complete. The full API
checkpoint has exactly the same three accepted baseline failures and no new failure.

Preflight at the post-B tree on `dev`:

- 50 tools; schema version 36; listing 17,978 characters; descriptions 6,600;
  first lines 3,499; zero invalid first lines; longest description 343
  (`get_product_guide`); instructions 2,806; `LISTING_BUDGET` 17,978.
- Guide topics were the ten ordered slugs `overview`, `setup`, `chat_authoring`,
  `connected`, `privacy`, `troubleshooting`, `assessments`, `full`,
  `writing_timeline`, and `writing_record`.
- Existing tool discoverability was 37 names in `connected`, 40 in `full`, and 6 in
  `overview`.
- `py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py -p no:randomly`
  -> 199 passed before slice-C edits.

Achieved state:

- 11 annotated topics now return as an ordered object of one-line summaries on every
  successful guide response. The unknown-topic refusal uses the same ordered registry.
- `topic="tools"` is generated at call time from `contract.load_contract()` and emits
  all 50 schema-v36 tool names exactly once across 11 non-empty teacher-facing groups.
  The grouping validator rejects duplicate, missing, unknown, or empty memberships;
  a test registers a temporary throwaway tool and proves an unplaced name fails.
- The listing is 17,717 characters; `LISTING_BUDGET` is ratcheted to 17,717. The
  description total is 6,345, first-line total remains 3,499, zero first lines are
  invalid, the longest description is now 280 (`get_submissions`), and instructions
  remain 2,806. Slice A's first-line and B's 343-character maximum tests still pass.
- Appendix D now routes agents to `get_product_guide(topic="tools")`; neither the
  generated inventory nor the two changed descriptions names `docs/mcp-server.md` or
  a repository path. The guide/download route still serves the same canonical source
  bytes for `full` and `writing_timeline`.
- `get_product_guide` and `get_writing_history` wrapper descriptions were shortened
  only after their preserved first sentences. The overview, all other tool descriptions,
  guide extraction, web download route, instruction block, schemas, authorization, and
  final response gate were not changed.

Changed files for slice C:

- `api/mcp_server/tools.py`
- `api/mcp_server/server.py`
- `api/tests/mcp_server/test_tools.py`
- `api/tests/mcp_server/test_server_instructions.py`
- `api/tests/test_beta075_mcp.py`
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt` (Appendix D prose only)
- `docs/mcp-server.md`
- this brief, plus the slice-B status transition to retired/accepted

Verification:

- Focused C gate: `py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py
  -p no:randomly` -> 202 passed.
- Full checkpoint: `py -m pytest api/tests -p no:randomly` -> 2,377 passed,
  3 failed. The failures are exactly the accepted A/B baseline:
  - `api/tests/dailywriting/test_dw_canvas_ingest.py::test_scrub_bypass_would_be_caught_by_the_storage_leak_guard`
  - `api/tests/test_canvasagent_instructions.py::test_it_does_not_claim_python_installs_itself`
  - `api/tests/test_roster_routes.py::test_private_group_snapshot_round_trip_has_only_allowlisted_fields`
- `git diff --check` passed (line-ending warnings only). `contract.py` and every
  `tool_schema_vN.json` remain unchanged. No commit or push was made.

Cold-session trail with the instruction block assumed absent:

1. The tool list's complete first line and schema identify `get_product_guide`; its
   bare call returns the annotated eleven-topic object.
2. The `tools` summary identifies the inventory topic; that call returns the generated
   50-name map, and the `PowerGrader` group lands directly on the scoring tools.
3. The trail never needs `get_authoring_contract`, an instruction-block hint, or a
   repository path. The generated inventory has no student data and no external path.

The grouping boundary choices that cross product vocabulary are explicit in code
comments: course discovery/catalog owns section discovery and mirror refresh, Create and
Forge owns guide selection and staging, PowerGrader owns the gradebook snapshot,
Writing Timeline owns mirror submissions, and School Calendar owns bell and teacher
schedule inputs. No new taxonomy bucket was invented beyond the one required plainly
named course-discovery/catalog exception.
