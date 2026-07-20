"""Run the existing qf_pusher / push_tiers / validate_qf CLI scripts as
subprocesses, with per-request Canvas credentials injected via the
environment. canvas.py calls `load_dotenv()` (which never overrides vars
already present in the environment), so setting CANVAS_BASE / COURSE_ID /
CANVAS_TOKEN here makes the subprocess target exactly the chosen profile,
regardless of what's in api/.env.
"""
import os
import json
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


def run_json_object(args, extra_env=None, timeout=30, max_output_bytes=2_000_000):
    """Run a local planner and return its one bounded JSON-object response.

    Canvas credentials are deliberately removed: operation preparation is a
    local transformation boundary, not a live-write subprocess.
    """
    env = _env(extra_env or {})
    for key in ("CANVAS_TOKEN", "CANVAS_BASE", "COURSE_ID"):
        env.pop(key, None)
    try:
        proc = subprocess.run(
            [sys.executable, "-u", *args],
            cwd=API_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("planner timed out") from exc
    if len(proc.stdout) > max_output_bytes or len(proc.stderr) > max_output_bytes:
        raise ValueError("planner output exceeded limit")
    if proc.returncode != 0:
        raise ValueError("planner failed")
    try:
        text = proc.stdout.decode("utf-8")
        parsed = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("planner returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("planner response must be a JSON object")
    return parsed


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
