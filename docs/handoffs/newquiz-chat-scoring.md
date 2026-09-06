# Batch brief: score New Quiz written responses from the conversation

**Status:** READY FOR ORCHESTRATION. Not started.
**Opened:** 2026-09-06 on `dev` at `ac58ae5`.
**Addressed to:** the orchestrating agent, acting as senior of record.
**Risk:** High. This touches grades and adds a Canvas write surface to the MCP server.

Batch brief, not durable documentation. Delete it when the batch closes and is accepted.
Read `AGENTS.md` first; this assumes it.

This is the single current direct brief. The SIS grade-bridge brief was retired on
2026-09-06: the teacher confirmed its two outstanding passbacks landed and that the
feature works in production.

---

## 0. Your role and what is expected of you

You own dispatch, acceptance, and the traffic light. You do not own the design; it was
traced against the live tree and confirmed with the teacher. If repository truth
contradicts section 2, that is RED: stop and report.

1. Run the preflight in section 6 before dispatching anything.
2. Dispatch per section 5. This is one vertical improvement, not four deliverables.
3. Verify executor claims against the tree, not against the report. Diff the files.
4. This is High risk work per `AGENTS.md`. Happy path, failure path, and idempotency
   evidence are all required, plus teacher diff review before anything writes to a real
   course. Do not accept "tests pass" as sufficient for the write path.
5. Nothing in this batch may push to a live course without the teacher present. The
   sandbox is course 109559; CS 8 is 121046 and has real students in it.

---

## 1. Objective

The teacher wants to grade New Quiz written responses inside a conversation with their
assistant: pull the responses, score the essay items, and land the scores in Canvas,
without opening PowerGrader.

Most of that already exists. This batch closes the two ends that do not.

---

## 2. Verified state at `ac58ae5`

Traced directly. Do not re-derive.

**The middle of the flow already works over MCP.** `list_scoring_sessions` →
`get_scoring_packet` → `stage_scores` are live. `docs/contracts/feedback-scoring-contract.md`
line 176 says outright that an assistant over MCP reaches the same session without a file,
under the same session lock and the same `import_results` validation as a pasted file.

**Per-item scoring is already supported.** `stage_scores` takes results as
`{pseudonym, item_id, score, feedback}` (`api/mcp_server/tools.py:2843`). It is not
assignment-total only. Essay items on a New Quiz can be staged today.

**The New Quizzes machinery is built and live-verified**, shipped 2026-07-14:
- `api/powergrader/new_quiz_fetch.py` acquires real item responses natively.
- The item-finalization lane writes teacher-reviewed per-item scores and grader feedback
  through Canvas's short-lived signed grader transport, with a drift check against a
  cached state digest, an idempotency key, a post-write re-fetch and verify, and
  content-minimized receipts. See `docs/reference/new-quizzes-grading-transport.md`.

**Gap 1: no session can be created over MCP.** `api/webui/routes/powergrader.py:290`,
`pg_start`, is 236 lines that mix form parsing, file uploads, oral-reading validation and
auto-post triggering with the actual orchestration. None of it is callable from anywhere
but the HTTP route, so the teacher must open PowerGrader once per quiz.

**Gap 2: the write is route-only.** But it is much closer than it looks. Both halves are
already extracted with injected dependencies, and the routes are thin wrappers:

- `session_actions.review_new_quiz_finalization(session_id, user_id=, decisions_json=,
  load_session=, save_session=, preflight=)` at `powergrader.py:879`
- `session_actions.finalize_new_quiz(session_id, user_id=, review_token=, decisions_json=,
  load_session=, save_session=, apply=)` at `powergrader.py:905`

Both are callable from an MCP tool as they stand.

**The trap in gap 2.** `_converge_new_quiz_after_finalize` (`powergrader.py:888`) lives in
the route, not in `session_actions`. It refreshes the gradebook submission and invalidates
the New Quiz response snapshot. An MCP path that calls `finalize_new_quiz` directly and
skips it lands the grade in Canvas and leaves CanvasExpert's own mirror stale, which is
exactly the class of bug that makes a teacher distrust the tool. See D5.

