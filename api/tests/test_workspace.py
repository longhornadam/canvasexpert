import json
from pathlib import Path

from api.webui import config, workspace


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

    for folder in ["AI-TA", "Rubrics", "Quizzes", "Assignments", "Pages", "Exports"]:
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
    monkeypatch.setattr(config, "CONFIG_PATH", str(machine_config))
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
    monkeypatch.setattr(config, "CONFIG_PATH", str(machine_config))
    monkeypatch.setattr(workspace, "workspace_root", lambda: None)

    _write_json(machine_config, {"canvas_base": config.CANVAS_BASE_DEFAULT, "saved_courses": []})

    config.bookmark_course("777", "Biology", "Bio")

    machine_state = json.loads(machine_config.read_text(encoding="utf-8"))
    assert machine_state["saved_courses"][0]["id"] == "777"
    assert not (tmp_path / "OneDrive").exists()


def test_workspace_migration_is_idempotent(tmp_path, monkeypatch):
    machine_config = tmp_path / "config.json"
    workspace_root = tmp_path / "OneDrive" / "CanvasExpert"
    workspace_root.mkdir(parents=True)
    monkeypatch.setattr(config, "CONFIG_PATH", str(machine_config))
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
