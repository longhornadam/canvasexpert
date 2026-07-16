# Execution brief: CanvasExpert read-only MCP server

Status: **GREEN — automated verification complete; user diff review pending (mandatory stop condition)**

Risk: **high**

Executor: **Luna**

## Outcome

A teacher can plan lessons and manage rosters conversationally with any MCP-capable
assistant (Claude Code, Claude Desktop, Cowork, eventually ChatGPT) while CanvasExpert
keeps sole custody of the Canvas PAT and all write paths. This ships a local stdio MCP
server exposing 5 read-only tools, with all student data pseudonymized through the
existing identity vault before it reaches any client.

## Locked decisions

- Pseudonymization stays for every client — the assistant addressing students as
  "Sparky McGee" is a feature (it visibly communicates the privacy boundary). No
  re-identification burden on teachers.
- `get_gradebook_snapshot` IS included in v1 despite having no existing vault coverage.
  Fix: map gradebook rows through the existing `Vault.get_or_assign` keyed by Canvas
  user ID — same vault, no parallel identity scheme.
- Payload key vocabulary is dictated by the existing outbound safety gate
  (`feedback_safety.scan_payload`), which hard-blocks any payload containing a
  non-empty key from `{name, real_name, canvas_id, sis_id, section, sectionnames,
  sectionids, sectionsisids, sisid}` or a known real identifier as a value. The MCP
  tools therefore use: students → `pseudonym`, assignments → `title`, courses →
  `course_name`, sections → `section_names`. With that vocabulary the existing gate
  runs unmodified as the final check on every student-data tool.
- Final gate (`pseudonym.gate`) runs `feedback_safety.scan_payload` on the fully
  assembled payload of the three student-data tools. Fail-closed: not green → withhold
  the payload, return `{ok: false, error, violations}` with hard-violation descriptions
  only — never echo flagged names. Soft flags are dropped silently (never surfaced to
  the MCP client).
- Transport is stdio only, read-only only. No attachment/file exposure (filenames leak
  identity). No persistent logging of tool args/results; no `print()` anywhere in the
  package. Never import `api.webui.server`; never add a second credential path.

## Scope

- New package `api/mcp_server/` (`__init__.py`, `__main__.py`, `server.py`,
  `pseudonym.py`, `tools.py`).
- New tests `api/tests/test_mcp_server_tools.py`.
- New docs `docs/mcp-server.md` (client config snippets) and this handoff.
- One existing file changes: `api/webui/routes/gradebook_snapshot.py` — extract pure
  `build_snapshot(students, assignments, subs) -> dict`.
- One dependency addition: `mcp>=1.12,<2` in `api/requirements.txt`.

## Out of scope

Write tools of any kind; generic Canvas passthrough; live-Canvas fallback for the
catalog; attachment/file exposure; changes to PAT storage; mounting MCP in the FastAPI
app; any network bind.

## Reference pattern and routing

- Credentials: `config.get_token()` (keyring, service `quizforge-api`) via
  `api/webui/config/canvas.py:27`; Canvas HTTP via `_canvas_get` / `_canvas_get_all` in
  `api/webui/canvas_client.py`.
- Vault: global, `_System/Identity Vault/vault.json`, keyed by Canvas user id —
  `api/feedback_vault.py` (`get_or_assign:128`, `reverse:253`). Roster upsert pattern:
  `_upsert_roster` in `api/webui/routes/names.py:39`.
- Safety gate: `scan_payload(payload, vault)` in `api/feedback_safety.py:37`.
- Free-text scrub: `api/feedback_scrub.py` (`build_replacement_map:42`,
  `scrub_text:108`); HTML→text via `html_to_text` in `api/nq_report.py:55`.
- Submissions fetch (pure read, no file writes): `_assignment_submissions` /
  `_assignment` in `api/webui/routes/gradebook_common.py`.
- Gradebook aggregation: extracted from `api_gradebook` into
  `build_snapshot` in `api/webui/routes/gradebook_snapshot.py`;
  `api/tests/test_gradebook_routes.py` guards the extraction (must pass unmodified).
- Dual import guard pattern: `api/powergrader/canvas_fetch.py:17-24`.

## Implementation requirements

1. `api/requirements.txt`: append `mcp>=1.12,<2` (raise floor if 3.14 resolution
   requires; note as a deviation).
