"""Canvas MCP server for CanvasExpert.

Exposes the current read/authoring tool set (including list_courses, list_sections,
get_course_assignments,
get_modules, get_roster, get_seating_context, get_submissions,
get_writing_history, get_gradebook_snapshot, get_authoring_contract,
get_product_guide, get_standards_profile, list_staged_content, refresh_mirror) over stdio so any
MCP-capable assistant can help plan lessons and manage rosters. CanvasExpert
keeps sole custody of the Canvas PAT and every write path — this package
never writes to Canvas and never binds a network port.

Every student-data tool pseudonymizes real Canvas identity through the
existing identity vault (``api/feedback_vault.py``) and runs the outbound
safety gate (``api/feedback_safety.py``) before a result is returned. Real
names, Canvas IDs, and SIS IDs never leave this machine. Results are
session-local: nothing here writes to files, and nothing here logs tool
arguments or results. ``get_writing_history`` is the one exception to
"student data implies a course_id": it reads the private per-student daily
writing store (``api/dailywriting``) rather than a Canvas course, but still
runs the same identity vault and outbound safety gate as every other
student-data tool.
"""
