"""One-click connect for local AI desktop apps (Claude Desktop, ChatGPT desktop).

Both clients read a local, user-owned config file to register a local stdio MCP
server, so "connecting" means merging one entry into that file. This module owns
that merge and is deliberately conservative:

* merge, never overwrite: every other server and top-level key is preserved;
* a timestamped backup is written before any change (pruned to the last few);
* after writing we re-parse the file and roll back if it is invalid or our entry
  is missing;
* disconnect removes only our entry;
* the operation is idempotent, so reconnecting after the folder moves just
  rewrites the current paths.

Privacy guardrail: the returned status never includes the contents of another
server's entry (which may hold that user's own tokens). Only our own block,
booleans, paths, and a count of preserved servers are surfaced, and file
contents are never logged.

This module writes only to files the current user owns, in user space. It never
requires administrator rights and never touches Canvas.
"""
from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path

from api import operational_log, runtime_paths
from api.storage_support import utc_compact_stamp


__all__ = [
    "SERVER_NAME",
    "ClientError",
    "clients_status",
    "claude_status",
    "chatgpt_status",
    "connect_claude",
    "disconnect_claude",
    "connect_chatgpt",
    "disconnect_chatgpt",
]

SERVER_NAME = "canvas-expert"
_MARKER_COMMENT = (
    "# Canvas Expert (read-only). Managed by the Canvas Expert CanvasAgent page."
)
_MAX_BACKUPS = 5


class ClientError(Exception):
    """A connect/disconnect failure with a teacher-readable detail and a code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- #
# Paths and desired server entry
# --------------------------------------------------------------------------- #
def claude_config_path() -> Path:
    """%APPDATA%\\Claude\\claude_desktop_config.json (falls back to ~ if unset)."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
    return base / "Claude" / "claude_desktop_config.json"


def codex_config_path() -> Path:
    """~/.codex/config.toml, shared by the unified ChatGPT desktop app and Codex."""
    return Path.home() / ".codex" / "config.toml"


def _desired_server() -> dict:
    python_executable = Path(runtime_paths.python_executable()).resolve()
    mcp_entrypoint = Path(runtime_paths.mcp_entrypoint()).resolve()
    return {"command": str(python_executable), "args": [str(mcp_entrypoint)]}


def _pin_workspace() -> None:
    """Best-effort: pin the workspace path so the headless MCP server this connect
    is enabling resolves the same workspace the app does. Never blocks a connect."""
    try:
        from api.webui import config

        config.ensure_workspace_pinned()
    except Exception as exc:
        operational_log.emit("mcp.workspace_pin_write", "failed", error_class=type(exc))


