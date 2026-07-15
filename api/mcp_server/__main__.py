"""Entry point for the CanvasExpert read-only MCP server, run over stdio.

Cwd-independent: mirrors the ``sys.path`` bootstrap in
``api/webui/server.py`` so this works regardless of the caller's working
directory (MCP clients typically launch it with an absolute path and an
unpredictable cwd). No network bind — stdio transport only.
"""
import os
import sys

_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_API_DIR)
for _path in (_API_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.mcp_server.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="stdio")
