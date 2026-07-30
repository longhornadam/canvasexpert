import json
import os
import runpy
import sys
import types
import zipfile
from pathlib import Path


def test_support_bundle_is_minimal_and_identifier_free(tmp_path, monkeypatch):
    from api import __version__, diagnostics, operational_log
    from api.mcp_server.contract import TOOL_SCHEMA_VERSION
    from api.webui import workspace

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(diagnostics.config, "get_canvas_base", lambda: "")
    monkeypatch.setattr(diagnostics.config, "token_is_set", lambda: False)

    operational_log.emit("diagnostics.health", "ok", duration_ms=5, count=1)
    operational_log.emit("canvas.request", "failed", status_code=503, error_class=RuntimeError)
    rejected = [
        {"event": "diagnostics.rejected", "outcome": "ok", "path": str(tmp_path)},
        {"event": "diagnostics.rejected", "outcome": "ok", "token": "secret-token-value"},
        {"event": "diagnostics.rejected", "outcome": "ok", "user": "Real User Name"},
        {"event": "diagnostics.rejected", "outcome": "ok", "course_id": "course_id-42"},
        {"event": "diagnostics.rejected", "outcome": "ok", "student_id": "student_id-7"},
        {"event": "diagnostics.rejected", "outcome": "ok", "provider": {"body": "provider-body"}},
        {"event": "diagnostics.rejected", "outcome": "ok", "exception": "RuntimeError: stack details"},
    ]
    log_path = operational_log._log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        for record in rejected:
            handle.write(json.dumps(record) + "\n")

    destination = tmp_path / "support-bundle.zip"
    result = diagnostics.build_support_bundle(destination)
    assert result == destination
    with zipfile.ZipFile(result) as archive:
        member_names = archive.namelist()
        assert member_names == ["health.json", "manifest.json", "operations.jsonl"]
        manifest = json.loads(archive.read("manifest.json"))
        health = json.loads(archive.read("health.json"))
        operations = archive.read("operations.jsonl").decode("utf-8")
        member_contents = {name: archive.read(name).decode("utf-8") for name in member_names}

    assert manifest["schema_version"] == 1
    assert manifest["app_version"] == __version__
    assert manifest["tool_schema_version"] == TOOL_SCHEMA_VERSION
    assert manifest["created_at"].endswith("Z")
    assert health == diagnostics.health_snapshot()
    assert '"event":"diagnostics.health"' in operations
    assert '"event":"canvas.request"' in operations

    forbidden = [
        str(tmp_path), "secret-token-value", "Real User Name", "course_id-42",
        "student_id-7", "provider-body", "RuntimeError: stack details",
    ]
    probe_markers = ("probe", "support-bundle.", ".support-")
    for name in member_names:
        assert not any(marker in name for marker in probe_markers)
        content = member_contents[name]
        assert not any(value in name or value in content for value in forbidden)

    assert not (workspace_root / "_System").exists()
    assert not any(path.name.startswith((".diagnostic-", ".support-", ".tmp"))
                   for path in tmp_path.iterdir())


