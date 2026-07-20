"""Thin Canvas API client for sandbox experiments.

Wraps both API surfaces from one place:
  - Core REST   : {base}/api/v1/...      (courses, assignments, overrides, grades)
  - New Quizzes : {base}/api/quiz/v1/... (quizzes + items)

Config comes from .env (never hardcode tokens). Every call logs method, URL,
status, and a truncated body so the experiment console is self-documenting.
"""
import os
import sys
import textwrap

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["CANVAS_BASE"].rstrip("/")
COURSE_ID = os.environ["COURSE_ID"]
TOKEN = os.environ.get("CANVAS_TOKEN", "")

if not TOKEN or TOKEN.startswith("PASTE"):
    raise SystemExit(
        "CANVAS_TOKEN is not set in .env — paste your sandbox token there first."
    )

_session = requests.Session()
_session.headers.update({"Authorization": f"Bearer {TOKEN}"})

MAX_LOG = 1500


def _log(method, url, resp):
    body = resp.text or ""
    if len(body) > MAX_LOG:
        body = body[:MAX_LOG] + f"\n... [+{len(body) - MAX_LOG} more chars]"
    # encode with replace so Unicode chars (✓ ✗ etc.) don't crash cp1252 consoles
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    def _p(s):
        print(s.encode(enc, errors="replace").decode(enc))
    _p(f"  -> {method} {url}")
    _p(f"     HTTP {resp.status_code} {resp.reason}")
    if body.strip():
        _p(textwrap.indent(body, "     "))


def core(path):
    """Build a core REST URL: core('/courses/123') -> {base}/api/v1/courses/123"""
    return f"{BASE}/api/v1{path}"


def quiz(path):
    """Build a New Quizzes URL: quiz('/courses/123/quizzes') -> {base}/api/quiz/v1/..."""
    return f"{BASE}/api/quiz/v1{path}"


def request(method, url, **kw):
    """Make a request, log it, return (status_code, parsed_json_or_None)."""
    resp = _session.request(method, url, timeout=30, **kw)
    _log(method, url, resp)
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)


def put(url, **kw):
    return request("PUT", url, **kw)


def patch(url, **kw):
    return request("PATCH", url, **kw)


def delete(url, **kw):
    return request("DELETE", url, **kw)
