"""Focused route/render contracts for the slice-07 Desk surface."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.webui.server import app
from api.webui.routes import pages
from api.work_registry.models import material_version, stable_fingerprint
from api.work_registry.providers import finding


def _client():
    return TestClient(app, base_url="http://127.0.0.1:8765")


def _configure(monkeypatch):
    monkeypatch.setattr(pages.config, "token_is_set", lambda: True)
    monkeypatch.setattr(pages.config, "get_canvas_base", lambda: "https://canvas.example.test")
    monkeypatch.setattr(pages.workspace, "workspace_root", lambda: None)
    monkeypatch.setattr(pages.config, "active_courses", lambda: [
        {"id": "course-1", "name": "Course One", "nickname": "Course One", "active": True},
        {"id": "course-2", "name": "Course Two", "nickname": "Course Two", "active": True},
    ])
    monkeypatch.setattr(pages.work_routes, "_session_assignment_names", lambda: {})
    monkeypatch.setattr(pages.work_routes, "_scheduled_display_metadata", lambda: {})


def _powergrader_job():
    source = {"type": "powergrader_session", "value": "session-fictitious"}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {"total": 24, "pending": 22, "affected": 2}
    return {
        "job_id": "job-fictitious-session",
        "fingerprint": stable_fingerprint(
            "grade.powergrader", source, ["course-1"], "assignment-1"
        ),
        "material_version": material_version({"status": "attention", "counts": counts}),
        "origin": "intentional",
        "kind": "grade.powergrader",
        "status": "attention",
        "title": "PowerGrader work",
        "course_ids": ["course-1"],
        "focused_course_id": "course-1",
        "assignment_id": "assignment-1",
        "resumable_url": "/powergrader/session/session-fictitious",
        "source_ref": source,
        "counts": counts,
        "attention_reason": "Work needs attention",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
    }


def test_desk_empty_render_is_local_and_honest(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [])
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])

    response = _client().get("/")

    assert response.status_code == 200
    assert 'class="ce-desk-shell"' in response.text
    assert 'id="desk-course-field"' in response.text
    assert "No open work." in response.text
    assert "No items need review." in response.text
    assert "No prepared operations." in response.text
    assert "No receipts." in response.text
    assert "/api/operations" not in response.text
    assert 'name="canvasexpert-csrf-token"' in response.text


def test_student_reports_has_a_direct_students_page_and_old_tab_redirect(monkeypatch):
    _configure(monkeypatch)

    redirected = _client().get("/course-expert?tab=students", follow_redirects=False)
    response = _client().get("/students/reports")
    roster = _client().get("/roster")
    create = _client().get("/course-expert?tab=assignment")

    assert redirected.status_code == 307
    assert redirected.headers["location"] == "/students/reports"
    assert response.status_code == 200
    assert create.status_code == 200
    assert 'id="ce-tab-assignment"' in create.text
    for control in ("sr-course", "sr-student", "sr-generate", "nqp-file", "mp-generate"):
        assert f'id="{control}"' in response.text
    assert "/static/course_expert/student_reports.js" in response.text
    assert "/static/course_expert/portfolio.js" in response.text
    assert "/static/course_expert/student_reports.js" not in create.text
    assert "/static/course_expert/portfolio.js" not in create.text
    assert 'nav-section-manage' in response.text
    assert 'href="/students/reports"' in roster.text


def test_desk_populated_render_uses_registry_and_real_receipt_projection(monkeypatch):
    _configure(monkeypatch)
    job = finding(
        kind="grade.debt",
        course_id="course-1",
        assignment_id="assignment-1",
        counts={"total": 2, "pending": 1, "affected": 1},
        now="2026-07-11T12:00:00+00:00",
        resumable_url="/gradebook",
    )
    receipt = {
        "receipt_id": "receipt-1",
        "kind": "gradebook.sweep",
        "status": "partial",
        "target_count": 1,
        "detail_url": "/api/receipts/receipt-1",
    }
    operations = [
        {
            "operation_id": "operation-private-id",
            "kind": "content.page",
            "status": "prepared",
            "target_count": 2,
        },
        {
            "operation_id": "operation-reviewed-id",
            "kind": "content.quiz",
            "status": "reviewed",
            "target_count": 1,
        },
        {
            "operation_id": "operation-applied-id",
            "kind": "content.page",
            "status": "applied",
            "target_count": 3,
        },
    ]
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [job])
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: operations)
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [receipt])

    response = _client().get("/")

    assert response.status_code == 200
    assert "1 submission awaiting grading" in response.text
    assert "gradebook.sweep" in response.text
    assert "/api/receipts/receipt-1" in response.text
    assert "Course One" in response.text
    assert "content.page" in response.text
    assert "prepared · 2 targets" in response.text
    assert "content.quiz" in response.text
    assert "reviewed · 1 target" in response.text
    assert "operation-private-id" not in response.text
    assert "operation-reviewed-id" not in response.text
    assert "operation-applied-id" not in response.text


def test_desk_populated_powergrader_row_uses_semantic_sidecar(monkeypatch):
    _configure(monkeypatch)
    job = _powergrader_job()
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: [job])
    monkeypatch.setattr(
        pages.work_routes,
        "_session_assignment_names",
        lambda: {"session-fictitious": "Fictional Reflection"},
    )
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])

    response = _client().get("/")

    assert response.status_code == 200
    assert "Course One" in response.text
    assert "Fictional Reflection" in response.text
    assert "24 students · 22 awaiting review · 2 approved, not posted" in response.text
    assert "Review &amp; post" in response.text
    assert "grade.powergrader · 24 items" not in response.text


def test_desk_home_attention_render_is_aggregate_only(monkeypatch):
    _configure(monkeypatch)
    jobs = [
        finding(
            kind="grade.followup", course_id="course-1", assignment_id="assignment-1",
            counts={"total": 2, "pending": 2, "affected": 2},
            now="2026-07-11T12:00:00+00:00", resumable_url="/powergrader",
        ),
        finding(
            kind="grade.staff_check", course_id="course-1", assignment_id="assignment-2",
            counts={"total": 1, "pending": 1, "affected": 1},
            now="2026-07-11T12:00:00+00:00", resumable_url="/powergrader",
        ),
        finding(
            kind="grade.powergrader_ready", course_id="course-1", assignment_id="assignment-3",
            counts={"total": 3, "pending": 3, "affected": 3},
            now="2026-07-11T12:00:00+00:00", resumable_url="/powergrader",
        ),
    ]
    monkeypatch.setattr(pages.work_routes, "_section_jobs", lambda section: jobs)
    monkeypatch.setattr(pages.operation_store, "list_operations_pii_minimized", lambda: [])
    monkeypatch.setattr(pages.receipt_store, "list_receipts", lambda: [])

    response = _client().get("/")

    assert response.status_code == 200
    for text in (
        "Student follow-up", "2 responses need a human check",
        "Staff response check", "1 response needs a staff response check",
        "PowerGrader-ready", "3 ungraded text entries ready for review",
    ):
        assert text in response.text
    assert "synthetic-student" not in response.text
    assert "submission_comments" not in response.text
