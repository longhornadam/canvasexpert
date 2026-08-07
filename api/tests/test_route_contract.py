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
import json

from api.webui.server import app
from api.webui.routes import powergrader as powergrader_routes

EXPECTED = [
    ('/', ('GET',)),
    ('/about', ('GET',)),
    ('/assessments', ('GET',)),
    ('/assessments/coverage', ('GET',)),
    ('/assessments/dashboard/{run_id}', ('GET',)),
    ('/assessments/download-all/{run_id}', ('GET',)),
    ('/assessments/download/{name:path}', ('GET',)),
    ('/assessments/export/standards-profile', ('GET',)),
    ('/assessments/history', ('GET',)),
    ('/assessments/history/delete', ('POST',)),
    ('/assessments/history/update', ('POST',)),
    ('/assessments/process', ('POST',)),
    ('/assessments/results/{run_id}', ('GET',)),
    ('/ai-expert', ('GET',)),
    ('/api/af/validate', ('POST',)),
    ('/api/ai-ta/file', ('GET',)),
    ('/api/ai-ta/files', ('GET',)),
    ('/api/ai-ta/rebuild', ('POST',)),
    ('/api/ai-ta/toolkit-file', ('GET',)),
    ('/api/assignment-groups', ('GET',)),
    ('/api/assignments-full', ('GET',)),
    ('/api/calendar', ('GET',)),
    ('/api/calendar/import', ('POST',)),
    ('/api/calendar/import/template', ('GET',)),
    ('/api/calendar/change/preview', ('POST',)),
    ('/api/calendar/change/apply', ('POST',)),
    ('/api/calendar/event/preview', ('POST',)),
    ('/api/calendar/event/apply', ('POST',)),
    ('/api/calendar/open-folder', ('POST',)),
    ('/api/calendar/year/preview', ('POST',)),
    ('/api/calendar/year/apply', ('POST',)),
    ('/api/connections/claude-package', ('POST',)),
    ('/api/connections/claude/connect', ('POST',)),
    ('/api/connections/claude/disconnect', ('POST',)),
    ('/api/connections/chatgpt/connect', ('POST',)),
    ('/api/connections/chatgpt/disconnect', ('POST',)),
    ('/api/connections/health', ('GET',)),
    ('/api/course-detail', ('GET',)),
    ('/api/course-catalog', ('GET',)),
    ('/api/course-catalog/refresh', ('POST',)),
    ('/api/course-folder', ('GET',)),
    ('/api/courses', ('GET',)),
    ('/api/curve/apply', ('POST',)),
    ('/api/curve/assignments', ('GET',)),
    ('/api/curve/events', ('GET',)),
    ('/api/curve/preview', ('POST',)),
    ('/api/curve/revert', ('POST',)),
    ('/api/dailywriting/ingest-canvas', ('POST',)),
    ('/api/download-contract', ('GET',)),
    ('/api/download-root', ('GET',)),
    ('/api/extend-due', ('POST',)),
    ('/api/extra-time', ('GET',)),
    ('/api/extra-time', ('POST',)),
    ('/api/files', ('GET',)),
    ('/api/gradebook', ('GET',)),
    ('/api/groups', ('GET',)),
    ('/api/inbox-files', ('GET',)),
    ('/api/late-policy', ('GET',)),
    ('/api/late-policy/apply', ('POST',)),
    ('/api/modules', ('GET',)),
    ('/api/operations', ('GET',)),
    ('/api/operations/{kind}/prepare', ('POST',)),
    ('/api/operations/{operation_id}/status', ('GET',)),
    ('/api/operation-batches/review', ('POST',)),
    ('/api/operation-batches/{batch_id}/apply', ('POST',)),
    ('/api/operations/{operation_id}/retry', ('POST',)),
    ('/api/mirror/status', ('GET',)),
    ('/api/mirror/sync-now', ('POST',)),
    ('/api/open-folder', ('POST',)),
    ('/api/open-path', ('POST',)),
    ('/api/pf/validate', ('POST',)),
    ('/api/physical/quiz', ('POST',)),
    ('/api/pick-download-folder', ('POST',)),
    ('/api/portfolio/from-nq-csv', ('POST',)),
    ('/api/portfolio/merged', ('POST',)),
    ('/api/push/preview', ('POST',)),
    ('/api/rf/files', ('GET',)),
    ('/api/rf/validate', ('POST',)),
    ('/api/routines', ('GET',)),
    ('/api/routines/run', ('POST',)),
    ('/api/routines/save', ('POST',)),
    ('/api/schedule', ('GET',)),
    ('/api/schedule/teacher', ('POST',)),
    ('/api/student-packet/stream', ('GET',)),
    ('/api/students', ('GET',)),
    ('/api/students/list', ('GET',)),
    ('/api/students/monitor', ('POST',)),
    ('/api/students/monitored', ('GET',)),
    ('/api/support-bundle', ('POST',)),
    ('/api/powergrader/refresh', ('POST',)),
    ('/api/powergrader/open-assignment-folder', ('POST',)),
    ('/api/sweep/preview', ('POST',)),
    ('/api/temp-upload', ('POST',)),
    ('/api/tier-tags', ('GET',)),
    ('/api/tier-tags', ('POST',)),
    ('/api/update/apply', ('POST',)),
    ('/api/update/cancel', ('POST',)),
    ('/api/update/download', ('POST',)),
    ('/api/update/status', ('GET',)),
    ('/api/validate', ('POST',)),
    ('/course', ('GET',)),
    ('/course-expert', ('GET',)),
    ('/connections', ('GET',)),
    ('/docs', ('GET',)),
    ('/docs/oauth2-redirect', ('GET',)),
    ('/gradebook', ('GET',)),
    ('/calendar', ('GET',)),
    ('/openapi.json', ('GET',)),
    ('/redoc', ('GET',)),
    ('/routines', ('GET',)),
    ('/settings', ('GET',)),
    ('/students/reports', ('GET',)),
    ('/settings/canvas', ('POST',)),
    ('/settings/courses/bookmark', ('POST',)),
    ('/settings/courses/{course_id}/remove', ('POST',)),
    ('/settings/courses/{course_id}/set-active', ('POST',)),
    ('/settings/download-root', ('POST',)),
    ('/settings/openrouter', ('POST',)),
    ('/settings/openrouter/models', ('GET',)),
    ('/settings/openrouter/test', ('POST',)),
    ('/settings/test-connection', ('POST',)),
    ('/welcome', ('GET',)),
    ('/welcome/workspace', ('POST',)),
    ('/welcome/browse-workspace', ('POST',)),
    ('/feedback-expert', ('GET',)),
    ('/api/feedback/personas', ('GET',)),
    ('/api/feedback/personas/custom', ('POST',)),
    ('/api/feedback/personas/custom', ('DELETE',)),
    ('/api/feedback/patterns', ('GET',)),
    ('/api/feedback/patterns', ('POST',)),
    ('/api/names/backup-vault', ('POST',)),
    ('/api/names/collisions', ('GET',)),
    ('/api/names/nickname', ('POST',)),
    ('/api/names/protected', ('GET',)),
    ('/api/names/protected', ('POST',)),
    ('/api/names/pseudonym', ('POST',)),
    ('/api/names/pseudonym/regenerate', ('POST',)),
    ('/api/names/roster', ('GET',)),
    ('/api/names/scrub-test', ('POST',)),
    ('/api/names/vault-conflict', ('GET',)),
    ('/api/names/who-is-who', ('POST',)),
    ('/api/open-file', ('POST',)),
    ('/api/roster', ('GET',)),
    ('/api/roster/assessment-groups/preview', ('POST',)),
    ('/api/roster/assessment-groups/sources', ('GET',)),
    ('/api/roster/bulk', ('POST',)),
    ('/api/roster/group-set', ('POST',)),
    ('/api/roster/group-labels', ('GET',)),
    ('/api/roster/group-labels', ('POST',)),
    ('/api/roster/group-set-preference', ('POST',)),
    ('/api/roster/groups', ('POST',)),
    ('/api/roster/relationships', ('POST',)),
    ('/api/roster/score-matrix', ('POST',)),
    ('/api/roster/student', ('POST',)),
    ('/name-manager', ('GET',)),
    ('/roster', ('GET',)),
    ('/seating', ('GET',)),
    ('/api/seating', ('GET',)),
    ('/api/seating/apply', ('POST',)),
    ('/api/seating/proposal', ('POST',)),
    ('/api/seating/state', ('POST',)),
    ('/panels', ('GET',)),
    # Generated CSS for the teacher's own themes. Must stay registered
    # ahead of /panels/{kind}, which is a catch-all that would otherwise
    # read this path as a Panel kind and 404 it.
    ('/panels/themes.css', ('GET',)),
    ('/panels/theme-art/{key}/{index}.{ext}', ('GET',)),
    ('/panels/{kind}', ('GET',)),
    ('/panels/{kind}/data', ('GET',)),
    ('/powergrader', ('GET',)),
    ('/powergrader/session/{session_id}', ('GET',)),
    ('/api/powergrader/session/{session_id}', ('GET',)),
    ('/api/powergrader/session/{session_id}/staged', ('GET',)),
    ('/api/powergrader/session/{session_id}/blind-first', ('POST',)),
    ('/api/powergrader/session/{session_id}/blind-reveal', ('POST',)),
    ('/api/powergrader/session/{session_id}/grade', ('POST',)),
    ('/api/powergrader/session/{session_id}/late-preview', ('POST',)),
    ('/api/powergrader/session/{session_id}/late-score', ('POST',)),
    ('/api/powergrader/session/{session_id}/late-watch', ('POST',)),
    ('/api/powergrader/session/{session_id}/import-results', ('POST',)),
    ('/api/powergrader/session/{session_id}/auto-post-disable', ('POST',)),
    ('/api/powergrader/session/{session_id}/new-quiz-finalize', ('POST',)),
    ('/api/powergrader/session/{session_id}/new-quiz-csv-resolve', ('POST',)),
    ('/api/powergrader/session/{session_id}/new-quiz-review', ('POST',)),
    ('/api/powergrader/session/{session_id}/push-review', ('POST',)),
    ('/api/powergrader/session/{session_id}/push', ('POST',)),
    ('/api/powergrader/estimate', ('POST',)),
    ('/api/powergrader/sessions', ('GET',)),
    ('/api/powergrader/start', ('POST',)),
    ('/api/powergrader/new-quiz-csv', ('POST',)),
    ('/api/readiness', ('GET',)),
    ('/api/readiness/probe', ('POST',)),
    ('/api/receipts', ('GET',)),
    ('/api/receipts/{receipt_id}', ('GET',)),
    ('/api/work', ('GET',)),
    ('/api/work/scan', ('POST',)),
    ('/api/work/{job_id}/complete', ('POST',)),
    ('/api/work/{job_id}/ignore', ('POST',)),
    ('/api/work/{job_id}/snooze', ('POST',)),
]


def test_powergrader_staged_route_is_narrow_and_404s(monkeypatch):
    monkeypatch.setattr(powergrader_routes, "_load_session", lambda _session_id: {
        "students": [{"ai_score": 7}, {"ai_score": None}],
        "assistant_staged": {"staged_at": "2026-08-04T12:00:00", "updated": 1},
    })
    response = powergrader_routes.pg_get_staged("session-1")
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "ok": True,
        "staged_at": "2026-08-04T12:00:00",
        "updated": 1,
        "scored": 1,
    }

    monkeypatch.setattr(powergrader_routes, "_load_session", lambda _session_id: None)
    missing = powergrader_routes.pg_get_staged("missing")
    assert missing.status_code == 404
    assert json.loads(missing.body) == {"ok": False, "error": "Session not found."}


def _current_routes():
    out = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        if not methods:          # skip Mounts (static)
            continue
        out.append((r.path, tuple(sorted(m for m in methods if m != "HEAD"))))
    return sorted(out)


def test_route_contract():
    """The full (path, methods) surface must match the frozen baseline."""
    assert _current_routes() == sorted(EXPECTED)
