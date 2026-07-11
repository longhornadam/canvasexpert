import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.webui.local_request_guard import csrf_token
from api.webui.server import app
from api.webui.routes import work
from api.work_registry.models import material_version, stable_fingerprint
from api.work_registry.providers import finding


def _job(origin="intentional", status="attention"):
    source = {"type": "powergrader_session", "value": "session-1"}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "job_id": "job-route-1",
        "fingerprint": stable_fingerprint("grade.powergrader", source, ["course-1"], "assignment-1"),
        "material_version": material_version({"status": status, "counts": {"total": 1, "pending": 1, "affected": 0}}),
        "origin": origin,
        "kind": "grade.powergrader",
        "status": status,
        "title": "PowerGrader work",
        "course_ids": ["course-1"],
        "focused_course_id": "course-1",
        "assignment_id": "assignment-1",
        "resumable_url": "/powergrader/session/session-1",
        "source_ref": source,
        "counts": {"total": 1, "pending": 1, "affected": 0},
        "attention_reason": "Work needs attention" if status == "attention" else "",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
    }


def _client():
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_get_work_is_local_pii_free_and_rejects_unknown_section(monkeypatch):
    job = _job()
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [job])
    monkeypatch.setattr(work.adapters, "collect_start_sources", lambda: [{"kind": "create.assignment", "title": "Assignment source", "path": "Assignments/sample.txt"}])
    response = _client().get("/api/work?section=attention")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["jobs"][0]["title"] == "PowerGrader work"
    assert "student" not in json.dumps(payload).lower()
    assert "C:\\" not in json.dumps(payload)
    assert _client().get("/api/work?section=unknown").status_code == 400


def test_mutation_guard_rejection_matrix_and_valid_same_origin(monkeypatch, tmp_path):
    job = _job()
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [job])
    monkeypatch.setattr(work.adapters, "collect_start_sources", lambda: [])
    monkeypatch.setattr(work.storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    client = _client()
    body = {"material_version": job["material_version"]}
    assert client.post("/api/work/job-route-1/ignore", json=body).status_code == 403
    assert client.post("/api/work/job-route-1/ignore", json=body, headers={"X-CanvasExpert-CSRF": "wrong"}).status_code == 403
    assert client.post("/api/work/job-route-1/ignore", json=body, headers={"X-CanvasExpert-CSRF": csrf_token(), "Host": "192.0.2.1:8765"}).status_code == 403
    assert client.post("/api/work/job-route-1/ignore", json=body, headers={"X-CanvasExpert-CSRF": csrf_token(), "Origin": "http://evil.invalid:8765"}).status_code == 403
    assert client.post("/api/work/job-route-1/ignore", json=body, headers={"X-CanvasExpert-CSRF": csrf_token(), "Origin": "not-an-origin"}).status_code == 403
    valid = client.post("/api/work/job-route-1/ignore", json=body, headers={"X-CanvasExpert-CSRF": csrf_token(), "Origin": "http://127.0.0.1:8765"})
    assert valid.status_code == 200
    assert valid.json()["job"]["status"] == "ignored"
    assert client.get("/api/work?section=attention").json()["jobs"] == []


def test_stale_and_unknown_mutations_fail_closed(monkeypatch, tmp_path):
    job = _job()
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [job])
    monkeypatch.setattr(work.adapters, "collect_start_sources", lambda: [])
    monkeypatch.setattr(work.storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    headers = {"X-CanvasExpert-CSRF": csrf_token()}
    stale = {"material_version": "stale"}
    client = _client()
    assert client.post("/api/work/job-route-1/ignore", json=stale, headers=headers).status_code == 409
    assert client.post("/api/work/missing/ignore", json={"material_version": job["material_version"]}, headers=headers).status_code == 409
    assert client.post("/api/work/job-route-1/snooze", json={"material_version": job["material_version"], "until": "not-a-date"}, headers=headers).status_code == 409
    assert not (tmp_path / "workspace" / "_system" / "workbench" / "suppressions.v1.json").exists()


def test_complete_only_intentional_and_no_canvas_calls(monkeypatch, tmp_path):
    detected = _job(origin="detected")
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [detected])
    monkeypatch.setattr(work.adapters, "collect_start_sources", lambda: [])
    monkeypatch.setattr(work.storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    headers = {"X-CanvasExpert-CSRF": csrf_token()}
    client = _client()
    response = client.post("/api/work/job-route-1/complete", json={"material_version": detected["material_version"]}, headers=headers)
    assert response.status_code == 409

    intentional = _job(origin="intentional", status="in_progress")
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [intentional])
    response = client.post("/api/work/job-route-1/complete", json={"material_version": intentional["material_version"]}, headers=headers)
    assert response.status_code == 200
    assert response.json()["job"]["status"] == "completed"
    disk = (tmp_path / "workspace" / "_system" / "workbench" / "registry.v1.json").read_text(encoding="utf-8")
    assert "student" not in disk.lower()
    assert "submission" not in disk.lower()

    refreshed = client.get("/api/work?section=all")
    assert refreshed.status_code == 200
    assert refreshed.json()["jobs"][0]["status"] == "completed"


def test_scan_is_guarded_merges_findings_and_get_stays_local(monkeypatch, tmp_path):
    discovered = finding(
        kind="grade.debt",
        course_id="course-1",
        assignment_id="assignment-1",
        counts={"total": 1, "pending": 1, "affected": 1},
        now="2026-07-11T12:00:00+00:00",
        resumable_url="/powergrader",
    )
    result = {
        "ok": True,
        "partial": False,
        "courses_scanned": 1,
        "findings": 1,
        "stale_course_ids": [],
        "error_codes": [],
        "courses": {
            "course-1": {
                "checked_at": "2026-07-11T12:00:00+00:00",
                "findings": [discovered],
                "stale": False,
                "error_code": "",
            }
        },
    }
    monkeypatch.setattr(work.storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    monkeypatch.setattr(work.discovery, "scan_active_courses", lambda: result)
    monkeypatch.setattr(work.adapters, "collect_local_jobs", lambda: [])
    monkeypatch.setattr(work.adapters, "collect_start_sources", lambda: [])
    client = _client()

    assert client.post("/api/work/scan").status_code == 403
    response = client.post(
        "/api/work/scan",
        headers={
            "X-CanvasExpert-CSRF": csrf_token(),
            "Origin": "http://127.0.0.1:8765",
        },
    )
    assert response.status_code == 200
    assert response.json()["findings"] == 1

    monkeypatch.setattr(work.discovery, "scan_active_courses", lambda: (_ for _ in ()).throw(AssertionError("GET scanned Canvas")))
    get_response = client.get("/api/work?section=attention")
    assert get_response.status_code == 200
    assert get_response.json()["jobs"][0]["kind"] == "grade.debt"