def _norm(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _entry_matches(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    desired = _desired_server()
    command = entry.get("command")
    args = entry.get("args")
    if not isinstance(command, str) or not isinstance(args, list) or not args:
        return False
    if _norm(command) != _norm(desired["command"]):
        return False
    return _norm(str(args[0])) == _norm(desired["args"][0])


# --------------------------------------------------------------------------- #
# Backups and rollback (shared)
# --------------------------------------------------------------------------- #
def _timestamp() -> str:
    return utc_compact_stamp()


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    backups = path.parent / "canvasexpert-backups"
    backups.mkdir(parents=True, exist_ok=True)
    destination = backups / f"{path.name}.{_timestamp()}.bak"
    shutil.copy2(path, destination)
    _prune_backups(backups, path.name)
    return destination


def _prune_backups(backups: Path, name: str) -> None:
    kept = sorted(backups.glob(f"{name}.*.bak"))
    for stale in kept[:-_MAX_BACKUPS]:
        try:
            stale.unlink()
        except OSError:
            pass


def _rollback(path: Path, backup: Path | None, existed: bool) -> None:
    if backup is not None and backup.is_file():
        shutil.copy2(backup, path)
    elif not existed:
        try:
            path.unlink()
        except OSError:
            pass


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.canvasexpert-tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


# --------------------------------------------------------------------------- #
# Claude Desktop (JSON)
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> tuple[dict, bool, bool]:
    """Return (data, existed, invalid). Empty files parse as an empty object."""
    if not path.is_file():
        return {}, False, False
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return {}, True, False
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}, True, True
    if not isinstance(data, dict):
        return {}, True, True
    return data, True, False


def claude_status() -> dict:
    path = claude_config_path()
    detected = path.parent.is_dir()
    data, existed, invalid = _read_json(path)
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    entry = servers.get(SERVER_NAME)
    connected = entry is not None
    other = sum(1 for name in servers if name != SERVER_NAME)
    return {
        "client": "claude",
        "label": "Claude Desktop",
        "config_path": str(path),
        "detected": detected,
        "exists": existed,
        "invalid": invalid,
        "connected": connected,
        "current": connected and _entry_matches(entry),
        "other_server_count": other,
    }


def connect_claude() -> dict:
    _pin_workspace()
    path = claude_config_path()
    data, existed, invalid = _read_json(path)
    if invalid:
        raise ClientError(
            "invalid_config",
            "Claude's config file is not valid JSON, so it was left untouched. "
            "Fix or remove it, or use manual setup.",
        )
    backup = _backup(path)
    try:
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
        servers[SERVER_NAME] = _desired_server()
        data["mcpServers"] = servers
        _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        verify, _, verify_invalid = _read_json(path)
        entry = verify.get("mcpServers", {}).get(SERVER_NAME)
        if verify_invalid or not _entry_matches(entry):
            raise ClientError("verify_failed", "The written config did not verify.")
    except Exception:
        _rollback(path, backup, existed)
        raise
    return claude_status()


def disconnect_claude() -> dict:
    path = claude_config_path()
    data, existed, invalid = _read_json(path)
    if not existed or invalid:
        return claude_status()
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        return claude_status()
    backup = _backup(path)
    try:
        del servers[SERVER_NAME]
        if servers:
            data["mcpServers"] = servers
        else:
            data.pop("mcpServers", None)
        _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        _rollback(path, backup, existed)
        raise
    return claude_status()


# --------------------------------------------------------------------------- #
# ChatGPT desktop / Codex (TOML)
# --------------------------------------------------------------------------- #
def _toml_string(value: str) -> str:
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _codex_block() -> str:
    server = _desired_server()
    args = ", ".join(_toml_string(arg) for arg in server["args"])
    return "\n".join(
        [
            _MARKER_COMMENT,
            f"[mcp_servers.{SERVER_NAME}]",
            f"command = {_toml_string(server['command'])}",
            f"args = [{args}]",
            'default_tools_approval_mode = "writes"',
        ]
    ) + "\n"


def _table_header(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("[") or stripped.startswith("[[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip()


def _is_our_table(dotted: str) -> bool:
    parts: list[str] = []
    for raw in dotted.split("."):
        part = raw.strip()
        if len(part) >= 2 and part[0] in "\"'" and part[-1] == part[0]:
            part = part[1:-1]
        parts.append(part)
    return len(parts) >= 2 and parts[0] == "mcp_servers" and parts[1] == SERVER_NAME


def _strip_our_block(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    total = len(lines)
    removed = False
    while index < total:
        header = _table_header(lines[index])
        if header is not None and _is_our_table(header):
            if out and out[-1].strip() == _MARKER_COMMENT:
                out.pop()
            index += 1
            while index < total:
                inner = _table_header(lines[index])
                if inner is not None and not _is_our_table(inner):
                    break
                index += 1
            removed = True
            continue
        out.append(lines[index])
        index += 1
    return "\n".join(out), removed


def _read_toml(path: Path) -> tuple[str, bool, bool]:
    """Return (text, existed, invalid)."""
    if not path.is_file():
        return "", False, False
    text = path.read_text(encoding="utf-8")
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return text, True, True
    return text, True, False


def chatgpt_status() -> dict:
    path = codex_config_path()
    detected = path.parent.is_dir()
    text, existed, invalid = _read_toml(path)
    connected = False
    current = False
    other = 0
    if existed and not invalid:
        data = tomllib.loads(text)
        servers = data.get("mcp_servers")
        servers = servers if isinstance(servers, dict) else {}
        entry = servers.get(SERVER_NAME)
        connected = entry is not None
        current = connected and _entry_matches(entry)
        other = sum(1 for name in servers if name != SERVER_NAME)
    return {
        "client": "chatgpt",
        "label": "ChatGPT desktop",
        "config_path": str(path),
        "detected": detected,
        "exists": existed,
        "invalid": invalid,
        "connected": connected,
        "current": current,
        "other_server_count": other,
    }


def connect_chatgpt() -> dict:
    _pin_workspace()
    path = codex_config_path()
    text, existed, invalid = _read_toml(path)
    if invalid:
        raise ClientError(
            "invalid_config",
            "ChatGPT's config.toml is not valid TOML, so it was left untouched. "
            "Fix or remove it, or use manual setup.",
        )
    backup = _backup(path)
    try:
        stripped, _ = _strip_our_block(text)
        base = stripped.rstrip("\n")
        new_text = f"{base}\n\n{_codex_block()}" if base else _codex_block()
        _atomic_write(path, new_text)
        verify_text, _, verify_invalid = _read_toml(path)
        if verify_invalid:
            raise ClientError("verify_failed", "The written config did not verify.")
        entry = tomllib.loads(verify_text).get("mcp_servers", {}).get(SERVER_NAME)
        if not _entry_matches(entry):
            raise ClientError("verify_failed", "The written config did not verify.")
    except Exception:
        _rollback(path, backup, existed)
        raise
    return chatgpt_status()


def disconnect_chatgpt() -> dict:
    path = codex_config_path()
    text, existed, invalid = _read_toml(path)
    if not existed or invalid:
        return chatgpt_status()
    stripped, removed = _strip_our_block(text)
    if not removed:
        return chatgpt_status()
    backup = _backup(path)
    try:
        _atomic_write(path, stripped.rstrip("\n") + "\n" if stripped.strip() else "")
    except Exception:
        _rollback(path, backup, existed)
        raise
    return chatgpt_status()


# --------------------------------------------------------------------------- #
# Combined status for the page
# --------------------------------------------------------------------------- #
def clients_status() -> dict:
    def _safe(fn):
        try:
            return fn()
        except Exception as error:  # status must never break the page
            return {"error": str(error)}

    return {"claude": _safe(claude_status), "chatgpt": _safe(chatgpt_status)}
