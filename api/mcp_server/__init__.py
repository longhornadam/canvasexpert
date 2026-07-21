"""Canvas MCP server for CanvasExpert.

Exposes 7 tools (list_courses, get_course_assignments, get_roster,
get_seating_context, get_submissions, get_gradebook_snapshot, refresh_mirror)
over stdio so any MCP-capable
assistant can help plan lessons and manage rosters. CanvasExpert keeps sole
custody of the Canvas PAT and every write path — this package never writes to
Canvas and never binds a network port.

Every student-data tool pseudonymizes real Canvas identity through the
existing identity vault (``api/feedback_vault.py``) and runs the outbound
safety gate (``api/feedback_safety.py``) before a result is returned. Real
names, Canvas IDs, and SIS IDs never leave this machine. Results are
session-local: nothing here writes to files, and nothing here logs tool
arguments or results.
"""
