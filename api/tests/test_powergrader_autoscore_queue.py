from __future__ import annotations

import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader import autoscore_queue
from api.webui import workspace


def _use_workspace(monkeypatch, root):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))


def _base_assignment(submission_types, **extra):
    assignment = {
        "name": "Essay 1",
        "submission_types": submission_types,
    }
    assignment.update(extra)
    return assignment


def test_scheduled_at_from_due_adds_six_hours_with_timezone():
    assert autoscore_queue.scheduled_at_from_due("2026-09-10T23:59:00-05:00") == "2026-09-11T05:59:00-05:00"


def test_classify_assignment_for_autoscore_covers_supported_and_unsupported_types():
    assert autoscore_queue.classify_assignment_for_autoscore(_base_assignment(["online_text_entry"])) == (
        "eligible",
        "text entry gives PowerGrader readable response text",
    )

    upload_status, upload_reason = autoscore_queue.classify_assignment_for_autoscore(
        _base_assignment(["online_upload"], allowed_extensions=["py", "txt"])
    )
    assert upload_status in {"eligible", "needs_attention"}
    assert upload_reason

    for submission_type in ["none", "on_paper", "external_tool", "media_recording", "student_annotation", "discussion_topic"]:
        status, reason = autoscore_queue.classify_assignment_for_autoscore(_base_assignment([submission_type]))
        assert status == "unsupported"
        assert reason


def test_upsert_job_is_idempotent_for_same_course_and_assignment(monkeypatch, tmp_path):
    _use_workspace(monkeypatch, tmp_path)
    first = autoscore_queue.upsert_job(
        course_id="course-1",
        course_name="Period 1",
        assignment_id="assign-1",
        assignment_name="Essay 1",
        due_at="2026-09-10T23:59:00-05:00",
        assignment=_base_assignment(["online_text_entry"]),
    )
    second = autoscore_queue.upsert_job(
        course_id="course-1",
        course_name="Period 1",
        assignment_id="assign-1",
        assignment_name="Essay 1",
        due_at="2026-09-10T23:59:00-05:00",
        assignment=_base_assignment(["online_text_entry"]),
    )

    queue = autoscore_queue.load_queue()
    assert len(queue["jobs"]) == 1
    assert first["job_id"] == second["job_id"] == "course-1_assign-1"
    assert second["created_at"] == first["created_at"]


def test_due_jobs_returns_only_scheduled_eligible_jobs_that_are_due():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "a",
                "status": "scheduled",
                "eligibility": "eligible",
                "scheduled_at": "2026-09-10T10:00:00+00:00",
            },
            {
                "job_id": "b",
                "status": "needs_attention",
                "eligibility": "eligible",
                "scheduled_at": "2026-09-10T10:00:00+00:00",
            },
            {
                "job_id": "c",
                "status": "scheduled",
                "eligibility": "unsupported",
                "scheduled_at": "2026-09-10T10:00:00+00:00",
            },
            {
                "job_id": "d",
                "status": "scheduled",
                "eligibility": "eligible",
                "scheduled_at": "2026-09-10T11:00:00+00:00",
            },
        ],
    }
    now = datetime(2026, 9, 10, 10, 30, tzinfo=timezone.utc)

    due = autoscore_queue.due_jobs(queue, now=now)

    assert [job["job_id"] for job in due] == ["a"]


def test_unclaimed_job_can_be_claimed_and_gets_lease_fields():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "scheduled",
            }
        ],
    }
    now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-a", lease_minutes=15, now=now)

    assert claimed is True
    assert job is queue["jobs"][0]
    assert job["claimed_by"] == "worker-a"
    assert job["machine_id"] == "worker-a"
    assert job["claimed_at"] == "2026-07-01T12:00:00+00:00"
    assert job["lease_until"] == "2026-07-01T12:15:00+00:00"
    assert job["updated_at"] == "2026-07-01T12:00:00+00:00"


def test_active_lease_blocks_a_different_worker():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "running",
                "claimed_by": "worker-a",
                "machine_id": "worker-a",
                "claimed_at": "2026-07-01T12:00:00+00:00",
                "lease_until": "2026-07-01T12:30:00+00:00",
            }
        ],
    }
    now = datetime(2026, 7, 1, 12, 5, tzinfo=timezone.utc)

    claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-b", now=now)

    assert claimed is False
    assert job is None
    assert queue["jobs"][0]["claimed_by"] == "worker-a"
    assert queue["jobs"][0]["lease_until"] == "2026-07-01T12:30:00+00:00"


def test_expired_lease_can_be_claimed_by_another_worker():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "running",
                "claimed_by": "worker-a",
                "machine_id": "worker-a",
                "claimed_at": "2026-07-01T11:00:00+00:00",
                "lease_until": "2026-07-01T11:30:00+00:00",
            }
        ],
    }
    now = datetime(2026, 7, 1, 12, 5, tzinfo=timezone.utc)

    claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-b", lease_minutes=20, now=now)

    assert claimed is True
    assert job["claimed_by"] == "worker-b"
    assert job["machine_id"] == "worker-b"
    assert job["claimed_at"] == "2026-07-01T12:05:00+00:00"
    assert job["lease_until"] == "2026-07-01T12:25:00+00:00"


