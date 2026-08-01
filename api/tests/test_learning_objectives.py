import copy
import json

from api import course_catalog, learning_objectives
from api.mcp_server import tools
from api.webui import workspace
from api.webui.panel_data import learning_objective_payload


STAMP = "2026-08-30T12:00:00+00:00"


def _catalog():
    return {
        "version": 3,
        "course_id": "course-1",
        "course_name": "Fictional Course",
        "updated_at": STAMP,
        "assignments": {"state": "current", "last_success_at": STAMP, "last_attempt_at": STAMP, "error_code": "", "records": {
            "a1": {"id": "a1", "name": "Explain Evidence", "description_text": "", "points_possible": 10,
                   "due_at": "", "unlock_at": "", "lock_at": "", "created_at": "", "updated_at": "",
                   "published": True, "submission_types": [], "assignment_group_id": "", "quiz_id": "",
                   "is_quiz": False, "quiz_kind": "", "is_quiz_lti_assignment": False, "rubric": [],
                   "rubric_settings": {"id": "", "title": "", "points_possible": None,
                                        "free_form_criterion_comments": False,
                                        "hide_score_total_for_assessment": False, "hide_points": False,
                                        "hide_outcome_results": False}},
        }},
        "modules": {"state": "current", "last_success_at": STAMP, "last_attempt_at": STAMP, "error_code": "", "records": [
            {"id": "m1", "name": "Unit 1", "position": 1, "items": []},
        ]},
        "assignment_groups": {"state": "current", "last_success_at": STAMP, "last_attempt_at": STAMP, "error_code": "", "records": []},
        "pages": {"state": "current", "last_success_at": STAMP, "last_attempt_at": STAMP, "error_code": "", "records": [
            {"id": "p1", "title": "Welcome", "body_text": "Read this.", "published": True, "front_page": True, "updated_at": STAMP},
        ]},
    }


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    course_catalog.write_catalog(_catalog(), root=str(tmp_path))
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": "course-1", "active": True}])


def test_preview_apply_is_exact_revision_safe_and_atomic(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    preview = tools.preview_learning_objective(
        "course-1", "Explain how evidence supports a claim.", "2026-09-01", "2026-09-12",
        [{"kind": "module", "id": "m1", "title": "Unit 1"}],
    )
    assert preview["ok"] is True
    assert preview["preview"]["source_titles"] == ["Unit 1"]
    applied = tools.apply_learning_objective(
        "course-1", preview["preview"], preview["preview_digest"], 0,
    )
    assert applied == {"ok": True, "revision": 1, "course_id": "course-1"}
    path = workspace.learning_objectives_path()
    stored = json.loads(open(path, encoding="utf-8").read())
    assert stored["revision"] == 1
    assert set(stored) == {"version", "revision", "objectives"}
    assert set(stored["objectives"]["course-1"][0]) == learning_objectives.ENTRY_KEYS
    stale = tools.apply_learning_objective(
        "course-1", preview["preview"], preview["preview_digest"], 0,
    )
    assert stale["ok"] is False
    assert "revision" in stale["error"]


def test_mcp_pages_are_current_gated_and_bounded(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    catalog = _catalog()
    catalog["pages"]["records"][0]["body_text"] = "x" * 400
    course_catalog.write_catalog(catalog, root=str(tmp_path))
    preview = tools.get_course_pages("course-1")
    assert preview["ok"] is True
    assert preview["state"] == "current"
    assert len(preview["pages"]["rows"][0][2]) < 400
    full = tools.get_course_pages("course-1", full_text=True)
    assert full["pages"]["rows"][0][2] == "x" * 400
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": "other", "active": True}])
    blocked = tools.get_course_pages("course-1")
    assert blocked["ok"] is False


def test_mcp_pages_omits_unpublished_records(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    catalog = _catalog()
    catalog["pages"]["records"].append({
        "id": "p2", "title": "Draft", "body_text": "Not for the classroom.",
        "published": False, "front_page": False, "updated_at": STAMP,
    })
    course_catalog.write_catalog(catalog, root=str(tmp_path))
    result = tools.get_course_pages("course-1")
    assert result["pages"]["rows"] == [["p1", "Welcome", "Read this.", True, True, STAMP]]


def test_preview_rejects_unknown_source_and_overlapping_ranges(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    missing = tools.preview_learning_objective(
        "course-1", "Use evidence.", "2026-09-01", "2026-09-12",
        [{"kind": "page", "id": "missing", "title": "Missing"}],
    )
    assert missing["ok"] is False
    assert "source ref" in missing["error"]
    first = tools.preview_learning_objective(
        "course-1", "Use evidence.", "2026-09-01", "2026-09-12",
        [{"kind": "page", "id": "p1", "title": "Welcome"}],
    )
    assert tools.apply_learning_objective("course-1", first["preview"], first["preview_digest"], 0)["ok"]
    overlap = tools.preview_learning_objective(
        "course-1", "Explain evidence.", "2026-09-10", "2026-09-20",
        [{"kind": "page", "id": "p1", "title": "Welcome"}],
    )
    assert overlap["ok"] is False
    assert "overlap" in overlap["error"]


def test_panel_only_invalidates_when_a_referenced_source_changes():
    catalog = _catalog()
    entry = {
        "objective": "Read the welcome page.",
        "effective_start": "2026-09-01",
        "effective_end": "2026-09-12",
        "source_refs": [{"kind": "page", "id": "p1", "title": "Welcome"}],
        "source_digest": learning_objectives.source_digest(catalog, [{"kind": "page", "id": "p1", "title": "Welcome"}]),
        "catalog_updated_at": STAMP,
        "authored_at": STAMP,
    }
    document = {"version": 1, "revision": 1, "objectives": {"course-1": [entry]}}
    changed_catalog = copy.deepcopy(catalog)
    changed_catalog["updated_at"] = "2026-08-30T13:00:00+00:00"
    assert learning_objective_payload(
        "course-1", now=__import__("datetime").datetime(2026, 9, 5),
        document_reader=lambda: document, catalog_reader=lambda _cid: {"catalog": changed_catalog},
    )["state"] == "ready"
    changed_catalog["pages"]["records"][0]["body_text"] = "Changed."
    out = learning_objective_payload(
        "course-1", now=__import__("datetime").datetime(2026, 9, 5),
        document_reader=lambda: document, catalog_reader=lambda _cid: {"catalog": changed_catalog},
    )
    assert out["state"] == "changed_source"
    assert out["message"] == "Objective needs review."


def test_panel_reports_invalid_objective_document_as_attention():
    out = learning_objective_payload(
        "course-1", document_reader=lambda: {"broken": True},
        catalog_reader=lambda _cid: {"catalog": _catalog()},
    )
    assert out["state"] == "catalog_needs_attention"
