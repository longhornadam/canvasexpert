"""Call-time paths for the portable Canvas Expert application.

Stable application paths come from this module's location. Workspace-derived
paths are resolved through the current workspace setting on every call so a
workspace switch does not require a Python restart.
"""
from __future__ import annotations

import sys
from pathlib import Path


_API_ROOT = Path(__file__).resolve().parent
_APP_ROOT = _API_ROOT.parent


def _workspace_module():
    """Return the workspace module for either supported import layout."""
    loaded = sys.modules.get("webui.workspace") or sys.modules.get("api.webui.workspace")
    if loaded is not None:
        return loaded
    from .webui import workspace
    return workspace


def app_root() -> Path:
    """The single unzipped Canvas Expert application root."""
    return _APP_ROOT


def api_root() -> Path:
    return _API_ROOT


def python_executable() -> Path:
    return Path(sys.executable).resolve()


def mcp_entrypoint() -> Path:
    return api_root() / "mcp_server" / "__main__.py"


def workspace_root() -> Path | None:
    value = _workspace_module().workspace_root()
    return Path(value) if value else None


def workspace_folder(name: str) -> Path | None:
    value = _workspace_module().folder(name)
    return Path(value) if value else None


def exports_dir() -> Path:
    return workspace_folder("Exports") or (app_root() / "Finished_Exports")


def temp_dir() -> Path:
    return api_root() / "temp"


_KIND_WORKSPACE_NAMES = {
    "quiz": "Quizzes",
    "assignment": "Assignments",
    "page": "Pages",
    "rubric": "Rubrics",
}


def content_folders(kind: str) -> list[Path]:
    workspace_name = _KIND_WORKSPACE_NAMES.get(kind)
    if workspace_name is None:
        raise ValueError(f"unknown content folder kind: {kind}")

    folders: list[Path] = []
    if kind == "quiz":
        folders.extend([
            api_root() / "qf_materials" / "qf quiz examples",
            app_root() / "DropZone",
            app_root() / "Finished_Exports",
        ])
    elif kind == "assignment":
        folders.extend([
            api_root() / "qf_materials" / "assignment examples",
            api_root() / "qf_materials" / "qf quiz examples",
        ])
    elif kind == "page":
        folders.append(api_root() / "qf_materials" / "qf quiz examples")

    current = workspace_folder(workspace_name)
    if current:
        if kind == "rubric":
            folders.insert(0, current)
        else:
            folders.append(current)
    if kind == "rubric":
        folders.append(api_root() / "rubrics")
    return folders


def inbox_folder(kind: str) -> Path | None:
    """Per-kind Inbox drop folder where an MCP-capable assistant stages a
    draft for the teacher to review and push.

    Distinct from the teacher's own library folders returned by
    ``content_folders`` (Quizzes/Assignments/Pages/Rubrics): this is a
    separate, marker-gated pickup surface -- see
    ``webui.deps.list_inbox_files``. Not included in ``content_folders``'s
    plain glob, since that glob has no marker gate and would surface a
    half-synced drop.

    Resolves against the workspace root the same way ``workspace_folder``
    does, and returns None when the workspace is unavailable. When the
    workspace is available, ensures the folder exists (parents included) so
    the assistant always has a stable place to drop a file.
    """
    workspace_name = _KIND_WORKSPACE_NAMES.get(kind)
    if workspace_name is None:
        raise ValueError(f"unknown content folder kind: {kind}")

    root = workspace_root()
    if not root:
        return None
    folder = root / "Inbox" / workspace_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ai_ta_dir() -> Path:
    return workspace_folder("AI-TA") or (app_root() / "AI-TA")


def rubric_folders() -> list[Path]:
    return content_folders("rubric")
