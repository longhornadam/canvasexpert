"""Contract tests for the local-only typed Canvas read spine."""

from __future__ import annotations

import pytest

from api.mirror import read_service, store


COURSE = "course-1"
STAMP = "2026-07-18T12:00:00Z"


def _populate(root):
    store.write_roster(COURSE, [{
        "id": "student-1", "name": "Synthetic learner", "sortable_name": "Learner, Synthetic",
        "short_name": "Synthetic", "enrollments": [],
    }], {}, root=root, attempted_at=STAMP)
    store.write_groups(COURSE, [{
        "category_id": "category-1", "category_name": "Teams", "groups": [{
            "id": "group-1", "name": "Team 1",
            "memberships": [{"id": "membership-1", "user_id": "student-1"}],
        }],
    }], root=root, attempted_at=STAMP)
    store.write_assignments(COURSE, [{
        "id": "assignment-1", "name": "Practice", "due_at": "", "points_possible": 10,
        "published": True, "submission_types": [],
    }], root=root, attempted_at=STAMP)
    store.merge_submissions(COURSE, "assignment-1", [{
        "assignment_id": "assignment-1", "user_id": "student-1",
        "workflow_state": "submitted", "submitted_at": STAMP, "score": None,
    }], root=root, attempted_at=STAMP, replace=True)
    for pass_name in ("full", "roster"):
        store.record_pass(COURSE, pass_name, ok=True, attempted_at=STAMP, root=root)


def _catalog_reader(course_id):
    scope = {"state": "current", "last_success_at": STAMP,
             "last_attempt_at": STAMP, "error_code": ""}
    return {"catalog": {
        "version": 2, "course_id": course_id, "course_name": "Synthetic course",
        "assignments": {**scope, "records": {"assignment-1": {
            "id": "assignment-1", "name": "Practice", "description_text": "",
        }}},
        "modules": {**scope, "records": [{"id": "module-1", "name": "Unit 1"}]},
        "assignment_groups": {**scope, "records": [{"id": "group-1", "name": "Work"}]},
    }, "source": "canonical", "warnings": []}


def test_private_scopes_have_exact_copied_local_envelopes(tmp_path):
    _populate(str(tmp_path))
    readers = (
        read_service.private_roster,
        read_service.private_groups,
        read_service.private_assignments,
        read_service.private_submissions,
    )
    expected_keys = {
        "course_id", "scope", "state", "capability", "source", "last_success_at",
        "last_attempt_at", "canvas_observed_at", "retry_after", "generation",
        "error_code", "records",
    }

    results = [reader(COURSE, root=str(tmp_path)) for reader in readers]

    assert {result["scope"] for result in results} == {
        read_service.PRIVATE_ROSTER, read_service.PRIVATE_GROUPS,
        read_service.PRIVATE_ASSIGNMENTS, read_service.PRIVATE_SUBMISSIONS,
    }
    assert all(set(result) == expected_keys for result in results)
    assert all(result["source"] == "mirror" and result["state"] == "current" for result in results)
    assert all(result["capability"] == "supported" for result in results)
    assert results[1]["records"][0]["groups"][0]["memberships"] == [
        {"id": "membership-1", "user_id": "student-1"},
    ]

    results[2]["records"][0]["name"] = "changed only in caller"
    stored = store.read_assignments(COURSE, root=str(tmp_path))
    assert stored["assignments"]["assignment-1"]["name"] == "Practice"


def test_age_limit_labels_last_good_private_records_stale(tmp_path):
    _populate(str(tmp_path))

    result = read_service.private_roster(
        COURSE, root=str(tmp_path), max_age_hours=1, now="2026-07-18T14:00:00Z")

    assert result["state"] == "stale"
    assert result["records"]
    assert result["source"] == "mirror"


def test_catalog_scopes_adapt_only_catalog_records_without_forbidden_fields():
    readers = (
        read_service.catalog_assignments,
        read_service.catalog_modules,
        read_service.catalog_assignment_groups,
    )

    catalog_result = _catalog_reader(COURSE)
    results = [reader(COURSE, catalog_reader=lambda _course_id: catalog_result) for reader in readers]

    assert [result["scope"] for result in results] == [
        read_service.CATALOG_ASSIGNMENTS, read_service.CATALOG_MODULES,
        read_service.CATALOG_ASSIGNMENT_GROUPS,
    ]
    assert all(result["source"] == "catalog" and result["state"] == "current" for result in results)
    assert "html_url" not in results[0]["records"][0]
    results[0]["records"][0]["name"] = "changed only in caller"
    assert catalog_result["catalog"]["assignments"]["records"]["assignment-1"]["name"] == "Practice"


def test_only_local_display_and_offline_intents_are_implemented(tmp_path):
    _populate(str(tmp_path))

    offline = read_service.read(
        read_service.PRIVATE_ROSTER, COURSE, intent=read_service.OFFLINE, root=str(tmp_path))
    assert offline["source"] == "mirror"
    with pytest.raises(ValueError, match="not local"):
        read_service.read(read_service.PRIVATE_ROSTER, COURSE,
                          intent=read_service.AUTHORITATIVE_LIVE, root=str(tmp_path))
