import pytest
from fastapi.testclient import TestClient

from api.dataforge import paths as dataforge_paths
from api.dataforge import views
from api.webui import server
from api.webui.routes import assessments


def _client():
    return TestClient(server.app, base_url="http://127.0.0.1:8765")


def _configure(monkeypatch, tmp_path):
    root = tmp_path / "CanvasExpert"
    paths = dataforge_paths.Paths(
        data_dir=root / "Student Work" / "DataForge",
        input_dir=root / "Student Work" / "DataForge" / "input",
        output_dir=root / "Student Work" / "Reports" / "DataForge",
        upload_dir=tmp_path / "uploads",
        history_dir=root / "_System" / "DataForge" / "history",
        anon_map=root / "_System" / "DataForge" / "anonymize_map.csv",
    )

    def get_paths(ensure=True):
        return paths.ensure() if ensure else paths

    monkeypatch.setattr(dataforge_paths, "get_paths", get_paths)
    monkeypatch.setattr(server.config, "token_is_set", lambda: True)
    monkeypatch.setattr(server.config, "get_canvas_base", lambda: "https://canvas.example.test")
    return paths


def test_assessments_index_renders_native_shell_and_populated_context(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.views,
        "index",
        lambda: views.Render(
            "index.html",
            existing=["synthetic-assessment.xlsx"],
            data_dir="Student Work/DataForge",
            anon_exists=True,
        ),
    )

    response = _client().get("/assessments")

    assert response.status_code == 200
    assert 'data-ce-layout="workspace"' in response.text
    assert "<h1>Assessments</h1>" in response.text
    assert "synthetic-assessment.xlsx" in response.text
    assert 'href="/assessments"' in response.text
    assert 'aria-current="page"' in response.text
    assert "/static/pages/assessments.css" in response.text


def test_pseudonymize_checkbox_defaults_checked(monkeypatch, tmp_path):
    """A7: an un-anonymized run silently disables assessment history and
    the standards profile, so the default must produce one, not opt in."""
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.views,
        "index",
        lambda: views.Render("index.html", existing=[], data_dir="", anon_exists=False),
    )

    response = _client().get("/assessments")

    assert 'name="anonymize" value="true" checked' in response.text


def test_results_page_explains_an_unanonymized_run(monkeypatch, tmp_path):
    """A7: when a run keeps real names, the results page must say plainly
    that no history was saved and no profile was published, and why."""
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.views,
        "results",
        lambda run_id: views.Render(
            "results.html",
            run_id=run_id,
            results=[{
                "descriptive": "Synthetic Assessment", "source_name": "synthetic.xlsx",
                "total_students": 10, "avg_pct": 80,
                "json_path": "a.json", "txt_path": "a.txt", "parent_path": "a_parents.txt",
            }],
            errors=[],
            anonymized=False,
        ),
    )

    response = _client().get("/assessments/results/run-1")

    assert response.status_code == 200
    assert "No history was saved and no standards profile was published" in response.text
    assert "kept real names" in response.text


def test_results_page_says_nothing_extra_when_anonymized(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.views,
        "results",
        lambda run_id: views.Render(
            "results.html", run_id=run_id, results=[], errors=[], anonymized=True,
        ),
    )

    response = _client().get("/assessments/results/run-1")

    assert response.status_code == 200
    assert "No history was saved" not in response.text


@pytest.mark.parametrize(
    ("url", "view_name", "result", "marker"),
    [
        ("/assessments/results/run-1", "results", views.Render("results.html", run_id="run-1", results=[], errors=[], anonymized=True), "Assessment results"),
        ("/assessments/dashboard/run-1", "dashboard", views.Render("dashboard.html", run_id="run-1", dash={}, anonymized=True), "Assessment dashboard"),
        ("/assessments/history", "history", views.Render("history.html", snapshots=[]), "Assessment history"),
    ],
)
def test_assessment_view_results_map_to_ce_templates(monkeypatch, tmp_path, url, view_name, result, marker):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(assessments.views, view_name, lambda *args: result)

    response = _client().get(url)

    assert response.status_code == 200
    assert f"<h1>{marker}</h1>" in response.text
    assert 'data-ce-layout="workspace"' in response.text
    assert "<main" in response.text


