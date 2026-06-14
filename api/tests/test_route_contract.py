"""Route-contract snapshot — the app's public HTTP surface, frozen.

This is the safety net for the `server.py` breakup (dev/REFACTOR_PLAN.md): any
extraction that drops, renames, or reshapes a route makes this test fail loudly,
so refactors can't silently change behavior. Importing the app is side-effect-free
(the heavy startup work lives in `server.init_app`, fired only when serving), so
this test is cheap.

If you INTENTIONALLY add or remove a route, update EXPECTED in the same commit —
that's the whole point: a surface change must be a deliberate, reviewed edit.

The gradebook student-list endpoint is at `/api/students/list` (returns id+name for
the extra-time panel). The reports endpoint is at `/api/students` (returns id+name+monitored).
These were previously both at `/api/students` causing a shadow; the gradebook one was renamed.
"""
from api.webui.server import app

EXPECTED = [
    ('/', ('GET',)),
    ('/about', ('GET',)),
    ('/ai-expert', ('GET',)),
    ('/api/activity', ('GET',)),
    ('/api/af/validate', ('POST',)),
    ('/api/ai-ta/file', ('GET',)),
    ('/api/ai-ta/files', ('GET',)),
    ('/api/ai-ta/rebuild', ('POST',)),
    ('/api/ai-ta/toolkit-file', ('GET',)),
    ('/api/assignment-groups', ('GET',)),
    ('/api/assignments-full', ('GET',)),
    ('/api/calendar', ('GET',)),
    ('/api/calendar/clear', ('POST',)),
    ('/api/calendar/load-builtin', ('POST',)),
    ('/api/calendar/set', ('POST',)),
    ('/api/calendar/template', ('GET',)),
    ('/api/content/push', ('POST',)),
    ('/api/course-detail', ('GET',)),
    ('/api/course-folder', ('GET',)),
    ('/api/courses', ('GET',)),
    ('/api/curve/apply', ('POST',)),
    ('/api/curve/assignments', ('GET',)),
    ('/api/curve/events', ('GET',)),
    ('/api/curve/preview', ('POST',)),
    ('/api/curve/revert', ('POST',)),
    ('/api/download-contract', ('GET',)),
    ('/api/download-root', ('GET',)),
    ('/api/extend-due', ('POST',)),
    ('/api/extra-time', ('GET',)),
    ('/api/extra-time', ('POST',)),
    ('/api/files', ('GET',)),
    ('/api/gradebook', ('GET',)),
    ('/api/groups', ('GET',)),
    ('/api/late-policy', ('GET',)),
    ('/api/late-policy/apply', ('POST',)),
    ('/api/modules', ('GET',)),
    ('/api/open-folder', ('POST',)),
    ('/api/open-path', ('POST',)),
    ('/api/pf/validate', ('POST',)),
    ('/api/physical/quiz', ('POST',)),
    ('/api/pick-download-folder', ('POST',)),
    ('/api/push-multi-whole/stream', ('GET',)),
    ('/api/push-multi/stream', ('GET',)),
    ('/api/push-variants/stream', ('GET',)),
    ('/api/push/preview', ('POST',)),
    ('/api/push/stream', ('GET',)),
    ('/api/rf/files', ('GET',)),
    ('/api/rf/scoring-prompt', ('GET',)),
    ('/api/rf/validate', ('POST',)),
    ('/api/routines', ('GET',)),
    ('/api/routines/run', ('POST',)),
    ('/api/routines/save', ('POST',)),
    ('/api/student-packet/stream', ('GET',)),
    ('/api/students', ('GET',)),
    ('/api/students/list', ('GET',)),
    ('/api/students/monitor', ('POST',)),
    ('/api/students/monitored', ('GET',)),
    ('/api/submissions/download/stream', ('GET',)),
    ('/api/sweep/apply', ('POST',)),
    ('/api/sweep/preview', ('POST',)),
    ('/api/temp-upload', ('POST',)),
    ('/api/tier-tags', ('GET',)),
    ('/api/tier-tags', ('POST',)),
    ('/api/validate', ('POST',)),
    ('/assessment', ('GET',)),
    ('/course', ('GET',)),
    ('/course-expert', ('GET',)),
    ('/docs', ('GET',)),
    ('/docs/oauth2-redirect', ('GET',)),
    ('/gradebook', ('GET',)),
    ('/openapi.json', ('GET',)),
    ('/redoc', ('GET',)),
    ('/routines', ('GET',)),
    ('/settings', ('GET',)),
    ('/settings/canvas', ('POST',)),
    ('/settings/courses/bookmark', ('POST',)),
    ('/settings/courses/{course_id}/remove', ('POST',)),
    ('/settings/courses/{course_id}/set-active', ('POST',)),
    ('/settings/download-root', ('POST',)),
    ('/settings/test-connection', ('POST',)),
    ('/welcome', ('GET',)),
    ('/welcome/workspace', ('POST',)),
]


def _current_routes():
    out = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        if not methods:          # skip Mounts (static, /forge/quizforge)
            continue
        out.append((r.path, tuple(sorted(m for m in methods if m != "HEAD"))))
    return sorted(out)


def test_route_contract():
    """The full (path, methods) surface must match the frozen baseline."""
    assert _current_routes() == sorted(EXPECTED)
