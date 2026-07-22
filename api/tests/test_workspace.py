import json
import os
from pathlib import Path

import pytest

from api.webui import config, workspace
from api.webui.config import _io as config_io


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_onedrive_root_prefers_commercial(monkeypatch):
    monkeypatch.setenv("OneDriveCommercial", r"C:\OD-Commercial")
    monkeypatch.setenv("OneDrive", r"C:\OD-Personal")
    assert workspace.onedrive_root() == r"C:\OD-Commercial"

    monkeypatch.delenv("OneDriveCommercial", raising=False)
    assert workspace.onedrive_root() == r"C:\OD-Personal"

    monkeypatch.delenv("OneDrive", raising=False)
    assert workspace.onedrive_root() is None


def test_ensure_workspace_creates_and_seeds_rubrics(tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive"
    root = onedrive / "CanvasExpert"
    source_api = tmp_path / "api"
    source_rubrics = source_api / "default_docs" / "Rubrics"
    source_rubrics.mkdir(parents=True)
    (source_rubrics / "ELA7_Classroom_Writing_Rubric.txt").write_text("default v1", encoding="utf-8")
    (source_rubrics / "New_Default_Rubric.txt").write_text("new default", encoding="utf-8")

    monkeypatch.setenv("OneDrive", str(onedrive))
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    monkeypatch.setattr(workspace, "API_DIR", str(source_api))
    monkeypatch.setattr(workspace, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(workspace, "DEFAULT_DOCS_DIR", str(source_api / "default_docs"))

    seeded = root / "Rubrics" / "ELA7_Classroom_Writing_Rubric.txt"
    seeded.parent.mkdir(parents=True, exist_ok=True)
    seeded.write_text("user edited version", encoding="utf-8")

    resolved = workspace.ensure_workspace()
    assert resolved == str(root)

    for folder in ["AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Exports", "Source Materials"]:
        assert (root / folder).is_dir()

    assert seeded.read_text(encoding="utf-8") == "user edited version"
    assert (root / "Rubrics" / "New_Default_Rubric.txt").read_text(encoding="utf-8") == "new default"

    (source_rubrics / "Later_Default_Rubric.txt").write_text("later default", encoding="utf-8")
    workspace.ensure_workspace()
    assert (root / "Rubrics" / "Later_Default_Rubric.txt").read_text(encoding="utf-8") == "later default"


def test_config_split_writes_workspace_settings_when_available(tmp_path, monkeypatch):
    machine_config = tmp_path / "config.json"
    workspace_root = tmp_path / "OneDrive" / "CanvasExpert"
    workspace_root.mkdir(parents=True)
    monkeypatch.setattr(config_io, "CONFIG_PATH", str(machine_config))
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))

    _write_json(machine_config, {"canvas_base": config.CANVAS_BASE_DEFAULT, "saved_courses": []})

    config.bookmark_course("123", "Algebra", "Algebra 1")

    machine_state = json.loads(machine_config.read_text(encoding="utf-8"))
    workspace_state = json.loads((workspace_root / "settings.json").read_text(encoding="utf-8"))

    assert machine_state["saved_courses"] == []
    assert workspace_state["saved_courses"][0]["id"] == "123"
    assert workspace_state["saved_courses"][0]["nickname"] == "Algebra 1"


def test_config_split_stays_machine_local_without_workspace(tmp_path, monkeypatch):
    machine_config = tmp_path / "config.json"
    monkeypatch.setattr(config_io, "CONFIG_PATH", str(machine_config))
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)

    _write_json(machine_config, {"canvas_base": config.CANVAS_BASE_DEFAULT, "saved_courses": []})

    config.bookmark_course("777", "Biology", "Bio")

    machine_state = json.loads(machine_config.read_text(encoding="utf-8"))
    assert machine_state["saved_courses"][0]["id"] == "777"
    assert not (tmp_path / "OneDrive").exists()


