from fastapi.testclient import TestClient

from api.webui.routes import push
from api.webui.server import app


def _catalog(*, state="current", records=None):
    return {
        "catalog": {
            "modules": {
                "state": state,
                "records": records if records is not None else [
                    {"id": "module-2", "name": "Second"},
                    {"id": "module-1", "name": "First"},
                ],
            },
        },
    }


def _catalog_with_groups(*, state="current", records=None):
    return {
        "catalog": {
            "version": 3,
            "assignment_groups": {
                "state": state,
                "records": records if records is not None else [
                    {"id": "3", "name": "Projects", "position": 1, "group_weight": 20},
                ],
            },
        },
    }


def test_modules_uses_current_catalog_scope_without_canvas(monkeypatch):
    monkeypatch.setattr(push.course_catalog, "read_catalog", lambda course_id: _catalog())
    monkeypatch.setattr(
        push,
        "_canvas_get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Canvas must not be called")),
    )

    response = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/modules?course_id=course-1")

    assert response.json() == {
        "ok": True,
        "modules": [{"id": "module-2", "name": "Second"}, {"id": "module-1", "name": "First"}],
    }


def test_modules_falls_back_to_live_for_missing_or_noncurrent_catalog_scope(monkeypatch):
    calls = []
    catalogs = [
        {"catalog": None},
        _catalog(state="stale"),
        _catalog(state="incomplete"),
        _catalog(state="unavailable"),
        _catalog(records=[{"id": "module-1"}]),
    ]

    def read_catalog(course_id):
        return catalogs.pop(0)

    def canvas_get(path, params):
        calls.append((path, params))
        return [{"id": 7, "name": "Live module"}], None

    monkeypatch.setattr(push.course_catalog, "read_catalog", read_catalog)
    monkeypatch.setattr(push, "_canvas_get", canvas_get)
    client = TestClient(app, base_url="http://127.0.0.1:8765")

    for _ in range(5):
        response = client.get("/api/modules?course_id=course-1")
        assert response.json() == {"ok": True, "modules": [{"id": "7", "name": "Live module"}]}

    assert calls == [
        ("/api/v1/courses/course-1/modules", {"per_page": 100}),
    ] * 5


def test_modules_preserves_live_error_when_catalog_is_not_current(monkeypatch):
    monkeypatch.setattr(push.course_catalog, "read_catalog", lambda course_id: _catalog(state="stale"))
    monkeypatch.setattr(push, "_canvas_get", lambda path, params: (None, "Canvas unavailable"))

    response = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/modules?course_id=course-1")

    assert response.json() == {"ok": False, "error": "Canvas unavailable"}


def test_assignment_groups_remains_live_when_catalog_modules_are_current(monkeypatch):
    calls = []
    monkeypatch.setattr(push.course_catalog, "read_catalog", lambda course_id: _catalog())

    def canvas_get(path, params=None):
        calls.append((path, params))
        return [{"id": 3, "name": "Projects"}], None

    monkeypatch.setattr(push, "_canvas_get", canvas_get)

    response = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/assignment-groups?course_id=course-1")

    assert response.json() == {"ok": True, "groups": [{"id": "3", "name": "Projects"}]}
    assert calls == [("/api/v1/courses/course-1/assignment_groups", None)]


def test_assignment_groups_uses_exactly_current_v3_catalog_without_canvas(monkeypatch):
    monkeypatch.setattr(push.course_catalog, "read_catalog", lambda course_id: _catalog_with_groups())
    monkeypatch.setattr(
        push, "_canvas_get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Canvas must not be called")),
    )

    response = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/assignment-groups?course_id=course-1")

    assert response.json() == {"ok": True, "groups": [{"id": "3", "name": "Projects"}]}


def test_assignment_groups_falls_back_live_for_noncurrent_or_malformed_v2_scope(monkeypatch):
    catalogs = [
        _catalog_with_groups(state="stale"),
        _catalog_with_groups(records=[{"id": "3"}]),
        _catalog_with_groups(records=[{"id": "3", "name": "Projects", "position": 1, "group_weight": 20, "url": "drop"}]),
        {"catalog": {"version": 1}},
    ]
    calls = []

    monkeypatch.setattr(push.course_catalog, "read_catalog", lambda course_id: catalogs.pop(0))
    monkeypatch.setattr(
        push, "_canvas_get",
        lambda path, params=None: calls.append((path, params)) or ([{"id": 3, "name": "Live group"}], None),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    for _ in range(4):
        assert client.get("/api/assignment-groups?course_id=course-1").json() == {
            "ok": True, "groups": [{"id": "3", "name": "Live group"}],
        }
    assert calls == [("/api/v1/courses/course-1/assignment_groups", None)] * 4
