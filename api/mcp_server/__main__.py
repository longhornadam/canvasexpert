"""Entry point for the CanvasExpert read-only MCP server, run over stdio.

Cwd-independent: resolves the repository root from this file so it works
regardless of the caller's working directory (MCP clients typically launch it
with an absolute path and an unpredictable cwd). No network bind — stdio
transport only.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.mcp_server.server import run_stdio  # noqa: E402

if __name__ == "__main__":
    run_stdio()
