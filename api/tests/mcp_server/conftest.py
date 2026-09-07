from __future__ import annotations

import pytest

from api.feedback_vault import Vault
from api.mcp_server import server, tools
from api.mirror import store as mirror_store
from api.platform_services import workspace


@pytest.fixture
def _synthetic_mcp(monkeypatch):
    """Stub every wrapper delegate for in-memory FastMCP boundary calls."""
    names = sorted(server.mcp._tool_manager._tools)
    calls = []
    gated = []

    for name in names:
        def delegate(*args, _name=name, **kwargs):
            calls.append((_name, args, kwargs))
            return {"ok": True, "delegate": _name}
        monkeypatch.setattr(tools, name, delegate)

    def gate(payload):
        gated.append(payload)
        return {
            "ok": payload.get("ok"),
            "delegate": payload.get("delegate"),
            "table": {"columns": ["élève"], "rows": [["Zoë"]]},
        }
    monkeypatch.setattr(tools, "final_response_gate", gate)

    def required_arguments(name):
        tool = next(item for item in server.mcp._tool_manager._tools.values()
                    if item.name == name)
        schema = tool.parameters
        arguments = {}
        for key in schema.get("required") or []:
            kind = (schema.get("properties") or {}).get(key, {}).get("type")
            arguments[key] = {
                "string": f"synthetic-{name}-{key}",
                "integer": 1,
                "number": 1.0,
                "boolean": False,
                "array": [],
                "object": {},
            }.get(kind, None)
        return arguments

    return {"names": names, "calls": calls, "gated": gated,
            "required_arguments": required_arguments}


@pytest.fixture
def _rows():
    def rows(table: dict) -> list[dict]:
        return [dict(zip(table["columns"], row)) for row in table["rows"]]

    return rows


@pytest.fixture
def _use_vault(monkeypatch, tmp_path) -> str:
    vault_path = str(tmp_path / "vault.json")
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(vault_path))
    return vault_path


@pytest.fixture
def _set_active_courses(monkeypatch):
    def set_active_courses(course_ids):
        monkeypatch.setattr(
            tools.config, "active_courses",
            lambda: [{"id": cid, "name": f"Course {cid}"} for cid in course_ids],
        )

    return set_active_courses


@pytest.fixture
def _set_previous_course(_set_active_courses, monkeypatch):
    def set_previous_course(course_id="111"):
        _set_active_courses(["222"])
        monkeypatch.setattr(
            tools.config, "saved_courses",
            lambda: [{"id": course_id, "name": f"Course {course_id}", "active": False}],
        )

    return set_previous_course


@pytest.fixture
def _catalog_document():
    def catalog_document(assignment_records, module_records):
        scope = {"state": "current", "last_success_at": "2026-07-01T00:00:00Z",
                 "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
        return {
            "course_id": "111",
            "course_name": "Test Course",
            "updated_at": "2026-07-01T00:00:00Z",
            "assignments": {**scope, "records": assignment_records},
            "modules": {**scope, "records": module_records},
        }

    return catalog_document


@pytest.fixture
def _module_catalog_document():
    def module_catalog_document(module_records, *, state="current"):
        module_scope = {"state": state, "last_success_at": "2026-07-01T00:00:00Z",
                        "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
        assignment_scope = {"state": "current", "last_success_at": "2026-07-01T00:00:00Z",
                            "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
        return {
            "course_id": "111",
            "course_name": "Test Course",
            "updated_at": "2026-07-01T00:00:00Z",
            "assignments": {**assignment_scope, "records": {}},
            "modules": {**module_scope, "records": module_records},
        }

    return module_catalog_document


@pytest.fixture
def _mount_mirror(monkeypatch, tmp_path):
    def mount_mirror():
        monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))

    return mount_mirror


@pytest.fixture
def _submissions_fixture(request, _mount_mirror, _use_vault, _set_active_courses, tmp_path):
    def submissions_fixture(bodies_by_user=None):
        bodies_by_user = bodies_by_user or {
            900001: "<p>First essay body.</p>",
            900002: "<p>Second essay body.</p>",
        }
        _mount_mirror()
        _set_active_courses(["111"])
        module = request.module
        root = str(tmp_path)
        mirror_store.write_roster("111", module.FIXTURE_USERS, module.SECTION_MAP, root=root)
        mirror_store.write_assignments("111", [
            {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""},
        ], root=root)
        mirror_store.merge_submissions("111", "700010", [
            {"assignment_id": 700010, "user_id": uid, "workflow_state": "submitted",
             "submitted_at": "2026-07-01T20:00:00Z", "body": body}
            for uid, body in bodies_by_user.items()
        ], root=root, replace=True)
        mirror_store.record_pass("111", "full", ok=True, root=root)

    return submissions_fixture
