"""Local-spine read behavior for ``GET /api/course-detail`` (Course Info).

Assignments, students, and group sets each read their local projection
(Course Catalog / roster mirror / groups mirror) only while current, and
independently fall back to the existing live Canvas call otherwise. Modules
stay live and unchanged. No email field, token, signed URL, or private path
may ever appear in a response.
"""

from __future__ import annotations

import json

from api.mirror import store as mirror_store
from api.webui.routes import courses


COURSE = "555001"
BASE = "https://canvas.example.test"


def _body(response):
    return json.loads(response.body)


def _headers():
    return {"Authorization": "Bearer secret-token"}, BASE


def _canvas_calls(monkeypatch, table):
    """Install a fake ``canvas_get_all`` recording every call path."""
    calls = []

    def fake(path, params=None):
        calls.append(path)
        return table.get(path, ([], None))

    monkeypatch.setattr(courses, "canvas_get_all", fake)
    return calls


def _current_catalog(records):
    return {
        "catalog": {
            "assignments": {
                "state": "current",
                "last_success_at": "2026-07-18T00:00:00+00:00",
                "last_attempt_at": "2026-07-18T00:00:00+00:00",
                "error_code": "",
                "records": records,
            },
        },
        "source": "canonical",
        "warnings": [],
    }


def _current_roster(students):
    return {
        "schema_version": mirror_store.MIRROR_VERSION,
        "course_id": COURSE,
        "state": "current",
        "last_success_at": mirror_store.now_iso(),
        "last_attempt_at": mirror_store.now_iso(),
        "error_code": "",
        "students": students,
        "sections": {},
    }


def _current_groups(categories):
    return {
        "schema_version": mirror_store.MIRROR_VERSION,
        "course_id": COURSE,
        "state": "current",
        "last_success_at": mirror_store.now_iso(),
        "last_attempt_at": mirror_store.now_iso(),
        "error_code": "",
        "categories": categories,
    }


CATALOG_RECORDS = {
    "501": {
        "id": "501",
        "name": "Warm-up Quiz",
        "due_at": "2026-08-01T12:00:00+00:00",
        "points_possible": 10,
        "published": True,
    },
}

ROSTER_STUDENTS = {
    "101": {"id": "101", "name": "Ada Lovelace", "sortable_name": "Lovelace, Ada"},
    "102": {"id": "102", "name": "Bo Diaz", "sortable_name": "Diaz, Bo"},
}

GROUPS_CATEGORIES = [{
    "category_id": "cat-1",
    "category_name": "Teams",
    "groups": [{
        "id": "grp-1",
        "name": "Team 1",
        "memberships": [{"id": "mem-1", "user_id": "101"}],
    }],
}]


def _install_all_current(monkeypatch):
    monkeypatch.setattr(courses.course_catalog, "read_catalog",
                        lambda course_id: _current_catalog(CATALOG_RECORDS))
    monkeypatch.setattr(courses.mirror_store, "read_roster",
                        lambda course_id: _current_roster(ROSTER_STUDENTS))
    monkeypatch.setattr(courses.mirror_store, "read_groups",
                        lambda course_id: _current_groups(GROUPS_CATEGORIES))
    monkeypatch.setattr(courses, "canvas_headers", _headers)


def test_current_catalog_serves_assignments_with_reconstructed_html_url_and_no_live_call(monkeypatch):
    _install_all_current(monkeypatch)
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["assignments"] == [{
        "id": "501",
        "name": "Warm-up Quiz",
        "due_at": "2026-08-01",
        "points": 10,
        "published": True,
        "html_url": f"{BASE}/courses/{COURSE}/assignments/501",
    }]
    assert not any(f"/courses/{COURSE}/assignments" in c for c in calls)
    # No catalog envelope/source/freshness fields leak.
    assert set(data["assignments"][0]) == {"id", "name", "due_at", "points", "published", "html_url"}


def test_current_roster_serves_students_with_no_email_key(monkeypatch):
    _install_all_current(monkeypatch)
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    names = {s["name"] for s in data["students"]}
    assert names == {"Ada Lovelace", "Bo Diaz"}
    for student in data["students"]:
        assert "email" not in student
        assert set(student) == {"name", "sortable_name"}
    assert not any(f"/courses/{COURSE}/users" in c for c in calls)


