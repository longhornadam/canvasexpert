"""Local-catalog read behavior for ``GET /api/assignments-full``.

The download/report assignment picker reads Course Catalog's assignment and
assignment-group scopes when both are exactly ``current`` and reshapes them
into the same output the existing live paginated fetch already produces,
making zero Canvas calls. Whenever either scope is not current, the route
falls through to exactly today's live-fetch code, unchanged.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.webui.routes import reports
from api.webui.server import app


BASE = "https://canvas.example.test"
COURSE = "course-1"


def _body(response):
    return json.loads(response.body if hasattr(response, "body") else response.content)


def _client():
    return TestClient(app, base_url="http://127.0.0.1:8765")


def _headers():
    return {"Authorization": "Bearer secret-token"}, BASE


def _catalog_document(*, assignments_state="current", groups_state="current",
                       assignment_records=None, group_records=None):
    return {
        "catalog": {
            "assignments": {
                "state": assignments_state,
                "last_success_at": "2026-07-18T00:00:00+00:00",
                "last_attempt_at": "2026-07-18T00:00:00+00:00",
                "error_code": "",
                "records": assignment_records if assignment_records is not None else [],
            },
            "assignment_groups": {
                "state": groups_state,
                "last_success_at": "2026-07-18T00:00:00+00:00",
                "last_attempt_at": "2026-07-18T00:00:00+00:00",
                "error_code": "",
                "records": group_records if group_records is not None else [],
            },
        },
    }


def _forbid_canvas(monkeypatch):
    """Fail loudly if the live path is ever reached."""
    monkeypatch.setattr(
        reports, "_canvas_headers",
        lambda: (_ for _ in ()).throw(AssertionError("Canvas must not be called")),
    )
    monkeypatch.setattr(
        reports.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Canvas must not be called")),
    )


class _FakeResponse:
    def __init__(self, rows, status_code=200, link_header=""):
        self._rows = rows
        self.status_code = status_code
        self.headers = {"Link": link_header} if link_header else {}

    def json(self):
        return self._rows


# ── (a) catalog-current: identical shape/sort/zero Canvas calls ───────────

def test_catalog_current_serves_assignments_with_zero_canvas_calls(monkeypatch):
    assignment_records = [
        {
            "id": "501",
            "name": "Warm-up Quiz",
            "submission_types": ["online_quiz"],
            "due_at": "2026-08-01T12:00:00+00:00",
            "points_possible": 10,
            "assignment_group_id": "10",
            "quiz_id": "900",
            "is_quiz": True,
            "quiz_kind": "classic_quiz",
            "is_quiz_lti_assignment": False,
        },
        {
            "id": "502",
            "name": "Essay Draft",
            "submission_types": ["online_text_entry"],
            "due_at": "2026-08-10T23:59:00+00:00",
            "points_possible": 20,
            "assignment_group_id": "10",
            "quiz_id": "",
            "is_quiz": False,
            "quiz_kind": "",
            "is_quiz_lti_assignment": False,
        },
        {
            "id": "503",
            "name": "No Due Date",
            "submission_types": ["online_upload"],
            "due_at": "",
            "points_possible": 5,
            "assignment_group_id": "",
            "quiz_id": "",
            "is_quiz": False,
            "quiz_kind": "",
            "is_quiz_lti_assignment": False,
        },
    ]
    group_records = [{"id": "10", "name": "Formative", "position": 1, "group_weight": 50}]

    monkeypatch.setattr(
        reports.read_service.course_catalog, "read_catalog",
        lambda course_id: _catalog_document(
            assignment_records=assignment_records, group_records=group_records,
        ),
    )
    _forbid_canvas(monkeypatch)

    response = _client().get(f"/api/assignments-full?course_id={COURSE}")
    body = response.json()

    assert body == {
        "ok": True,
        "assignments": [
            {
                "id": "502",
                "name": "Essay Draft",
                "submission_types": ["online_text_entry"],
                "due_at": "2026-08-10",
                "points_possible": 20,
                "quiz_id": "",
                "assignment_group_id": "10",
                "assignment_group_name": "Formative",
                "is_quiz": False,
                "quiz_kind": "",
                "is_quiz_lti_assignment": False,
            },
            {
                "id": "501",
                "name": "Warm-up Quiz",
                "submission_types": ["online_quiz"],
                "due_at": "2026-08-01",
                "points_possible": 10,
                "quiz_id": "900",
                "assignment_group_id": "10",
                "assignment_group_name": "Formative",
                "is_quiz": True,
                "quiz_kind": "classic_quiz",
                "is_quiz_lti_assignment": False,
            },
            {
                "id": "503",
                "name": "No Due Date",
                "submission_types": ["online_upload"],
                "due_at": "",
                "points_possible": 5,
                "quiz_id": "",
                "assignment_group_id": "",
                "assignment_group_name": "",
                "is_quiz": False,
                "quiz_kind": "",
                "is_quiz_lti_assignment": False,
            },
        ],
    }


# ── (b) either scope not current: unchanged live fallback ─────────────────

def test_falls_back_to_live_fetch_when_group_scope_is_not_current(monkeypatch):
    monkeypatch.setattr(
        reports.read_service.course_catalog, "read_catalog",
        lambda course_id: _catalog_document(assignments_state="current", groups_state="stale"),
    )
    monkeypatch.setattr(reports, "_canvas_headers", _headers)

    live_rows = [
        {
            "id": 7,
            "name": "Live Assignment",
            "submission_types": ["online_upload"],
            "due_at": "2026-09-01T12:00:00Z",
            "points_possible": 15,
            "quiz_id": None,
            "assignment_group_id": 20,
            "assignment_group": {"name": "Summative"},
            "is_quiz_lti_assignment": False,
        },
        {
            "id": 8,
            "name": "Live New Quiz",
            "submission_types": ["online_quiz"],
            "due_at": None,
            "points_possible": None,
            "quiz_id": None,
            "assignment_group_id": 21,
            "is_quiz_lti_assignment": True,
        },
    ]
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        return _FakeResponse(live_rows)

    monkeypatch.setattr(reports.requests, "get", fake_get)

    response = _client().get(f"/api/assignments-full?course_id={COURSE}")
    body = response.json()

    assert len(calls) == 1
    assert body == {
        "ok": True,
        "assignments": [
            {
                "id": "7",
                "name": "Live Assignment",
                "submission_types": ["online_upload"],
                "due_at": "2026-09-01",
                "points_possible": 15,
                "quiz_id": "",
                "assignment_group_id": "20",
                "assignment_group_name": "Summative",
                "is_quiz": False,
                "quiz_kind": "",
                "is_quiz_lti_assignment": False,
            },
            {
                "id": "8",
                "name": "Live New Quiz",
                "submission_types": ["online_quiz"],
                "due_at": "",
                "points_possible": None,
                "quiz_id": "",
                "assignment_group_id": "21",
                "assignment_group_name": "",
                "is_quiz": True,
                "quiz_kind": "new_quiz",
                "is_quiz_lti_assignment": True,
            },
        ],
    }


def test_falls_back_to_live_fetch_when_assignment_scope_is_not_current(monkeypatch):
    monkeypatch.setattr(
        reports.read_service.course_catalog, "read_catalog",
        lambda course_id: _catalog_document(assignments_state="unavailable", groups_state="current"),
    )
    monkeypatch.setattr(reports, "_canvas_headers", _headers)

    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        return _FakeResponse([])

    monkeypatch.setattr(reports.requests, "get", fake_get)

    response = _client().get(f"/api/assignments-full?course_id={COURSE}")
    body = response.json()

    assert len(calls) == 1
    assert body == {"ok": True, "assignments": []}


def test_falls_back_to_live_fetch_when_no_catalog_exists(monkeypatch):
    """No catalog document at all (e.g. never refreshed) must also fall through."""
    monkeypatch.setattr(
        reports.read_service.course_catalog, "read_catalog",
        lambda course_id: {"catalog": None},
    )
    monkeypatch.setattr(reports, "_canvas_headers", lambda: (None, ""))

    response = _client().get(f"/api/assignments-full?course_id={COURSE}")
    body = response.json()

    assert body == {"ok": False, "error": "No token saved."}


# ── (c) group-name resolution: matched, unmatched, and absent group ids ───

def test_group_name_resolution_matches_or_falls_back_to_empty_string(monkeypatch):
    assignment_records = [
        {
            "id": "1",
            "name": "Matched Group",
            "submission_types": [],
            "due_at": "",
            "points_possible": None,
            "assignment_group_id": "10",
            "quiz_id": "",
            "is_quiz": False,
            "quiz_kind": "",
            "is_quiz_lti_assignment": False,
        },
        {
            "id": "2",
            "name": "Unmatched Group",
            "submission_types": [],
            "due_at": "",
            "points_possible": None,
            "assignment_group_id": "999",
            "quiz_id": "",
            "is_quiz": False,
            "quiz_kind": "",
            "is_quiz_lti_assignment": False,
        },
        {
            "id": "3",
            "name": "No Group At All",
            "submission_types": [],
            "due_at": "",
            "points_possible": None,
            "assignment_group_id": "",
            "quiz_id": "",
            "is_quiz": False,
            "quiz_kind": "",
            "is_quiz_lti_assignment": False,
        },
    ]
    group_records = [{"id": "10", "name": "Formative", "position": 1, "group_weight": 50}]

    monkeypatch.setattr(
        reports.read_service.course_catalog, "read_catalog",
        lambda course_id: _catalog_document(
            assignment_records=assignment_records, group_records=group_records,
        ),
    )
    _forbid_canvas(monkeypatch)

    response = _client().get(f"/api/assignments-full?course_id={COURSE}")
    body = response.json()

    names = {a["id"]: a["assignment_group_name"] for a in body["assignments"]}
    assert names == {"1": "Formative", "2": "", "3": ""}
