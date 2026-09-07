"""FastMCP wiring for the CanvasExpert MCP server.

Thin ``@mcp.tool()`` wrappers delegate to the plain functions in
``tools.py`` so the tool layer stays testable without an MCP client. The
authoritative count and shape live in ``contract.TOOL_SCHEMA_VERSION`` and its
snapshot, not in prose here, so this docstring cannot drift. Run via
``api/mcp_server/__main__.py`` over stdio — this module never binds a network
port and is never mounted inside the FastAPI web UI (``api.webui.server``).

Token discipline: the shared privacy rules live ONCE in the server
instructions (not per tool), tool descriptions stay to a functional line or
two, and every result is serialized compactly here — FastMCP would otherwise
pretty-print dict returns with indent=2, which wastes client context on
whitespace. List data is shaped as {columns, rows} tables in ``tools.py``.
Wire character counts are a transport measure, not a per-turn token promise.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import tools

_SERVER_INSTRUCTIONS = (
    "CanvasExpert reads this teacher's own Canvas courses, assignments, "
    "rosters, grades, submissions, and seating context from a local copy on "
    "their computer. Call list_courses first for a course_id. Student data "
    "comes through a local vault: stable one-word stand-in names (e.g. "
    "\"Pikachu\") take the place of real students, and real names and Canvas/SIS "
    "ids stay on the machine, so the stand-in is the only handle you have. "
    "get_roster, get_seating_context, get_submissions, and "
    "get_gradebook_snapshot serve only from the local mirror and refuse when "
    "it is stale; call refresh_mirror for that course, then retry once. "
    "Results are compact JSON, with list data as {columns, rows} tables. "
    "Prefer narrow calls: include_text=false or specific stand-ins first. "
    "To help the teacher create other content, call get_authoring_contract "
    "for the kind and follow the staging steps in its response. "
    "For AI-assisted scoring: call list_scoring_sessions, get_scoring_packet "
    "for the pseudonymized bundle, score it with your chosen LLM, then "
    "stage_scores. The PowerGrader queue is where scored work belongs by "
    "default; the teacher reviews it there, and staged scores never reach "
    "Canvas on their own. Staging is also the way in to the New Quiz write "
    "below, so nothing skips it. "
    "If the teacher would rather land a New Quiz from the chat, "
    "preview_new_quiz_scores freezes the staged item scores and returns "
    "aggregate counts only, and apply_new_quiz_scores lands exactly that "
    "frozen review. SIS grade bridges are a separate bounded path on their "
    "own data: preview_sis_grade_bridge returns an aggregate review and "
    "apply_sis_grade_bridge lands it. For either pair, summarize the preview "
    "and wait for the teacher. One teacher command may preauthorize that "
    "exact preview/apply cycle when it names the target: the course and "
    "assignment for a New Quiz, the course and family for a bridge (or "
    "explicitly all already-registered bridges). That authorization covers "
    "that one cycle, not another assignment, course, family, or session, and "
    "any invariant failure still stops. "
    "Before answering what CanvasExpert itself can do, or planning writing "
    "work, call get_product_guide: it carries the app's surfaces and the "
    "tracked / not-tracked Writing Timeline choice every writing assignment "
    "makes. Check it before telling a teacher a feature does not exist. "
    "get_writing_history reads a separate, private per-student writing record "
    "that some teachers keep for daily or weekly short-writing practice: "
    "stand-in first, no course_id, for coaching a writer's development over "
    "time rather than grading one assignment; call "
    "get_product_guide(topic=\"writing_record\") before assuming it does not "
    "exist."
)

mcp = FastMCP("canvas-expert", instructions=_SERVER_INSTRUCTIONS)


def run_stdio() -> None:
    mcp.run(transport="stdio")


def _compact(payload: dict) -> str:
    """Serialize ourselves: compact separators, no ASCII-escaping of student
    text. The tools layer applies a final structural privacy gate before the
    response is serialized. A ``str`` return passes through FastMCP verbatim."""
    payload = tools.final_response_gate(payload)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@mcp.tool(structured_output=False)
def list_courses() -> str:
    """This teacher's courses as {course_id, course_name, active, lifecycle};
    active=true marks a current course, lifecycle tells Canvas concluded status.
    Call first to get a course_id. No student data."""
    return _compact(tools.list_courses())


@mcp.tool(structured_output=False)
def list_sis_grade_bridges(course_id: str) -> str:
    """Configured SIS grade bridges for one Current course; student-free."""
    return _compact(tools.list_sis_grade_bridges(course_id))


@mcp.tool(structured_output=False)
def preview_sis_grade_bridge(course_id: str, family_title: str) -> str:
    """Freeze one exact differentiated family and return an aggregate review."""
    return _compact(tools.preview_sis_grade_bridge(course_id, family_title))


@mcp.tool(structured_output=False)
def apply_sis_grade_bridge(
    operation_id: str, batch_id: str, review_digest: str
) -> str:
    """Apply only the exact opaque SIS bridge review previously returned."""
    return _compact(tools.apply_sis_grade_bridge(
        operation_id, batch_id, review_digest
    ))


@mcp.tool(structured_output=False)
def confirm_sis_grade_bridge_passback(
    operation_id: str, observed_last_sync_at: str,
) -> str:
    """Confirm one ambiguous SIS passback from exact teacher-observed evidence.

    Only the teacher's own Canvas Grade Sync row counts: pass the Last Sync
    timestamp they read there, and only when it is at or after the persisted
    request marker. Do not infer the row or the timestamp, and do not resend
    passback while confirming."""
    return _compact(tools.confirm_sis_grade_bridge_passback(
        operation_id, observed_last_sync_at
    ))


@mcp.tool(structured_output=False)
def list_sections(course_id: str) -> str:
    """A course's section names from the local mirror as a {columns, rows}
    table of (section_id, section_name). Call before get_seating_context to
    discover its section_id/section_name values. No student data."""
    return _compact(tools.list_sections(course_id))


@mcp.tool(structured_output=False)
def get_course_assignments(course_id: str, full_descriptions: bool = False) -> str:
    """A course's assignments from the local catalog as a {columns, rows} table
    (id, title, due_at, points_possible, published, description_text).
    Descriptions are previews unless full_descriptions=true. No student data."""
    return _compact(tools.get_course_assignments(course_id, full_descriptions))


@mcp.tool(structured_output=False)
def get_modules(course_id: str, include_items: bool = False) -> str:
    """A course's modules from the local catalog as a {columns, rows} table
    (id, name, position, item_count). include_items=true adds each module's
    items (id, type, title, position, content_id). No student data."""
    return _compact(tools.get_modules(course_id, include_items))


@mcp.tool(structured_output=False)
def get_course_pages(course_id: str, full_text: bool = False) -> str:
    """Published pages from the local v3 catalog as a bounded {columns, rows}
    table; full_text=true requests the complete normalized body. Current course only."""
    return _compact(tools.get_course_pages(course_id, full_text))


@mcp.tool(structured_output=False)
def list_learning_objectives(course_id: str) -> str:
    """Reviewed objectives for the Current course as a {columns, rows} table."""
    return _compact(tools.list_learning_objectives(course_id))


@mcp.tool(structured_output=False)
def preview_learning_objective(course_id: str, objective: str,
                               effective_start: str, effective_end: str,
                               source_refs: list, replaces: str = None) -> str:
    """Preview one objective grounded in current local module, assignment, or page evidence."""
    return _compact(tools.preview_learning_objective(
        course_id, objective, effective_start, effective_end, source_refs, replaces))


@mcp.tool(structured_output=False)
def apply_learning_objective(course_id: str, preview: dict,
                             preview_digest: str, expected_revision: int) -> str:
    """Apply an exact reviewed objective preview after revision and source checks."""
    return _compact(tools.apply_learning_objective(
        course_id, preview, preview_digest, expected_revision))


@mcp.tool(structured_output=False)
def delete_learning_objective(course_id: str, entry_id: str,
                              expected_revision: int) -> str:
    """Delete one reviewed objective using an expected document revision."""
    return _compact(tools.delete_learning_objective(course_id, entry_id, expected_revision))


@mcp.tool(structured_output=False)
def get_roster(course_id: str) -> str:
    """Course roster as a {columns, rows} table of (pseudonym, section_names),
    sorted by pseudonym."""
    return _compact(tools.get_roster(course_id))


@mcp.tool(structured_output=False)
def get_roster_student_settings(course_id: str, pseudonym: str) -> str:
    """Read one current roster student's safe local settings by pseudonym;
    excludes stored nicknames and all identity IDs."""
    return _compact(tools.get_roster_student_settings(course_id, pseudonym))


@mcp.tool(structured_output=False)
def preview_roster_student_change(course_id: str, pseudonym: str, patch: dict) -> str:
    """Preview a validated pseudonym-first roster settings change; apply the
    exact digest-protected preview only after teacher confirmation."""
    return _compact(tools.preview_roster_student_change(course_id, pseudonym, patch))


@mcp.tool(structured_output=False)
def apply_roster_student_change(course_id: str, preview: dict,
                                preview_digest: str, expected_settings_digest: str) -> str:
    """Apply an unchanged roster preview after current-course, pseudonym, and
    hidden settings-digest checks."""
    return _compact(tools.apply_roster_student_change(
        course_id, preview, preview_digest, expected_settings_digest))


@mcp.tool(structured_output=False)
def clear_roster_student_field(course_id: str, pseudonym: str, field: str,
                               expected_settings_digest: str) -> str:
    """Directly clear one supported local setting with a fresh hidden digest;
    nickname fields are never clearable through MCP."""
    return _compact(tools.clear_roster_student_field(
        course_id, pseudonym, field, expected_settings_digest))


@mcp.tool(structured_output=False)
def get_seating_context(course_id: str, section_name: str = "", section_id: str = "") -> str:
    """One section's pseudonymized seating context: supports, score values,
    AI-context notes, and pair preferences. section_name matches exactly, or
    loosely on case/whitespace; pass section_id instead if that is ever
    ambiguous. No Canvas IDs or private reasons."""
    return _compact(tools.get_seating_context(course_id, section_name, section_id))


@mcp.tool(structured_output=False)
def get_submissions(course_id: str, assignment_id: str,
                    include_text: bool = True, pseudonyms: str = "",
                    max_text_chars: int = 2000) -> str:
    """One assignment's submissions as a {columns, rows} table (pseudonym,
    workflow_state, submitted_at, late, missing, excused, score, grade, text).
    include_text=false for status and scores only; pseudonyms=\"Name A,Name B\"
    narrows to specific students; text trims to max_text_chars (0 = full). No
    attachments."""
    return _compact(tools.get_submissions(
        course_id, assignment_id,
        include_text=include_text, pseudonyms=pseudonyms,
        max_text_chars=max_text_chars,
    ))


@mcp.tool(structured_output=False)
def get_writing_history(pseudonym: str, since: str = "", until: str = "",
                        include_text: bool = False,
                        max_text_chars: int = 2000) -> str:
    """One student's Writing Record evidence across time, pseudonym-first:
    dated submissions, assignment context, word counts, segment attribution,
    and structural flags. Writing Record does not score, coach, or judge work.
    No course_id -- this reads a private per-student store, not a course.
    since/until are YYYY-MM-DD (both default to a two-year lookback).
    include_text=false (default) omits every span quoted from student
    writing; true includes it trimmed to max_text_chars (0 = full). Call
    get_product_guide(topic="writing_record") first if unsure this exists."""
    return _compact(tools.get_writing_history(
        pseudonym, since=since, until=until,
        include_text=include_text, max_text_chars=max_text_chars,
    ))


@mcp.tool(structured_output=False)
def get_gradebook_snapshot(course_id: str) -> str:
    """Whole-course grading snapshot: class totals plus {columns, rows} tables
    of per-assignment stats (title, due_at, points, submitted, graded, missing,
    late, avg_pct) and per-student stats (pseudonym, missing, late, ungraded,
    pct)."""
    return _compact(tools.get_gradebook_snapshot(course_id))


@mcp.tool(structured_output=False)
def get_authoring_contract(kind: str) -> str:
    """Canonical Forge authoring contract. No student data."""
    return _compact(tools.get_authoring_contract(kind))


@mcp.tool(structured_output=False)
def get_product_guide(topic: str = "") -> str:
    """What CanvasExpert itself can do, so you plan and answer from the product
    rather than guessing. Omit topic for the compact capability overview;
    topic="connected", "assessments", or "full" selects the matching
    CanvasAgent guidance; topic="writing_timeline" selects tracked vs
    not-tracked writing assignments; topic="writing_record" selects the
    get_writing_history longitudinal writing record. Every response lists all
    available topics.
    No student data."""
    return _compact(tools.get_product_guide(topic))


@mcp.tool(structured_output=False)
def get_standards_profile() -> str:
    """Published offline DataForge standards profile, safety-scanned and
    pseudonymized. No course_id and no Canvas call; Identity Vault access is
    still required because this is student data."""
    return _compact(tools.get_standards_profile())


@mcp.tool(structured_output=False)
def get_assessment_context(course_id: str, pseudonyms: str = "") -> str:
    """Current-roster assessment context by exact pseudonym filter, joined
    with bounded local longitudinal DataForge evidence; mirror-only and
    observational, never a placement or judgment."""
    return _compact(tools.get_assessment_context(course_id, pseudonyms))


@mcp.tool(structured_output=False)
def get_assessment_grouping_proposal(
    course_id: str,
    snapshot_id: str,
    method: str = "overall_pct",
    cutoffs: str = "",
    no_data_group: str = "",
    group_set_label: str = "",
) -> str:
    """Read-only Students-page grouping proposal by exact teacher-safe group-set label;
    pseudonymized placements only, with no Canvas apply path."""
    return _compact(tools.get_assessment_grouping_proposal(
        course_id,
        snapshot_id,
        method=method,
        cutoffs=cutoffs,
        no_data_group=no_data_group,
        group_set_label=group_set_label,
    ))


@mcp.tool(structured_output=False)
def list_staged_content(kind: str = "") -> str:
    """Drafts currently staged in the Inbox for the teacher to review, as a
    {columns, rows} table (kind, label). Pass kind to filter; omit for all.
    No student data."""
    return _compact(tools.list_staged_content(kind))


@mcp.tool(structured_output=False)
def refresh_mirror(course_id: str) -> str:
    """Call only after a read refuses as stale. Triggers Canvas Expert's own
    sync of this course, then reports status (synced, syncing, or failed),
    never data. On "synced", re-call the read that refused."""
    return _compact(tools.refresh_mirror(course_id))


@mcp.tool(structured_output=False)
def get_bell_schedule(schedule_id: str = "") -> str:
    """Bell schedule(s) from the workspace as ordered meeting lists with
    {seq, period_id, start, end, segment} entries.
    schedule_id="" returns all variants; else returns one variant or error.
    No student data."""
    return _compact(tools.get_bell_schedule(schedule_id))


@mcp.tool(structured_output=False)
def preview_bell_schedule(schedule_id: str, content: str) -> str:
    """Preview creating or replacing one Bell Schedule CSV. Never writes;
    summarize the before/after meeting projection and get teacher confirmation
    before calling apply_bell_schedule with its base_digest."""
    return _compact(tools.preview_bell_schedule(schedule_id, content))


@mcp.tool(structured_output=False)
def apply_bell_schedule(preview: dict, expected_digest: str) -> str:
    """Apply an exact preview from preview_bell_schedule. Stale files,
    altered projections, and altered preview digests are refused."""
    return _compact(tools.apply_bell_schedule(preview, expected_digest))


@mcp.tool(structured_output=False)
def get_day_schedule(date: str) -> str:
    """Teacher blocks resolved for a specific date, plus the Calendar's own
    resolution state (unconfigured, invalid_calendar, outside_coverage,
    no_school, no_regular_classes, unknown_schedule, or ready). Blocks are
    {name, label, start, end, raw_periods, schedule_id, period_ids, segments,
    seq}, sorted by start time. Repeated blocks produce one entry per
    consecutive meeting run. date is YYYY-MM-DD. No student data."""
    return _compact(tools.get_day_schedule(date))


@mcp.tool(structured_output=False)
def get_teacher_schedule() -> str:
    """Teacher schedule from workspace as version and blocks list with their
    periods and class labels. No student data."""
    return _compact(tools.get_teacher_schedule())


@mcp.tool(structured_output=False)
def save_teacher_schedule(blocks: list) -> str:
    """Save the teacher's schedule blocks live to the workspace.
    No course ID or student data. No review queue."""
    return _compact(tools.save_teacher_schedule(blocks))


@mcp.tool(structured_output=False)
def get_school_calendar(date_from: str = "", date_to: str = "") -> str:
    """Read the canonical School Calendar: readiness plus a bounded range of
    days/grading-periods/events. Pass both date_from and date_to for range
    rows; omit both for readiness only. No student data."""
    return _compact(tools.get_school_calendar(date_from, date_to))


@mcp.tool(structured_output=False)
def preview_school_calendar_replacement(school_year: str, coverage_start: str, coverage_end: str,
                                       default_schedule_id: str, weekday_schedules: dict = None,
                                       no_school_dates: list = None,
                                       no_regular_classes_dates: list = None,
                                       date_labels: dict = None, grading_periods: list = None,
                                       events: list = None) -> str:
    """Preview creating or replacing the complete canonical School Calendar for
    one school year: every date in coverage becomes instructional, a generated
    weekend, or an explicit no-school/no-regular-classes day. Returns the base
    revision (0 for a first-ever calendar), current vs. proposed school year
    and coverage, and material change counts. Summarize this to the teacher
    and get their confirmation before calling
    apply_school_calendar_replacement with its base_revision as
    expected_revision. No course ID or student data."""
    return _compact(tools.preview_school_calendar_replacement(
        school_year, coverage_start, coverage_end, default_schedule_id,
        weekday_schedules, no_school_dates, no_regular_classes_dates,
        date_labels, grading_periods, events,
    ))


@mcp.tool(structured_output=False)
def apply_school_calendar_replacement(preview: dict, expected_revision: int) -> str:
    """Apply a preview returned by preview_school_calendar_replacement. Pass
    the preview object back verbatim along with its base_revision as
    expected_revision; a stale revision is refused rather than silently
    reapplied against newer state. No course ID or student data."""
    return _compact(tools.apply_school_calendar_replacement(preview, expected_revision))


@mcp.tool(structured_output=False)
def preview_school_calendar_change(kind: str, schedule_id: str = "", label: str = "",
                                   dates: list = None, date_from: str = "", date_to: str = "",
                                   weekdays: list = None) -> str:
    """Preview a day-kind/schedule/label change against the live School
    Calendar: pass either an explicit dates list or a date_from/date_to range
    (optionally narrowed by weekdays). Returns the base revision and the
    affected dates' before/after values. Summarize this to the teacher and
    get their confirmation before calling apply_school_calendar_change with
    its expected_revision. No course ID or student data."""
    return _compact(tools.preview_school_calendar_change(
        kind, schedule_id, label, dates, date_from, date_to, weekdays,
    ))


@mcp.tool(structured_output=False)
def apply_school_calendar_change(preview: dict, expected_revision: int) -> str:
    """Apply a preview returned by preview_school_calendar_change. Pass the
    preview object back verbatim along with its base_revision as
    expected_revision; a stale revision is refused rather than silently
    reapplied against newer state. No course ID or student data."""
    return _compact(tools.apply_school_calendar_change(preview, expected_revision))


@mcp.tool(structured_output=False)
def preview_school_calendar_event_change(action: str, event: dict = None,
                                         event_id: str = "") -> str:
    """Preview one structured public Calendar event upsert or delete.
    Summarize its before/after values and get teacher confirmation before
    applying. No course ID or student data."""
    return _compact(tools.preview_school_calendar_event_change(action, event, event_id))


@mcp.tool(structured_output=False)
def apply_school_calendar_event_change(preview: dict, expected_revision: int) -> str:
    """Apply a preview returned by preview_school_calendar_event_change.
    Stale revisions, altered digests, or altered projections are refused.
    No course ID or student data."""
    return _compact(tools.apply_school_calendar_event_change(preview, expected_revision))


@mcp.tool(structured_output=False)
def preview_school_calendar_game_score(event_id: str, score: str) -> str:
    """Preview recording a score on one existing public Calendar game event.
    The event_id must identify an existing event whose kind is game. The
    preview carries every other event field forward unchanged; summarize the
    before/after result and get teacher confirmation before applying it. No
    course ID or student data."""
    return _compact(tools.preview_school_calendar_game_score(event_id, score))


@mcp.tool(structured_output=False)
def apply_school_calendar_game_score(preview: dict, expected_revision: int) -> str:
    """Apply a preview returned by preview_school_calendar_game_score.
    Stale revisions, altered digests, altered projections, and non-game event
    previews are refused. No course ID or student data."""
    return _compact(tools.apply_school_calendar_game_score(preview, expected_revision))


@mcp.tool(structured_output=False)
def start_scoring_session(course_id: str, assignment_id: str) -> str:
    """Start a packet-mode PowerGrader scoring session for one assignment so
    this chat can score it. Always packet mode: never opens an assisted
    session against the teacher's own AI key, never turns on auto-post, no
    file uploads. Returns session_id, assignment_name, student_count,
    response_count, and new_quiz_item_finalization_supported. Pass session_id
    to get_scoring_packet next. Course-gated. Never raises."""
    return _compact(tools.start_scoring_session(course_id, assignment_id))


@mcp.tool(structured_output=False)
def list_scoring_sessions() -> str:
    """PowerGrader sessions with SAFE bundles, newest first, filtered to Current
    courses. Returns {columns, rows} table of (session_id, assignment_name,
    course_id, created, mode_label, total, scored, approved). No student
    response data."""
    return _compact(tools.list_scoring_sessions())


@mcp.tool(structured_output=False)
def get_scoring_packet(session_id: str, offset: int = 0, limit: int = 10,
                       include_context: bool = True) -> str:
    """Retrieve pseudonymized student responses from a PowerGrader session's
    SAFE bundle for AI scoring. Returns items (prompts, deduplicated) and
    students (responses, text-only, no media). Paging counts responses, not
    students: on a multi-item quiz one student fills several rows, and total
    counts rows while students_total counts people. Set include_context=false
    on later pages to save tokens (context included once per session).
    Projected payload is returned as estimated_tokens; refuses over 25,000
    tokens with a workable smaller limit. Course-gated. Never raises."""
    return _compact(tools.get_scoring_packet(
        session_id, offset, limit, include_context))


@mcp.tool(structured_output=False)
def stage_scores(session_id: str, results: list,
                 expected_packet_digest: str) -> str:
    """Stage AI-generated scores into a PowerGrader session, awaiting teacher
    review. Results is a list of scoring dicts (each with pseudonym, item_id,
    score, feedback, etc.). Pass expected_packet_digest from get_scoring_packet
    to guard against stale scores (refuses if session was re-run). Partial
    staging works: scores 6 of 28, leaves 22 untouched. Does not post to Canvas.
    Course-gated. Never raises."""
    return _compact(tools.stage_scores(session_id, results, expected_packet_digest))


@mcp.tool(structured_output=False)
def preview_new_quiz_scores(session_id: str) -> str:
    """Freeze a New Quiz item-finalization review for every student in this
    session carrying a staged item score, and stash it. Returns opaque
    operation_id/review_digest plus aggregate counts (students, items, ready,
    refused, already_finalized) and warnings; no real name or Canvas/SIS id,
    no Canvas write. Pass operation_id and review_digest, unchanged, to
    apply_new_quiz_scores. Course-gated. Never raises."""
    return _compact(tools.preview_new_quiz_scores(session_id))


@mcp.tool(structured_output=False)
def apply_new_quiz_scores(operation_id: str, review_digest: str) -> str:
    """Apply exactly the New Quiz item scores preview_new_quiz_scores froze.
    Takes only the opaque operation_id/review_digest pair; refuses cleanly,
    with no Canvas call, on a mismatched digest, an unrecognized operation_id,
    or an expired review. Idempotent: replaying the same coordinates never
    re-applies an already-finalized student. Reports per-student outcomes by
    pseudonym; a concluded or restricted enrollment can refuse one student
    while the rest of the batch continues. Never raises."""
    return _compact(tools.apply_new_quiz_scores(operation_id, review_digest))


def _strip_generated_schema_titles(mcp_server) -> int:
    """Drop pydantic's generated ``title`` from every tool's input schema.

    FastMCP derives each schema from the function signature, and pydantic
    labels every property with a title made from that property's own name, so
    ``course_id`` ships as ``{"title": "Course Id", "type": "string"}``. The
    key already said that. It is nobody's authored text and it is a large part
    of the tool listing, so it is the cheapest wire weight on this surface to
    lose. Client and model token treatment varies.

    Result transport is explicitly text-only on every tool, so FastMCP does not
    advertise an output schema or structured result alongside the text. The
    input schema itself stays intact: names, types, defaults, and required lists
    remain available to clients.

    Names, types, defaults, and required lists are untouched, and the frozen
    ``tool_schema_vN.json`` snapshots record only property types, so no
    contract version moves. Runs once at import, after every tool is
    registered.
    """
    removed = 0
    registry = getattr(getattr(mcp_server, "_tool_manager", None), "_tools", {}) or {}
    for tool in registry.values():
        for attribute in ("parameters", "output_schema"):
            schema = getattr(tool, attribute, None)
            if not isinstance(schema, dict):
                continue
            if schema.pop("title", None) is not None:
                removed += 1
            for prop in (schema.get("properties") or {}).values():
                if isinstance(prop, dict) and prop.pop("title", None) is not None:
                    removed += 1
    return removed


_STRIPPED_SCHEMA_TITLES = _strip_generated_schema_titles(mcp)
