# CanvasExpert read-only MCP server

A local, stdio-only [Model Context Protocol](https://modelcontextprotocol.io) server that
lets any MCP-capable assistant (Claude Code, Claude Desktop, Cowork, etc.) help plan
lessons and manage rosters conversationally, while CanvasExpert keeps sole custody of the
Canvas PAT and every write path.

- **Read-only.** No tool writes to Canvas. No tool writes to disk beyond the existing
  identity vault it already shares with the rest of CanvasExpert.
- **Pseudonymized.** Every student-data tool routes its result through the identity vault
  (`api/feedback_vault.py`) before returning it. Students are identified only by a stable
  fake name (e.g. "Sparky McGee") — never a real name, Canvas user ID, or SIS ID.
- **Fail-closed.** Every student-data result also passes the existing outbound safety scan
  (`api/feedback_safety.py::scan_payload`) as a final check. If it isn't green, the tool
  withholds the payload and returns only a sanitized violation description.
- **Session-local.** Nothing here logs tool arguments or results. Don't write results to a
  file, and don't attempt to re-identify a student from a pseudonym.
- **stdio transport only.** No network port is ever bound.

## Tools

| Tool | Purpose | Student data? |
|---|---|---|
| `list_courses` | Every saved course (Current + Previous) | No |
| `get_course_assignments(course_id)` | Assignments from the local course catalog (disk-only) | No |
| `get_roster(course_id)` | `[{pseudonym, section_names}]` | Yes — pseudonymized |
| `get_submissions(course_id, assignment_id)` | One assignment's submissions, scrubbed | Yes — pseudonymized |
| `get_gradebook_snapshot(course_id)` | Whole-course per-assignment/per-student stats | Yes — pseudonymized |

`get_course_assignments` only reads the local course catalog written by the CanvasExpert
web UI — it never falls back to a live Canvas call. If the catalog hasn't been refreshed
yet, refresh it from the web UI first, then retry.

Every `course_id` tool is scoped to Current courses (`config.active_courses()`) — the same
scope the web UI uses.

## Running it

The server is a plain Python entry point, launched by the MCP client (not by
CanvasExpert's own web server). In the snippets below, replace
`C:\path\to\CanvasExpert` with wherever you unpacked CanvasExpert:

```
py "C:\path\to\CanvasExpert\api\mcp_server\__main__.py"
```

It bootstraps its own `sys.path` from `__file__`, so it works regardless of the caller's
working directory. It must run as the **Windows user whose Credential Manager holds the
Canvas token** (the same `keyring` service, `quizforge-api`, used by the web UI).

No admin rights are needed anywhere: dependencies (`api/requirements.txt`, including the
`mcp` package) install per-user — running `Open Canvas Expert.bat` once after unpacking
handles this automatically via `pip install --user`, the same first-run setup the web UI
uses.

## Claude Code

Add to `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "canvas-expert": {
      "command": "py",
      "args": ["C:\\path\\to\\CanvasExpert\\api\\mcp_server\\__main__.py"]
    }
  }
}
```

Or register it with the CLI:

```
claude mcp add canvas-expert -- py "C:\path\to\CanvasExpert\api\mcp_server\__main__.py"
```

## Claude Desktop

Add the same block to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "canvas-expert": {
      "command": "py",
      "args": ["C:\\path\\to\\CanvasExpert\\api\\mcp_server\\__main__.py"]
    }
  }
}
```

Restart the client after editing either config file so it picks up the new server.

## Verifying it works

After registering, try `list_courses` first (no Canvas call, no student data — a quick
sanity check that the process starts and the interpreter resolves correctly), then
`get_gradebook_snapshot` on a Current course. Every student name in the output should be a
pseudonym you don't recognize from the real roster — that's the privacy boundary working as
intended, not a bug.
