"""FastMCP wiring for the CanvasExpert MCP server.

Seventeen thin ``@mcp.tool()`` wrappers delegate to the plain functions in
``tools.py`` so the tool layer stays testable without an MCP client. Run via
``api/mcp_server/__main__.py`` over stdio — this module never binds a network
port and is never mounted inside the FastAPI web UI (``api.webui.server``).

Token discipline: the shared privacy rules live ONCE in the server
instructions (not per tool), tool descriptions stay to a functional line or
two, and every result is serialized compactly here — FastMCP would otherwise
pretty-print dict returns with indent=2, which wastes client context on
whitespace. List data is shaped as {columns, rows} tables in ``tools.py``.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import tools

_FERPA_NOTICE = (
    "CanvasExpert reads this teacher's own Canvas courses, assignments, "
    "rosters, grades, submissions, and seating context from a local copy on "
    "their computer. Call list_courses first for a course_id. Student data is "
    "pseudonymized through a local vault before you see it: stable fake names "
    "(e.g. \"Sparky McGee\") stand in for real students, and real names and "
    "Canvas/SIS IDs never leave the machine. Do not re-identify anyone or save "
    "student data to a file. get_roster, get_seating_context, get_submissions, "
    "and get_gradebook_snapshot serve only from the local mirror and refuse "
    "when it is stale; call refresh_mirror for that course, then retry once. "
    "Results are compact JSON, with list data as {columns, rows} tables. "
    "Prefer narrow calls: include_text=false or specific pseudonyms first. To "
    "For Glass, call get_authoring_contract for glass_pane or glass_scene, then "
    "get_glass_context before saving a pending Glass draft; the teacher alone approves it. "
    "To help the teacher create other content, call get_authoring_contract for the kind "
    "and follow the staging steps in its response. Before answering what "
    "CanvasExpert itself can do, or planning writing work, call "
    "get_product_guide: it carries the app's surfaces and the tracked / "
    "not-tracked Writing Timeline choice every writing assignment makes. Check "
    "it before telling a teacher a feature does not exist. get_writing_history "
    "reads a separate, private per-student writing record that some teachers "
    "keep for daily or weekly short-writing practice -- pseudonym-first, no "
    "course_id, for coaching a writer's development over time rather than "
    "grading one assignment; call get_product_guide(topic=\"writing_record\") "
    "before assuming it does not exist."
)

mcp = FastMCP("canvas-expert", instructions=_FERPA_NOTICE)


def run_stdio() -> None:
    mcp.run(transport="stdio")


def _compact(payload: dict) -> str:
    """Serialize ourselves: compact separators, no ASCII-escaping of student
    text. A ``str`` return passes through FastMCP verbatim."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@mcp.tool()
def list_courses() -> str:
    """This teacher's courses as {course_id, course_name, active, lifecycle};
    active=true marks a current course, lifecycle tells Canvas concluded status.
    Call first to get a course_id. No student data."""
    return _compact(tools.list_courses())


@mcp.tool()
def list_sections(course_id: str) -> str:
    """A course's section names from the local mirror as a {columns, rows}
    table of (section_id, section_name). Call before get_seating_context to
    discover valid section_name values. No student data."""
    return _compact(tools.list_sections(course_id))


@mcp.tool()
def get_course_assignments(course_id: str, full_descriptions: bool = False) -> str:
    """A course's assignments from the local catalog as a {columns, rows} table
    (id, title, due_at, points_possible, published, description_text).
    Descriptions are previews unless full_descriptions=true. No student data."""
    return _compact(tools.get_course_assignments(course_id, full_descriptions))


@mcp.tool()
def get_modules(course_id: str, include_items: bool = False) -> str:
    """A course's modules from the local catalog as a {columns, rows} table
    (id, name, position, published, item_count). include_items=true adds each
    module's items (id, type, title, position). No student data."""
    return _compact(tools.get_modules(course_id, include_items))


@mcp.tool()
def get_roster(course_id: str) -> str:
    """Course roster as a {columns, rows} table of (pseudonym, section_names),
    sorted by pseudonym."""
    return _compact(tools.get_roster(course_id))


@mcp.tool()
def get_seating_context(course_id: str, section_name: str) -> str:
    """One section's pseudonymized seating context: supports, score values,
    AI-context notes, and pair preferences. Needs an exact section_name;
    refuses when it is absent or ambiguous. No Canvas IDs or private reasons."""
    return _compact(tools.get_seating_context(course_id, section_name))


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def get_gradebook_snapshot(course_id: str) -> str:
    """Whole-course grading snapshot: class totals plus {columns, rows} tables
    of per-assignment stats (title, due_at, points, submitted, graded, missing,
    late, avg_pct) and per-student stats (pseudonym, missing, late, ungraded,
    pct)."""
    return _compact(tools.get_gradebook_snapshot(course_id))


@mcp.tool()
def get_authoring_contract(kind: str) -> str:
    """Canonical Forge or Glass authoring contract. Glass kinds are
    glass_pane and glass_scene; their teacher-review flow has no Forge staging
    appendix. No student data."""
    return _compact(tools.get_authoring_contract(kind))


@mcp.tool()
def get_glass_context(date: str, lookahead_days: int = 14) -> str:
    """Public bell-schedule/calendar context plus approved pane and scene status.
    It never reads Canvas, course work, or student data."""
    return _compact(tools.get_glass_context(date, lookahead_days))


@mcp.tool()
def save_glass_pane_draft(manifest: dict, pane_html: str, pane_css: str = "", pane_js: str = "", assets: list = None, draft_id: str = "") -> str:
    """Validate and stage one pending pane in To Review/Glass. Never publishes."""
    return _compact(tools.save_glass_pane_draft(manifest, pane_html, pane_css, pane_js, assets, draft_id))


@mcp.tool()
def save_glass_scene_draft(scene: dict, draft_id: str = "") -> str:
    """Validate and stage one dated scene in To Review/Glass. Never publishes."""
    return _compact(tools.save_glass_scene_draft(scene, draft_id))


@mcp.tool()
def list_glass_drafts() -> str:
    """Compact pending Glass draft metadata; never returns source, assets, or paths."""
    return _compact(tools.list_glass_drafts())


@mcp.tool()
def get_product_guide(topic: str = "") -> str:
    """What CanvasExpert itself can do, so you plan and answer from the product
    rather than guessing. Omit topic for the whole briefing (surfaces, the hard
    lines, staging, privacy); topic="writing_timeline" for tracked vs
    not-tracked writing assignments and what the timeline can and cannot show;
    topic="writing_record" for get_writing_history, the per-student
    longitudinal writing record. Every response lists the available topics.
    No student data."""
    return _compact(tools.get_product_guide(topic))


@mcp.tool()
def list_staged_content(kind: str = "") -> str:
    """Drafts currently staged in the Inbox for the teacher to review, as a
    {columns, rows} table (kind, label). Pass kind to filter; omit for all.
    No student data."""
    return _compact(tools.list_staged_content(kind))


@mcp.tool()
def refresh_mirror(course_id: str) -> str:
    """Call only after a read refuses as stale. Triggers Canvas Expert's own
    sync of this course, then reports status (synced, syncing, or failed),
    never data. On "synced", re-call the read that refused."""
    return _compact(tools.refresh_mirror(course_id))
