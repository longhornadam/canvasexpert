# MCP lean interface

> **Retired, 2026-09-07.** Nothing here is implementation authority. The last open
> item, criterion F's external client checks, is closed out under "Execution result":
> the ChatGPT Work half is satisfied by that day's capability probe, and the Cowork
> half is blocked on a client tool-surface question that is not this brief's work and
> now sits in `mcp-surface-legibility.md`. Its write-policy decisions were already
> superseded by commits `277e9d2` and `5656dff`, so read the current
> `_SERVER_INSTRUCTIONS` and `docs/mcp-server.md` rather than decisions 5 and 6 below.
> Kept for the size measurements and the guide-routing decisions, which are still
> accurate. The annotations inline mark what changed.

Status: RETIRED, closed 2026-09-07. Local implementation accepted; external client
evidence recorded below.

## Objective and boundaries

Reduce redundant MCP wire content and return a useful, compact default product
guide without removing operations or hiding product capabilities. User approved
the direction on 2026-09-07 and requested Luna execution. Work on dev; preserve
unrelated changes; do not commit, push, install, change client configuration,
start tunnels, contact Canvas, or read real student data.

Risk: medium transport compatibility; documentation describes high-risk writes
but their implementation and authorization rules must not change.

## Required references and insertion points

Read AGENTS.md and docs/reference/project-state.md. Then only:
- api/mcp_server/server.py: registrations, _compact, schema-title normalization,
  _SERVER_INSTRUCTIONS and get_product_guide wrapper.
- api/mcp_server/tools.py: _GUIDE_FILES, _DEFAULT_GUIDE_TOPIC,
  _read_authoring_doc and get_product_guide. Do not change other tool functions.
- api/default_docs/AI Authoring/START HERE - CanvasAgent.txt: CORE and appendices
  A-G. This remains the single source for both full and sectioned guidance.
- docs/mcp-server.md: opening safety bullets, Tools table and the explanations
  of the three Canvas apply paths, get_product_guide, scoring, and Token-lean
  results (all before Running it). These own the actual write semantics.
- api/mcp_server/contract.py and tool_schema_v36.json: read-only input contract.
- api/tests/mcp_server/test_server_instructions.py;
  api/tests/mcp_server/test_tools.py: product-guide tests around lines 587-697
  and compact wrapper tests around 2176; api/tests/mcp_server/conftest.py;
  api/tests/mcp_server/test_standards_profile.py: default-guide assertion;
  api/tests/test_beta075_mcp.py: schema-contract test only.
- api/webui/routes/library.py: api_download_contract only, read-only to verify
  full download identity. Other guide files may be read only via tests.
- Installed MCP SDK source/signatures for FastMCP.tool, list_tools, call_tool,
  result conversion and in-memory protocol testing if needed.

Editable files: server.py, the named guide seams in tools.py, CanvasAgent.txt,
docs/mcp-server.md, the three named MCP test files and nearest conftest.py;
optionally api/tests/mcp_server/test_server.py for protocol laws/contracts.
Update this brief's Execution result. No other edits without senior direction.

## Locked decisions

1. Set structured_output=False explicitly on all 50 existing @mcp.tool
   registrations using the SDK's supported argument. No new decorator, subclass,
   dispatcher, registry framework, dependency, or post-hoc output-model patch.
   Keep str returns and _compact/final_response_gate intact. Keep input-title
   stripping, with accurate comments: wire size is not a per-turn token promise.
   All names, argument schemas/defaults and operations remain unchanged.
2. Default get_product_guide() and topic=overview serve Appendix B only. Make B
   a concise capability map, at most 7,000 characters, with actionable topic
   pointers. Keep the existing response keys ok/topic/topics/guide and topic
   trim/case normalization. No new tool or argument; keep schema version 36
   because its frozen contract describes names/inputs, not result transport.