def test_current_groups_snapshot_serves_group_sets_with_names_mapped_and_no_membership_call(monkeypatch):
    _install_all_current(monkeypatch)
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["group_sets"] == [{
        "name": "Teams",
        "groups": [{"name": "Team 1", "members": ["Ada Lovelace"]}],
    }]
    assert not any("group_categories" in c or "/groups" in c or "memberships" in c for c in calls)


def test_catalog_non_current_falls_back_live_while_other_scopes_stay_local(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.course_catalog, "read_catalog",
                        lambda course_id: {"catalog": None, "source": "none", "warnings": []})
    live_assignments = [{
        "id": 900, "name": "Live Assignment", "due_at": "2026-08-05T00:00:00Z",
        "points_possible": 5, "published": False, "html_url": f"{BASE}/live/900",
    }]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/assignments": (live_assignments, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["assignments"] == [{
        "id": "900", "name": "Live Assignment", "due_at": "2026-08-05",
        "points": 5, "published": False, "html_url": f"{BASE}/live/900",
    }]
    assert calls.count(f"/api/v1/courses/{COURSE}/assignments") == 1
    # Roster/groups scopes remained on their current-local path: no live calls.
    assert not any(f"/courses/{COURSE}/users" in c for c in calls)
    assert not any("group_categories" in c for c in calls)
    assert data["group_sets"] == [{
        "name": "Teams",
        "groups": [{"name": "Team 1", "members": ["Ada Lovelace"]}],
    }]


def test_roster_non_current_falls_back_live_while_other_scopes_stay_local(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.mirror_store, "read_roster",
                        lambda course_id: {"state": "stale", "students": {}, "sections": {}})
    live_users = [{"id": 101, "name": "Live Ada", "sortable_name": "Ada, Live"}]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/users": (live_users, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["students"] == [{"name": "Live Ada", "sortable_name": "Ada, Live"}]
    assert calls.count(f"/api/v1/courses/{COURSE}/users") == 1
    assert not any(f"/courses/{COURSE}/assignments" in c for c in calls)
    assert not any("group_categories" in c for c in calls)
    assert data["assignments"] == [{
        "id": "501", "name": "Warm-up Quiz", "due_at": "2026-08-01",
        "points": 10, "published": True,
        "html_url": f"{BASE}/courses/{COURSE}/assignments/501",
    }]


