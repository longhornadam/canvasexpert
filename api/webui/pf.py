"""PageForge — parse and validate <PAGEFORGE_JSON> payloads.

Pure functions only, mirroring af.py: no HTTP here. server.py owns the Canvas
calls. Contract: LLM_Modules/PageForge_Base.md (v1.0-json).
"""
import json
import re

from . import af  # shared {{file:…}}/{{page:…}} placeholder grammar

ENVELOPE_RE = re.compile(
    r"<PAGEFORGE_JSON>\s*(\{.*\})\s*</PAGEFORGE_JSON>", re.S)

PLACEHOLDER_RE = af.PLACEHOLDER_RE


def parse_file(path):
    """Read a file and return (data, problems). data is None when unusable."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, [f"cannot read file: {e}"]
    return parse(text)


def parse(text):
    m = ENVELOPE_RE.search(text)
    if not m:
        return None, ["no <PAGEFORGE_JSON> … </PAGEFORGE_JSON> envelope found"]
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON inside envelope: {e}"]
    return data, validate(data)


def validate(d):
    problems = []
    if d.get("version") != "1.0-json":
        problems.append(f"version must be \"1.0-json\" (got {d.get('version')!r})")
    if d.get("type") != "PAGE":
        problems.append(f"type must be PAGE (got {d.get('type')!r})")
    if not str(d.get("title", "")).strip():
        problems.append("title is required")
    if not str(d.get("body", "")).strip():
        problems.append("body is required")
    return problems