**Finalization is per student.** `finalize_new_quiz` takes one `user_id`. A class-wide
flow loops; there is no batch entry point.

**Session shape.** `session_builder.build_session` sets, for a New Quiz:
`canvas_writeback_supported=False`, `comment_writeback_supported=True`,
`new_quiz_item_finalization_supported=True`. Modes are `fast`, `packet`, `assisted`
(`powergrader_helpers.py:6`). Packet is the AI-chat lane this batch cares about.

**The safety template to copy is the SIS grade bridge.** `preview_sis_grade_bridge`
returns aggregate review facts only; `apply_sis_grade_bridge(operation_id, batch_id,
review_digest)` accepts nothing but opaque coordinates. `docs/mcp-server.md:100` states
the authorization rule: the assistant previews, summarizes counts and warnings, and waits,
and one teacher command may preauthorize the full cycle only when it names that exact
course and family.

**A Canvas write from MCP is not a new precedent.** `AGENTS.md`'s routing table still says
the MCP server is "never a Canvas write". That line is stale. `docs/mcp-server.md`, the
authority, documents two: `canvas_group` for real roster group membership, and the SIS
grade-bridge preview/apply pair. See D8.

**Registry versioning.** Schema is v33, 53 tools. `api/tests/test_beta075_mcp.py:104` pins
`docs/mcp-server.md`'s declared version, its declared tool count, and its per-tool table
rows to the live registry. Adding a tool stays red until the doc gains its row.

---

## 3. Locked decisions

**D1. Packet mode only.** The MCP session-start tool creates `mode="packet"` and nothing
else. `assisted` runs an LLM against the teacher's own key and `auto_post` can post to
Canvas on a trigger; neither belongs behind a chat request. No file uploads, no
oral-reading passage.

**D2. Extract, do not duplicate.** The orchestration inside `pg_start` moves to a callable
function; the route becomes a thin adapter over it, exactly as the two New Quiz routes
already are. A second copy of session construction would drift from the first within a
semester. The existing route tests in `api/tests/webui/routes/test_powergrader.py` are the
proof the extraction changed no behavior.

**D3. The write mirrors the SIS grade bridge.** A `preview` returning aggregate review
facts plus opaque coordinates, and an `apply` accepting only those opaque coordinates and
a review digest. Do not invent a new safety shape.

**D4. Reuse the existing finalization.** The MCP apply calls
`review_new_quiz_finalization` and `finalize_new_quiz`. Do not write a second finalization
path. The drift check, idempotency key, post-write verification and receipts already exist
and were live-verified; a parallel path would have none of them.

**D5. Convergence moves with the finalize.** `_converge_new_quiz_after_finalize` moves out
of the route into shared code so both the HTTP caller and the MCP caller get it. Landing a
grade without invalidating the response snapshot is a defect, not an optimization.

**D6. The preview carries no student identity.** It routes through the identity vault and
the outbound safety scan like every other student-data tool, and reports aggregate counts
and warnings. Pseudonyms where individual rows are unavoidable, never names or Canvas ids.

**D7. Preauthorization is bounded the way the bridge is.** One teacher command may
preauthorize the whole preview and apply cycle only when it names that exact course and
that exact assignment. It never generalizes to another assignment, another course, or a
later session.

**D8. Correct the stale line.** `AGENTS.md`'s MCP routing row is updated to match
`docs/mcp-server.md`: bounded, documented Canvas write surfaces behind preview/apply
pairs, rather than "never a Canvas write". Documentation only, but it is the line a future
executor would otherwise treat as a stop condition.

---

## 4. Work units

### Unit A: extract the session start (refactor, no behavior change)

Files: `api/webui/routes/powergrader.py`, plus a new or existing module under
`api/powergrader/` (`start_workflow.py` already owns adjacent logic and is the natural
home).

