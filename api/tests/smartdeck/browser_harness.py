"""Reusable Playwright/Edge browser-test scaffolding for local display tests."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def launch_server(root, tmp, wait_path="/"):
    """Start the real app as a subprocess pointed at a throwaway workspace,
    and wait until it answers `wait_path`. Returns (process, base_url)."""
    local = tmp / "local"
    (local / "CanvasExpert").mkdir(parents=True)
    (local / "CanvasExpert" / "config.json").write_text(json.dumps({
        "workspace_path": str(root), "canvas_base": "https://canvas.example.test",
        "saved_courses": [],
    }))
    port = free_port()
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(local)
    process = subprocess.Popen(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,sys.argv[1]);import uvicorn;"
         "uvicorn.run('api.webui.server:app',host='127.0.0.1',port=int(sys.argv[2]),lifespan='off',log_level='warning')",
         str(ROOT), str(port)],
        cwd=str(ROOT), env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            if urllib.request.urlopen(url + wait_path, timeout=1).status == 200:
                return process, url
        except OSError:
            time.sleep(.1)
    process.terminate()
    raise AssertionError("server did not become ready")


def frozen_clock_init_script(iso_timestamp):
    """A Playwright page.add_init_script() payload that freezes Date.now() at
    iso_timestamp and exposes window.__advanceClock(iso) to move it forward."""
    return (
        "(()=>{const R=Date;let n=new R(%r).valueOf();"
        "class D extends R{constructor(...a){super(...(a.length?a:[n]))}static now(){return n}}"
        "window.Date=D;window.__advanceClock=v=>n=new R(v).valueOf()})()" % iso_timestamp
    )
