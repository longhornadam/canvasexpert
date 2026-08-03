from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from api.webui import server
from api.webui.routes import roster_assessment_groups as grouping_routes


ROOT = Path(__file__).resolve().parents[4]


COURSE = "synthetic-course"
SNAPSHOT = {
    "id": "synthetic-benchmark",
    "label": "Synthetic Benchmark",
    "date": "2026-08-01",
    "students": [
        {"n": "Student_001", "pct": 42, "app": "n", "met": "n", "mas": "n"},
        {"n": "Student_002", "pct": 66, "app": "y", "met": "n", "mas": "n"},
        {"n": "Student_003", "pct": 82, "app": "y", "met": "y", "mas": "n"},
        {"n": "Student_004", "pct": 96, "app": "y", "met": "y", "mas": "y"},
    ],
}

ROSTER_DOCUMENT = {
    "state": "current",
    "students": {
        "canvas-1": {"id": "canvas-1", "name": "Synthetic One", "sis_user_id": "SIS-1"},
        "canvas-2": {"id": "canvas-2", "name": "Synthetic Two", "sis_user_id": "SIS-2"},
        "canvas-3": {"id": "canvas-3", "name": "Synthetic Three", "sis_user_id": "SIS-3"},
        "canvas-4": {"id": "canvas-4", "name": "Synthetic Four", "sis_user_id": "SIS-4"},
        "canvas-5": {"id": "canvas-5", "name": "Synthetic Five", "sis_user_id": "SIS-5"},
    },
}

GROUPS_DOCUMENT = {
    "state": "current",
    "categories": [{
        "category_id": "category-1",
        "category_name": "Synthetic Benchmark Tiers",
        "groups": [
            {"id": "group-support", "name": "Support", "memberships": []},
            {"id": "group-core", "name": "Core", "memberships": []},
            {"id": "group-accelerate", "name": "Accelerate", "memberships": []},
            {"id": "group-extend", "name": "Extend", "memberships": []},
        ],
    }],
}


def _client():
    return TestClient(server.app, base_url="http://127.0.0.1:8765")


def _configure(monkeypatch):
    monkeypatch.setattr(grouping_routes.mirror_store, "read_roster", lambda course_id: ROSTER_DOCUMENT)
    monkeypatch.setattr(grouping_routes.mirror_store, "read_groups", lambda course_id: GROUPS_DOCUMENT)
    monkeypatch.setattr(
        grouping_routes.dataforge_paths,
        "get_paths",
        lambda: SimpleNamespace(anon_map="synthetic-map.csv"),
    )
    monkeypatch.setattr(grouping_routes.history_store, "list_snapshots", lambda paths: [SNAPSHOT])

    class FakeIdentity:
        @classmethod
        def from_paths(cls, paths):
            assert str(paths.anon_map) == "synthetic-map.csv"
            return cls()

        def linked_students(self):
            return {
                "Student_001": "SIS-1",
                "Student_002": "SIS-2",
                "Student_003": "SIS-3",
                "Student_004": "SIS-4",
            }

    monkeypatch.setattr(grouping_routes, "VaultIdentity", FakeIdentity)


def test_sources_are_local_only_and_return_synthetic_choices(monkeypatch):
    _configure(monkeypatch)
    response = _client().get("/api/roster/assessment-groups/sources", params={"course_id": COURSE})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["snapshots"][0]["id"] == "synthetic-benchmark"
    assert data["groups"][0]["groups"][-1]["name"] == "Extend"


def test_preview_uses_mirror_and_offline_snapshot_without_canvas(monkeypatch):
    _configure(monkeypatch)
    response = _client().post(
        "/api/roster/assessment-groups/preview",
        data={
            "course_id": COURSE,
            "snapshot_id": "synthetic-benchmark",
            "method": "overall_pct",
            "cutoffs": '{"support": 60, "core": 75, "accelerate": 90}',
            "no_data_group": "Core",
            "category_id": "category-1",
        },
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["roster_count"] == 5
    assert proposal["no_data_count"] == 1
    assert [tier["student_count"] for tier in proposal["tiers"]] == [1, 2, 1, 1]
    assert proposal["proposal_digest"]


def test_preview_rejects_missing_no_data_placement_and_stale_mirror(monkeypatch):
    _configure(monkeypatch)
    missing = _client().post(
        "/api/roster/assessment-groups/preview",
        data={"course_id": COURSE, "snapshot_id": "synthetic-benchmark", "category_id": "category-1"},
    )
    assert missing.status_code == 400
    assert "no-data" in missing.json()["error"]

    monkeypatch.setattr(grouping_routes.mirror_store, "read_roster", lambda course_id: {"state": "stale"})
    stale = _client().get("/api/roster/assessment-groups/sources", params={"course_id": COURSE})
    assert stale.status_code == 409
    assert "current local roster mirror" in stale.json()["error"]


def test_preview_reports_malformed_cutoffs_as_a_validation_error(monkeypatch):
    """A bad cutoff value is the teacher's input, not a server fault: 400 with a
    sentence they can act on, not 409 with a JSON decoder message."""
    _configure(monkeypatch)
    response = _client().post(
        "/api/roster/assessment-groups/preview",
        data={
            "course_id": COURSE,
            "snapshot_id": "synthetic-benchmark",
            "method": "overall_pct",
            "cutoffs": "{not json",
            "no_data_group": "Core",
            "category_id": "category-1",
        },
    )
    assert response.status_code == 400
    assert "valid JSON" in response.json()["error"]


def test_apply_rechecks_the_preview_and_walks_tiers_one_at_a_time():
    """Two guarantees that live only in the browser, because apply reuses the
    pre-existing bulk endpoint: the write is re-checked against a fresh preview
    digest, and a failure part-way through names what landed."""
    script = (ROOT / "api" / "webui" / "static" / "roster" / "assessment_groups.js").read_text(encoding="utf-8")
    assert "proposal_digest !== reviewed" in script, "apply must compare against the reviewed digest"
    assert "Promise.all" not in script, "tiers must be applied one at a time, not fired together"
    assert "Already applied: " in script
    assert "Not applied: " in script


def test_students_panel_has_review_controls_and_reuses_existing_bulk_action():
    template = (ROOT / "api" / "webui" / "templates" / "roster.html").read_text(encoding="utf-8")
    script = (ROOT / "api" / "webui" / "static" / "roster" / "assessment_groups.js").read_text(encoding="utf-8")
    assert 'id="roster-assessment-grouping"' in template
    for marker in (
        'id="roster-assessment-snapshot"',
        'id="roster-assessment-method"',
        'id="roster-assessment-no-data-group"',
        'id="roster-assessment-preview"',
        'id="roster-assessment-apply"',
    ):
        assert marker in template
    assert '/api/roster/assessment-groups/preview' in script
    assert '/api/roster/bulk' in script
    assert 'action: "set_canvas_group"' in script
