"""Safety tests for the one-click AI-client config merge (api/ai_clients.py).

The core promise is that connecting merges one entry without disturbing anything
else the teacher had, keeps a backup, and refuses to touch an unparseable file.
"""
import json
import tomllib

import pytest

from api import ai_clients


@pytest.fixture
def claude_path(tmp_path, monkeypatch):
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(ai_clients, "claude_config_path", lambda: path)
    return path


@pytest.fixture
def codex_path(tmp_path, monkeypatch):
    path = tmp_path / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(ai_clients, "codex_config_path", lambda: path)
    return path


# --------------------------------------------------------------------------- #
# Claude Desktop (JSON)
# --------------------------------------------------------------------------- #
def test_claude_connect_then_disconnect_roundtrip(claude_path):
    status = ai_clients.connect_claude()
    assert status["connected"] is True
    assert status["current"] is True

    data = json.loads(claude_path.read_text(encoding="utf-8"))
    entry = data["mcpServers"][ai_clients.SERVER_NAME]
    assert entry["command"].endswith(("python.exe", "python", "python3"))
    assert entry["args"] and entry["args"][0].endswith("__main__.py")

    ai_clients.disconnect_claude()
    data = json.loads(claude_path.read_text(encoding="utf-8"))
    assert ai_clients.SERVER_NAME not in data.get("mcpServers", {})


def test_claude_connect_preserves_other_servers_and_keys(claude_path):
    claude_path.write_text(
        json.dumps(
            {
                "mcpServers": {"other": {"command": "node", "args": ["x.js"]}},
                "globalShortcut": "Ctrl+Space",
            }
        ),
        encoding="utf-8",
    )
    ai_clients.connect_claude()
    data = json.loads(claude_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "node", "args": ["x.js"]}
    assert data["globalShortcut"] == "Ctrl+Space"
    assert ai_clients.SERVER_NAME in data["mcpServers"]

    # Disconnect must leave the unrelated server and top-level key untouched.
    ai_clients.disconnect_claude()
    data = json.loads(claude_path.read_text(encoding="utf-8"))
    assert data["mcpServers"] == {"other": {"command": "node", "args": ["x.js"]}}
    assert data["globalShortcut"] == "Ctrl+Space"


def test_claude_connect_is_idempotent(claude_path):
    ai_clients.connect_claude()
    ai_clients.connect_claude()
    data = json.loads(claude_path.read_text(encoding="utf-8"))
    assert list(data["mcpServers"]).count(ai_clients.SERVER_NAME) == 1


def test_claude_invalid_json_is_left_untouched(claude_path):
    claude_path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ai_clients.ClientError) as excinfo:
        ai_clients.connect_claude()
    assert excinfo.value.code == "invalid_config"
    assert claude_path.read_text(encoding="utf-8") == "{ this is not json"


def test_claude_backup_created_before_overwrite(claude_path):
    claude_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    ai_clients.connect_claude()
    backups = list((claude_path.parent / "canvasexpert-backups").glob("*.bak"))
    assert len(backups) == 1


def test_claude_status_flags_stale_paths(claude_path):
    claude_path.write_text(
        json.dumps({"mcpServers": {ai_clients.SERVER_NAME: {"command": "python", "args": ["old"]}}}),
        encoding="utf-8",
    )
    status = ai_clients.claude_status()
    assert status["connected"] is True
    assert status["current"] is False
    assert status["other_server_count"] == 0


# --------------------------------------------------------------------------- #
# ChatGPT desktop / Codex (TOML)
# --------------------------------------------------------------------------- #
def test_chatgpt_connect_writes_parseable_block(codex_path):
    status = ai_clients.connect_chatgpt()
    assert status["connected"] is True
    assert status["current"] is True

    data = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    entry = data["mcp_servers"][ai_clients.SERVER_NAME]
    assert entry["args"][0].endswith("__main__.py")


def test_chatgpt_connect_preserves_existing_config(codex_path):
    codex_path.write_text(
        "# my notes\n"
        "model = \"gpt-5.6\"\n\n"
        "[mcp_servers.other]\n"
        "command = 'node'\n"
        "args = ['x.js']\n",
        encoding="utf-8",
    )
    ai_clients.connect_chatgpt()
    data = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert data["model"] == "gpt-5.6"
    assert data["mcp_servers"]["other"] == {"command": "node", "args": ["x.js"]}
    assert ai_clients.SERVER_NAME in data["mcp_servers"]

    ai_clients.disconnect_chatgpt()
    data = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    assert ai_clients.SERVER_NAME not in data.get("mcp_servers", {})
    assert data["mcp_servers"]["other"] == {"command": "node", "args": ["x.js"]}
    assert data["model"] == "gpt-5.6"


def test_chatgpt_connect_is_idempotent(codex_path):
    ai_clients.connect_chatgpt()
    ai_clients.connect_chatgpt()
    text = codex_path.read_text(encoding="utf-8")
    assert text.count(f"[mcp_servers.{ai_clients.SERVER_NAME}]") == 1
    tomllib.loads(text)  # still valid


def test_chatgpt_invalid_toml_is_left_untouched(codex_path):
    codex_path.write_text("this = = broken", encoding="utf-8")
    with pytest.raises(ai_clients.ClientError) as excinfo:
        ai_clients.connect_chatgpt()
    assert excinfo.value.code == "invalid_config"
    assert codex_path.read_text(encoding="utf-8") == "this = = broken"


def test_chatgpt_windows_paths_roundtrip(codex_path, monkeypatch):
    monkeypatch.setattr(
        ai_clients,
        "_desired_server",
        lambda: {
            "command": r"C:\Program Files\Python314\python.exe",
            "args": [r"D:\Development Projects\CanvasExpert\api\mcp_server\__main__.py"],
        },
    )
    ai_clients.connect_chatgpt()
    data = tomllib.loads(codex_path.read_text(encoding="utf-8"))
    entry = data["mcp_servers"][ai_clients.SERVER_NAME]
    assert entry["command"] == r"C:\Program Files\Python314\python.exe"
    assert entry["args"][0] == r"D:\Development Projects\CanvasExpert\api\mcp_server\__main__.py"


def test_clients_status_never_raises(claude_path, codex_path):
    status = ai_clients.clients_status()
    assert set(status) == {"claude", "chatgpt"}
    assert status["claude"]["client"] == "claude"
    assert status["chatgpt"]["client"] == "chatgpt"
