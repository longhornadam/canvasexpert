"""FastMCP wiring for the read-only CanvasExpert MCP server.

Six thin ``@mcp.tool()`` wrappers delegate to the plain functions in
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
    "CanvasExpert gives you read-only access to THIS teacher's own Canvas "
    "courses, assignments, rosters, grades, and student submissions, read "
    "locally through Canvas Expert on their computer. Use these tools whenever "
    "the teacher asks about their courses, classes, students, assignments, or "
    "grades; call list_courses first to get a course_id for the other tools. "
    "Every result about students is pseudonymized through a local identity "
    "vault before it reaches you: real names, Canvas user IDs, and SIS IDs "
    "never leave that machine. Stable fake names (e.g. \"Sparky McGee\") stand "
    "in for real students so you can refer to them consistently without ever "
    "seeing who they are. Results are session-local; do not write them to a "
    "file, and do not attempt to re-identify a student from a pseudonym, "
    "writing style, or any other clue. This server is read-only: no tool "
    "writes to Canvas. get_roster, get_submissions, and get_gradebook_snapshot "
    "are served ONLY from Canvas Expert's local CanvasMirror, never a live "
    "Canvas fetch, so they refuse with a clear error when the mirror is "
    "stale or missing instead of returning live data; if that happens, call "
    "refresh_mirror for that course, then retry the same call once. Results "
    "are compact JSON; list data arrives as {columns, rows} tables. Prefer "
    "narrow calls: include_text=false or specific pseudonyms first, full "
    "text only for the students you actually need."
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
    """List this teacher's Canvas courses in Canvas Expert as
    {course_id, course_name, active}. Start here to get a course_id for the
    other tools; active=true marks a current course. No student data."""
    return _compact(tools.list_courses())


@mcp.tool()
def get_course_assignments(course_id: str, full_descriptions: bool = False) -> str:
    """List a course's assignments from CanvasExpert's local catalog as a
    {columns, rows} table (id, title, due_at, points_possible, published,
    description_text). Descriptions are trimmed to a preview unless
    full_descriptions=true. Errors if the catalog needs a refresh from the
    CanvasExpert web UI. No student data."""
    return _compact(tools.get_course_assignments(course_id, full_descriptions))


@mcp.tool()
def get_roster(course_id: str) -> str:
    """Current course roster as a {columns, rows} table of
    (pseudonym, section_names), sorted by pseudonym. Refuses if the local
    mirror isn't fresh enough to serve it (call refresh_mirror), rather than
    fetching live from Canvas."""
    return _compact(tools.get_roster(course_id))


@mcp.tool()
def get_seating_context(course_id: str, section_name: str) -> str:
    """Read one exact Current-course section's mirror+local seating context:
    fresh mirrored identity/membership joined with private local supports,
    score values, AI-context notes, and pair preferences. It never fetches
    Canvas, never returns Canvas IDs or private local reasons, and refuses
    absent or ambiguous section names rather than guessing."""
    return _compact(tools.get_seating_context(course_id, section_name))


@mcp.tool()
def get_submissions(course_id: str, assignment_id: str,
                    include_text: bool = True, pseudonyms: str = "",
                    max_text_chars: int = 2000) -> str:
    """One assignment's submissions as a {columns, rows} table (pseudonym,
    workflow_state, submitted_at, late, missing, excused, score, grade,
    text). Student text is scrubbed of real names and trimmed to
    max_text_chars (0 = full text). Set include_text=false for status and
    scores only, or pseudonyms=\"Name A,Name B\" for specific students.
    Attachments are never included. Refuses if the local mirror isn't fresh
    enough to serve it (call refresh_mirror), rather than fetching live from
    Canvas."""
    return _compact(tools.get_submissions(
        course_id, assignment_id,
        include_text=include_text, pseudonyms=pseudonyms,
        max_text_chars=max_text_chars,
    ))


@mcp.tool()
def get_gradebook_snapshot(course_id: str) -> str:
    """Whole-course grading snapshot: class totals plus {columns, rows}
    tables of per-assignment stats (title, due_at, points, submitted, graded,
    missing, late, avg_pct) and per-student stats (pseudonym, missing, late,
    ungraded, pct). Refuses if the local mirror isn't fresh enough to serve
    it (call refresh_mirror), rather than fetching live from Canvas."""
    return _compact(tools.get_gradebook_snapshot(course_id))


@mcp.tool()
def refresh_mirror(course_id: str) -> str:
    """Call this ONLY after get_roster, get_submissions, or
    get_gradebook_snapshot refuses with a stale/unavailable error. Triggers
    Canvas Expert's own sync of this course's local data from Canvas and
    waits briefly, then reports sync status (synced, syncing, or failed) --
    never course, roster, or submission data. After a "synced" result,
    re-call the tool that refused."""
    return _compact(tools.refresh_mirror(course_id))
