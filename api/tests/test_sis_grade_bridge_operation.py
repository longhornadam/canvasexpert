"""Laws and one end-to-end example for the SIS grade-bridge ledger adapter."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest

from api import course_catalog, sis_grade_bridge
from api.operation_ledger import executor, operations, paths, receipts
from api.operation_ledger.adapters.sis_grade_bridge import (
    KIND,
    SisGradeBridgeAdapter,
    _grade_request,
)
from api.platform_services import canvas_client, config
from api.webui import mirror_service


class FakeCanvas:
    def __init__(self):
        due = "2026-10-01T23:59:00Z"
        common = {
            "course_id": "course-1",
            "published": True,
            "grading_type": "points",
            "only_visible_to_overrides": True,
            "points_possible": 10,
            "assignment_group_id": "group-1",
            "due_at": due,
            "omit_from_final_grade": False,
            "post_to_sis": True,
        }
        self.assignments = {
            "source-a": {**common, "id": "source-a", "name": "Synthetic Family - Alpha"},
            "source-b": {**common, "id": "source-b", "name": "Synthetic Family - Beta"},
        }
        self.overrides = {
            "source-a": [{"id": "oa", "student_ids": ["student-1", "student-2"], "due_at": due}],
            "source-b": [{"id": "ob", "student_ids": ["student-3"], "due_at": due}],
        }
        self.users = [{"id": f"student-{index}"} for index in range(1, 5)]
        self.submissions = {
            "source-a": {
                "student-1": {"user_id": "student-1", "workflow_state": "graded", "score": 8},
                "student-2": {"user_id": "student-2", "workflow_state": "pending_review", "score": 7},
            },
            "source-b": {
                "student-3": {"user_id": "student-3", "workflow_state": "graded", "score": 9},
            },
        }
        self.bridge_submissions = {}
        self.groups = {}
        self.group_categories = {}
        self.group_members = {}
        self.incomplete_group_memberships = set()
        self.get_all_calls = []
        self.send_calls = []
        self.uncertain_on = None
        self.reject_grades = False
        self.reject_passback_once = False

    def get_all(self, path, params=None):
        self.get_all_calls.append((path, copy.deepcopy(params)))
        if path.endswith("/assignments"):
            rows = list(self.assignments.values())
        elif path.startswith("/api/v1/groups/") and path.endswith("/users"):
            group_id = path.split("/groups/", 1)[1].split("/", 1)[0]
            rows = self.group_members.get(group_id, [])
            if group_id in self.incomplete_group_memberships:
                return copy.deepcopy(rows), "pagination_incomplete", False
        elif path.endswith("/users"):
            rows = self.users
        elif path.endswith("/overrides"):
            assignment_id = path.split("/assignments/", 1)[1].split("/", 1)[0]
            rows = self.overrides.get(assignment_id, [])
        elif path.endswith("/submissions"):
            assignment_id = path.split("/assignments/", 1)[1].split("/", 1)[0]
            rows = list(self.submissions.get(assignment_id, {}).values())
        else:
            raise AssertionError(f"unexpected collection read: {path}")
        return copy.deepcopy(rows), None, True

    def get(self, path, params=None, timeout=20):
        if path.startswith("/api/v1/group_categories/"):
            category_id = path.rsplit("/", 1)[1]
            row = self.group_categories.get(category_id)
            return (copy.deepcopy(row), None) if row else (None, "HTTP 404")
        if path.startswith("/api/v1/groups/"):
            group_id = path.rsplit("/", 1)[1]
            row = self.groups.get(group_id)
            return (copy.deepcopy(row), None) if row else (None, "HTTP 404")
        if "/submissions/" in path:
            user_id = path.rsplit("/", 1)[1]
            row = self.bridge_submissions.get(user_id, {
                "user_id": user_id, "workflow_state": "unsubmitted",
                "score": None, "excused": False,
            })
            return copy.deepcopy(row), None
        if "/assignments/" in path:
            assignment_id = path.rsplit("/", 1)[1]
            row = self.assignments.get(assignment_id)
            return (copy.deepcopy(row), None) if row else (None, "HTTP 404")
        raise AssertionError(f"unexpected object read: {path}")

    def send(self, method, path, payload, timeout=30):
        self.send_calls.append((method, path, copy.deepcopy(payload)))
        if method == "POST" and path.endswith("/assignments"):
            if self.uncertain_on == "create":
                return None, "connection timed out"
            row = copy.deepcopy(payload["assignment"])
            row.update({
                "id": "9001", "course_id": "course-1",
                "html_url": "https://canvas.invalid/9001",
            })
            self.assignments["9001"] = row
            self.overrides["9001"] = []
            return {"id": "9001", "html_url": row["html_url"]}, None
        if method == "PUT" and "/submissions/" in path:
            bridge_id = path.split("/assignments/", 1)[1].split("/", 1)[0]
            if not self.assignments[bridge_id]["published"]:
                return None, "HTTP 403: user not authorized"
            if self.reject_grades:
                return None, "HTTP 403: grade rejected"
            user_id = path.rsplit("/", 1)[1]
            request = payload["submission"]
            row = {"user_id": user_id, "workflow_state": "graded", "excused": False}
            if request.get("excuse"):
                row.update({"excused": True, "score": None})
            else:
                row["score"] = request.get("posted_grade")
            if request.get("late_policy_status"):
                row["late_policy_status"] = request["late_policy_status"]
            self.bridge_submissions[user_id] = row
            return copy.deepcopy(row), None
        if method == "PUT" and "/assignments/" in path:
            assignment_id = path.rsplit("/", 1)[1]
            self.assignments[assignment_id].update(copy.deepcopy(payload["assignment"]))
            return copy.deepcopy(self.assignments[assignment_id]), None
        if method == "POST" and path.endswith("/post_grades"):
            if self.reject_passback_once:
                self.reject_passback_once = False
                return None, 'HTTP 400: {"error":"Missing parameters"}'
            if self.uncertain_on == "passback":
                return None, "connection timed out"
            return {"accepted": True}, None
        raise AssertionError(f"unexpected mutation: {method} {path}")


@pytest.fixture
def bridge_harness(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    monkeypatch.setattr(config, "active_courses", lambda: [
        {"id": "course-1", "name": "Synthetic Course", "active": True}
    ])
    registrations = {}

    def get_registration(course_id, title):
        return copy.deepcopy(registrations.get((str(course_id), str(title))))

    def list_registrations(course_id):
        return [
            copy.deepcopy(value) for (saved_course, _title), value in registrations.items()
            if saved_course == str(course_id)
        ]

    def save_registration(course_id, registration):
        registrations[(str(course_id), registration["family_title"])] = copy.deepcopy(registration)
        return copy.deepcopy(registration)

    monkeypatch.setattr(config, "get_sis_grade_bridge", get_registration)
    monkeypatch.setattr(config, "list_sis_grade_bridges", list_registrations)
    monkeypatch.setattr(config, "save_sis_grade_bridge", save_registration)
    fake = FakeCanvas()
    monkeypatch.setattr(canvas_client, "canvas_get_all_complete", fake.get_all)
    monkeypatch.setattr(canvas_client, "canvas_get", fake.get)
    monkeypatch.setattr(canvas_client, "_canvas_send", fake.send)
    catalog_calls = []
    refresh_calls = []
    monkeypatch.setattr(
        course_catalog, "invalidate_scope",
        lambda course_id, scope, **_kwargs: catalog_calls.append((course_id, scope)),
    )
    monkeypatch.setattr(
        mirror_service, "notify_course_changed",
        lambda course_id, **_kwargs: refresh_calls.append(course_id),
    )
    return fake, registrations, catalog_calls, refresh_calls


def _preview():
    return sis_grade_bridge.preview_sis_grade_bridge(
        "course-1", "Synthetic Family"
    )


def _use_differentiation_tags(fake):
    fake.overrides = {
        "source-a": [{"id": "oa", "group_id": "tag-a", "due_at": fake.assignments["source-a"]["due_at"]}],
        "source-b": [{"id": "ob", "group_id": "tag-b", "due_at": fake.assignments["source-b"]["due_at"]}],
    }
    fake.groups = {
        "tag-a": {
            "id": "tag-a", "course_id": "course-1",
            "group_category_id": "category-a", "non_collaborative": True,
        },
        "tag-b": {
            "id": "tag-b", "course_id": "course-1",
            "group_category_id": "category-b", "non_collaborative": True,
        },
    }
    fake.group_categories = {
        "category-a": {"id": "category-a", "course_id": "course-1"},
        "category-b": {"id": "category-b", "course_id": "course-1"},
    }
    fake.group_members = {
        "tag-a": [{"id": "student-1"}, {"id": "student-2"}],
        "tag-b": [{"id": "student-3"}],
    }


def test_grade_transport_uses_canvas_string_and_excused_payloads():
    assert _grade_request({"score": 8.5, "excused": False}) == {
        "posted_grade": "8.5"
    }
    assert _grade_request({"score": None, "excused": True}) == {
        "excuse": True
    }


def test_bridge_end_to_end_example_creates_copies_cuts_over_and_reconciles(
    bridge_harness,
):
    fake, registrations, catalog_calls, refresh_calls = bridge_harness

    preview = _preview()
    assert preview["ok"] is True
    assert preview["preview"]["source_count"] == 2
    assert preview["preview"]["counts"] == {
        "active_students": 4,
        "assigned_active": 3,
        "uncovered_active": 1,
        "overlapping_active": 0,
        "inactive_assignees": 0,
        "eligible_final": 2,
        "eligible_numeric": 2,
        "eligible_excused": 0,
        "pending_review": 1,
        "unsubmitted": 0,
        "skipped_other": 0,
    }

    result = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )

    assert result["ok"] is True
    assert result["status"] == "applied"
    assert result["passback"] == "accepted"
    assert set(fake.bridge_submissions) == {"student-1", "student-3"}
    assert "student-2" not in fake.bridge_submissions
    grade_calls = [call for call in fake.send_calls if "/submissions/" in call[1]]
    assert all(
        isinstance(call[2]["submission"]["posted_grade"], str)
        for call in grade_calls
    )
    assert all(not row["post_to_sis"] and row["omit_from_final_grade"]
               for key, row in fake.assignments.items() if key.startswith("source-"))
    bridge = fake.assignments["9001"]
    assert bridge["description"] == (
        "<p><strong>This is not your quiz.</strong> This assignment is only used "
        "to sync your grade. Open your Canvas Dashboard or To Do list and complete "
        "the version whose title includes your color tag (Red, Blue, or Silver).</p>"
    )
    assert bridge["published"] is True
    assert bridge["omit_from_final_grade"] is False
    assert bridge["post_to_sis"] is True
    assert bridge["only_visible_to_overrides"] is False
    assert fake.overrides["9001"] == []
    assert registrations[("course-1", "Synthetic Family")]["bridge_assignment_id"] == "9001"
    assert refresh_calls == ["course-1"]
    assert catalog_calls == [("course-1", "assignments")]
    passback = [call for call in fake.send_calls if call[1].endswith("/post_grades")]
    assert passback == [(
        "POST", "/api/v1/courses/course-1/post_grades",
        {"assignments": [9001]},
    )]
    assert result["receipt_id"]
    assert len(receipts.list_receipts()) == 1

    stored = operations.get_operation(preview["operation_id"])
    mutation_steps = [
        step for step in stored["targets"][0]["steps"]
        if step["step_key"] != "register_bridge"
    ]
    assert all(step.get("outbound_started_at") for step in mutation_steps)
    assert [step["step_key"] for step in stored["targets"][0]["steps"]] == [
        "create_bridge", "publish_bridge", "copy_grade:0", "copy_grade:1",
        "exclude_source:0", "exclude_source:1", "activate_bridge",
        "post_grades", "register_bridge",
    ]
    create_index = next(
        index for index, call in enumerate(fake.send_calls)
        if call[0] == "POST" and call[1].endswith("/assignments")
    )
    publish_index = next(
        index for index, call in enumerate(fake.send_calls)
        if call[0] == "PUT" and call[1].endswith("/assignments/9001")
    )
    first_grade_index = next(
        index for index, call in enumerate(fake.send_calls)
        if "/submissions/" in call[1]
    )
    assert create_index < publish_index < first_grade_index
    adapter = SisGradeBridgeAdapter()
    reconciled = adapter.reconcile(
        stored["normalized_payload"], stored["targets"][0],
        stored["targets"][0]["baseline"],
    )
    assert reconciled["state"] == "applied"


def test_differentiation_tag_contract_resolves_complete_membership_and_copies_grades(
    bridge_harness,
):
    fake, registrations, _catalog, _refresh = bridge_harness
    _use_differentiation_tags(fake)

    preview = _preview()
    result = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )

    assert preview["ok"] is True
    assert preview["preview"]["source_targeting_kind"] == "differentiation_tag"
    assert preview["preview"]["counts"]["assigned_active"] == 3
    assert result["status"] == "applied"
    assert set(fake.bridge_submissions) == {"student-1", "student-3"}
    membership_reads = [
        (path, params) for path, params in fake.get_all_calls
        if path.startswith("/api/v1/groups/") and path.endswith("/users")
    ]
    assert {params["per_page"] for _path, params in membership_reads} == {100}
    assert len(membership_reads) >= 4
    stored = operations.get_operation(preview["operation_id"])
    baseline = stored["targets"][0]["baseline"]
    assert baseline["source_targeting_kind"] == "differentiation_tag"
    assert [
        row["kind"] for row in baseline["source_target_evidence"]
    ] == ["differentiation_tag", "differentiation_tag"]
    assert baseline["validation_digest"]
    assert "tag-a" not in str(preview)
    assert "tag-b" not in str(preview)
    assert "category-a" not in str(preview)
    assert "student-1" not in str(preview)
    assert "tag-a" not in str(result)
    assert "category-a" not in str(result)
    assert "student-1" not in str(result)
    assert "tag-a" not in str(registrations)
    assert "category-a" not in str(registrations)
    assert "student-1" not in str(registrations)


@pytest.mark.parametrize(
    ("violation", "expected_error"),
    [
        ("collaborative_group", "collaborative_group_not_allowed"),
        ("group_assignment", "group_assignment_not_allowed"),
        ("group_course_mismatch", "tag_group_course_mismatch"),
        ("category_course_mismatch", "tag_category_course_mismatch"),
        ("section_override", "section_override_not_allowed"),
        ("mixed_family_targeting", "mixed_family_targeting"),
        ("incomplete_membership", "tag_membership_incomplete"),
        ("active_overlap", "overlapping_active_memberships"),
    ],
)
def test_differentiation_tag_laws_refuse_unsafe_targeting_before_mutation(
    bridge_harness, violation, expected_error,
):
    fake, _registrations, _catalog, _refresh = bridge_harness
    _use_differentiation_tags(fake)
    if violation == "collaborative_group":
        fake.groups["tag-a"]["non_collaborative"] = False
    elif violation == "group_assignment":
        fake.assignments["source-a"]["group_category_id"] = "category-a"
    elif violation == "group_course_mismatch":
        fake.groups["tag-a"]["course_id"] = "course-other"
    elif violation == "category_course_mismatch":
        fake.group_categories["category-a"]["course_id"] = "course-other"
    elif violation == "section_override":
        fake.overrides["source-a"] = [{
            "id": "oa", "course_section_id": "section-a",
            "due_at": fake.assignments["source-a"]["due_at"],
        }]
    elif violation == "mixed_family_targeting":
        fake.overrides["source-b"] = [{
            "id": "ob", "student_ids": ["student-3"],
            "due_at": fake.assignments["source-b"]["due_at"],
        }]
    elif violation == "incomplete_membership":
        fake.incomplete_group_memberships.add("tag-a")
    elif violation == "active_overlap":
        fake.group_members["tag-b"].append({"id": "student-1"})

    result = _preview()

    assert result == {"ok": False, "error": expected_error, "blocking": True}
    assert operations.list_operations() == []
    assert fake.send_calls == []


def test_overlap_law_refuses_before_operation_or_mutation(bridge_harness):
    fake, _registrations, _catalog, _refresh = bridge_harness
    fake.overrides["source-b"][0]["student_ids"].append("student-1")

    result = _preview()

    assert result == {
        "ok": False, "error": "overlapping_active_memberships", "blocking": True,
    }
    assert operations.list_operations() == []
    assert fake.send_calls == []


def test_common_due_date_law_refuses_mixed_effective_dates(bridge_harness):
    fake, _registrations, _catalog, _refresh = bridge_harness
    fake.overrides["source-b"][0]["due_at"] = "2026-10-02T23:59:00Z"

    result = _preview()

    assert result["ok"] is False
    assert result["error"] == "mixed_effective_due_dates"
    assert operations.list_operations() == []
    assert fake.send_calls == []


def test_pending_review_numeric_score_is_counted_and_never_copied(bridge_harness):
    fake, _registrations, _catalog, _refresh = bridge_harness

    preview = _preview()
    result = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )

    assert preview["preview"]["counts"]["pending_review"] == 1
    assert result["counts"]["eligible_final"] == 2
    assert "student-2" not in fake.bridge_submissions


def test_grade_failure_leaves_published_bridge_safe_and_sources_untouched(
    bridge_harness,
):
    fake, registrations, _catalog, _refresh = bridge_harness
    fake.reject_grades = True
    preview = _preview()

    result = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )

    assert result["ok"] is False
    assert result["status"] == "attention"
    bridge = fake.assignments["9001"]
    assert bridge["published"] is True
    assert bridge["omit_from_final_grade"] is True
    assert bridge["post_to_sis"] is False
    assert all(
        row["omit_from_final_grade"] is False and row["post_to_sis"] is True
        for key, row in fake.assignments.items() if key.startswith("source-")
    )
    assert registrations == {}
    assert not any(call[1].endswith("/post_grades") for call in fake.send_calls)


def test_source_title_drift_refuses_before_first_mutation(bridge_harness):
    fake, _registrations, _catalog, _refresh = bridge_harness
    preview = _preview()
    fake.assignments["source-b"]["name"] = "Synthetic Family - Changed"

    result = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )

    assert result["ok"] is False
    assert result["status"] == "attention"
    assert fake.send_calls == []


def test_uncertain_create_is_never_resent(bridge_harness):
    fake, _registrations, _catalog, _refresh = bridge_harness
    fake.uncertain_on = "create"
    preview = _preview()

    first = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )
    retry = executor.retry_operation(preview["operation_id"])

    assert first["status"] == "attention"
    assert retry["status"] == "attention"
    creates = [call for call in fake.send_calls if call[0] == "POST" and call[1].endswith("/assignments")]
    assert len(creates) == 1


def test_uncertain_passback_is_never_resent(bridge_harness):
    fake, registrations, catalog_calls, _refresh = bridge_harness
    fake.uncertain_on = "passback"
    preview = _preview()

    first = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )
    retry = executor.retry_operation(preview["operation_id"])

    assert first["status"] == "attention"
    assert retry["status"] == "attention"
    passbacks = [call for call in fake.send_calls if call[1].endswith("/post_grades")]
    assert len(passbacks) == 1
    assert registrations == {}
    assert catalog_calls == []


def test_teacher_observed_passback_confirmation_never_resends_and_resumes(
    bridge_harness,
):
    fake, registrations, catalog_calls, _refresh = bridge_harness
    fake.uncertain_on = "passback"
    preview = _preview()
    first = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )
    stored = operations.get_operation(preview["operation_id"])
    post = next(
        step for step in stored["targets"][0]["steps"]
        if step["step_key"] == "post_grades"
    )
    calls_before = len([
        call for call in fake.send_calls if call[1].endswith("/post_grades")
    ])

    result = sis_grade_bridge.confirm_sis_grade_bridge_passback(
        preview["operation_id"], post["outbound_started_at"]
    )

    calls_after = len([
        call for call in fake.send_calls if call[1].endswith("/post_grades")
    ])
    assert first["status"] == "attention"
    assert result["status"] == "applied"
    assert result["passback"] == "accepted"
    assert calls_before == calls_after == 1
    assert registrations[("course-1", "Synthetic Family")][
        "bridge_assignment_id"
    ] == "9001"
    assert catalog_calls == [("course-1", "assignments")]
    confirmed = operations.get_operation(preview["operation_id"])
    confirmed_post = next(
        step for step in confirmed["targets"][0]["steps"]
        if step["step_key"] == "post_grades"
    )
    assert confirmed_post["external_evidence"] == {
        "kind": "teacher_observed_canvas_grade_sync_last_sync",
        "observed_last_sync_at": datetime.fromisoformat(
            post["outbound_started_at"]
        ).isoformat(),
    }
    assert "student-1" not in str(result)


def test_passback_confirmation_refuses_old_or_invalid_evidence_without_mutation(
    bridge_harness,
):
    fake, _registrations, _catalog, _refresh = bridge_harness
    fake.uncertain_on = "passback"
    preview = _preview()
    sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )
    stored = operations.get_operation(preview["operation_id"])
    post = next(
        step for step in stored["targets"][0]["steps"]
        if step["step_key"] == "post_grades"
    )
    older = (
        datetime.fromisoformat(post["outbound_started_at"]) - timedelta(seconds=1)
    ).isoformat()

    missing_result = sis_grade_bridge.confirm_sis_grade_bridge_passback(
        preview["operation_id"], ""
    )
    assert "required" in missing_result["error"]
    assert operations.get_operation(preview["operation_id"]) == stored

    old_result = sis_grade_bridge.confirm_sis_grade_bridge_passback(
        preview["operation_id"], older
    )
    assert "predates" in old_result["error"]
    assert operations.get_operation(preview["operation_id"]) == stored

    invalid_result = sis_grade_bridge.confirm_sis_grade_bridge_passback(
        preview["operation_id"], "2030-01-02T03:04:05"
    )
    assert "timezone-aware" in invalid_result["error"]
    assert operations.get_operation(preview["operation_id"]) == stored

    def add_other_incomplete(candidate):
        other = next(
            step for step in candidate["targets"][0]["steps"]
            if step["step_key"] == "copy_grade:0"
        )
        other["state"] = "pending"
        return candidate

    operations.update_operation(preview["operation_id"], add_other_incomplete)
    structurally_inapplicable = operations.get_operation(preview["operation_id"])
    structural_result = sis_grade_bridge.confirm_sis_grade_bridge_passback(
        preview["operation_id"], post["outbound_started_at"]
    )
    assert "sole incomplete" in structural_result["error"]
    assert (
        operations.get_operation(preview["operation_id"])
        == structurally_inapplicable
    )


def test_definite_passback_retry_repairs_only_previous_bridge_description(
    bridge_harness,
):
    fake, registrations, _catalog, _refresh = bridge_harness
    fake.reject_passback_once = True
    preview = _preview()

    first = sis_grade_bridge.apply_sis_grade_bridge(
        preview["operation_id"], preview["batch_id"], preview["review_digest"]
    )
    fake.assignments["9001"]["description"] = (
        "<p>No submission is required here. Your grade is copied from the "
        "version of this assignment that was assigned to you.</p>"
    )
    retry = executor.retry_operation(preview["operation_id"])

    assert first["status"] == "attention"
    assert retry["status"] == "applied"
    assert registrations[("course-1", "Synthetic Family")][
        "bridge_assignment_id"
    ] == "9001"
    description_writes = [
        call for call in fake.send_calls
        if call[2] == {"assignment": {"description": (
            "<p><strong>This is not your quiz.</strong> This assignment is only "
            "used to sync your grade. Open your Canvas Dashboard or To Do list "
            "and complete the version whose title includes your color tag "
            "(Red, Blue, or Silver).</p>"
        )}}
    ]
    assert len(description_writes) == 1
    creates = [
        call for call in fake.send_calls
        if call[0] == "POST" and call[1].endswith("/assignments")
    ]
    assert len(creates) == 1


def test_adapter_kind_is_registered():
    from api.operation_ledger import registry

    assert registry.get_adapter(KIND).kind == KIND
