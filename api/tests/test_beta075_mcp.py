import json
import os
import sys
from pathlib import Path

from api import course_scope, gradebook_queries, gradebook_snapshot, roster_service
from api.feedback_vault import Vault
from api.mcp_server import contract, pseudonym, tools
from api.webui.routes import gradebook_snapshot as gradebook_route


def test_live_mcp_schema_matches_versioned_contract():
    from api.mcp_server import server

    assert contract.TOOL_SCHEMA_VERSION == 2
    expected = contract.load_contract()
    live = contract.live_contract(server.mcp)
    assert live == expected
    # v1 stays immutable and loadable for clients pinned to it.
    v1 = contract.load_contract(1)
    assert v1["schema_version"] == 1
    assert [t["name"] for t in v1["tools"]] == [t["name"] for t in expected["tools"]]
    assert len(live["tools"]) == 5
    forbidden = ("write", "update", "comment", "push", "delete", "create", "canvas")
    assert all(not any(word in tool["name"].lower() for word in forbidden) for tool in live["tools"])


def test_http_and_mcp_share_use_cases_and_student_outputs_stay_green(tmp_path, monkeypatch):
    api_dir = str(Path(__file__).resolve().parents[1])
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    from api.webui.routes import powergrader as powergrader_routes

    tools_source = Path(tools.__file__).read_text(encoding="utf-8")
    pseudonym_source = Path(pseudonym.__file__).read_text(encoding="utf-8")
    assert "webui.routes" not in tools_source
    assert "webui.routes" not in pseudonym_source

    users = [{
        "id": "900001",
        "name": "Learner One",
        "sortable_name": "One, Learner",
        "short_name": "Lee",
        "sis_user_id": "SIS-900001",
        "enrollments": [{"course_section_id": "800001"}],
    }]
    assignments = [{
        "id": "700010", "name": "Synthetic Essay", "due_at": "2026-07-01T23:59:00Z",
        "points_possible": 10, "html_url": "https://example.invalid/essay", "published": True,
    }]
    submissions = [{
        "assignment_id": "700010", "user_id": "900001", "workflow_state": "graded",
        "score": 9, "submitted_at": "2026-07-01T20:00:00Z",
        "body": "Learner One wrote this.",
        "attachments": [{"filename": "private-name.pdf"}],
    }]
    monkeypatch.setattr(gradebook_queries, "course_students", lambda _course: (users, None))
    monkeypatch.setattr(gradebook_queries, "course_assignments", lambda _course: (assignments, None))
    monkeypatch.setattr(gradebook_queries, "course_submissions", lambda _course: (submissions, None))
    monkeypatch.setattr(gradebook_queries, "assignment", lambda *_args: (assignments[0], None))
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", lambda *_args: (submissions, None))
    monkeypatch.setattr(roster_service, "fetch_students", lambda _course, **_kwargs: (users, None))
    monkeypatch.setattr(roster_service, "fetch_sections", lambda _course, **_kwargs: {"800001": "Period 1"})
    monkeypatch.setattr(tools.config, "active_courses", lambda: [
        {"id": "current", "active": True}, {"id": "previous", "active": False},
    ])
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(str(tmp_path / "vault.json")))

    real_loader = gradebook_snapshot.load_snapshot
    loader_calls = []

    def counted_loader(course_id, **kwargs):
        loader_calls.append(course_id)
        return real_loader(course_id, **kwargs)

    monkeypatch.setattr(gradebook_snapshot, "load_snapshot", counted_loader)
    http_result = gradebook_route.api_gradebook("current")
    assert http_result.body
    http_payload = json.loads(http_result.body)
    mcp_gradebook = tools.get_gradebook_snapshot("current")
    assert len(loader_calls) == 2
    assert "user_id" not in http_payload["students"][0]
    assert mcp_gradebook["students"]["columns"] == [
        "pseudonym", "missing", "late", "ungraded", "pct"]
    assert len(mcp_gradebook["students"]["rows"]) == 1

    mcp_roster = tools.get_roster("current")
    mcp_submissions = tools.get_submissions("current", "700010")
    for payload in (mcp_roster, mcp_submissions, mcp_gradebook):
        assert payload["ok"] is True
        verdict = __import__("api.feedback_safety", fromlist=["scan_payload"]).scan_payload(
            payload, Vault(str(tmp_path / "vault.json"))
        )
        assert verdict["green"] is True
        dumped = json.dumps(payload)
        for leak in ("Learner One", "Learner", "900001", "SIS-900001", "private-name.pdf"):
            assert leak not in dumped

    assert tools.get_course_assignments("previous")["error"] == course_scope.current_course_error(
        "previous", tools.config.active_courses()
    )
    assert powergrader_routes._powergrader_assignment_context("previous", "700010")[1] == \
        course_scope.current_course_error("previous", tools.config.active_courses())
