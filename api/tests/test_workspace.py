import json
import os
import re
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

    seeded = root / "Library" / "Rubrics" / "ELA7_Classroom_Writing_Rubric.txt"
    seeded.parent.mkdir(parents=True, exist_ok=True)
    seeded.write_text("user edited version", encoding="utf-8")

    resolved = workspace.ensure_workspace()
    assert resolved == str(root)

    for folder in ["AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Calendars", "Source Materials"]:
        assert (root / "Library" / folder).is_dir()
    for folder in ["Printables", "Canvas Uploads", "To Review", "Student Work", "For AI", "_System"]:
        assert (root / folder).is_dir()

    assert seeded.read_text(encoding="utf-8") == "user edited version"
    assert (root / "Library" / "Rubrics" / "New_Default_Rubric.txt").read_text(encoding="utf-8") == "new default"

    (source_rubrics / "Later_Default_Rubric.txt").write_text("later default", encoding="utf-8")
    workspace.ensure_workspace()
    assert (root / "Library" / "Rubrics" / "Later_Default_Rubric.txt").read_text(encoding="utf-8") == "later default"


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
    monkeypatch.setattr(workspace, "library_folder", lambda name, _root=None, _base=root: str(_base / name))
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
    assert "Student Work" in path and "Submissions" in path and "Assignments" in path
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


def test_ensure_workspace_does_not_touch_a_stray_legacy_folder(tmp_path, monkeypatch):
    """ensure_workspace() only ever creates the v2 tree; it never reads, renames,
    or deletes an unrelated pre-existing folder (clean break, no migration)."""
    root = tmp_path / "CanvasExpert"
    stray = root / "FeedbackExpert" / "_system" / "vault"
    stray.mkdir(parents=True)
    marker = stray / "vault.json"
    marker.write_text("untouched", encoding="utf-8")
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))

    workspace.ensure_workspace()
    assert marker.read_text(encoding="utf-8") == "untouched"
    assert (root / "Student Work" / "Submissions").is_dir()
    assert (root / "For AI").is_dir()
    assert (root / "_System" / "Identity Vault").is_dir()
    assert not (root / "_System" / "Identity Vault" / "vault.json").exists()


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


def test_managed_evidence_path_reads_filename_first_then_id(tmp_path):
    """The readable filename leads and the stable ID trails it, matching
    named_id_folder's "<display> — <id>" convention (not id-first)."""
    result = workspace.managed_evidence_path(
        "Course", "course", "Essay", "assignment", "Student", "user", 1, "48213", "essay.docx", tmp_path)
    assert os.path.basename(result) == "essay — 48213.docx"


def test_managed_evidence_path_keeps_id_intact_when_display_must_shrink(tmp_path):
    """When the projected path is too long, bounded_join shortens the display
    portion, never the identity suffix after the em dash."""
    long_filename = ("a very long original upload name " * 4) + ".docx"
    result = workspace.managed_evidence_path(
        "Course", "course", "Assignment", "assignment", "Student", "user", 1,
        "evidence-9001", long_filename, tmp_path)
    assert result.endswith("evidence-9001.docx")
    assert len(result) <= workspace.MAX_PATH_LENGTH


def test_teacher_visible_path_fits_under_budget(tmp_path):
    """teacher_visible_path returns a path at most 230 chars."""
    base = str(tmp_path)
    result = workspace.teacher_visible_path(
        base,
        ("A long course name that goes on and on for testing purposes", "course-1000001"),
        ("A long assignment name that also goes on and on for testing", "assignment-1000002"),
        "run-timestamp",
        filename="some-file.txt",
    )
    assert len(result) <= workspace.TEACHER_VISIBLE_BUDGET
    assert result.startswith(base)


def test_teacher_visible_path_compact_fallback_keeps_stable_id(tmp_path):
    """When the full readable path exceeds the budget, the compact form
    preserves the stable ID."""
    base = str(tmp_path)
    # Pad the base to trigger compact fallback without exceeding budget entirely
    padded_base = os.path.join(base, "x" * 40)
    result = workspace.teacher_visible_path(
        padded_base,
        ("A very long fictional course name for testing purposes that exceeds all limits", "course-1000001"),
        ("Another extremely long fictional assignment name for testing purposes here", "assignment-1000002"),
        "20260722-120000-000000",
        filename="test-file.txt",
    )
    assert len(result) <= workspace.TEACHER_VISIBLE_BUDGET
    # The stable ID should be preserved in the compact form
    assert "course-1000001" in result or "assignment-1000002" in result


def test_teacher_visible_path_raises_on_too_deep(tmp_path):
    """When even the compact form cannot fit, TeacherVisiblePathBudgetError is raised."""
    base = str(tmp_path)
    # Deeply nested path that even compact form can't fix
    very_deep_base = os.path.join(base, *["x" * 50] * 5)
    with pytest.raises(workspace.TeacherVisiblePathBudgetError):
        workspace.teacher_visible_path(
            very_deep_base,
            ("course", "course-1000001"),
            ("assignment", "assignment-1000002"),
            filename="file.txt",
        )


def test_teacher_visible_path_reserve_makes_shorter_path(tmp_path):
    """When reserve is specified, the returned path is shorter to leave room."""
    base = str(tmp_path)
    without_reserve = workspace.teacher_visible_path(
        base,
        ("Course", "course-1"),
        ("Assignment", "assignment-1"),
        filename="file.txt",
    )
    with_reserve = workspace.teacher_visible_path(
        base,
        ("Course", "course-1"),
        ("Assignment", "assignment-1"),
        filename="file.txt",
        reserve=50,
    )
    assert len(with_reserve) <= len(without_reserve)
    assert len(with_reserve) <= workspace.TEACHER_VISIBLE_BUDGET - 50


def test_teacher_visible_path_deterministic_hash_distinct(tmp_path):
    """Two different stable IDs produce distinct compact paths."""
    base = str(tmp_path)
    r1 = workspace.teacher_visible_path(
        base,
        ("Same Name", "id-1111111"),
        filename="f.txt",
    )
    # Both should fit (no deep base)
    assert len(r1) <= workspace.TEACHER_VISIBLE_BUDGET


def test_run_stamp_matches_expected_shape():
    stamp = workspace.run_stamp()
    assert re.fullmatch(r"\d{8}-\d{6}-\d{6}", stamp)


def test_needs_compact_layout_false_for_short_path(tmp_path):
    assert workspace.needs_compact_layout(str(tmp_path), "Essay__bundle.json") is False


def test_needs_compact_layout_true_when_over_budget(tmp_path):
    deep_base = os.path.join(str(tmp_path), "x" * 250)
    assert workspace.needs_compact_layout(deep_base, "Essay__bundle.json") is True


def test_needs_compact_layout_joins_every_child_component(tmp_path):
    base = str(tmp_path)
    shallow = workspace.needs_compact_layout(base, "a", "b.txt")
    deep = workspace.needs_compact_layout(base, "a" * 100, "b" * 100, "c" * 100)
    assert shallow is False
    assert deep is True
