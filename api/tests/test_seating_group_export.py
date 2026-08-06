"""Create-only Seating group-set export tests with synthetic Canvas responses."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from api.operation_ledger import operations, paths, registry
from api.operation_ledger.adapters.seating_group_set import KIND, SeatingGroupSetAdapter
from api.webui.local_request_guard import csrf_token
from api.webui.server import app


def _headers():
    return {
        "X-CanvasExpert-CSRF": csrf_token(),
        "Origin": "http://127.0.0.1:8765",
    }


def _seating_state():
    return {
        "layouts": [{
            "id": "layout-a", "name": "Room", "rows": 1, "columns": 4,
            "seats": [
                {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
                {"id": "seat-1-2", "row": 1, "column": 2, "label": "1-2"},
                {"id": "seat-1-3", "row": 1, "column": 3, "label": "1-3"},
                {"id": "seat-1-4", "row": 1, "column": 4, "label": "1-4"},
            ],
            "near_teacher_seat_ids": [],
        }],
        "modes": [{
            "id": "mode-a", "name": "Pairs", "section_id": "section-a",
            "layout_id": "layout-a", "strategy": "buddy_pairs",
            "assignment": {
                "seat-1-1": "student-a", "seat-1-2": "student-b",
                "seat-1-3": "student-c", "seat-1-4": "student-d",
            },
        }],
    }


class _Canvas:
    def __init__(self, *, existing=None, category_error=None, group_error=None):
        self.categories = deepcopy(existing or [])
        self.groups: dict[str, list[dict]] = {}
        self.memberships: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.category_error = category_error
        self.group_error = group_error
        self._counter = 0

    def get_all(self, path, params=None, timeout=30):
        if path == "/api/v1/courses/course-a/group_categories":
            return deepcopy(self.categories), None
        if path.startswith("/api/v1/group_categories/") and path.endswith("/groups"):
            category_id = path.split("/")[4]
            return deepcopy(self.groups.get(category_id, [])), None
        if path.startswith("/api/v1/groups/") and path.endswith("/memberships"):
            group_id = path.split("/")[4]
            return deepcopy(self.memberships.get(group_id, [])), None
        raise AssertionError(f"unexpected synthetic Canvas read: {path}")

    def send(self, method, path, payload, timeout=30):
        self.calls.append((method, path, deepcopy(payload)))
        assert method == "POST"
        if path == "/api/v1/courses/course-a/group_categories":
            if self.category_error:
                return None, self.category_error
            self._counter += 1
            category_id = f"category-{self._counter}"
            self.categories.append({"id": category_id, "name": payload["name"]})
            return {"id": category_id, "name": payload["name"]}, None
        if path.startswith("/api/v1/group_categories/") and path.endswith("/groups"):
            if self.group_error:
                return None, self.group_error
            self._counter += 1
            category_id = path.split("/")[4]
            group_id = f"group-{self._counter}"
            self.groups.setdefault(category_id, []).append({"id": group_id, "name": payload["name"]})
            return {"id": group_id, "name": payload["name"]}, None
        if path.startswith("/api/v1/groups/") and path.endswith("/memberships"):
            self._counter += 1
            group_id = path.split("/")[4]
            membership_id = f"membership-{self._counter}"
            membership = {"id": membership_id, "user_id": payload["user_id"]}
            self.memberships.setdefault(group_id, []).append(membership)
            return membership, None
        raise AssertionError(f"unexpected synthetic Canvas write: {path}")


@pytest.fixture
def group_export_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "private_root", lambda: tmp_path / "ledger")
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.config.active_courses",
        lambda: [{"id": "course-a", "name": "Synthetic Course"}],
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.config.get_seating_course_state",
        lambda course_id: _seating_state() if str(course_id) == "course-a" else {},
    )
    reconciled = []
    monkeypatch.setattr(
        SeatingGroupSetAdapter,
        "_reconcile_new_category",
        staticmethod(lambda course_id, category_id, category_name: reconciled.append(
            (course_id, category_id, category_name)
        )),
    )
    return TestClient(app, base_url="http://127.0.0.1:8765"), reconciled


def _prepare(client, name="New Seating Groups"):
    return client.post(
        f"/api/operations/{KIND}/prepare",
        json={
            "payload": {
                "course_id": "course-a",
                "mode_id": "mode-a",
                "group_set_name": name,
            },
            "targets": [{"course_id": "course-a"}],
        },
        headers=_headers(),
    )


def _review_and_apply(client, operation_id):
    reviewed = client.post(
        "/api/operation-batches/review",
        json={"operation_ids": [operation_id]}, headers=_headers(),
    )
    assert reviewed.status_code == 200
    review = reviewed.json()
    return client.post(
        f"/api/operation-batches/{review['batch_id']}/apply",
        json={"review_digest": review["review_digest"]}, headers=_headers(),
    )


def test_adapter_is_registered():
    assert registry.get_adapter(KIND).kind == KIND


def test_prepare_refuses_an_existing_canvas_category_name(group_export_env, monkeypatch):
    client, _ = group_export_env
    canvas = _Canvas(existing=[{"id": "category-old", "name": "New Seating Groups"}])
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client.canvas_get_all", canvas.get_all,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client._canvas_send", canvas.send,
    )

    response = _prepare(client)

    assert response.status_code == 400
    assert "already exists" in response.json()["error"]
    assert operations.list_operations() == []
    assert canvas.calls == []


def test_prepare_rejects_an_invalid_new_group_set_name_before_canvas_lookup(group_export_env, monkeypatch):
    client, _ = group_export_env
    canvas = _Canvas()
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client.canvas_get_all", canvas.get_all,
    )

    response = _prepare(client, "New\nGroups")

    assert response.status_code == 400
    assert "1 to 100" in response.json()["error"]
    assert operations.list_operations() == []
    assert canvas.calls == []


def test_prepare_review_apply_creates_only_one_new_category_groups_and_memberships(group_export_env, monkeypatch):
    client, reconciled = group_export_env
    canvas = _Canvas(existing=[{"id": "category-existing", "name": "Existing groups"}])
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client.canvas_get_all", canvas.get_all,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client._canvas_send", canvas.send,
    )

    prepared = _prepare(client)
    assert prepared.status_code == 200
    summary = prepared.json()["review_summary"]["frozen_reviews"][0]
    assert summary == {
        "course_name": "Synthetic Course",
        "new_group_set_name": "New Seating Groups",
        "group_count": 2,
        "member_count": 4,
        "partial_group_count": 0,
        "baseline_name_collision": False,
        "new_set_only": True,
    }
    status_text = json.dumps(client.get(
        f"/api/operations/{prepared.json()['operation_id']}/status"
    ).json())
    review_text = json.dumps(summary)
    assert all(student_id not in status_text + review_text for student_id in (
        "student-a", "student-b", "student-c", "student-d",
    ))

    applied = _review_and_apply(client, prepared.json()["operation_id"])

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert [path for _method, path, _payload in canvas.calls] == [
        "/api/v1/courses/course-a/group_categories",
        "/api/v1/group_categories/category-1/groups",
        "/api/v1/groups/group-2/memberships",
        "/api/v1/groups/group-2/memberships",
        "/api/v1/group_categories/category-1/groups",
        "/api/v1/groups/group-5/memberships",
        "/api/v1/groups/group-5/memberships",
    ]
    assert all(method == "POST" for method, _path, _payload in canvas.calls)
    assert not any("category-existing" in path for _method, path, _payload in canvas.calls)
    assert reconciled == [("course-a", "category-1", "New Seating Groups")]
    stored = operations.get_operation(prepared.json()["operation_id"])
    assert [step["step_key"] for step in stored["targets"][0]["steps"]] == [
        "create_category", "create_group_0", "add_member_0_0", "add_member_0_1",
        "create_group_1", "add_member_1_0", "add_member_1_1",
    ]
    assert all(step["returned_object_id"] for step in stored["targets"][0]["steps"])


def test_uncertain_category_creation_never_sends_a_duplicate_on_retry(group_export_env, monkeypatch):
    client, reconciled = group_export_env
    canvas = _Canvas(category_error="timeout while waiting for Canvas")
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client.canvas_get_all", canvas.get_all,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client._canvas_send", canvas.send,
    )

    prepared = _prepare(client)
    applied = _review_and_apply(client, prepared.json()["operation_id"])
    retried = client.post(
        f"/api/operations/{prepared.json()['operation_id']}/retry", headers=_headers(),
    )

    assert applied.status_code == 200
    assert applied.json()["status"] == "attention"
    assert retried.status_code == 200
    assert len(canvas.calls) == 1
    assert canvas.calls[0][1] == "/api/v1/courses/course-a/group_categories"
    assert reconciled == []


def test_group_failure_is_partial_and_reconciles_the_exact_new_category(group_export_env, monkeypatch):
    client, reconciled = group_export_env
    canvas = _Canvas(group_error="HTTP 400: group rejected")
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client.canvas_get_all", canvas.get_all,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.seating_group_set.canvas_client._canvas_send", canvas.send,
    )

    prepared = _prepare(client)
    applied = _review_and_apply(client, prepared.json()["operation_id"])

    assert applied.status_code == 200
    assert applied.json()["status"] == "partial"
    assert [method for method, _path, _payload in canvas.calls] == ["POST", "POST"]
    assert reconciled == [("course-a", "category-1", "New Seating Groups")]