Lift the orchestration out of `pg_start` into a callable that takes plain arguments and
returns the built session plus the payload pieces. The route keeps form parsing, upload
handling, and the `assisted` auto-post trigger, and calls the new function for the rest.

The seam to aim for is the one the New Quiz routes already demonstrate: pure function with
injected `load_session` / `save_session`, thin HTTP wrapper.

No behavior change. `api/tests/webui/routes/test_powergrader.py` must pass untouched. If a
test needs editing to accommodate the refactor, stop and report: that means behavior moved.

### Unit B: start a packet-mode session from MCP

New tool, e.g. `start_scoring_session(course_id, assignment_id)`.

- Packet mode only, per D1.
- Course-gated the way every other student-data tool is (`_course_gate_check`), Current
  courses only.
- Returns the `session_id` plus what the assistant needs to proceed to
  `get_scoring_packet`: assignment name, student count, response count, and the
  `new_quiz_item_finalization_supported` flag so the assistant knows whether the write
  lane will be available.
- Creates a local session file. No Canvas write. Refuses cleanly when there are no
  submissions, when the workspace is unconfigured, or when the course is not Current.

### Unit C: the write pair

Move the convergence per D5 first, then add the pair per D3 and D4.

- `preview_new_quiz_scores(session_id)`: aggregate review facts. How many students, how
  many items, how many carry a staged score, how many are unresolved or drifted, plus
  warnings. Returns opaque coordinates and a review digest. No Canvas write.
- `apply_new_quiz_scores(operation_id, review_digest)`: applies exactly the reviewed set
  through `review_new_quiz_finalization` and `finalize_new_quiz`, looping per student
  (section 2, finalization is per `user_id`), running the convergence after each verified
  finalize, and returning per-student outcomes including partial failure.

Partial failure is the normal case, not the edge case: a concluded enrollment returns 403
per the transport doc. Report which students landed and which did not. Never roll the
whole batch back on one failure, and never retry a finalize that already verified.

### Unit D: documentation and registry

- `docs/mcp-server.md`: bump the declared schema version and tool count, add a table row
  per new tool, and document the preauthorization rule from D7 alongside the SIS bridge's.
- `api/mcp_server/tool_schema_v34.json` and the version constant in `contract.py`.
- `AGENTS.md` routing row per D8.
- `docs/contracts/feedback-scoring-contract.md`: its step 1 currently says the teacher
  starts the session. Update it to record the MCP route as a second way in.

---

## 5. Dispatch plan

Three waves. Unit A is a refactor everything else sits on, so it lands and is accepted
first.

**Wave 1, one executor: Unit A.** Refactor only. Accept before dispatching wave 2.

**Wave 2, two executors on disjoint files:**
- **Executor 2A: Unit B.** MCP tool plus tests. Owns `api/mcp_server/`.
- **Executor 2B: Unit C's convergence move only** (D5), in `api/powergrader/` and
  `api/webui/routes/powergrader.py`.

**Wave 3, one executor: Unit C's tool pair plus Unit D.** It needs both wave 2 halves in
place, and Unit D's registry bump has to count every new tool at once or the doc-pin test
cannot go green.

Unit D cannot be split from Unit C's tools: the pinning test fails the moment a tool is
registered without its doc row, so tools and docs land together.

---

## 6. Preflight, run by you

Stop and report if any is false.

1. `git status` clean on `dev`; fetch and compare `origin/dev` and `origin/main`.
2. `session_actions.review_new_quiz_finalization` and `finalize_new_quiz` still take
   injected `load_session` / `save_session` and are still called from thin routes.
3. `_converge_new_quiz_after_finalize` is still route-level with no other caller.
4. `stage_scores` still accepts `item_id` per result.
5. `docs/mcp-server.md` still declares "Tool schema version 33 (53 tools)." and
   `contract.TOOL_SCHEMA_VERSION` still agrees.
6. Baseline both suites once and record the commands and counts here, so later units cite
   the record instead of rerunning:

```bash
py -m pytest api/tests -p no:randomly -q
```

