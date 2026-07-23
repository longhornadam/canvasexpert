import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_workspace_paths_are_resolved_at_call_time(tmp_path, monkeypatch):
    from api import runtime_paths
    from api.webui import ai_ta, config, deps, workspace
    from api.webui.routes import library

    roots = {
        "current": tmp_path / "one",
    }
    for label in ("one", "two"):
        root = tmp_path / label
        (root / "Library" / "Rubrics").mkdir(parents=True)
        (root / "Library" / "AI Authoring").mkdir(parents=True)
        (root / "Library" / "Rubrics" / f"{label}-rubric.txt").write_text(
            f"{label} rubric marker\n", encoding="utf-8"
        )
        (root / "Library" / "AI Authoring" / f"{label}-ai-authoring.txt").write_text(
            f"{label} AI Authoring marker\n", encoding="utf-8"
        )

    monkeypatch.setattr(
        workspace, "workspace_root", lambda: str(roots["current"])
    )

    first_rubrics = deps.list_rubric_files()
    first_ai_ta = deps.list_ai_ta_files()
    assert any(str(tmp_path / "one") in item["path"] for item in first_rubrics)
    assert any(str(tmp_path / "one") in item["path"] for item in first_ai_ta)

    roots["current"] = tmp_path / "two"
    second_rubrics = deps.list_rubric_files()
    second_ai_ta = deps.list_ai_ta_files()
    assert any(str(tmp_path / "two") in item["path"] for item in second_rubrics)
    assert all(str(tmp_path / "one") not in item["path"] for item in second_rubrics)
    assert any(str(tmp_path / "two") in item["path"] for item in second_ai_ta)
    assert all(str(tmp_path / "one") not in item["path"] for item in second_ai_ta)

    def fake_parse(path):
        if str(tmp_path / "two" / "Library" / "Rubrics") in str(path):
            return {"title": "Workspace Two Marker"}, []
        return None, ["not a workspace sentinel"]

    monkeypatch.setattr(ai_ta.rf, "parse_file", fake_parse)
    monkeypatch.setattr(
        ai_ta.rf,
        "scoring_prompt",
        lambda data: f"rubric marker: {data['title']}",
    )
    built = ai_ta.build_library(runtime_paths.ai_ta_dir(), rubric_folders=None)
    assert (tmp_path / "two" / "Library" / "AI Authoring" / "Score with - Workspace Two Marker.txt").exists()
    assert not (tmp_path / "one" / "Library" / "AI Authoring" / "Score with - Workspace Two Marker.txt").exists()
    assert all(Path(path).is_relative_to(tmp_path / "two") for path in built)

    rebuilt = json.loads(library.api_ai_ta_rebuild().body)
    assert rebuilt["ok"] is True
    assert "Workspace Two Marker" in "\n".join(rebuilt["files"])
    assert not hasattr(config, "RUBRIC_" + "FOLDERS")

    cwd = tmp_path / "unrelated-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", "")
    repo_root = Path(__file__).resolve().parents[2]
    assert runtime_paths.app_root() == repo_root
    assert runtime_paths.mcp_entrypoint() == repo_root / "api" / "mcp_server" / "__main__.py"
    assert runtime_paths.python_executable() == Path(sys.executable).resolve()


def test_quick_fix_contract_and_version(monkeypatch, tmp_path):
    from api import __version__
    from api.webui import server, workspace

    from api.mcp_server import tools
    from api.mirror import store as mirror_store

    for module_name in (
        "api.webui.routes." + "feedback_" + "run",
        "api.webui.routes." + "feedback_" + "manual",
        "api.webui.routes." + "feedback_" + "push",
    ):
        assert importlib.util.find_spec(module_name) is None
    assert any(route.path == "/api/feedback/personas" for route in server.app.routes)

    class CountingVault:
        def __init__(self):
            self.save_calls = 0
            self.pseudonyms = {}

        def get_or_assign(self, canvas_id, *_args, **_kwargs):
            return self.pseudonyms.setdefault(str(canvas_id), "Avery Example")

        def add_nicknames(self, *_args, **_kwargs):
            return None

        def all_real_identifiers(self):
            return [], []

        def save(self):
            self.save_calls += 1

    vault = CountingVault()
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": "course-1"}])
    mirror_store.write_roster(
        "course-1", [{"id": "student-1", "name": "Synthetic Student"}], {},
        root=str(tmp_path),
    )
    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)

    result = tools.get_roster("course-1")
    assert result["ok"] is True
    assert vault.save_calls == 1

    monkeypatch.setattr(server.config, "token_is_set", lambda: True)
    monkeypatch.setattr(server.config, "get_canvas_base", lambda: "https://canvas.invalid")
    response = TestClient(server.app).get("/about")
    assert response.status_code == 200
    assert __version__ in response.text
