# CanvasExpert MCP server

A local, stdio-only [Model Context Protocol](https://modelcontextprotocol.io) server that
lets any MCP-capable assistant help plan lessons and manage rosters conversationally,
while CanvasExpert keeps sole custody of the Canvas PAT and every write path.

- **Local and indirect.** Serves this teacher's own Canvas data from Canvas Expert's
  local copy on their computer. It never holds the Canvas token, and writes nothing
  beyond the identity vault it already shares with the rest of CanvasExpert.
- **Pseudonymized, not anonymous.** Every student-data tool routes its result through the identity vault
  (`api/feedback_vault.py`) before returning it. Students are identified only by a stable
  fake name (e.g. "Sparky McGee") — never a real name, Canvas user ID, or SIS ID.
- **Fail-closed.** Every student-data result also passes the existing outbound safety scan
  (`api/feedback_safety.py::scan_payload`) as a final check. If it isn't green, the tool
  withholds the payload and returns only a sanitized violation description.
- **Session-local.** Nothing here logs tool arguments or results. Don't write results to a
  file, and don't attempt to re-identify a student from a pseudonym.
- **stdio transport only.** No network port is ever bound.
- **Mirror-bounded, never a live relay.** `get_roster`, `get_submissions`, and
  `get_gradebook_snapshot` serve exclusively from the local CanvasMirror
  (`docs/mirror.md`). `get_seating_context` combines current mirrored identity
  and section membership with private local Roster context. All four refuse
  with a clear error when the required mirror data is stale or missing, instead
  of fetching live from Canvas. The assistant's only way past a refusal is
  `refresh_mirror`, which triggers Canvas Expert's own sync and reports
  freshness — never Canvas data. This keeps the AI's whole path to Canvas
  indirect: it can ask Canvas Expert to sync, then read what Canvas Expert
  wrote to disk, but it can never receive a live Canvas response directly.

## Tools

Tool schema version 9.

| Tool | Purpose | Student data? |
|---|---|---|
| `list_courses` | Every saved course (Current + Previous) | No |
| `list_sections(course_id)` | Section names from the local mirror roster; how to find the exact `section_name` `get_seating_context` requires | No |
| `get_course_assignments(course_id, full_descriptions=false)` | Assignments from the local course catalog (disk-only); descriptions trimmed to a preview unless `full_descriptions` | No |
| `get_modules(course_id, include_items=false)` | Module structure from the local course catalog (disk-only); `include_items` nests each module's items | No |
| `get_authoring_contract(kind)` | The Forge authoring contract (envelope format) for one content kind (`quiz`, `assignment`, `page`, `rubric`), served verbatim from `api/default_docs/AI Authoring/` | No |
| `get_product_guide(topic="")` | CanvasExpert's own product knowledge, served verbatim from the same `api/default_docs/AI Authoring/` source: the CanvasAgent briefing by default, `writing_timeline` for tracked vs not-tracked assignments | No |
| `list_staged_content(kind="")` | Drafts already staged in the per-kind To Review folder, so an assistant can confirm a drop landed instead of losing track or duplicating it; pass `kind` to narrow, omit for all four | No |
| `get_roster(course_id)` | Table of `(pseudonym, section_names)`, mirror-only | Yes — pseudonymized |
| `get_seating_context(course_id, section_name)` | `mirror+local`: one exact section's current mirrored identity/membership plus private local pseudonymized supports, score values, AI-context notes, and pair preferences; excludes IDs, private notes, and private relationship reasons | Yes — pseudonymized |
| `get_submissions(course_id, assignment_id, include_text=true, pseudonyms="", max_text_chars=2000)` | One assignment's submissions, scrubbed, mirror-only | Yes — pseudonymized |
| `get_gradebook_snapshot(course_id)` | Whole-course per-assignment/per-student stats, mirror-only | Yes — pseudonymized |
| `refresh_mirror(course_id)` | Sync this course's local mirror from Canvas, then report freshness status | No — returns a sync status, never course data |

`get_course_assignments` and `get_modules` only read the local course catalog written by
the CanvasExpert web UI — neither ever falls back to a live Canvas call. If the catalog
hasn't been refreshed yet, refresh it from the web UI first, then retry. Unlike the mirror
tools below, `get_modules` never refuses on staleness: it returns whatever module records
the catalog holds, labeled with `source`, `synced_at`, and `state`, since module structure
is far lower-risk than student data.

`get_authoring_contract(kind)` takes no `course_id` and carries no student data, so it
needs no course gate, no identity vault, and no safety scan. It reads the same
`api/default_docs/AI Authoring/` file the web UI's own `/api/download-contract` route
serves, so the Forge envelope format lives in exactly one place. Pull it before authoring
a quiz, assignment, page, or rubric so the resulting file validates.

`get_product_guide(topic="")` closes the gap between what the tool list implies and what
the app actually does — an assistant that sees only the read tools cannot tell that
Writing Timeline exists, or that every writing assignment is *tracked* (File Upload alone,
`docx` alone, so PowerGrader reads the submitted document's revision history) or *not
tracked*. It reads the same canonical files `/api/download-contract` hands out for pasting
into a chat-only assistant (`CanvasAgent`, `WritingTimeline`), so a connected assistant and
a pasted one work from one text rather than two that drift. Same gate posture as
`get_authoring_contract`: no `course_id`, no vault, no safety scan. Every response also
lists the available topics. The always-on server instructions point here rather than
restating any of it.

`list_staged_content(kind="")` also takes no `course_id` and carries no student data, so
it likewise needs no course gate, no identity vault, and no safety scan. It reuses
`webui.deps.list_inbox_files` (the same marker-gated To Review listing the push tabs use) and
returns only each draft's label, never its absolute path. Pass `kind` to narrow to one of
`quiz`, `assignment`, `page`, or `rubric`; omit it to see everything staged across all four.

`get_roster`, `get_submissions`, and `get_gradebook_snapshot` only read the local
CanvasMirror. `get_seating_context` uses the current mirror for identity and section
membership, then joins the private local Roster context for that course. None fall back to
a live Canvas call. If the required mirror data is stale or missing, they return
`{"ok": false, "error": "..."}` naming the problem; call `refresh_mirror(course_id)` and
retry the same read once it reports `"synced"`.

Every `course_id` tool is scoped to Current courses (`config.active_courses()`) — the same
scope the web UI uses. `get_seating_context` requires exactly one matching mirror section
name and withholds all student data when the name is absent or ambiguous. Pseudonymized
artifacts are scrubbed, not anonymous or guaranteed FERPA-safe; teachers review them before
any external upload.

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
intended, not a bug. If the mirror hasn't synced this course yet, `get_gradebook_snapshot`
(or `get_roster`/`get_submissions`) refuses instead — call `refresh_mirror` for that course
and retry.
