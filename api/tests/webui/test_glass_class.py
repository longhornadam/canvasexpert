"""Acceptance examples for Glass class mode."""

from api.mirror import read_service
from api.webui import glass_class


AT = "2026-09-02T10:15:00-05:00"
AS_OF = "2026-09-02T14:00:00Z"


def _context():
    return {
        "at": AT,
        "mode": "class",
        "state": "in_class",
        "block": {
            "name": "4th/5th",
            "label": "ELA 4/5",
            "course_id": "course-ela",
            "period_ids": ["4"],
            "starts_at": "9:30 AM",
            "ends_at": "10:45 AM",
        },
        "next": {"name": "6th/7th", "label": "ELA 6/7", "starts_at": "10:50 AM"},
    }


def _scope(scope, records):
    return {
        "course_id": "course-ela", "scope": scope, "state": "current",
        "capability": "supported", "source": "mirror", "last_success_at": AS_OF,
        "records": records,
    }


def test_class_mode_projects_period_data_and_independent_class_regions(monkeypatch):
    scopes = {
        read_service.PRIVATE_ROSTER: _scope(read_service.PRIVATE_ROSTER, [
            {"id": "student-1", "name": "Alpha One"},
            {"id": "student-2", "name": "Beta Two"},
        ]),
        read_service.PRIVATE_ASSIGNMENTS: _scope(read_service.PRIVATE_ASSIGNMENTS, [
            {"id": "a1", "name": "Build", "published": True},
        ]),
        read_service.PRIVATE_SUBMISSIONS: _scope(read_service.PRIVATE_SUBMISSIONS, [
            {"assignment_id": "a1", "user_id": "student-1", "missing": True, "excused": False},
        ]),
    }
    catalog = {
        "catalog": {
            "version": 3, "course_name": "Synthetic ELA",
            "updated_at": AS_OF,
            "assignments": {"state": "current", "last_success_at": AS_OF, "records": [
                {"id": "a2", "name": "Explain", "published": True,
                 "due_at": "2026-09-05T15:00:00Z", "points_possible": 10},
            ]},
        }
    }
    profiles = {
        "student-2": {"classroom_profile": {"birthday": "09-03", "celebrations": []}},
    }

    monkeypatch.setattr(glass_class.config, "mirror_serve_max_age_hours", lambda: 6.0)
    out = glass_class.get_class_context(
        _context(),
        scope_reader=lambda scope, _course, **_kwargs: scopes[scope],
        catalog_reader=lambda _course: catalog,
        objective_reader=lambda: {"version": 2, "revision": 0, "objectives": {}},
        profile_reader=lambda _course: profiles,
    )

    assert out["state"] == "ready"
    assert out["period"]["name"] == "4th/5th"
    assert out["period"]["remaining_seconds"] == 1800
    assert out["period"]["next"]["name"] == "6th/7th"
    assert out["due"]["assignments"][0]["title"] == "Explain"
    assert out["missing"]["students"][0]["student_name"] == "Alpha O."
    assert out["celebrations"]["items"][0]["student_name"] == "Beta T."
    assert out["random_name"]["names"] == ["Alpha O.", "Beta T."]
    assert "student-" not in str(out)


def test_class_mode_keeps_random_roster_usable_when_due_data_needs_attention():
    scopes = {
        read_service.PRIVATE_ROSTER: _scope(read_service.PRIVATE_ROSTER, [{"id": "s1", "name": "Alpha One"}]),
        read_service.PRIVATE_ASSIGNMENTS: _scope(read_service.PRIVATE_ASSIGNMENTS, []),
        read_service.PRIVATE_SUBMISSIONS: _scope(read_service.PRIVATE_SUBMISSIONS, []),
    }
    out = glass_class.get_class_context(
        _context(),
        scope_reader=lambda scope, _course, **_kwargs: scopes[scope],
        catalog_reader=lambda _course: {},
        objective_reader=lambda: {"version": 2, "revision": 0, "objectives": {}},
        profile_reader=lambda _course: {},
    )

    assert out["random_name"]["names"] == ["Alpha O."]
    assert out["due"]["state"] == "no_catalog"
    assert out["missing"]["state"] == "no_missing_work"