def test_adding_a_saved_previous_course_makes_it_current(tmp_path, monkeypatch):
    machine_config = tmp_path / "config.json"
    monkeypatch.setattr(config_io, "CONFIG_PATH", str(machine_config))
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)
    _write_json(machine_config, {
        "saved_courses": [{
            "id": "777", "name": "Biology", "nickname": "Old Bio", "active": False,
        }],
    })

    config.bookmark_course("777", "Biology", "Summer Bio")

    saved = json.loads(machine_config.read_text(encoding="utf-8"))["saved_courses"]
    assert saved == [{
        "id": "777", "name": "Biology", "nickname": "Summer Bio", "active": True,
    }]


def test_personas_seed_once_then_follow_folder_changes(tmp_path, monkeypatch):
    root = tmp_path / "CanvasExpert"
    root.mkdir()
    monkeypatch.setattr(workspace, "folder", lambda name: str(root / name))
    monkeypatch.setattr(config._io, "_synced_state", lambda: {})

    first = config.list_personas()
    persona_dir = root / "AI-TA" / "Personas"
    assert any(p["id"] == "sage" for p in first)
    assert (persona_dir / "Sage.json").exists()

    (persona_dir / "Sage.json").unlink()
    second = config.list_personas()

    assert not any(p["id"] == "sage" for p in second)
    assert any(p["id"] == "coach_vale" for p in second)

    for path in persona_dir.glob("*.json"):
        path.unlink()
    assert config.list_personas() == []


def test_workspace_migration_is_idempotent(tmp_path, monkeypatch):
    machine_config = tmp_path / "config.json"
    workspace_root = tmp_path / "OneDrive" / "CanvasExpert"
    workspace_root.mkdir(parents=True)
    monkeypatch.setattr(config_io, "CONFIG_PATH", str(machine_config))
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))

    _write_json(
        machine_config,
        {
            "canvas_base": config.CANVAS_BASE_DEFAULT,
            "saved_courses": [{"id": "1", "name": "History", "nickname": "Hist", "active": True}],
            "extra_time": {"1": [{"id": "a", "name": "Ada", "days": 2}]},
            "late_sweep": {"skip_weekends": False},
            "calendars": {"custom": {"label": "Custom", "no_count_dates": ["2026-01-01"], "grading_periods": []}},
        },
    )

    first = config.saved_courses()
    settings_path = workspace_root / "settings.json"
    assert settings_path.exists()
    assert first[0]["nickname"] == "Hist"

    _write_json(
        machine_config,
        {
            "canvas_base": config.CANVAS_BASE_DEFAULT,
            "saved_courses": [{"id": "2", "name": "Math", "nickname": "Math", "active": True}],
            "extra_time": {},
            "late_sweep": {},
            "calendars": {},
        },
    )

    second = config.saved_courses()
    workspace_state = json.loads(settings_path.read_text(encoding="utf-8"))

    assert second[0]["id"] == "1"
    assert workspace_state["saved_courses"][0]["id"] == "1"
    assert workspace_state["extra_time"]["1"][0]["name"] == "Ada"


def test_canonical_course_first_paths_keep_ids_and_bound_long_names(tmp_path, monkeypatch):
    root = tmp_path / "CanvasExpert"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    path = workspace.attempt_folder(
        "A" * 400, "course/fictional", "B" * 400, "assignment/fictional",
        "C" * 400, "student/fictional", 3,
    )
    assert "Courses" in path and "Assignments" in path and "Student Work" in path
    assert "course_fictional" in path and "assignment_fictional" in path and "student_fictional" in path
    assert path.endswith("Attempt 3")
    assert len(path) <= workspace.MAX_PATH_LENGTH


def test_extended_path_leaves_short_paths_unchanged(monkeypatch):
    # Short paths keep their exact current behavior — no \\?\ prefix — so normal
    # I/O is never perturbed by the long-path workaround.
    monkeypatch.setattr(workspace.os, "name", "nt")
    short = r"C:\Users\user\OneDrive\deep\file.txt"
    assert workspace.extended_path(short) == short
    assert workspace.extended_path("") == ""