def test_same_worker_refreshes_and_reclaims_idempotently():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "running",
            }
        ],
    }
    first = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    later = first + timedelta(minutes=10)
    latest = first + timedelta(minutes=20)

    claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-a", lease_minutes=30, now=first)
    assert claimed is True
    first_claimed_at = job["claimed_at"]
    assert first_claimed_at == "2026-07-01T12:00:00+00:00"
    assert job["lease_until"] == "2026-07-01T12:30:00+00:00"

    claimed_again, job_again = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-a", lease_minutes=30, now=later)
    assert claimed_again is True
    assert job_again["claimed_at"] == first_claimed_at
    assert job_again["lease_until"] == "2026-07-01T12:40:00+00:00"

    refreshed = autoscore_queue.refresh_lease(queue, "job-1", worker_id="worker-a", lease_minutes=30, now=latest)
    assert refreshed is True
    assert job_again["claimed_at"] == first_claimed_at
    assert job_again["lease_until"] == "2026-07-01T12:50:00+00:00"


def test_release_only_works_for_the_owning_worker():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "running",
                "claimed_by": "worker-a",
                "machine_id": "worker-a",
                "claimed_at": "2026-07-01T12:00:00+00:00",
                "lease_until": "2026-07-01T12:30:00+00:00",
            }
        ],
    }
    now = datetime(2026, 7, 1, 12, 10, tzinfo=timezone.utc)

    released_by_other = autoscore_queue.release_job(queue, "job-1", worker_id="worker-b", now=now)
    assert released_by_other is False
    assert queue["jobs"][0]["claimed_by"] == "worker-a"

    released_by_owner = autoscore_queue.release_job(queue, "job-1", worker_id="worker-a", now=now)
    assert released_by_owner is True
    assert queue["jobs"][0]["claimed_by"] == ""
    assert queue["jobs"][0]["machine_id"] == ""
    assert queue["jobs"][0]["claimed_at"] == ""
    assert queue["jobs"][0]["lease_until"] == ""


def test_terminal_status_is_not_claimable():
    for status in ["session_ready", "cancelled", "failed"]:
        queue = {
            "version": 1,
            "jobs": [
                {
                    "job_id": "job-1",
                    "status": status,
                }
            ],
        }

        claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-a")

        assert claimed is False
        assert job is None


def test_session_ready_autopush_job_is_due_and_claimable():
    queue = {
        "version": 1,
        "jobs": [
            {
                "job_id": "job-1",
                "status": "session_ready",
                "eligibility": "eligible",
                "session_id": "session-1",
                "auto_push": True,
                "push_policy": {"enabled": True},
                "scheduled_at": "2026-07-01T10:00:00+00:00",
            }
        ],
    }
    now = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)

    due = autoscore_queue.due_jobs(queue, now=now)
    claimed, job = autoscore_queue.claim_job(queue, "job-1", worker_id="worker-a", now=now)

    assert [item["job_id"] for item in due] == ["job-1"]
    assert claimed is True
    assert job["claimed_by"] == "worker-a"


def test_reconcile_due_date_reschedules_when_due_date_moves_later():
    job = {
        "job_id": "course-1_assign-1",
        "status": "scheduled",
        "eligibility": "eligible",
        "reason": "",
        "due_at": "2026-09-10T23:59:00-05:00",
        "delay_hours": 6,
        "scheduled_at": "2026-09-11T05:59:00-05:00",
    }
    latest_assignment = _base_assignment(["online_text_entry"], due_at="2026-09-11T23:59:00-05:00")

    reconciled = autoscore_queue.reconcile_due_date(copy.deepcopy(job), latest_assignment)

    assert reconciled["due_at"] == "2026-09-11T23:59:00-05:00"
    assert reconciled["scheduled_at"] == "2026-09-12T05:59:00-05:00"
    assert reconciled["status"] == "scheduled"


def test_reconcile_due_date_marks_needs_attention_when_due_is_removed():
    job = {
        "job_id": "course-1_assign-1",
        "status": "scheduled",
        "eligibility": "eligible",
        "reason": "",
        "due_at": "2026-09-10T23:59:00-05:00",
        "delay_hours": 6,
        "scheduled_at": "2026-09-11T05:59:00-05:00",
    }

    reconciled = autoscore_queue.reconcile_due_date(copy.deepcopy(job), {"name": "Essay 1", "submission_types": ["online_text_entry"], "due_at": ""})

    assert reconciled["status"] == "needs_attention"
    assert reconciled["eligibility"] == "needs_attention"
    assert reconciled["scheduled_at"] == ""
    assert reconciled["due_at"] == ""
