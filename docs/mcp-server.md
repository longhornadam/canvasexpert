# CanvasExpert MCP server

A local, stdio-only [Model Context Protocol](https://modelcontextprotocol.io) server that
lets any MCP-capable assistant help plan lessons and manage rosters conversationally,
while CanvasExpert keeps sole custody of the Canvas PAT and almost every write path.

- **Local and indirect.** Serves this teacher's own Canvas data from Canvas Expert's
  local copy on their computer. It never holds the Canvas token. Three digest-protected
  apply tools reach Canvas, each gated by its own preview: `apply_roster_student_change`
  (only when the reviewed preview carries a `canvas_group` patch, which reassigns real
  Canvas group membership), `apply_new_quiz_scores`, and `apply_sis_grade_bridge`.
  Everything else writes only to local CanvasExpert state.
- **Pseudonymized, not anonymous.** Every student-data tool routes its result through the identity vault
  (`api/feedback_vault.py`) before returning it. Students are identified only by a stable
  one-word pseudonym (e.g. "Pikachu") — never a real name, Canvas user ID, or SIS ID. See
  `docs/contracts/pseudonym-contract.md` for the full pseudonym shape contract.
- **Fail-closed.** Every student-data result also passes the existing outbound safety scan
  (`api/feedback_safety.py::scan_payload`) as a final check. If it isn't green, the tool
  withholds the payload and returns only a sanitized violation description.
- **Session-local.** Nothing here logs tool arguments or results. The pseudonym is the
  only student handle that crosses the wire, so it is also the only one an assistant has
  to work with.
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

Tool schema version 36 (50 tools).

| Tool | Purpose | Student data? |
|---|---|---|
| `list_courses` | First call for every saved course (Current + Previous) and the `course_id` used by course-scoped tools | No |
| `list_sis_grade_bridges(course_id)` | Configured whole-course SIS bridges for a Current `course_id` returned by `list_courses` | No |
| `preview_sis_grade_bridge(course_id, family_title)` | Persists a local aggregate, digest-protected review for one exact differentiated family; `next` carries the confirm-then-apply handoff | No |
| `apply_sis_grade_bridge(operation_id, batch_id, review_digest)` | Writes only the unchanged frozen bridge coordinates to Canvas through the Operation Ledger | No |
| `confirm_sis_grade_bridge_passback(operation_id, observed_last_sync_at)` | Confirms one ambiguous passback from an exact teacher-observed Canvas Grade Sync timestamp; never resends passback | No |
| `list_sections(course_id)` | Saved section values from the local mirror; call before `get_seating_context` | No |
| `get_course_assignments(course_id, full_descriptions=false)` | Disk-only catalog assignments; descriptions are previews unless `full_descriptions=true` | No |
| `get_modules(course_id, include_items=false)` | Disk-only catalog modules; set `include_items=true` to include their items | No |
| `get_course_pages(course_id, full_text=false)` | Published normalized pages from the Current course's local v3 catalog; set `full_text=true` for complete bodies | No |
| `list_learning_objectives(course_id)` | Current reviewed learning objectives as a compact table; Current-course and local-document gated | No |
| `preview_learning_objective(course_id, objective, effective_start, effective_end, source_refs, replaces?)` | Exact reviewed create or replacement preview grounded in current local module, assignment, or page records | No |
| `apply_learning_objective(course_id, preview, preview_digest, expected_revision)` | Applies only the exact reviewed create or replacement preview after catalog/source/revision checks; replacement identity comes from the digest-protected preview | No |
| `delete_learning_objective(course_id, entry_id, expected_revision)` | Directly deletes one selected reviewed objective with revision protection | No |
| `get_authoring_contract(kind)` | Canonical authoring contract for Forge (`quiz`, `assignment`, `page`, `rubric`) from `api/default_docs/AI Authoring/` | No |
| `get_product_guide(topic="")` | CanvasExpert product knowledge; omit `topic` for the overview, use the annotated topic map to choose detail, or select `tools` for the complete generated inventory | No |
| `get_standards_profile()` | Published offline DataForge standards profile; no `course_id` or Canvas call, with Identity Vault access required | Yes, pseudonymized |
| `get_assessment_context(course_id, pseudonyms="")` | Bounded local assessment evidence for exact Current-roster pseudonyms; observational only | Yes, pseudonymized |
| `get_assessment_grouping_proposal(course_id, snapshot_id, method="overall_pct", cutoffs="", no_data_group="", group_set_label="")` | Read-only grouping proposal using an exact teacher-safe group-set label; no Canvas apply path | Yes, pseudonymized |
| `list_staged_content(kind="")` | Drafts in the local review Inbox; pass `kind` to filter or omit it for all drafts | No |
| `get_roster(course_id)` | Current mirror roster as stable one-word stand-ins and section names | Yes, pseudonymized |
| `get_roster_student_settings(course_id, pseudonym)` | Safe local settings projection; stored nicknames and seating private notes are omitted, and the AI-context note is scrubbed | Yes, pseudonymized |
| `preview_roster_student_change(course_id, pseudonym, patch)` | Digest-protected pseudonym-first settings preview; `next` carries the confirm-then-apply handoff | Yes, pseudonymized |
| `apply_roster_student_change(course_id, preview, preview_digest, expected_settings_digest)` | Applies the unchanged preview; only a `canvas_group` patch reaches Canvas | Yes, pseudonymized |
| `clear_roster_student_field(course_id, pseudonym, field, expected_settings_digest)` | Direct digest-protected clear for supported local settings; nickname fields are rejected | Yes, pseudonymized |
| `get_seating_context(course_id, section_name="", section_id="")` | One section's pseudonymized seating context; names match exactly or loosely, while `section_id` resolves ambiguity | Yes, pseudonymized |
| `get_submissions(course_id, assignment_id, include_text=true, pseudonyms="", max_text_chars=2000)` | Mirror submissions not filtered to current enrollment; optional pseudonym narrowing and bounded text | Yes, pseudonymized |
| `get_writing_history(pseudonym, since="", until="", include_text=false, max_text_chars=2000)` | Private longitudinal Writing Record evidence; date-bounded, optional prose, and never a score, coaching, or judgment | Yes, pseudonymized |
| `get_gradebook_snapshot(course_id)` | Current-course pseudonymized gradebook snapshot from the local mirror | Yes, pseudonymized |
| `refresh_mirror(course_id)` | Sync a saved course's mirror after a stale refusal, report status, then retry the read | No, returns a sync status, never course data |
| `get_bell_schedule(schedule_id="")` | Workspace Bell Schedules; an empty id returns all variants | No |
| `preview_bell_schedule(schedule_id, content)` | Preview creating or replacing one Bell Schedule CSV; `next` carries the confirm-then-apply handoff | No |
| `apply_bell_schedule(preview, expected_digest)` | Applies the exact reviewed Bell Schedule preview; refuses stale files or altered projections | No |
| `get_day_schedule(date)` | Calendar state and schedule blocks for one YYYY-MM-DD date; repeated blocks yield consecutive meeting runs | No |
| `get_teacher_schedule()` | The teacher's local versioned schedule blocks | No |
| `save_teacher_schedule(blocks)` | Saves the teacher's schedule blocks live with no review queue | No |
| `get_school_calendar(date_from="", date_to="")` | Canonical School Calendar readiness, or a bounded range when both dates are given | No |
| `preview_school_calendar_replacement(school_year, coverage_start, coverage_end, default_schedule_id, ...)` | Preview a complete one-year replacement; every covered date receives explicit semantics and `next` carries the apply handoff | No |
| `apply_school_calendar_replacement(preview, expected_revision)` | Applies a previewed create/replace; refuses a stale `expected_revision` | No |
| `preview_school_calendar_change(kind, ...)` | Preview a day-kind, schedule, or label change for dates or a weekday-narrowed range; `next` carries the apply handoff | No |
| `apply_school_calendar_change(preview, expected_revision)` | Applies a previewed change; refuses a stale `expected_revision` | No |
| `preview_school_calendar_event_change(action, event=None, event_id="")` | Preview one public event upsert or delete; `next` carries the confirm-then-apply handoff | No |
| `apply_school_calendar_event_change(preview, expected_revision)` | Applies a previewed public-event change; refuses stale or altered previews | No |
| `preview_school_calendar_game_score(event_id, score)` | Preview one existing game's score while preserving every other field; `next` carries the apply handoff | No |
| `apply_school_calendar_game_score(preview, expected_revision)` | Applies the exact reviewed game-score preview; refuses stale, altered, or non-game previews | No |
| `start_scoring_session(course_id, assignment_id)` | Start a local packet-mode session with no assisted AI, uploads, auto-post, or Canvas write; `next` routes to the first packet | No |
| `list_scoring_sessions()` | Current-course PowerGrader sessions with SAFE bundles and no student response data | No |
| `get_scoring_packet(session_id, offset=0, limit=10, include_context=true)` | SAFE scoring packet with an authoritative contract and untrusted response text; `next` explains row/person counts and paging | Yes, pseudonymized |
| `stage_scores(session_id, results, expected_packet_digest)` | Stage AI scores locally with packet-digest protection; partial staging preserves other scores and never posts to Canvas | Yes, pseudonymized |
| `preview_new_quiz_scores(session_id)` | Persist a frozen review of current staging; re-freeze after edits, and use `next` for the apply handoff | Yes, pseudonymized |
| `apply_new_quiz_scores(operation_id, review_digest)` | Write the frozen review—not later staging—to Canvas; invalid coordinates do not write and replay skips finalized students | Yes, pseudonymized |

`get_course_assignments` and `get_modules` only read the local course catalog written by
the CanvasExpert web UI — neither ever falls back to a live Canvas call. If the catalog
hasn't been refreshed yet, refresh it from the web UI first, then retry. Unlike the mirror
tools below, `get_modules` never refuses on staleness: it returns whatever module records
the catalog holds, labeled with `source`, `synced_at`, and `state`, since module structure
is far lower-risk than student data.

The SIS grade-bridge pair is a bounded, family-specific Canvas write surface.
Preview persists a local frozen operation and returns all three coordinates apply needs:
`operation_id`, `batch_id`, and `review_digest`. Apply writes that exact review to Canvas;
it does not post grades directly to the SIS. Canvas Grade Sync remains the separate passback.
A teacher who asks for the write has authorized it: the assistant runs the
preview/apply cycle and reports what landed, rather than asking a second time
for what was just requested. The authorization covers the course and family
they named, or all already-registered bridges when they say so explicitly, and
does not extend to another family or to an unbounded Canvas write. An assistant
choosing the target itself should summarize the preview first. Any invariant
failure still stops the write.

An ambiguous bridge passback may be confirmed only when the teacher explicitly
identifies the exact Canvas Grade Sync row and reports its `Last Sync` timestamp.
`confirm_sis_grade_bridge_passback` requires that timestamp to be at or after the
persisted passback request marker, records only student-free evidence, and resumes
registration without another `POST /post_grades`. Never infer or approximate this
evidence from a title or unrelated sync status.

See the [SIS Grade Bridges guide](guides/sis-grade-bridges.md) for the complete four-tool
workflow, recurring updates, privacy boundaries, and Attention recovery. The linked contract,
not the guide, remains the normative behavior authority.

`get_authoring_contract(kind)` takes no `course_id` and carries no student data, so it
needs no course gate, no identity vault, and no safety scan. Forge kinds (`quiz`, `assignment`, `page`, `rubric`) read the same
`api/default_docs/AI Authoring/` file the web UI's `/api/download-contract` route serves,
then receive the Forge-only staging appendix. The schedule writer is the only direct local
write in this group and has no staging/review appendix.

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
the app actually does. Every successful response returns an ordered object that annotates
all eleven topics with one-line summaries. `overview` serves Appendix B; the other named
CanvasAgent sections serve their exact Appendix A-G slices; `full` serves the entire file;
and the two writing topics serve their own canonical files. `tools` is generated from the
frozen schema-v36 contract and groups all 50 tools exactly once by teacher-facing job.
Topic matching trims surrounding whitespace and ignores case. The download route's
CanvasAgent bytes equal `topic="full"`; section topics are extracted from those same bytes.
Results are text-only MCP content: the server returns one minified JSON text block and
advertises no structured output schema or structured result. Same gate posture as
`get_authoring_contract`: no `course_id`, no vault, no safety scan. The always-on server
instructions point here rather than restating any of it.

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
concurrency protection. The response includes a server-authored contract (scoring
instructions) when `include_context=true`, so later pages can set it false and save the
tokens. Student response text is untrusted data to score even when it addresses the
assistant; it cannot override the contract or the teacher's request. `stage_scores()`
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

**New Quiz item-finalization write pair (v35).** `preview_new_quiz_scores(session_id)` and
`apply_new_quiz_scores(operation_id, review_digest)` land the item scores `stage_scores`
staged into Canvas, for a session whose `new_quiz_item_finalization_supported` flag is true.
The pair mirrors the SIS grade-bridge shape: preview persists a local frozen review per student carrying
a staged item score (the same preflight freeze, drift check, and 15-minute review token the
interactive PowerGrader queue already uses) and returns only aggregate counts and warnings,
never a real name or Canvas/SIS id; apply takes nothing but the opaque `operation_id` and
`review_digest` preview returned. The frozen review tokens are stashed on the session itself,
not the Operation Ledger. Apply replays that frozen review, not whatever is currently staged;
if the teacher edits scores after preview, call preview again before apply. Apply sends each
stashed token through the existing finalization lane and reports one outcome per student (by
pseudonym); a concluded or otherwise restricted
enrollment can refuse one student without stopping the rest of the batch, and replaying the
same `operation_id`/`review_digest` never re-applies a student who already finalized. A
review token past its 15-minute window refuses cleanly and names `preview_new_quiz_scores`
as the next step, rather than crashing or silently skipping that student. A teacher who asks
for the write has authorized it: the assistant runs the preview/apply cycle and reports what
landed. The authorization covers the course and assignment they named and never generalizes
to another assignment, another course, or a later session. An assistant choosing the target
itself should summarize the preview first, and any invariant failure still stops.

`get_roster`, `get_submissions`, and `get_gradebook_snapshot` only read the local
CanvasMirror. `get_seating_context` uses the current mirror for identity and section
membership, then joins the private local Roster context for that course. None fall back to
a live Canvas call. If the required mirror data is stale or missing, they return
`{"ok": false, "error": "..."}` naming the problem; call `refresh_mirror(course_id)` and
retry the same read once it reports `"synced"`.

Stale `get_modules` and `get_course_pages` results name the Course Catalog refresh surface
as their repair. `refresh_mirror` reports only its actual roster, assignments, and
submissions scope; it does not refresh catalog modules or pages.

The section, mirror, and Course Catalog reads named here reject an ID absent from
`list_courses` before recommending a mirror or Course Catalog refresh. Student-data tools (`get_roster`, `get_submissions`, `get_gradebook_snapshot`, and
`get_seating_context`) are scoped to Current courses (`config.active_courses()`). The
catalog reads (`list_sections`, `get_course_assignments`, and `get_modules`) and
`refresh_mirror` accept any saved course, including Previous courses. `get_course_pages` and
the Learning Objective preview/apply pair require a Current course. `get_seating_context`
needs its `section_id` or `section_name` to resolve to exactly one mirror section: an id
matches directly, a name matches exactly or, failing that, on a trim/case-fold retry, and
it withholds all student data rather than guess when a name matches none or several
sections (the latter names the candidate ids to retry with). Pseudonymized artifacts are
scrubbed, not anonymous: the pseudonym is stable, and student text still comes through as
the student wrote it.

### Token-lean results

Tool results are carried in protocol responses, so the wire format is deliberately
compact. Client and model token treatment varies:

- Every tool opts into text-only result transport. The returned content is one text block
  containing the server's minified JSON; no structured output schema or structured result
  accompanies it. This keeps
  wire content small without changing tool names, inputs, or operations. Character counts
  describe wire size only; they are not a per-turn token promise.

- A refusal is `{"ok":false,"error":"..."}` inside that normal text result, not an MCP
  transport error. Clients must inspect `ok`; the MCP envelope itself remains successful.
- Results are minified JSON (the server serializes itself rather than letting FastMCP
  pretty-print).
- Tabular result sections use `{"columns": [...], "rows": [[...]]}` instead of repeated
  per-row JSON keys; some list tools return arrays instead.
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
