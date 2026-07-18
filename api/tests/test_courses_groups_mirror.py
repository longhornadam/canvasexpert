"""Focused mirror behavior for the existing ``GET /api/groups`` route."""

from __future__ import annotations

import json

from api.mirror import store
from api.webui import workspace
from api.webui.routes import courses


COURSE = "555001"
CATEGORIES = [{
    "category_id": "cat-1",
    "category_name": "Teams",
    "groups": [{
        "id": "group-1",
        "name": "Team 1",
        "memberships": [{"id": "membership-1", "user_id": "900101"}],
    }],
}]


def _mount(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


def _body(response):
    return json.loads(response.body)


def test_list_groups_uses_fresh_private_snapshot_without_live_loader(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    store.write_groups(COURSE, CATEGORIES)
    monkeypatch.setattr(
        courses, "load_group_categories",
        lambda *_args: (_ for _ in ()).throw(AssertionError("live group loader attempted")),
    )

    body = _body(courses.list_groups(COURSE))

    assert body == {"ok": True, "categories": [{
        "category_id": "cat-1",
        "category_name": "Teams",
        "groups": [{
            "id": "group-1",
            "name": "Team 1",
            "memberships": [{"id": "membership-1", "user_id": "900101"}],
            "student_ids": ["900101"],
        }],
    }], "message": ""}


def test_list_groups_live_fallback_seeds_snapshot_only_after_success(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    monkeypatch.setattr(courses, "load_group_categories", lambda course_id: (CATEGORIES, None, ""))

    body = _body(courses.list_groups(COURSE))

    assert body == {"ok": True, "categories": CATEGORIES, "message": ""}
    document = store.read_groups(COURSE)
    assert document is not None
    assert document["state"] == "current"
    assert document["categories"] == CATEGORIES


def test_list_groups_failed_live_fallback_does_not_write_snapshot(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    monkeypatch.setattr(courses, "load_group_categories",
                        lambda course_id: ([], "Canvas unavailable", ""))

    body = _body(courses.list_groups(COURSE))

    assert body == {"ok": False, "error": "Canvas unavailable"}
    assert store.read_groups(COURSE) is None