@pytest.mark.skipif(os.name != "nt", reason="\\\\?\\ prefixing is Windows-only")
def test_extended_path_prefixes_paths_near_the_limit():
    long_path = r"C:\Users\user\OneDrive" + ("\\" + "x" * 30) * 8 + r"\file.txt"
    assert len(long_path) >= workspace.MAX_PATH_LENGTH
    out = workspace.extended_path(long_path)
    assert out == "\\\\?\\" + long_path
    assert workspace.extended_path(out) == out  # idempotent


def test_extended_path_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(workspace.os, "name", "posix")
    assert workspace.extended_path("/home/user/deep/file.txt") == "/home/user/deep/file.txt"
    assert workspace.extended_path("") == ""


def test_legacy_feedback_is_read_only_and_new_roots_are_seeded(tmp_path, monkeypatch):
    root = tmp_path / "CanvasExpert"
    legacy = root / "FeedbackExpert" / "_system" / "vault"
    legacy.mkdir(parents=True)
    marker = legacy / "vault.json"
    marker.write_text("legacy", encoding="utf-8")
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))

    workspace.ensure_workspace()
    assert marker.read_text(encoding="utf-8") == "legacy"
    assert (root / "Courses").is_dir()
    assert (root / "AI Packets (Pseudonymized)").is_dir()
    assert (root / "_System" / "Identity Vault").is_dir()
    assert not (root / "_System" / "Identity Vault" / "vault.json").exists()


def test_powergrader_compatibility_reads_are_new_first_and_non_destructive(tmp_path, monkeypatch):
    from api.powergrader import autoscore_queue, session_store

    root = tmp_path / "CanvasExpert"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(session_store.workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(autoscore_queue.workspace, "workspace_root", lambda: str(root))
    legacy = root / "PowerGrader"
    legacy.mkdir(parents=True)
    old_session = legacy / "sid_session.json"
    old_session.write_text(json.dumps({"session_id": "sid", "created": "old", "students": []}), encoding="utf-8")
    old_queue = legacy / "autoscore_queue.json"
    old_queue.write_text(json.dumps({"version": 1, "jobs": [{"job_id": "old"}]}), encoding="utf-8")

    assert session_store.load_session("sid")["created"] == "old"
    assert autoscore_queue.load_queue()["jobs"][0]["job_id"] == "old"
    session_store.save_session({"session_id": "sid", "created": "new", "students": []})
    assert old_session.read_text(encoding="utf-8").find('"old"') >= 0
    assert session_store.load_session("sid")["created"] == "new"
    autoscore_queue.save_queue({"version": 1, "jobs": [{"job_id": "new"}]})
    assert old_queue.read_text(encoding="utf-8").find('"old"') >= 0
    assert autoscore_queue.load_queue()["jobs"][0]["job_id"] == "new"


def test_assignment_evidence_manifest_is_atomic_identity_checked_and_conflict_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "CanvasExpert"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    kwargs = {"course_name": "Course", "course_id": "course-1", "assignment_name": "Essay", "assignment_id": "assignment-1"}
    manifest = {"version": 1, "course_id": "course-1", "assignment_id": "assignment-1", "evidence": []}
    path = workspace.write_assignment_evidence_manifest(manifest, **kwargs)
    assert path and workspace.read_assignment_evidence_manifest(**kwargs) == manifest
    assert workspace.write_assignment_evidence_manifest({**manifest, "course_id": "wrong"}, **kwargs) is None
    conflict = Path(path).with_name("Fictional assignment_evidence_manifest conflicted copy.json")
    conflict.write_text("{}", encoding="utf-8")
    assert workspace.read_assignment_evidence_manifest(**kwargs) is None
    assert workspace.write_assignment_evidence_manifest(manifest, **kwargs) is None


def test_managed_evidence_path_uses_identity_not_filename_suffix(tmp_path):
    first = workspace.managed_evidence_path("Course", "course", "Essay", "assignment", "Student", "user", 2, "file-1", "draft.docx", tmp_path)
    second = workspace.managed_evidence_path("Course", "course", "Essay", "assignment", "Student", "user", 2, "file-2", "draft.docx", tmp_path)
    assert first != second and "file-1" in first and "file-2" in second