def test_connections_page_and_mcpb_use_runtime_paths_without_client_config_writes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api import __version__, connections, diagnostics, runtime_paths
    from api.mcp_server.contract import TOOL_SCHEMA_VERSION
    from api.webui import config, workspace
    from api.webui import server

    first_app = tmp_path / "first-app"
    second_app = tmp_path / "second-app"
    first_workspace = tmp_path / "first-workspace"
    second_workspace = tmp_path / "second-workspace"
    for app_root in (first_app, second_app):
        (app_root / "api" / "mcp_server").mkdir(parents=True)
        (app_root / "api" / "mcp_server" / "server.py").write_text("", encoding="utf-8")
        (app_root / "tools").mkdir()
    current = {"app": first_app, "workspace": first_workspace}
    monkeypatch.setattr(runtime_paths, "app_root", lambda: current["app"])
    monkeypatch.setattr(runtime_paths, "python_executable", lambda: Path(sys.executable).resolve())
    monkeypatch.setattr(runtime_paths, "mcp_entrypoint", lambda: current["app"] / "api" / "mcp_server" / "__main__.py")
    monkeypatch.setattr(runtime_paths, "temp_dir", lambda: tmp_path / "server-temp")
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(current["workspace"]))
    monkeypatch.setattr(config, "get_canvas_base", lambda: "")
    monkeypatch.setattr(config, "token_is_set", lambda: False)
    monkeypatch.setenv("PATH", "")

    client_dirs = [tmp_path / name for name in ("claude", "chatgpt", "generic")]
    for path in client_dirs:
        path.mkdir()
    before = {path: sorted(item.name for item in path.iterdir()) for path in client_dirs}

    current["app"] = second_app
    current["workspace"] = second_workspace
    context = connections.connection_context()
    generic = connections.generic_stdio_config()
    package = connections.build_claude_mcpb(tmp_path / "CanvasExpert-test.mcpb")
    assert context["app_root"] == str(second_app)
    assert context["generic_stdio_config"] == generic
    assert generic == {
        "mcpServers": {
            "canvas-expert": {
                "command": str(Path(sys.executable).resolve()),
                "args": [str(second_app / "api" / "mcp_server" / "__main__.py")],
            }
        }
    }

    with zipfile.ZipFile(package) as archive:
        assert archive.namelist() == ["manifest.json", "server/launcher.py"]
        manifest = json.loads(archive.read("manifest.json"))
        launcher = archive.read("server/launcher.py").decode("utf-8")
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    assert manifest == {
        "manifest_version": "0.3",
        "name": "canvas-expert-read-only",
        "display_name": "Canvas Expert (Read Only)",
        "version": __version__,
        "description": "Launches the read-only Canvas Expert MCP server from this computer's unzipped CanvasExpert folder.",
        "author": {"name": "Canvas Expert"},
        "server": {
            "type": "python",
            "entry_point": "server/launcher.py",
            "mcp_config": {
                "command": str(Path(sys.executable).resolve()),
                "args": ["${__dirname}/server/launcher.py"],
                "env": {"CANVAS_EXPERT_ROOT": str(second_app)},
            },
        },
        "compatibility": {"platforms": ["win32"], "runtimes": {"python": ">=3.14,<4.0"}},
    }
    assert "subprocess" not in launcher
    assert str(second_app) not in launcher

    launcher_path = tmp_path / "launcher.py"
    launcher_path.write_text(launcher, encoding="utf-8")
    fake_api = types.ModuleType("api")
    fake_api.__path__ = []
    fake_mcp = types.ModuleType("api.mcp_server")
    fake_mcp.__path__ = []
    fake_server = types.ModuleType("api.mcp_server.server")
    calls = []
    fake_server.run_stdio = lambda: calls.append(True)
    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.mcp_server", fake_mcp)
    monkeypatch.setitem(sys.modules, "api.mcp_server.server", fake_server)
    monkeypatch.setenv("CANVAS_EXPERT_ROOT", str(second_app))
    runpy.run_path(str(launcher_path), run_name="__main__")
    assert calls == [True]

    monkeypatch.setattr(server.config, "token_is_set", lambda: True)
    monkeypatch.setattr(server.config, "get_canvas_base", lambda: "https://canvas.invalid")
    response = TestClient(server.app).get("/connections")
    assert response.status_code == 200
    assert response.text.count("Connections") >= 1
    assert "Canvas Expert runs from this unzipped folder." in response.text
    assert TestClient(server.app).get("/api/connections/health").status_code == 200
    assert TestClient(server.app).post("/api/connections/claude-package").status_code == 200
    assert TestClient(server.app).post("/api/support-bundle").status_code == 200

    after = {path: sorted(item.name for item in path.iterdir()) for path in client_dirs}
    assert after == before
    assert diagnostics.health_snapshot()["environment"]["tunnel_client_present"] is False
    (second_app / "tools" / "tunnel-client.exe").write_bytes(b"synthetic")
    assert diagnostics.health_snapshot()["environment"]["tunnel_client_present"] is True