```bash
py -m pytest engine/tests -p no:randomly -q
```

At `cbbd8ef` the api suite had 5 pre-existing failures unrelated to this surface
(dailywriting scrub guard, MCP tool registry, CanvasAgent instructions, theme studio,
roster routes). Confirm the same five and do not fix them.

---

## 7. Explicit non-goals

- No new scoring logic. The assistant scores; this batch only moves responses out and
  results back.
- No change to `get_scoring_packet` or `stage_scores` behavior.
- No `assisted` mode or auto-post over MCP, per D1.
- No batch finalize endpoint in the web UI. The loop lives in the MCP tool.
- No change to the signed grader transport, the drift check, the idempotency key, or the
  receipt format.
- No removal of the PowerGrader screens. This adds a route in, it does not replace the UI.
- No live-course push during development. Sandbox 109559 only, with the teacher present.

---

## 8. Stop conditions and standing constraints

Stop and report rather than working around:

- Unit A's extraction requires editing an existing route test, which would mean behavior
  moved rather than code.
- `finalize_new_quiz` turns out to need state the route holds and `session_actions` cannot
  reach.
- The preview cannot be built without returning student identity, which D6 forbids.
- A second finalization path looks necessary. That is D4 and it is a hard stop.

Standing constraints:

- **Every student-data result routes through the vault and the outbound safety scan.**
  Pseudonyms only. This is the whole basis of the MCP surface.
- **Tests follow the house taxonomy:** law, contract, or example. The idempotency and
  drift refusals are laws and belong tested at the law.
- **No student data or secrets** in fixtures, tests, logs, receipts, or commit messages.
- **No em-dashes** in prose, UI copy, comments, or docstrings. Calm teacher-facing voice.
- **`api/tests/test_beta075_imports.py`** forbids `except ImportError` in non-test `api/`
  code and requires `api.`-prefixed imports.

---

## 9. Verification gate

- Both suites green, or failing only on the recorded baseline.
- Unit A: the existing PowerGrader route tests pass unedited.
- A session created over MCP is byte-comparable to one created through the web UI for the
  same assignment, excluding `session_id` and timestamps.
- `start_scoring_session` refuses cleanly on: unknown course, non-Current course,
  assignment with no submissions, unconfigured workspace.
- Preview returns no real name and no Canvas or SIS id. Assert this directly against a
  fixture containing both.
- Apply refuses a mismatched `review_digest`, refuses a stale drift state, and is
  idempotent: calling it twice with the same coordinates writes once. All three are laws.
- Partial failure reports per student and does not roll back verified finalizes.
- After a verified finalize through the MCP path, the response snapshot is invalidated and
  the gradebook submission refreshed, proven the same way the route path proves it.
- Live sandbox run on 109559 with the teacher present: one essay item scored from a
  conversation end to end, then the receipt and the Canvas state both inspected.
- Teacher diff review before the batch is accepted. High risk work does not close on an
  executor's report.

---

## 10. Execution result

**Traffic light:** in progress.

**Preflight, run 2026-09-06 at `c85e53b`. All six held.**

- Clean tree on `dev`, 0 behind `origin/dev`. Note: local commits are ahead and unpushed.
- `review_new_quiz_finalization` and `finalize_new_quiz` still take injected
  `load_session` / `save_session` (`session_actions.py:69` and `:159`).
- `_converge_new_quiz_after_finalize` is still route-level with one caller
  (`powergrader.py:912`). One test reaches it as `pg._converge_new_quiz_after_finalize`
  (`api/tests/powergrader/test_interactive_autopush.py:505`), so that test moves with it
  in Unit C. Recorded here so the executor does not discover it as a surprise.
- `stage_scores` still takes `item_id` per result.
- `docs/mcp-server.md` declares "Tool schema version 33 (53 tools)." and
  `contract.TOOL_SCHEMA_VERSION` is 33.
- `pg_start` spans `powergrader.py:290` to `:523`.

**Baseline:**