3. Add topics sourced verbatim from the same CanvasAgent file: setup=A,
   chat_authoring=C, connected=D, privacy=E, troubleshooting=F, assessments=G,
   full=entire file. Keep writing_timeline and writing_record as their existing
   entire canonical files. Extend the small existing mapping, with a simple
   section mapping/helper; no generalized document framework. Extract exact
   section text including its heading up to the next appendix, with only outer
   whitespace stripping allowed. Missing, duplicate, or out-of-order expected
   appendix headings yield a structured error, never a silent full-guide fallback
   or partial wrong section. Every successful response advertises every topic.
4. B must preserve discovery of Create/Forge staging and offline print/export,
   differentiation, PowerGrader modes and MCP scoring, Learning Objectives,
   School Calendar/Teacher Schedule/bell schedules, Writing Timeline (tracked
   requires File Upload alone and docx alone, teacher chooses), Writing Record,
   Students/roster/group settings, Seating, Gradebook tools, Routines, Home,
   local freshness, DataForge/Assessments/profile/grouping, and SIS bridges.
   Distinguish app capabilities from tools. Include brief privacy facts (Identity
   Vault; pseudonymized, not anonymous; review SAFE artifacts) and the fact that
   Canvas writes are bounded reviewed operations; direct detailed workflow to
   connected and assessments topics. Do not reprint the tool listing in B.
5. Correct CORE/B/D contradictions using docs/mcp-server.md as authority:
   authored Forge content is staged for UI review/push; stage_scores alone never
   posts; New Quiz and SIS bridge preview/apply paths exist; roster canvas_group
   apply also reaches Canvas. New Quiz requires upstream staged scores. Preserve
   exact target-bounded preauthorization exceptions for New Quiz and SIS bridge,
   including all already-registered bridges; never generalize to roster or other
   writes.
   **Superseded by `5656dff`.** "Preauthorization exception" was the wrong frame:
   it made the teacher's own request an exception to a default of asking again.
   The teacher's ask is now the authorization, and the assistant runs the
   preview/apply pair and reports what landed. What survives is the target
   bounding, which this decision also names: one request covers the target the
   teacher named and does not carry to another assignment, course, family, or
   session. Do not restore the waiting default from this text. Other changes are local. Teacher Schedule save is direct local write;
   bell schedule has its own preview/apply pair. A preview may freeze local
   review state, so do not promise all previews change nothing. Keep revision,
   digest, review, and failure-stop rules. No workflow-policy expansion.
6. Keep A/C/E/F/G available; edit only stale topic/default references there if
   necessary. Keep CORE delimiter format and all text ASCII. Keep existing
   writing_timeline, writing_record, all Author a ... contracts, and Forge
   staging appendix unchanged. Keep _SERVER_INSTRUCTIONS unchanged.
   **Superseded by `5656dff`.** `_SERVER_INSTRUCTIONS` has since changed twice,
   for the write posture above and to move the SIS passback evidence rule onto
   its own tool. The Forge staging appendix also changed in `277e9d2`: it had
   ended with "You never write to Canvas", which is false. Treat both as live
   text, not frozen.
7. Document topic routing and text-only result transport in docs/mcp-server.md.
   Update the download-identity test so CanvasAgent download equals topic=full,
   and topic sections are extracted from that same source. No browser UI code
   changes or route loading required for this backend/text-only slice.

## Preflight

- Confirm dev, inspect git status, and preserve the senior-authored brief.
- Confirm 50 tools and live_contract equals frozen v36; inspect supported SDK
  structured_output flag. Capture complete current list_tools inputSchema per
  tool in memory or an untracked temporary file, not just normalized types.
- Record current minified serialized listing and get_product_guide protocol
  result sizes without printing the guide. Senior measured listing 27,439 chars,
  instructions 2,641, guide text 22,955, CallToolResult 48,129. A harmless
  in-memory registration experiment with structured_output=False gave listing
  22,589 and unchanged guide text in a 24,075-character CallToolResult.
- Run the named gate before edits to identify any existing focused failures.
  No full API/engine suite. Existing broader failures in pasted history are not
  new work to investigate.

## Acceptance criteria and named gate

