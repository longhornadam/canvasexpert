# CanvasExpert MCP server

A local, stdio-only [Model Context Protocol](https://modelcontextprotocol.io) server that
lets any MCP-capable assistant help plan lessons and manage rosters conversationally,
while CanvasExpert keeps sole custody of the Canvas PAT and almost every write path.

- **Local and indirect.** Serves this teacher's own Canvas data from Canvas Expert's
  local copy on their computer. It never holds the Canvas token. Writes nothing beyond
  the identity vault it already shares with the rest of CanvasExpert, except one
  explicit, digest-protected roster tool (`canvas_group`) that reassigns a student's
  real Canvas group membership when the teacher tells the assistant to do it.
- **Pseudonymized, not anonymous.** Every student-data tool routes its result through the identity vault
  (`api/feedback_vault.py`) before returning it. Students are identified only by a stable
  one-word pseudonym (e.g. "Pikachu") — never a real name, Canvas user ID, or SIS ID. See
  `docs/contracts/pseudonym-contract.md` for the full pseudonym shape contract.
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

Tool schema version 30 (47 tools).

| Tool | Purpose | Student data? |
|---|---|---|
| `list_courses` | Every saved course (Current + Previous) | No |
| `list_sections(course_id)` | Section ids and names from the local mirror roster; how to find the `section_id` or `section_name` `get_seating_context` takes | No |
| `get_course_assignments(course_id, full_descriptions=false)` | Assignments from the local course catalog (disk-only); descriptions trimmed to a preview unless `full_descriptions` | No |
| `get_modules(course_id, include_items=false)` | Module structure from the local course catalog (disk-only); `include_items` nests each module's items with their catalog `content_id` | No |
| `get_course_pages(course_id, full_text=false)` | Published normalized pages from the Current course's local v3 catalog; body text is bounded unless explicitly requested | No |
| `list_learning_objectives(course_id)` | Current reviewed learning objectives as a compact table; Current-course and local-document gated | No |
| `preview_learning_objective(course_id, objective, effective_start, effective_end, source_refs, replaces?)` | Exact reviewed create or replacement preview grounded in current local module, assignment, or page records | No |
| `apply_learning_objective(course_id, preview, preview_digest, expected_revision)` | Applies only the exact reviewed create or replacement preview after catalog/source/revision checks; replacement identity comes from the digest-protected preview | No |
| `delete_learning_objective(course_id, entry_id, expected_revision)` | Directly deletes one selected reviewed objective with revision protection | No |
| `get_authoring_contract(kind)` | Canonical authoring contract for Forge (`quiz`, `assignment`, `page`, `rubric`) from `api/default_docs/AI Authoring/` | No |
| `get_product_guide(topic="")` | CanvasExpert's own product knowledge, served verbatim from the same `api/default_docs/AI Authoring/` source: the CanvasAgent briefing by default, `writing_timeline` for tracked vs not-tracked assignments | No |
| `get_standards_profile()` | Published local DataForge standards profile, safety-scanned before return; no `course_id` and no Canvas call | Yes — pseudonymized |
| `get_assessment_context(course_id, pseudonyms="")` | Bounded current-roster join with local longitudinal DataForge assessment evidence; exact trimmed/case-folded pseudonym filters, observational only, no Canvas fallback | Yes — pseudonymized |
| `get_assessment_grouping_proposal(course_id, snapshot_id, method="overall_pct", cutoffs="", no_data_group="", group_set_label="")` | Read-only Students-page grouping proposal over a local snapshot; exact teacher-safe group-set label, bounded pseudonym placements, no Canvas apply path | Yes — pseudonymized |
| `list_staged_content(kind="")` | Drafts already staged in the per-kind To Review folder, so an assistant can confirm a drop landed instead of losing track or duplicating it; pass `kind` to narrow, omit for all four | No |
| `get_roster(course_id)` | Table of `(pseudonym, section_names)`, mirror-only | Yes — pseudonymized |
| `get_roster_student_settings(course_id, pseudonym)` | Safe local settings projection; stored nicknames and seating private notes are omitted, and the AI-context note is scrubbed | Yes — pseudonymized |
| `preview_roster_student_change(course_id, pseudonym, patch)` | Digest-protected preview of a pseudonym-first settings change; use before apply | Yes — pseudonymized |
| `apply_roster_student_change(course_id, preview, preview_digest, expected_settings_digest)` | Applies the exact reviewed preview through the existing Roster mutation path; a `canvas_group` patch reaches Canvas | Yes — pseudonymized |
| `clear_roster_student_field(course_id, pseudonym, field, expected_settings_digest)` | Direct digest-protected clear for supported local settings; nickname fields are rejected | Yes — pseudonymized |
| `get_seating_context(course_id, section_name="", section_id="")` | `mirror+local`: one section's current mirrored identity/membership plus private local pseudonymized supports, score values, AI-context notes, and pair preferences; excludes IDs, private notes, and private relationship reasons | Yes — pseudonymized |
| `get_submissions(course_id, assignment_id, include_text=true, pseudonyms="", max_text_chars=2000)` | One assignment's submissions, scrubbed, mirror-only | Yes — pseudonymized |
| `get_writing_history(pseudonym, since="", until="", include_text=false, max_text_chars=2000)` | One student's Writing Record across time: dated submissions, assignment context, word counts, segment attribution, structural flags. No `course_id`; this reads a private per-student store, not a course, and it does not score or judge work | Yes — pseudonymized |
| `get_gradebook_snapshot(course_id)` | Whole-course per-assignment/per-student stats, mirror-only | Yes — pseudonymized |
| `refresh_mirror(course_id)` | Sync this course's local mirror from Canvas, then report freshness status | No — returns a sync status, never course data |
| `get_bell_schedule(schedule_id="")` | Bell schedule CSV(s) from the workspace | No |
| `get_day_schedule(date)` | Resolved schedule blocks for one date | No |
| `get_teacher_schedule()` | The teacher's own block-name mapping | No |
| `save_teacher_schedule(blocks)` | Replaces the teacher's schedule blocks live | No |
| `get_school_calendar(date_from="", date_to="")` | Canonical School Calendar readiness, plus a bounded range of days/grading-periods/events when both dates are given | No |
| `preview_school_calendar_replacement(school_year, coverage_start, coverage_end, default_schedule_id, ...)` | Previews creating/replacing the complete canonical School Calendar for one year; returns the base revision (0 for a first-ever calendar) and material change counts | No |
| `apply_school_calendar_replacement(preview, expected_revision)` | Applies a previewed create/replace; refuses a stale `expected_revision` | No |
| `preview_school_calendar_change(kind, ...)` | Previews a day-kind/schedule/label change against the live calendar; returns the base revision and affected dates | No |
| `apply_school_calendar_change(preview, expected_revision)` | Applies a previewed change; refuses a stale `expected_revision` | No |
| `preview_school_calendar_event_change(action, event=None, event_id="")` | Previews an upsert or delete of one canonical public event and returns before/after projections | No |
| `apply_school_calendar_event_change(preview, expected_revision)` | Applies a previewed public-event change; refuses stale or altered previews | No |
| `preview_school_calendar_game_score(event_id, score)` | Previews changing the result of one existing `game` event while carrying every other field forward unchanged | No |
| `apply_school_calendar_game_score(preview, expected_revision)` | Applies the exact reviewed game-score preview; refuses stale, altered, or non-game previews | No |
| `list_scoring_sessions()` | PowerGrader sessions with SAFE bundles, Current courses only, as `{session_id, assignment_name, course_id, created, mode_label, total, scored, approved, assignment_id, newer_session_exists, staged_at}` | No |
| `get_scoring_packet(session_id, offset=0, limit=10, include_context=true)` | Pseudonymized student responses from one PowerGrader session's SAFE bundle, paged by response, text-only (no media), with a budget guard; context includes the declared rubric name and whether its text resolved | Yes — pseudonymized |
| `stage_scores(session_id, results, expected_packet_digest)` | Stage AI-generated scores back into a PowerGrader session for teacher review; returns updated count, unresolved count, and validation verdict; never posts to Canvas | Yes — pseudonymized |
| `get_theme_contract()` | The Panel theme format: the three or four colours and two names you set, the sixteen variables derived for you, and the closed font/ornament sets | No |
| `list_panel_themes()` | Built-in Panel themes plus the teacher's own as `(key, label, origin, authored_at)`, with any theme file that could not be read | No |
| `list_theme_art()` | Art files present in `Library/Panels/Themes/art/`, with each one's kind, dimensions or viewBox, and any diagnostic; call it so a theme references a filename that exists instead of an invented one | No |
| `preview_panel_theme(key, label, colors, font="sans", ornament="grid", art=None)` | Digest-protected preview of a theme: the derived palette, every measured contrast pairing, and any colour corrected to clear 4.5:1; `art` places named files from the art folder | No |
| `apply_panel_theme(preview, preview_digest)` | Writes exactly the previewed theme to `Library/Panels/Themes/<key>.json`; refuses a stale or altered preview | No |
| `delete_panel_theme(key)` | Deletes one of the teacher's own themes; built-in keys are refused | No |

`get_course_assignments` and `get_modules` only read the local course catalog written by
the CanvasExpert web UI — neither ever falls back to a live Canvas call. If the catalog
hasn't been refreshed yet, refresh it from the web UI first, then retry. Unlike the mirror
tools below, `get_modules` never refuses on staleness: it returns whatever module records
the catalog holds, labeled with `source`, `synced_at`, and `state`, since module structure
is far lower-risk than student data.

`get_authoring_contract(kind)` takes no `course_id` and carries no student data, so it
needs no course gate, no identity vault, and no safety scan. Forge kinds (`quiz`, `assignment`, `page`, `rubric`) read the same
`api/default_docs/AI Authoring/` file the web UI's `/api/download-contract` route serves,
then receive the Forge-only staging appendix. The schedule writer is the only direct local
write in this group and has no staging/review appendix.

The six Panel theme tools take no `course_id` and carry no student data, so they need
no course gate, no identity vault, and no safety scan. They are the one write surface here
that hands an assistant a file-writing path with no teacher review queue in front of it,
which is deliberate and rests on the format doing the safety work rather than the
assistant: colours are parsed to integers and re-serialized (a colour cannot be a CSS
fragment), fonts and ornaments come from closed sets (a theme cannot reach the network),
the generated CSS can only ever produce `html[data-panel-theme="<key>"]` (a theme cannot
change layout or what a Panel shows), and every text-on-background pairing is measured and
corrected to at least 4.5:1 (an assistant cannot produce an illegible projector). A
built-in key is refused rather than shadowed, at most 24 custom themes are kept, and a
malformed file is skipped with a reason instead of taking a saved board down.

Theme art keeps the same shape. An `art` entry names a file the teacher already put in
`Library/Panels/Themes/art/`; the assistant cannot supply an image, a path, or a URL, only
a filename that is already there, which is why `list_theme_art` exists and why inventing a
name is the one thing to avoid. Placement, recolour, size, and opacity are closed sets and
bounded numbers, so art can decorate a board but cannot resize its type or fetch anything.

Call `get_theme_contract` first; `preview_panel_theme` reports what it corrected, which is
worth telling the teacher. See `docs/reference/panels-route-card.md` for the full model.

`save_teacher_schedule` has no `course_id` parameter and makes no
Canvas call; a teacher-set block `course_id` passes through untouched after string
validation, so an assistant can read, edit, and write the binding safely.

The nine canonical Calendar tools (`get_school_calendar`,
`preview_school_calendar_replacement`, `apply_school_calendar_replacement`,
`preview_school_calendar_change`, `apply_school_calendar_change`,
`preview_school_calendar_event_change`, `apply_school_calendar_event_change`,
`preview_school_calendar_game_score`, `apply_school_calendar_game_score`) share the same
exemption: no `course_id`, no student data, no course gate, no safety scan. All writes
are staged preview/apply pairs, never a one-click overwrite: base revision is 0 only
before any calendar exists, and every successful write after that — including a complete
replacement — advances the revision by exactly one, never resetting it. The authoring
contract instructs the assistant to translate pasted public schedule facts into a
preview, summarize affected dates/years and conflicts, and apply only after the teacher
accepts that summary — never inside an email/inbox integration or a free-text parser
built into CanvasExpert itself. The event pair uses `action="upsert"` with one complete
structured event or `action="delete"` with its stable `event_id`; it mutates only the
canonical `events` array and supports the same revision/digest/atomic-write boundary.
The game-score pair is intentionally narrower: it requires an existing stable event ID whose
kind is `game`, changes only its `result`, and preserves the event's label, date, shape, and
other fields. It is the preferred tool for recording a result on a game that is already on the
calendar; it does not create or retarget events.

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

`get_standards_profile()` reads the one published local
`For AI/DataForge/standards-profile.json` artifact. It is offline and has no
`course_id`, but it is still student data: the Identity Vault and the same
outbound safety scan are required before the pseudonymized profile leaves the
process. A missing, malformed, unsupported, or unsafe artifact is withheld with
a structured error. It does not generate a profile, call Canvas, or apply a
grouping; the teacher reviews the profile and uses the Assessments coverage and
Students grouping surfaces for any later local review/apply step.

`get_assessment_context(course_id, pseudonyms="")` first requires a current local
mirror roster, then joins only its canonical pseudonyms to the published profile.
The roster source is labeled `local_mirror`; the assessment source is labeled
`local_longitudinal_history` with the profile's `generated`, `grain`, and
`snapshots_used` metadata. The result reports four coverage counts: current-roster
students with and without history, requested pseudonyms outside the current roster,
and published-profile students outside the current roster. It returns at most 25
students, at most 32 standards per student, and at most 8 `assessed_in` labels per
standard; a limit refusal never truncates evidence. Missing, stale, malformed, or
inconsistent roster state returns no rows with `action: "refresh_mirror"`. The tool
reports percentages and standards as source facts; it does not encode placement,
capability, integrity, remediation, or other judgment labels.

`get_assessment_grouping_proposal(course_id, snapshot_id, method="overall_pct", cutoffs="", no_data_group="", group_set_label="")`
requires a Current course, a current local roster mirror, and a current local group mirror.
The snapshot identifier is the exact trimmed local history ID. `group_set_label` is matched
after trim and case-folding against the teacher-facing Canvas group-category label; missing
or duplicate labels are blocking errors, and raw category/group IDs are never accepted from
or returned to the assistant. The proposal reuses the Students page's
`api.dataforge.canvas_join.build_coverage_report` and
`api.dataforge.grouping.build_grouping_proposal` seams, so method, cutoffs, No Data placement,
counts, tier membership, and the existing `proposal_digest` remain the UI proposal's facts.
The returned groups and placements contain pseudonyms only. Missing, stale, malformed, or
ambiguous local sources return no proposal rows and no live Canvas fallback. The tool is
read-only: the teacher reviews and applies a digest-protected change in Students; the
assistant must never imply that a Canvas group change was applied.

`list_staged_content(kind="")` also takes no `course_id` and carries no student data, so
it likewise needs no course gate, no identity vault, and no safety scan. It reuses
`webui.deps.list_inbox_files` (the same marker-gated To Review listing the push tabs use) and
returns only each draft's label, never its absolute path. Pass `kind` to narrow to one of
`quiz`, `assignment`, `page`, or `rubric`; omit it to see everything staged across all four.

**Scoring Packet Workflow (v22).** `list_scoring_sessions()` discovers PowerGrader sessions
with AI-ready SAFE bundles in Current courses; a session whose bundle is no longer on disk is
left out rather than offered and then refused. `get_scoring_packet()` retrieves one session's
pseudonymized student responses with full text (no truncation, no media) and a digest for
concurrency protection. The response includes a contract (scoring instructions) when
`include_context=true`, so later pages can set it false and save the tokens. `stage_scores()`
takes the scored results and stages them into the session for teacher review in PowerGrader;
it never posts to Canvas (the teacher pushes manually), and it takes the same session lock and
clears the same pending push review as the web UI's own import path. The digest guard
(`expected_packet_digest`) prevents stale scores from landing if the session has been re-run
between retrieval and staging.

Paging counts *responses*, not students. A multi-item quiz gives one row per student per item,
so `offset`, `limit`, `total` and `next_offset` are all measured in rows, and `students_total`
carries the distinct-student count separately. Walk pages by following `next_offset` until it
is absent rather than comparing an offset against `total`. Over the 25,000-token budget the
page is refused rather than trimmed, and the refusal names a smaller `limit` that fits, scaled
to how far over the page landed.

The safety scan walks dict keys, so it cannot see into `{columns, rows}` tables. Every tool
that returns student text therefore gates the dict-row payload first and tabulates only after
the gate has passed it, `get_scoring_packet` included.

`get_roster`, `get_submissions`, and `get_gradebook_snapshot` only read the local
CanvasMirror. `get_seating_context` uses the current mirror for identity and section
membership, then joins the private local Roster context for that course. None fall back to
a live Canvas call. If the required mirror data is stale or missing, they return
`{"ok": false, "error": "..."}` naming the problem; call `refresh_mirror(course_id)` and
retry the same read once it reports `"synced"`.

Stale `get_modules` and `get_course_pages` results name the Course Catalog refresh surface
as their repair. `refresh_mirror` reports only its actual roster, assignments, and
submissions scope; it does not refresh catalog modules or pages.

Student-data tools (`get_roster`, `get_submissions`, `get_gradebook_snapshot`, and
`get_seating_context`) are scoped to Current courses (`config.active_courses()`). The
catalog reads (`list_sections`, `get_course_assignments`, and `get_modules`) and
`refresh_mirror` accept any saved course, including Previous courses. `get_course_pages` and
the Learning Objective preview/apply pair require a Current course. `get_seating_context`
needs its `section_id` or `section_name` to resolve to exactly one mirror section: an id
matches directly, a name matches exactly or, failing that, on a trim/case-fold retry, and
it withholds all student data rather than guess when a name matches none or several
sections (the latter names the candidate ids to retry with). Pseudonymized
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
- `get_assessment_context` accepts the same comma-separated, trimmed, case-insensitive
  pseudonym filter and returns compact student rows with bounded standards evidence;
  omit the filter for the current roster (up to 25 students), or name only the students
  needed for the question. It refuses rather than silently truncating students or
  standards, and a missing/stale mirror requires `refresh_mirror` before retrying.
- `get_assessment_grouping_proposal` returns at most 25 current-roster placements and
  refuses rather than truncating when the compact result exceeds 20,000 serialized
  characters. It reports the method, cutoffs, group-set label, No Data group, coverage,
  group counts/membership, and proposal digest. Use the Students UI for review and apply.
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
