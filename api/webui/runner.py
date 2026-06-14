"""Run the existing qf_pusher / push_tiers / validate_qf CLI scripts as
subprocesses, with per-request Canvas credentials injected via the
environment. canvas.py calls `load_dotenv()` (which never overrides vars
already present in the environment), so setting CANVAS_BASE / COURSE_ID /
CANVAS_TOKEN here makes the subprocess target exactly the chosen profile,
regardless of what's in api/.env.
"""
import os
import subprocess
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(extra):
    env = dict(os.environ)
    env.update(extra)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def run_capture(args, extra_env=None, timeout=120):
    """Blocking run; returns (returncode, combined_output)."""
    proc = subprocess.run(
        [sys.executable, "-u", *args],
        cwd=API_DIR,
        env=_env(extra_env or {}),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def run_streaming(args, extra_env=None):
    """Yield stdout lines as they're produced, then a final '[exit N]' line."""
    proc = subprocess.Popen(
        [sys.executable, "-u", *args],
        cwd=API_DIR,
        env=_env(extra_env or {}),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        for line in proc.stdout:
            yield line.rstrip("\n")
    finally:
        proc.stdout.close()
        code = proc.wait()
        yield f"[exit {code}]"