- `py -m pytest api/tests -p no:randomly -q` gave `5 failed, 2440 passed in 69.23s`.
- `py -m pytest engine/tests -p no:randomly -q` gave `113 passed in 6.70s`.

**Baseline is now four, not five.** The MCP tool registry failure turned out to be a loose
end from the SIS grade-bridge batch: it shipped four tools and
`test_server_registers_the_expected_tool_set` was never updated with them. That test
enumerates the same set Units B and C add to, so leaving it red invited an executor to
"fix" it and silently absorb the SIS drift. Closed by the orchestrator at `33d41a0`.

The remaining four are pre-existing, unrelated, and not to be fixed by any executor in
this batch: dailywriting scrub guard, CanvasAgent instructions, theme studio, roster
routes. Cite this record rather than rerunning.

**Wave 1 accepted GREEN at `33d41a0`.** `start_workflow.run_start_session` now owns the
orchestration and carries no web-framework import, so it is callable from MCP. Route tests
passed unedited; the full suite held at 2440 passed before the registry fix and 2441 after.

**Correction to section 5, made by the orchestrator.** The plan said only Unit C's tools
land with Unit D's registry bump. That was wrong: `test_mcp_server_doc_matches_the_live_registry`
goes red the moment *any* tool is registered without its doc row, so Unit B must carry its
own schema bump (v34, `tool_schema_v34.json`, `contract.TOOL_SCHEMA_VERSION`) and its own
`docs/mcp-server.md` row and count. Unit C's pair then takes v35.

**Also flagged during Wave 1:** `powergrader_helpers` moved from `api/webui/routes/` to
`api/powergrader/helpers.py`. The extraction otherwise pointed `api/powergrader/` at
`api/webui/routes/`, an inverted layer the MCP server was about to depend on.

**Wave 2, Executor 2B (Unit C's convergence move, D5) accepted GREEN.** Moved
`_converge_new_quiz_after_finalize` out of `api/webui/routes/powergrader.py` into
`api/powergrader/session_actions.py` as `converge_new_quiz_after_finalize`, kept as its
own function rather than folded into `finalize_new_quiz` (Unit C's plan text runs the
convergence as a distinct step in the MCP apply loop after each verified finalize, so a
future MCP caller needs to call it the same way the route now does). `_notify_write_through`
stays route-level (it reaches `mirror_service`, a webui-layer module); the new function
takes it as an injected `notify_write_through` keyword, same seam as `finalize_new_quiz`'s
injected `load_session`/`save_session`. The route's call site is otherwise unchanged: same
reload of the session via `_load_session(session_id)`, same guard
(`status_code == 200 and payload.get("status") == "finalized"`), still outside the session
lock, still best-effort. No double-invalidation risk: the route is the only caller today
and calls it exactly once, same as before.

Moved `test_converge_new_quiz_after_finalize_hits_both_surfaces` from
`api/tests/powergrader/test_interactive_autopush.py:505` to new
`api/tests/powergrader/test_session_actions.py`, mirroring the function's new module path.
Reaches it as `session_actions.converge_new_quiz_after_finalize(...)` with an injected fake
`notify_write_through` instead of patching `pg.mirror_service`; still asserts both surfaces
(gradebook write-through call and `new_quizzes.invalidate_responses`) are hit with the
right arguments.

Gate: `py -m pytest api/tests/powergrader api/tests/webui/routes/test_powergrader.py
api/tests/test_powergrader_new_quizzes.py api/tests/test_beta075_imports.py -p no:randomly -q`
gave `250 passed`. Full suite: `py -m pytest api/tests -p no:randomly -q` gave
`4 failed, 2441 passed`, the same four recorded above (dailywriting scrub guard,
CanvasAgent instructions, theme studio, roster routes) and no others.

Files changed: `api/powergrader/session_actions.py`,
`api/webui/routes/powergrader.py`, `api/tests/powergrader/test_interactive_autopush.py`
(test removed), `api/tests/powergrader/test_session_actions.py` (new, test moved in).

**Wave 2, Executor 2A (Unit B) accepted GREEN.** Added `start_scoring_session(course_id,
assignment_id) -> dict` to `api/mcp_server/tools.py`, registered in
`api/mcp_server/server.py` alongside the other scoring tools. Course-gated with the same
`_course_gate_check` as every other student-data tool, then calls
`start_workflow.run_start_session` with `mode="packet"` and every optional side effect
hardcoded off (`auto_post="false"`, `watch_late="false"`, `source_uploads=None`,
`source_files_json=""`, `source_text=""`, `oral_reading_enabled="false"`,
`oral_reading_passage=""`); the function takes only `course_id`/`assignment_id`, so there
is no argument surface that could ever request `assisted` mode or auto-post. On success it
reloads the just-saved session for `new_quiz_item_finalization_supported`, and reuses
`scoring_packet.build_packet`'s existing `total` computation (limit=1, include_context=false,
falling back to `student_count` on any error) to report `response_count`, the same number
`get_scoring_packet` will total later. On failure it surfaces `run_start_session`'s own
payload `error` text verbatim rather than inventing new wording.

