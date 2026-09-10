# Brief: rename the MCP `session_id` parameter

**Status:** current
**Risk:** Low (parameter rename at one boundary; no Canvas write, no data shape change)
**Senior decision date:** 2026-09-10

## Objective

The whole PowerGrader path is unreachable from chat. Any tool argument named exactly
`session_id` is stripped before it reaches CanvasExpert, so the server's validator sees
`Field required [type=missing, input_value={'limit': 2}]` — every other argument arrives,
that one is gone. Renaming the parameter sidesteps it.

Field-reproduced on 2026-09-09 and again 2026-09-10 across three courses, with a real
UUID, with a non-UUID probe, after `RefreshMcpTools`, and from a separate subagent.

The cause is **not** CanvasExpert. A differential probe against a remote MCP server passed
`session_id` intact, so the strip is specific to the remote-devices bridge on the path to
locally-hosted servers — most likely because the bridge consumes the name for its own
session routing. We rename anyway: it is a few lines here versus an upstream fix we do not
control, and it unblocks the teacher today.

Blocked today, and unblocked by this: `get_scoring_packet`, `stage_scores`,
`preview_new_quiz_scores`. `apply_new_quiz_scores` takes `operation_id`, but it needs a
frozen preview only `preview_new_quiz_scores` can produce, so it is blocked
transitively and is fixed by the same change.

## Locked decisions

### 1. The new name is `scoring_session_id`.

Not `grading_session_id` or `pg_session`. The repo's domain word is *scoring session*
throughout — `start_scoring_session`, `list_scoring_sessions`, `get_scoring_packet`. Match
it.

### 2. Rename the whole MCP surface, not just the three parameters.

The MCP boundary speaks `scoring_session_id`; everything below it keeps `session_id`.

That means renaming, inside `api/mcp_server/` only:

- the three input parameters;
- the `session_id` key that `start_scoring_session` returns;
- the `session_id` column in `_SCORING_SESSION_COLUMNS` that `list_scoring_sessions` emits;
- every mention in tool docstrings and `next`-step guidance text.

The point is that an assistant never sees the token `session_id` anywhere on this surface.
A tool that *returns* `session_id` while the next tool *accepts* `scoring_session_id` is
how an agent ends up passing the stripped name again, which is the exact failure being
fixed.

### 3. Nothing below `api/mcp_server/` changes.

`session_store`, `api/powergrader/`, `scoring_packet`, session files on disk, and the web
UI keep `session_id`. The bridge never sees those names. Renaming them would be a large
diff against a name that is not broken.

### 4. No compatibility alias.

Do not accept both names. `project-state.md`: pre-launch, zero users, no legacy callers —
take the clean break.

### 5. `operation_id` is left exactly as it is.

`preview_new_quiz_scores` builds `operation_id` as `f"{session_id}::{token}"` and
`apply_new_quiz_scores` splits it back apart. That is an opaque composite string, not a
parameter name, and the bridge does not touch it. Do not "fix" it for consistency.

## Scope

| File | Change |
|---|---|
| `api/mcp_server/server.py` | The three `@mcp.tool` wrappers (≈ lines 480, 490, 499). This is the registered schema, so it is the load-bearing rename. |
| `api/mcp_server/tools.py` | Same three signatures (≈ 2805, 2907, 3127); `_SCORING_SESSION_COLUMNS` (≈ 115); the `next` guidance at ≈ 144; the returned key at ≈ 2724; docstrings at ≈ 2652–2659, 2810, 2839, 2911, 2927, 3252. |
| `api/mcp_server/contract.py` + `tool_schema_v42.json` | `TOOL_SCHEMA_VERSION` 41 → 42; add 42 to `_SUPPORTED_SCHEMA_VERSIONS`; generate the new schema from the live registry. Tool count stays **46** — this is a rename, not an addition. |
| `docs/mcp-server.md` | The three signature rows (≈ 87–89) and the v35 write-pair note (≈ 276). |
| pinned tests | `test_beta075_mcp.py`, `test_tools.py`, `test_server_instructions.py`, `test_contract.py` carry hardcoded version pins. Update the pins; the tool count does not move. |

Internal local variables inside the three tool bodies may keep `session_id` where they
are just passing through to `session_store` — rename the parameter, not every local. Do
not let this become a find-and-replace across the file.

## Acceptance criteria

1. The three tools accept `scoring_session_id` and no longer accept `session_id`.
2. `grep -rn "session_id" api/mcp_server/` returns **no** hit that is part of the
   assistant-visible surface — no parameter, no returned key, no emitted column, no
   docstring or guidance text. Pass-through locals and `operation_id` splitting may remain.
3. `contract.load_contract()` and `live_contract(mcp)` agree at version 42, with 46 tools.
4. Nothing under `api/powergrader/`, `session_store`, or `api/webui/` is modified.
5. An existing on-disk scoring session, created before this change, is still readable —
   the rename is at the call boundary, so session files must not need rewriting. Prove it
   with a test that loads a session fixture through the renamed tool.

## Non-goals

- Any change below `api/mcp_server/`.
- A back-compat alias accepting both names.
- The two path/packet defects in the same field report (duplicated `For AI — For AI` /
  `— <id> — <id>` segments in `workspace.ai_run_folder`, and packets orphaned on disk when
  the budget check fails after artifacts are written). Same report, different vertical,
  separate brief.
- Fixing the bridge. Worth reporting upstream — it will hit any locally-hosted MCP server
  using this parameter name — but that is not this repo.

## References

Read only these:

- `api/mcp_server/server.py` — the three wrappers.
- `api/mcp_server/tools.py` — the three tools and the scoring-session helpers around them.
- `api/mcp_server/contract.py` — version bump mechanics.
- `docs/mcp-server.md` — the rows to update.
- Commit `44337f9` — the immediately preceding v40 → v41 bump, as the worked example of
  everything a version bump touches.

## Verification gate

```powershell
py -m pytest api/tests/mcp_server/ api/tests/test_beta075_mcp.py -p no:randomly
```

Plus, per the test taxonomy:

- **Contract:** the v42 schema matches the live FastMCP registry.
- **Law:** no assistant-visible `session_id` remains on the MCP surface (assert over the
  live contract's parameter names, so a future tool cannot reintroduce it).
- **Example:** one happy path — `get_scoring_packet(scoring_session_id=...)` returns a
  packet for a fixture session.

**This gate cannot prove the bug is fixed.** It proves the rename is complete and
coherent. Whether the bridge stops stripping is only observable from a real chat client,
and that check belongs to the teacher after this lands. Say so in your report rather than
claiming the blocker is closed.

## Stop conditions

- Stop if `_SCORING_SESSION_COLUMNS` or the `start_scoring_session` return key turns out to
  have a consumer outside `api/mcp_server/` — that would make locked decision 2 wider than
  Low risk, and is a senior decision.
- Stop if renaming the parameter changes anything about how sessions are stored or located
  on disk. It must not.
- No Canvas writes, and no live scoring run against real student data. Use fixtures.

## Execution result

_(executor fills in: traffic light, changed files, commands and counts, deviations,
unresolved decisions)_
