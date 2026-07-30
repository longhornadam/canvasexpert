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

Tool schema version 2.

| Tool | Purpose | Student data? |
|---|---|---|
| `list_courses` | Every saved course (Current + Previous) | No |
| `get_course_assignments(course_id, full_descriptions=false)` | Assignments from the local course catalog (disk-only); descriptions trimmed to a preview unless `full_descriptions` | No |
| `get_roster(course_id)` | Table of `(pseudonym, section_names)` | Yes — pseudonymized |
| `get_submissions(course_id, assignment_id, include_text=true, pseudonyms="", max_text_chars=2000)` | One assignment's submissions, scrubbed | Yes — pseudonymized |
| `get_gradebook_snapshot(course_id)` | Whole-course per-assignment/per-student stats | Yes — pseudonymized |

`get_course_assignments` only reads the local course catalog written by the CanvasExpert
web UI — it never falls back to a live Canvas call. If the catalog hasn't been refreshed
yet, refresh it from the web UI first, then retry.

Every `course_id` tool is scoped to Current courses (`config.active_courses()`) — the same
scope the web UI uses.

### Token-lean results

Tool results occupy the assistant's context window and are re-sent on every following
turn of the conversation, so the wire format is deliberately compact:

- Results are minified JSON (the server serializes itself rather than letting FastMCP
  pretty-print).
- List data is one `{"columns": [...], "rows": [[...]]}` table per section instead of
  repeated per-row JSON keys.
- `get_submissions` supports narrowing: `include_text=false` returns status/scores only;
  `pseudonyms="Name A,Name B"` (comma-separated, case-insensitive) returns specific
  students; `max_text_chars` (default 2000, `0` = full) trims each submission's text with
  an explicit `…[truncated N more chars]` marker. The cheap pattern is status first, then
  full text for only the students that matter.
- The outbound safety scan always runs on the full row payload **before** tabulation and
  truncation happens **before** the scan — the gate inspects exactly the bytes that leave
  the machine.

The server also caches roster/section fetches in memory for 5 minutes (never on disk), so
back-to-back tool calls in one session don't each re-hit Canvas.

## Running it

The Connections page in the local web UI is the source for current, copy-only snippets.
It resolves the exact Python interpreter and absolute entry point from the unzipped
folder at the moment you copy them. Canvas Expert does not write client configuration
files, install a global module, change `PATH`, or require administrator access.

For another MCP client that supports local stdio, copy this shape and replace the values
with the current page values:

```json
{
  "mcpServers": {
    "canvas-expert": {
      "command": "C:\\path\\to\\your\\current\\python.exe",
      "args": ["C:\\path\\to\\CanvasExpert\\api\\mcp_server\\__main__.py"]
    }
  }
}
```

## Claude Desktop

Use Connections → Download `.mcpb`, then in the already installed Claude Desktop open
Settings → Extensions → Advanced settings → Install Extension and select the package.
The package is folder-linked: it contains only a launcher and a manifest, while Canvas
Expert and its dependencies remain in the unzipped folder. The package embeds the current
folder path, so regenerate it after moving Canvas Expert. This is a user-profile import,
not a Windows application installer; it should not show UAC or request administrator
credentials. If the client reports `Blocked by client policy`, stop and follow district
policy rather than attempting a bypass.

Official references: [Claude local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
and [MCPB manifest](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md).

## ChatGPT workspace

ChatGPT cannot connect directly to a local stdio server. The optional path uses OpenAI's
outbound-only [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
It has two distinct permission layers: Platform tunnel permissions and ChatGPT workspace
developer-mode permissions. Keep the tunnel client running, create a developer-mode app
with Connection set to Tunnel, select the tunnel or enter its `tunnel_id`, and run Scan
Tools. Use the PowerShell block on Connections as a copy-only starting point. Its
`CONTROL_PLANE_API_KEY` placeholder is set only for the external tunnel process at
runtime; Canvas Expert never asks for or stores that key. ChatGPT [developer mode](https://help.openai.com/en/articles/12584461)
may need a client review/refresh when the tool schema changes.

The optional portable tunnel executable lives under the current app folder when supplied;
Canvas Expert does not download, start, install, or assume a machine-wide client or `PATH`
entry. The tunnel's `run` command stays active until stopped, after which the cleanup
command should be run.

## Verifying it works

After registering, try `list_courses` first (no Canvas call, no student data — a quick
sanity check that the process starts and the interpreter resolves correctly), then
`get_gradebook_snapshot` on a Current course. Every student name in the output should be a
pseudonym you don't recognize from the real roster — that's the privacy boundary working as
intended, not a bug.