Registry bump landed with it, since the doc-pin test goes red the moment any tool is
registered without a matching row: `contract.TOOL_SCHEMA_VERSION` to 34,
`api/mcp_server/tool_schema_v34.json` generated from the live registry after wiring (54
tools, `start_scoring_session` the only addition over v33), `docs/mcp-server.md`'s
version/count line and a new table row, `api/tests/test_beta075_mcp.py`'s version/count
assertions, and `api/tests/mcp_server/test_tools.py`'s expected tool set.
`docs/contracts/feedback-scoring-contract.md` step 1 gained one sentence noting an
assistant over MCP can now start a session itself, packet mode only.

Tests: new `api/tests/mcp_server/test_start_scoring_session.py` (7 tests) with
`run_start_session` stubbed throughout. One example builds a packet-mode session end to
end and asserts `response_count` (3, from a two-item/two-student SAFE bundle) differs from
`student_count` (2), proving the count is read from the bundle rather than echoed. A
second example covers the no-bundle fallback. Laws: refuses a non-Current course without
ever calling `run_start_session` (a poisoned stub raises if it is), and a dedicated law
captures the exact kwargs reaching `run_start_session` and asserts `mode == "packet"`,
`auto_post == "false"`, and every upload/oral-reading argument stays at its off default,
pinning the no-assisted/no-auto-post property directly rather than assuming it from the
hardcoded call site. A parametrized contract test covers both named `run_start_session`
refusals (no submissions, no workspace) surfacing verbatim. A final test pins the
`server.py` wrapper's compact-JSON wiring.

Gate: `py -m pytest api/tests/mcp_server api/tests/test_beta075_mcp.py
api/tests/test_beta075_imports.py -p no:randomly -q` gave `153 passed`. Full suite:
`py -m pytest api/tests -p no:randomly -q` gave `4 failed, 2448 passed`, the same four
recorded above (dailywriting scrub guard, CanvasAgent instructions, theme studio, roster
routes) and no others.

Files changed: `api/mcp_server/tools.py`, `api/mcp_server/server.py`,
`api/mcp_server/contract.py`, `api/mcp_server/tool_schema_v34.json` (new),
`api/tests/mcp_server/test_start_scoring_session.py` (new),
`api/tests/mcp_server/test_tools.py`, `api/tests/test_beta075_mcp.py`,
`docs/mcp-server.md`, `docs/contracts/feedback-scoring-contract.md`.

No deviation from the locked decisions. One thing the brief left open that I resolved by
reuse rather than invention: "response count" has no prior single definition in this
codebase outside the scoring-packet surface itself, so I took `get_scoring_packet`'s own
`total` (scorable rows, distinct from `students_total`) as the authority, on the reasoning
that the assistant should see the same number twice rather than two different notions of
"how much work is here." Not run: `engine/tests` (untouched by this unit; no test under it
references `api.mcp_server` or PowerGrader).
