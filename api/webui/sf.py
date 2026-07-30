"""SlideForge — parse and validate <SLIDEFORGE_JSON> payloads.

Pure functions only, mirroring af.py and pf.py: no HTTP here. server.py owns the Canvas
calls and deck storage. Contract: default_docs/AI Authoring/Author a SmartDeck (SlideForge).txt (v1.0-json).
"""
import json
import re

ENVELOPE_RE = re.compile(
    r"<SLIDEFORGE_JSON>\s*(\{.*\})\s*</SLIDEFORGE_JSON>", re.S)


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
        return None, ["no <SLIDEFORGE_JSON> … </SLIDEFORGE_JSON> envelope found"]
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON inside envelope: {e}"]
    return data, validate(data)


def validate(d):
    """Validate a parsed SlideForge deck dict.

    Returns a list of problem strings. An empty list means the deck is valid.
    Never raises -- always degrades gracefully to problem messages even on
    wildly malformed input (missing keys, wrong types, etc.).
    """
    problems = []

    # Version and type
    if d.get("version") != "1.0-json":
        problems.append(f"version must be \"1.0-json\" (got {d.get('version')!r})")
    if d.get("type") != "DECK":
        problems.append(f"type must be DECK (got {d.get('type')!r})")

    # Date validation
    date_val = d.get("date")
    if not date_val:
        problems.append("date is required")
    elif not isinstance(date_val, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
        problems.append(f"date must match YYYY-MM-DD format (got {date_val!r})")

    # Title validation
    if not str(d.get("title", "")).strip():
        problems.append("title is required")

    # Check for top-level feed key (reserved, not supported)
    if "feed" in d:
        problems.append("feed bindings are not supported in v1")

    # Collect all unknown top-level keys
    valid_keys = {"version", "type", "date", "title", "widgets", "slides"}
    unknown_keys = set(d.keys()) - valid_keys
    for key in sorted(unknown_keys):
        problems.append(f"unknown top-level key: {key!r}")

    # Validate widgets array
    widgets_list = d.get("widgets") or []
    if not isinstance(widgets_list, list):
        widgets_list = []

    widget_ids = set()
    for widget in widgets_list:
        if not isinstance(widget, dict):
            problems.append("each widget must be a dict")
            continue

        widget_id = widget.get("id")
        if not widget_id:
            problems.append("widget is missing id")
        elif widget_id in widget_ids:
            problems.append(f"widget id {widget_id!r} is duplicated")
        else:
            widget_ids.add(widget_id)

        scope = widget.get("scope")
        if scope not in ("deck", "slide"):
            problems.append(f"widget scope must be 'deck' or 'slide' (got {scope!r})")

        kind = widget.get("kind")
        if kind != "timer":
            problems.append(f"widget kind must be 'timer' (got {kind!r})")

        if kind == "timer":
            params = widget.get("params") or {}
            duration = params.get("duration_seconds")
            if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1 or duration > 86400:
                problems.append(
                    f"widget {widget_id!r}: duration_seconds must be an integer from 1 to 86400 "
                    f"(got {duration!r})")

    # Validate slides array
    slides_list = d.get("slides") or []
    if not isinstance(slides_list, list):
        slides_list = []
    if not slides_list:
        problems.append("slides is required and must be non-empty")

    slide_ids = set()
    for slide in slides_list:
        if not isinstance(slide, dict):
            problems.append("each slide must be a dict")
            continue

        slide_id = slide.get("id")
        if not slide_id:
            problems.append("slide is missing id")
        elif slide_id in slide_ids:
            problems.append(f"slide id {slide_id!r} is duplicated")
        else:
            slide_ids.add(slide_id)

        # Check block
        block = slide.get("block")
        if not isinstance(block, str) or not block.strip():
            problems.append(f"slide {slide_id!r}: block must be a non-empty string (got {block!r})")

        # Check layout
        layout = slide.get("layout")
        if layout not in ("title_body", "title_only", "bulleted"):
            problems.append(
                f"slide {slide_id!r}: layout must be one of 'title_body', 'title_only', 'bulleted' "
                f"(got {layout!r})")

        # Check for feed key in slide (reserved)
        if "feed" in slide:
            problems.append(f"slide {slide_id!r}: feed bindings are not supported in v1")

        # Validate slide widget references
        slide_widgets = slide.get("widgets") or []
        if not isinstance(slide_widgets, list):
            slide_widgets = []

        for widget_ref in slide_widgets:
            if widget_ref not in widget_ids:
                problems.append(
                    f"slide {slide_id!r}: references unknown widget {widget_ref!r}")

    return problems