A. All 50 names and full input schemas/defaults match preflight exactly; no
outputSchema advertised, and actual tools/call results contain exactly one text
block and no structuredContent. Use registry-driven synthetic testing at the
FastMCP/protocol boundary, stubbing tool delegates before side effects. Check
ordinary success, structured failure, Unicode/table content preservation and
final outbound gating. Do not call real read/write tools on private workspace
data. One canonical guide read is a permitted student-free happy path.

B. The actual minified listing is <=23,000 characters; instructions unchanged.
Report observed character sizes, not inferred tokenizer/client costs.

C. overview is exactly canonical B (<=7,000 chars), with all capabilities in
decision 4 discoverable. All specified topics are reachable, normalized and
advertised; full and existing writing-guide bodies match their canonical files.
Every section matches its canonical slice; missing/duplicate/out-of-order
headings and unknown topics fail explicitly. Use boundary/registry-driven tests,
one happy path and the applicable extraction laws, not a case per appendix.

D. Senior reviews CORE/B/D for consistency with the three existing Canvas apply
paths and their review requirements. Existing authoring contracts/staging and
privacy/write implementation remain unchanged. Tests of guide privacy facts
must still apply to the compact default, not be silently moved to full.

E. Named gate:
py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py::test_live_mcp_schema_matches_versioned_contract -p no:randomly -q
Use plain test functions; this slice does not decide global test class or
pytest-randomly house style. Add meaningful new tests in module-mirroring paths;
shared synthetic setup goes in the nearest conftest.py. Run git diff --check.

F. External client acceptance remains required before claiming deployment/client
compatibility: fresh post-change guide read in ChatGPT Work and Claude Cowork,
showing text-only results remain usable. Executor should report this as pending
senior/client evidence, not start or reconfigure either client. Local MCP SDK
protocol evidence is required now and is not a substitute for these checks.

> **Closed 2026-09-07.** ChatGPT Work: satisfied. Cowork: reassigned, not satisfied.
> See the close-out under "Execution result". No further work belongs to this brief.

## Stop conditions

Stop RED if the expected SDK/seam is absent, a tool cannot preserve its input or
result semantics, guide corrections require undocumented authorization choices,
or unrelated subsystem changes are required. Report YELLOW if a required check
is unavailable. Do not expand scope to fix unrelated failures. Ask the same
senior for narrow follow-up and reuse this executor for corrections.

## Execution result

Senior accepted local implementation on 2026-09-07 after reviewing the
transport, canonical guide routing, write-policy prose, and synthetic boundary
evidence. The same Luna executor completed the correction round. The focused
gate was not rerun by the senior; only missing schema evidence and a fresh
stdio smoke were independently checked. No implementation decision remains.

**Corrected 2026-09-07.** Two regressions survived that acceptance and were
found by running the full suite rather than the `api/tests/mcp_server/` subset:
CORE went 49 chars over its custom-instructions budget, and the write rule left
CORE entirely. Both are fixed in `fe6ac12`. Two follow-on wording defects were
fixed after that: the "never write to Canvas" claim in `277e9d2`, and CORE
promising that generic "scores" could be written straight to Canvas when only
New Quiz item scores can. The seeded-briefing hash was also not retired here,
so the correction could not have reached a workspace already holding an earlier
copy. A scoped test run is not acceptance.

YELLOW (local implementation complete; external client acceptance remains
pending for senior). The user authorized committing this batch on 2026-09-07;
the containing Git commit records the implementation and this acceptance report.

Changed files: `api/mcp_server/server.py`, `api/mcp_server/tools.py`,
`api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`,
`docs/mcp-server.md`, `api/tests/mcp_server/test_tools.py`,
`api/tests/mcp_server/test_server_instructions.py`, and
`api/tests/mcp_server/conftest.py`. The senior-authored brief
and unrelated worktree changes were preserved.

Verification:

