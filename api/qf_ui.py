"""Launch the local Canvas Expert web UI.

Starts a local server (default http://127.0.0.1:8765) wrapping qf_pusher /
push_tiers / validate_qf behind a browser UI — no terminal commands, no
remembering tokens or course IDs (see api/webui/ for the implementation,
api/README.md for the walkthrough).

Run: py qf_ui.py [--port 8765] [--no-browser]
"""
import sys
import threading
import webbrowser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api import __version__

import uvicorn

from api.webui.server import app

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main():
    port = DEFAULT_PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    open_browser = "--no-browser" not in sys.argv

    url = f"http://{HOST}:{port}"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"Canvas Expert {__version__}: {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host=HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()
