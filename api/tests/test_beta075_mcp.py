import json
import os
import sys
from pathlib import Path

from api import course_scope, gradebook_queries, gradebook_snapshot
from api.feedback_vault import Vault
from api.mcp_server import contract, pseudonym, tools
from api.mirror import store as mirror_store
from api.webui import workspace
from api.webui.routes import gradebook_snapshot as gradebook_route


def _explode_live(*_args, **_kwargs):
    raise AssertionError("live Canvas read attempted")


def test_live_mcp_schema_matches_versioned_contract():
    from api.mcp_server import server

    assert contract.TOOL_SCHEMA_VERSION == 19
    expected = contract.load_contract()
    live = contract.live_contract(server.mcp)
    assert live == expected
    # Older contracts stay immutable and independently loadable for clients
    # pinned before refresh_mirror (v3), seating context (v4), modules (v5),
    # the authoring contract tool (v6), list_staged_content (v7),
    # list_sections (v8), get_product_guide (v9), get_writing_history (v10),
    # local-only Glass draft tools (v11), v12 removes those Glass tools,
    # v13 adds schedule-read tools get_bell_schedule, get_day_schedule, get_teacher_schedule,
    # v14 adds save_deck, list_active_decks, archive_deck, v15 adds the
    # teacher schedule write tools, v16 replaces save_day_calendar with the
    # canonical School Calendar tools (get/create/preview/apply_school_calendar_change),
    # and v17 removes the live-write create_school_calendar in favor of a staged
    # preview_school_calendar_replacement/apply_school_calendar_replacement pair
    # (revision-safe complete-year create/replace; v16 stays inert history).
    # v18 adds the revision-safe public-event preview/apply pair; v17 stays inert history.
    # v19 adds the disk-only Course Catalog pages read and reviewed objective pair.
    v1 = contract.load_contract(1)
    v2 = contract.load_contract(2)
    assert v1["schema_version"] == 1
    assert [t["name"] for t in v1["tools"]] == [t["name"] for t in v2["tools"]]
    v3 = contract.load_contract(3)
    assert v3["schema_version"] == 3
    assert len(v3["tools"]) == 6
    v4 = contract.load_contract(4)
    assert v4["schema_version"] == 4
    assert len(v4["tools"]) == 7
    v5 = contract.load_contract(5)
    assert v5["schema_version"] == 5
    assert len(v5["tools"]) == 8
    v6 = contract.load_contract(6)
    assert v6["schema_version"] == 6
    assert len(v6["tools"]) == 9
    v7 = contract.load_contract(7)
    assert v7["schema_version"] == 7
    assert len(v7["tools"]) == 10
    v8 = contract.load_contract(8)
    assert v8["schema_version"] == 8
    assert len(v8["tools"]) == 11
    v9 = contract.load_contract(9)
    assert v9["schema_version"] == 9
    assert len(v9["tools"]) == 12
    v11 = contract.load_contract(11)
    assert v11["schema_version"] == 11
    v16 = contract.load_contract(16)
    assert v16["schema_version"] == 16
    assert len(v16["tools"]) == 24
    v17 = contract.load_contract(17)
    assert v17["schema_version"] == 17
    assert len(v17["tools"]) == 25
    assert len(live["tools"]) == 30
    assert all("canvas" not in tool["name"].lower() for tool in live["tools"])


def test_v11_glass_pane_assets_property_is_an_array():
    pane_tool = next(tool for tool in contract.load_contract(11)["tools"]
                     if tool["name"] == "save_glass_pane_draft")
    assert pane_tool["properties"]["assets"] == "array"


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

    # Seed a real on-disk mirror instead of monkeypatching live Canvas reads:
    # both the HTTP route (mirror-first-with-live-fallback) and the MCP tool
    # (strict mirror-only) must genuinely read from it, not from a stub.
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    root = str(tmp_path)
    mirror_store.write_roster("current", users, {"800001": "Period 1"}, root=root)
    mirror_store.write_assignments("current", assignments, root=root)
    mirror_store.merge_submissions("current", "700010", submissions, root=root, replace=True)
    mirror_store.record_pass("current", "full", ok=True, root=root)

    # Tripwires: if either path ever fell back to a live Canvas read instead
    # of the mirror seeded above, one of these would raise. (roster_service
    # is deliberately left unpatched here -- tools._cache_safe() treats a
    # patched roster_service.fetch_students/fetch_sections as a test seam and
    # refuses to serve the mirror at all, which would break the very mirror
    # path this test is proving out.)
    monkeypatch.setattr(gradebook_queries, "course_students", _explode_live)
    monkeypatch.setattr(gradebook_queries, "course_assignments", _explode_live)
    monkeypatch.setattr(gradebook_queries, "course_submissions", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
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
    # One call from the HTTP route's own load_snapshot(course_id) (queries=None,
    # so it resolves the mirror itself), one from tools._load_snapshot's
    # internal load_snapshot(course_id, queries=namespace) -- both still hit
    # this wrapper even though the MCP path resolves the mirror namespace
    # itself via mirror_queries.snapshot_queries before calling in.
    assert len(loader_calls) == 2
    assert http_payload["source"] == "mirror"
    assert mcp_gradebook["source"] == "mirror"
    assert "user_id" not in http_payload["students"][0]
    assert mcp_gradebook["students"]["columns"] == [
        "pseudonym", "missing", "late", "ungraded", "pct"]
    assert len(mcp_gradebook["students"]["rows"]) == 1

    mcp_roster = tools.get_roster("current")
    mcp_submissions = tools.get_submissions("current", "700010")
    assert mcp_roster["source"] == "mirror"
    assert mcp_submissions["source"] == "mirror"
    for payload in (mcp_roster, mcp_submissions, mcp_gradebook):
        assert payload["ok"] is True
        verdict = __import__("api.feedback_safety", fromlist=["scan_payload"]).scan_payload(
            payload, Vault(str(tmp_path / "vault.json"))
        )
        assert verdict["green"] is True
        dumped = json.dumps(payload)
        for leak in ("Learner One", "Learner", "900001", "SIS-900001", "private-name.pdf"):
            assert leak not in dumped

    assert "No local course catalog found" in tools.get_course_assignments("previous")["error"]
    assert powergrader_routes._powergrader_assignment_context("previous", "700010")[1] == \
        course_scope.current_course_error("previous", tools.config.active_courses())