def test_groups_non_current_falls_back_live_while_other_scopes_stay_local(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.mirror_store, "read_groups", lambda course_id: None)
    live_cats = [{"id": "cat-9", "name": "Live Teams"}]
    live_groups = [{"id": "grp-9", "name": "Live Team"}]
    live_members = [{"user_id": 101}]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/group_categories": (live_cats, None),
        "/api/v1/group_categories/cat-9/groups": (live_groups, None),
        "/api/v1/groups/grp-9/memberships": (live_members, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    # Names resolved from the roster mirror's students without any live users call.
    assert data["group_sets"] == [{
        "name": "Live Teams",
        "groups": [{"name": "Live Team", "members": ["Ada Lovelace"]}],
    }]
    assert not any(f"/courses/{COURSE}/users" in c for c in calls)
    assert not any(f"/courses/{COURSE}/assignments" in c for c in calls)
    assert data["assignments"] == [{
        "id": "501", "name": "Warm-up Quiz", "due_at": "2026-08-01",
        "points": 10, "published": True,
        "html_url": f"{BASE}/courses/{COURSE}/assignments/501",
    }]


def test_malformed_catalog_records_falls_back_live(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.course_catalog, "read_catalog",
                        lambda course_id: _current_catalog("not-a-dict"))
    live_assignments = [{
        "id": 42, "name": "Fallback Assignment", "due_at": "", "points_possible": None,
        "published": True, "html_url": f"{BASE}/live/42",
    }]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/assignments": (live_assignments, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["assignments"][0]["name"] == "Fallback Assignment"
    assert calls.count(f"/api/v1/courses/{COURSE}/assignments") == 1


def test_malformed_roster_students_falls_back_live(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.mirror_store, "read_roster",
                        lambda course_id: {"state": "current", "students": "not-a-dict", "sections": {}})
    live_users = [{"id": 101, "name": "Live Ada", "sortable_name": "Ada, Live"}]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/users": (live_users, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["students"] == [{"name": "Live Ada", "sortable_name": "Ada, Live"}]
    assert calls.count(f"/api/v1/courses/{COURSE}/users") == 1


def test_malformed_groups_snapshot_falls_back_live(monkeypatch):
    _install_all_current(monkeypatch)
    monkeypatch.setattr(courses.mirror_store, "read_groups",
                        lambda course_id: {
                            "state": "current",
                            "last_success_at": mirror_store.now_iso(),
                            "categories": "not-a-list",
                        })
    live_cats = [{"id": "cat-9", "name": "Live Teams"}]
    live_groups = [{"id": "grp-9", "name": "Live Team"}]
    live_members = [{"user_id": 101}]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/modules": ([], None),
        f"/api/v1/courses/{COURSE}/group_categories": (live_cats, None),
        "/api/v1/group_categories/cat-9/groups": (live_groups, None),
        "/api/v1/groups/grp-9/memberships": (live_members, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["group_sets"][0]["name"] == "Live Teams"
    assert any("group_categories" in c for c in calls)


def test_full_live_fallback_shape_matches_legacy_minus_email(monkeypatch):
    """No mirror data anywhere: behaves like the pre-migration route, minus
    the removed email field, and reuses one live users call for both the
    roster display and group-name resolution (no duplicate /users call)."""
    monkeypatch.setattr(courses.course_catalog, "read_catalog",
                        lambda course_id: {"catalog": None, "source": "none", "warnings": []})
    monkeypatch.setattr(courses.mirror_store, "read_roster", lambda course_id: None)
    monkeypatch.setattr(courses.mirror_store, "read_groups", lambda course_id: None)
    monkeypatch.setattr(courses, "canvas_headers", _headers)

    live_users = [{"id": 101, "name": "Ada Lovelace", "sortable_name": "Lovelace, Ada"}]
    live_cats = [{"id": "cat-1", "name": "Teams"}]
    live_groups = [{"id": "grp-1", "name": "Team 1"}]
    live_members = [{"user_id": 101}]
    live_modules = [{"id": 7, "name": "Unit 1", "items_count": 3, "published": True}]
    live_assignments = [{
        "id": 501, "name": "Warm-up Quiz", "due_at": "2026-08-01T12:00:00Z",
        "points_possible": 10, "published": True, "html_url": f"{BASE}/courses/{COURSE}/assignments/501",
    }]
    calls = _canvas_calls(monkeypatch, {
        f"/api/v1/courses/{COURSE}/users": (live_users, None),
        f"/api/v1/courses/{COURSE}/group_categories": (live_cats, None),
        "/api/v1/group_categories/cat-1/groups": (live_groups, None),
        "/api/v1/groups/grp-1/memberships": (live_members, None),
        f"/api/v1/courses/{COURSE}/modules": (live_modules, None),
        f"/api/v1/courses/{COURSE}/assignments": (live_assignments, None),
    })

    data = _body(courses.course_detail(COURSE))

    assert data["ok"] is True
    assert data["students"] == [{"name": "Ada Lovelace", "sortable_name": "Lovelace, Ada"}]
    assert "email" not in data["students"][0]
    assert data["group_sets"] == [{"name": "Teams", "groups": [{"name": "Team 1", "members": ["Ada Lovelace"]}]}]
    assert data["modules"] == [{"id": "7", "name": "Unit 1", "items_count": 3, "published": True}]
    assert data["assignments"] == [{
        "id": "501", "name": "Warm-up Quiz", "due_at": "2026-08-01",
        "points": 10, "published": True, "html_url": f"{BASE}/courses/{COURSE}/assignments/501",
    }]
    assert calls.count(f"/api/v1/courses/{COURSE}/users") == 1


def test_response_never_leaks_email_token_or_signed_url(monkeypatch):
    _install_all_current(monkeypatch)
    _canvas_calls(monkeypatch, {f"/api/v1/courses/{COURSE}/modules": ([], None)})

    data = _body(courses.course_detail(COURSE))

    serialized = json.dumps(data)
    assert "email" not in serialized.lower()
    assert "secret-token" not in serialized
    assert "signed" not in serialized.lower()