* Preflight gate: `py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py::test_live_mcp_schema_matches_versioned_contract -p no:randomly -q` -> 169 passed.
* Final post-correction named gate: same command -> 179 passed.
* `git diff --check` -> clean.
* Live registry: 50 tools; the senior's isolated in-memory comparison found all
  complete `{name: inputSchema}` objects exactly equal to baseline `f99f3fd`; the server
  instructions are also byte-for-byte unchanged. `live_contract` equals frozen
  v36; no tool advertises `outputSchema`; protocol guide read returns one text
  block.
* Senior stdio subprocess smoke: MCP initialize negotiated successfully; tools/list
  returned 50 tools with no `outputSchema`; default plus all 10 guide topics each
  returned exactly one text block and no structured result; unknown topic refused.
* Registry-driven synthetic boundary tests stub all 50 delegates and exercise
  each FastMCP call, asserting one exact final-gated text block; ordinary,
  structured-failure, Unicode, and table payloads are covered. Listing budget
  is asserted at <=23,000 serialized characters. Extraction-law tests
  independently reject missing, duplicate, out-of-order, and unexpected
  headings.
* Character sizes: listing 27,439 -> 22,604; instructions 2,641 -> 2,641;
  default overview guide text 22,955 -> 5,819; internal serialized guide result
  23,510 -> 6,116; protocol CallToolResult 48,129 -> 6,327. The counts are
  serialized character measurements, not token claims.

The default guide now serves Appendix B (5,819 chars), with setup, chat_authoring,
connected, privacy, troubleshooting, assessments, full, writing_timeline, and
writing_record advertised and routed from canonical sources. Appendix extraction
rejects missing, duplicate, out-of-order, or unexpected heading sequences.

Deviation: no code or client configuration changes outside the brief. External
ChatGPT Work and Claude Cowork smoke checks are pending senior evidence; no
client was started or reconfigured here. Unresolved item is only that external
client acceptance, not a local test or implementation failure.

## Close-out, 2026-09-07

Criterion F was the only item still open. It is closed as follows, and this brief is
retired.

Local re-verification, run fresh at close-out rather than quoted from the execution
result above: default topic `overview` returns 5,819 characters opening
`Appendix B. What CanvasExpert can do`; exactly ten topics are advertised (overview,
setup, chat_authoring, connected, privacy, troubleshooting, assessments, full,
writing_timeline, writing_record); `topic="full"` returns 25,838 characters. Registry
at 50 tools, `TOOL_SCHEMA_VERSION` 36, serialized listing 22,604 characters.
Instructions are now 2,725 characters, up from the 2,641 recorded above because
`277e9d2` and `5656dff` added write-policy prose, still inside the 3,000 cap.

**ChatGPT Work: satisfied.** The 2026-09-07 capability probe from the ChatGPT/Codex
desktop client (GPT-5, 37 calls, no writes) read the default guide plus the
`connected`, `assessments` and `writing_record` topics, and the long page authoring
contract. It reported every result as a single readable text block that parsed
cleanly, with no schema, validation, or structured-output complaint from the client,
and nothing empty, doubled, truncated, or reshaped across the whole run. Its
capability map additionally claims reads of the setup, privacy, authoring and
Writing Timeline guides. That is the text-only usability evidence F asked for.

**Not exercised in either client:** `get_product_guide(topic="full")`. At 25,838
characters it is the largest single result on the surface, and the local read above is
clean, but no client has been handed a block that size. Carried as a single
opportunistic read in the next Work or Cowork session and recorded in
`mcp-surface-legibility.md`. It is not a blocker: nothing depends on `full` that the
default and the narrow topics do not already cover.

**Cowork: not satisfied, and reassigned.** That client's probe session received 7 of
the 50 registered tools and zero characters of server instruction text, so
`get_product_guide` was never reachable and the check could not run. None of that is
caused by the work in this brief: there is one `FastMCP` instance (server.py:70), no
tool gating anywhere in the server, and no tool allowlist in the connector writer
(connections.py:52). The client and tunnel-profile question now sits in
`mcp-surface-legibility.md` under "Out of scope, recorded", which is where it belongs,
because it is a connection question rather than a guide or transport question.

No decision, implementation, or verification item remains with this brief.