2. `build_snapshot` extraction in `gradebook_snapshot.py`; `test_gradebook_routes.py`
   must pass unmodified.
3. `api/mcp_server/pseudonym.py` → `tools.py` → `server.py` → `__main__.py`, per the
   design in the approved plan (`sync_vault_for_course`, `pseudonymize_roster`,
   `pseudonymize_submission_rows`, `pseudonymize_gradebook_rows`, `gate()`).
4. `api/tests/test_mcp_server_tools.py`: per-tool happy/empty/failure, gating
   rejection, catalog-missing error, scrub check, `Vault.reverse` round-trip, no-PII
   `json.dumps` sweep + `scan_payload` green assertion, gate fail-closed test.
5. `docs/mcp-server.md`: client config snippets (Claude Code `.mcp.json`, `claude mcp
   add` one-liner, Claude Desktop config) + keyring/interpreter notes.

## Verification

```powershell
py -m pytest api/tests/test_mcp_server_tools.py api/tests/test_gradebook_routes.py -q
py -m pytest api/tests -q
```

Manual smoke: register in Claude Code (`claude mcp add canvas-expert -- py
"D:\Development Projects\CanvasExpert\api\mcp_server\__main__.py"`), call
`list_courses`, then `get_gradebook_snapshot` on a Current course; eyeball
pseudonyms-only output.

**User diff review before merge is a mandatory stop condition, not optional.**

## Stop conditions

Stop with RED rather than guessing if:

- A named insertion point or assumed interface is missing.
- Existing behavior contradicts a locked decision.
- Any non-fixture `scan_payload` red, any need to write student data outside the
  vault, or the `mcp` pin is unresolvable on Python 3.14.
- A credential, FERPA, live-write, or scheduled-write question is underspecified.

## Return report

### Execution result

- Traffic light: **GREEN** (all automated checks pass; user-supervised diff review is the
  mandatory stop condition before merge, per the plan — not yet performed by the user)
- Commit hash: **uncommitted** (all changes left in the working tree; nothing staged or
  committed, per instructions)
- Files changed:
  - **New:** `api/mcp_server/__init__.py`, `api/mcp_server/pseudonym.py`,
    `api/mcp_server/tools.py`, `api/mcp_server/server.py`, `api/mcp_server/__main__.py`,
    `api/tests/test_mcp_server_tools.py`, `docs/mcp-server.md`,
    `docs/handoffs/mcp-read-only-server.md`
  - **Modified:** `api/requirements.txt` (append `mcp>=1.12,<2`),
    `api/webui/routes/gradebook_snapshot.py` (extracted pure `build_snapshot`)
- Installed `mcp` version: **1.28.1** (resolved cleanly on Python 3.14 against the stated
  `mcp>=1.12,<2` floor — no floor raise needed)
- Verification commands and pass/fail/skip counts:
  - `py -m pytest api/tests/test_mcp_server_tools.py api/tests/test_gradebook_routes.py -q`
    → **28 passed**
  - Affected suites (`test_feedback_pipeline.py`, `test_feedback_safety.py`,
    `test_feedback_scrub.py`, `test_feedback_vault.py`, `test_roster_config.py`,
    `test_roster_group_set_operation.py`, `test_roster_membership_operation.py`,
    `test_roster_routes.py`, `test_route_contract.py`) → **131 passed**
  - `py -m pytest api/tests -q` (full suite) → **749 passed, 1 skipped** (pre-existing
    skip, unrelated to this change)
  - Stdio import smoke: ran the exact `sys.path` bootstrap `__main__.py` uses, then
    `from api.mcp_server.server import mcp` — imported cleanly, `mcp.name ==
    "canvas-expert"`, 5 tools registered. Also covered as an in-suite pytest assertion:
    `test_server_registers_exactly_the_five_read_only_tools`.
- Rendered routes checked: none required (no browser-facing change; the extracted
  `build_snapshot` is verified via `test_gradebook_routes.py`'s exact-JSON-shape assertions,
  unmodified).
- Deviations from the brief: **none.** Every named file, function, and signature in the
  plan matched the repository as found; no insertion point was missing.
- Remaining blocker or decision: **none technical.** The plan's own stop condition — user
  diff review before merge — is outstanding and is not something this executor pass can
  satisfy; it requires the user/senior to review the working-tree diff.