def test_assessments_upload_stages_only_safe_supported_files(monkeypatch, tmp_path):
    paths = _configure(monkeypatch, tmp_path)
    captured = {}

    def fake_process(anonymize, use_existing, upload_paths):
        captured.update(anonymize=anonymize, use_existing=use_existing, upload_paths=list(upload_paths))
        return views.Redirect("index")

    monkeypatch.setattr(assessments.views, "process", fake_process)
    response = _client().post(
        "/assessments/process",
        data={"anonymize": "true", "use_existing": "true"},
        files=[
            ("files", ("../../synthetic-assessment.xlsx", b"xlsx", "application/octet-stream")),
            ("files", ("ignored.txt", b"not an assessment", "text/plain")),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/assessments")
    assert captured["anonymize"] is True
    assert captured["use_existing"] is True
    assert captured["upload_paths"] == [paths.upload_dir / "synthetic-assessment.xlsx"]
    assert (paths.upload_dir / "synthetic-assessment.xlsx").read_bytes() == b"xlsx"


def test_assessment_downloads_and_not_found_are_safe(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.views,
        "export_standards_profile",
        lambda: views.BytesDownload(b'{"ok": true}', "application/json", "synthetic_profile.json"),
    )
    exported = _client().get("/assessments/export/standards-profile")
    assert exported.status_code == 200
    assert exported.content == b'{"ok": true}'
    assert "synthetic_profile.json" in exported.headers["content-disposition"]

    output_file = tmp_path / "synthetic-report.txt"
    output_file.write_bytes(b"synthetic report")
    monkeypatch.setattr(
        assessments.views,
        "download",
        lambda name: views.FileDownload(output_file, "synthetic-report.txt"),
    )
    single = _client().get("/assessments/download/synthetic-report.txt")
    assert single.status_code == 200
    assert single.content == b"synthetic report"
    assert "synthetic-report.txt" in single.headers["content-disposition"]

    monkeypatch.setattr(
        assessments.views,
        "download_all",
        lambda run_id: views.BytesDownload(b"synthetic zip", "application/zip", "synthetic-results.zip"),
    )
    archive = _client().get("/assessments/download-all/run-1")
    assert archive.status_code == 200
    assert archive.content == b"synthetic zip"
    assert "synthetic-results.zip" in archive.headers["content-disposition"]

    def missing(name):
        raise views.NotFound(name)

    monkeypatch.setattr(assessments.views, "download", missing)
    missing_response = _client().get("/assessments/download/does-not-exist.txt")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Assessment artifact not found"
    assert "does-not-exist" not in missing_response.text


def test_assessment_redirects_resolve_inside_the_assessments_surface(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(assessments.views, "process", lambda *args: views.Redirect("results", run_id="run-1"))
    process_response = _client().post("/assessments/process", follow_redirects=False)
    assert process_response.status_code == 303
    assert process_response.headers["location"].endswith("/assessments/results/run-1")

    monkeypatch.setattr(assessments.views, "history_update", lambda *args: views.Redirect("history"))
    history_response = _client().post(
        "/assessments/history/update",
        data={"snap_id": "snapshot-1", "new_date": "2026-08-02"},
        follow_redirects=False,
    )
    assert history_response.status_code == 303
    assert history_response.headers["location"].endswith("/assessments/history")


def test_assessment_coverage_renders_join_report_from_the_local_mirror_only(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        assessments.config,
        "active_courses",
        lambda: [{"id": "course-1", "name": "Synthetic Course", "nickname": "Synthetic"}],
    )
    mirror_document = {
        "state": "current",
        "last_success_at": "2026-08-02T12:00:00Z",
        "students": {"canvas-1": {"id": "canvas-1", "name": "Synthetic One", "sis_user_id": "SIS-1"}},
    }
    calls = []

    def read_roster(course_id):
        calls.append(course_id)
        return mirror_document

    monkeypatch.setattr(assessments.mirror_store, "read_roster", read_roster)
    monkeypatch.setattr(
        assessments.views,
        "coverage",
        lambda course_id, roster: views.Render(
            "coverage.html",
            course_id=course_id,
            mirror_state=roster["state"],
            mirror_last_success_at=roster["last_success_at"],
            report={
                "matched_count": 1,
                "profile_student_count": 1,
                "roster_student_count": 1,
                "coverage_percent": 100.0,
                "roster_only_count": 0,
                "rows": [{
                    "pseudonym": "Student_001", "local_id": "SIS-1",
                    "canvas_name": "Synthetic One", "canvas_id": "canvas-1", "status": "matched",
                    "roster_names": [],
                }],
            },
        ),
    )

    response = _client().get("/assessments/coverage?course_id=course-1")

    assert response.status_code == 200
    assert calls == ["course-1"]
    assert "Assessment coverage" in response.text
    assert "Synthetic One" in response.text
    assert "100.0%" in response.text
    assert 'option value="course-1" selected' in response.text
    assert "not ready for grouping" not in response.text


def test_assessment_coverage_shows_unavailable_mirror_without_live_fallback(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(assessments.config, "active_courses", lambda: [{"id": "course-1", "name": "Synthetic"}])
    monkeypatch.setattr(assessments.mirror_store, "read_roster", lambda course_id: None)
    monkeypatch.setattr(
        assessments.views,
        "coverage",
        lambda course_id, roster: views.Render(
            "coverage.html",
            course_id=course_id,
            mirror_state="unavailable",
            mirror_last_success_at="",
            report=None,
        ),
    )

    response = _client().get("/assessments/coverage?course_id=course-1")

    assert response.status_code == 200
    assert "No local roster mirror is available" in response.text
    assert "refreshes Canvas by itself" in response.text


def test_assessments_is_available_before_canvas_configuration(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(server.config, "token_is_set", lambda: False)
    monkeypatch.setattr(server.config, "get_canvas_base", lambda: "")
    monkeypatch.setattr(assessments.views, "index", lambda: views.Render("index.html", existing=[], data_dir="", anon_exists=False))

    response = _client().get("/assessments", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers.get("location") is None
