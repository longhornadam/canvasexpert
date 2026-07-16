"""FastMCP wiring for the read-only CanvasExpert MCP server.

Five thin ``@mcp.tool()`` wrappers delegate to the plain functions in
``tools.py`` so the tool layer stays testable without an MCP client. Run via
``api/mcp_server/__main__.py`` over stdio — this module never binds a network
port and is never mounted inside the FastAPI web UI (``api.webui.server``).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools

_FERPA_NOTICE = (
    "CanvasExpert read-only Canvas tools. Every result about students is "
    "pseudonymized through a local identity vault before it reaches you: "
    "real names, Canvas user IDs, and SIS IDs never leave this machine. "
    "Stable fake names (e.g. \"Sparky McGee\") stand in for real students so "
    "you can refer to them consistently without ever seeing who they are. "
    "Results are session-local — do not write them to a file, and do not "
    "attempt to re-identify a student from a pseudonym, writing style, or "
    "any other clue. This server is read-only: it has no tool that writes "
    "to Canvas."
)

mcp = FastMCP("canvas-expert", instructions=_FERPA_NOTICE)


def run_stdio() -> None:
    mcp.run(transport="stdio")


@mcp.tool()
def list_courses() -> dict:
    """List every course CanvasExpert knows about (Current + Previous), with
    course_id and course_name. No student data is involved."""
    return tools.list_courses()


@mcp.tool()
def get_course_assignments(course_id: str) -> dict:
    """List assignments for a course from CanvasExpert's local course
    catalog (id, title, due_at, points_possible, description_text). Disk-only
    — if the catalog hasn't been refreshed in the CanvasExpert web UI yet,
    this returns an error asking you to refresh it there first. No student
    data is involved."""
    return tools.get_course_assignments(course_id)


@mcp.tool()
def get_roster(course_id: str) -> dict:
    """List the current roster for a course as
    ``[{pseudonym, section_names}]``, sorted by pseudonym. Every student is
    identified only by a stable pseudonym assigned from a local identity
    vault — their real name, Canvas ID, and SIS ID never leave this machine.
    Results are session-local: do not write them to a file, and do not
    attempt to re-identify a student from their pseudonym."""
    return tools.get_roster(course_id)


@mcp.tool()
def get_submissions(course_id: str, assignment_id: str) -> dict:
    """Get one assignment's submissions, pseudonymized: each submission is
    identified only by a stable pseudonym (never a real name or Canvas ID),
    and its text has been scrubbed of every roster student's real name and
    nickname. Attachments are never included. Results are session-local: do
    not write them to a file, and do not attempt to re-identify a student
    from their pseudonym or writing."""
    return tools.get_submissions(course_id, assignment_id)


@mcp.tool()
def get_gradebook_snapshot(course_id: str) -> dict:
    """Whole-course grading snapshot: per-assignment stats (title, due_at,
    points, submitted/graded/missing/late counts, avg_pct) and per-student
    stats (pseudonym, missing, late, ungraded, pct). Every student is
    identified only by a stable pseudonym — their real name, Canvas ID, and
    SIS ID never leave this machine. Results are session-local: do not write
    them to a file, and do not attempt to re-identify a student from their
    pseudonym."""
    return tools.get_gradebook_snapshot(course_id)
