"""RubricForge — parse, validate, and compose <RUBRICFORGE_JSON> payloads.

Pure functions only: no HTTP here. server.py owns the Canvas calls so this
module stays testable without a token. Contract: default_docs/AI Authoring/Author a
Rubric (RubricForge).txt (v1.0-json).
"""
import json
import re

ENVELOPE_RE = re.compile(
    r"<RUBRICFORGE_JSON>\s*(\{.*\})\s*</RUBRICFORGE_JSON>", re.S)


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
        return None, ["no <RUBRICFORGE_JSON> … </RUBRICFORGE_JSON> envelope found"]
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON inside envelope: {e}"]
    return data, validate(data)


def _text(value):
    return str(value or "").strip()


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _criterion_ref(index, criterion):
    name = _text((criterion or {}).get("name"))
    return f"criterion {index + 1}{f' ({name})' if name else ''}"


def _rating_ref(index, rating):
    label = _text((rating or {}).get("label"))
    return f"rating {index + 1}{f' ({label})' if label else ''}"


def validate(d):
    problems = []
    if d.get("version") != "1.0-json":
        problems.append(f"version must be \"1.0-json\" (got {d.get('version')!r})")
    if d.get("type") != "RUBRIC":
        problems.append(f"type must be RUBRIC (got {d.get('type')!r})")

    title = _text(d.get("title"))
    if not title:
        problems.append("title is required")

    student_page = d.get("student_page") or {}
    student_page_title = _text(student_page.get("title")) if isinstance(student_page, dict) else ""
    if not student_page_title:
        problems.append("student_page.title is required")
    elif title and student_page_title == title:
        problems.append("student_page.title must differ from title")

    criteria = d.get("criteria") or []
    if not isinstance(criteria, list) or not criteria:
        problems.append("criteria is required")
        criteria = []

    total = 0
    for i, criterion in enumerate(criteria):
        ref = _criterion_ref(i, criterion)
        if not isinstance(criterion, dict):
            problems.append(f"{ref}: must be an object")
            continue

        name = _text(criterion.get("name"))
        if not name:
            problems.append(f"{ref}: name is required")

        points = criterion.get("points")
        if not _is_number(points) or points <= 0:
            problems.append(f"{ref}: points must be a number > 0")
            points = 0
        total += points

        ratings = criterion.get("ratings") or []
        if not isinstance(ratings, list) or len(ratings) < 2:
            problems.append(f"{ref}: ratings must be a list with at least 2 entries")
            continue

        labels_seen = set()
        prev_points = None
        for j, rating in enumerate(ratings):
            rref = f"{ref}, {_rating_ref(j, rating)}"
            if not isinstance(rating, dict):
                problems.append(f"{rref}: must be an object")
                continue

            rpoints = rating.get("points")
            if not _is_number(rpoints):
                problems.append(f"{rref}: points must be a number")
            elif j == 0 and rpoints != points:
                problems.append(f"{rref}: first rating points must equal criterion points")
            elif j == len(ratings) - 1 and rpoints != 0:
                problems.append(f"{rref}: last rating points must be 0")
            if prev_points is not None and _is_number(rpoints) and rpoints >= prev_points:
                problems.append(f"{rref}: rating points must be strictly descending")
            if _is_number(rpoints):
                prev_points = rpoints

            label = _text(rating.get("label"))
            if label:
                low = label.lower()
                if low in labels_seen:
                    problems.append(f"{ref}: rating labels must be unique (case-insensitive)")
                labels_seen.add(low)

            if not _text(rating.get("description")):
                problems.append(f"{rref}: description is required")
            if not _text(rating.get("student_description")):
                problems.append(f"{rref}: student_description is required")

    total_points = d.get("total_points")
    if not _is_number(total_points):
        problems.append("total_points must be a number")
    elif total != total_points:
        problems.append(f"criteria points sum to {total} but total_points is {total_points}")

    return problems


def total_points(d):
    return d["total_points"]


def _join_text(*parts):
    return " ".join(part for part in (_text(p) for p in parts) if part)


def canvas_rubric_payload(d, course_id):
    rubric_criteria = {}
    for i, criterion in enumerate(d.get("criteria") or []):
        ratings = {}
        for j, rating in enumerate(criterion.get("ratings") or []):
            ratings[str(j)] = {
                "description": _text(rating.get("label")),
                "long_description": _text(rating.get("description")),
                "points": rating.get("points"),
            }
        rubric_criteria[str(i)] = {
            "description": _text(criterion.get("name")),
            "long_description": _join_text(
                criterion.get("core_question"),
                criterion.get("consistency_thread"),
                criterion.get("note"),
            ),
            "points": criterion.get("points"),
            "criterion_use_range": bool(criterion.get("use_range")),
            "ratings": ratings,
        }

    return {
        "rubric": {
            "title": _text(d.get("title")),
            "free_form_criterion_comments": False,
            "criteria": rubric_criteria,
        },
        "rubric_association": {
            "association_id": int(str(course_id).strip()),
            "association_type": "Course",
            "purpose": "bookkeeping",
        },
    }


def student_page_html(d):
    student_page = d.get("student_page") or {}
    tagline = _text(student_page.get("tagline"))
    reminder = _text(student_page.get("reminder"))
    criteria = d.get("criteria") or []
    header_criterion = max(criteria, key=lambda c: len(c.get("ratings") or []), default=None)
    header_ratings = (header_criterion or {}).get("ratings") or []
    total = total_points(d)

    parts = []
    if tagline:
        parts.append(tagline)
    parts.append('<table style="border-collapse:collapse;width:100%">')
    parts.append('  <thead><tr style="background:#eef5fc">')
    parts.append('    <th style="border:1px solid #ccc;padding:8px;text-align:left">What\'s being scored</th>')
    for rating in header_ratings:
        parts.append(
            f'    <th style="border:1px solid #ccc;padding:8px;text-align:left">{_text(rating.get("label"))}</th>'
        )
    parts.append('  </tr></thead>')
    parts.append('  <tbody>')
    for criterion in criteria:
        ratings = criterion.get("ratings") or []
        row = [
            '    <tr>',
            f'      <td style="border:1px solid #ccc;padding:8px"><strong>{_text(criterion.get("student_label") or criterion.get("name"))}</strong><br>{_text(criterion.get("points"))} points</td>',
        ]
        for rating in ratings:
            row.append(
                f'      <td style="border:1px solid #ccc;padding:8px">{_text(rating.get("student_description"))}</td>'
            )
        for _ in range(len(header_ratings) - len(ratings)):
            row.append('      <td style="border:1px solid #ccc;padding:8px">&nbsp;</td>')
        row.append('    </tr>')
        parts.extend(row)
    parts.append('  </tbody>')
    parts.append('</table>')
    if reminder:
        parts.append(reminder)
    parts.append(f'<p><strong>Total: {_text(total)} points</strong></p>')
    return "\n".join(parts)


def scoring_prompt(d):
    lines = [
        "You are an experienced teacher scoring student writing with the rubric below.",
        "Score each criterion independently and honestly — a response can be excellent in",
        "one criterion and weak in another. Use the full range. Quote briefly from the",
        "student's work to justify every score.",
        "",
        f"RUBRIC: {_text(d.get('title'))} ({total_points(d)} points)",
        "",
    ]

    for i, criterion in enumerate(d.get("criteria") or []):
        lines.append(f"CRITERION {i + 1}: {_text(criterion.get('name'))} — {_text(criterion.get('points'))} points")
        cq = _text(criterion.get('core_question'))
        if cq:
            lines.append(f"Core question: {cq}")
        for rating in criterion.get("ratings") or []:
            range_min = rating.get("range_min")
            band = f" (band {range_min}-{rating.get('points')})" if range_min is not None else ""
            lines.append(f"  [{rating.get('points')} pts{band}] {_text(rating.get('label'))}: {_text(rating.get('description'))}")
        lines.append("")

    guidance = d.get("scoring_guidance") or {}
    if guidance:
        lines.append("SCORING PRINCIPLES")
        for item in guidance.get("design_principles") or []:
            lines.append(f"- {_text(item)}")
        for item in guidance.get("consistency_tips") or []:
            lines.append(f"- {_text(item)}")
        scr_scaling = _text(guidance.get("scr_scaling"))
        if scr_scaling:
            lines.append(scr_scaling)
        lines.append("")

        output_template = guidance.get("output_template")
        if output_template is not None:
            lines.append("Return your evaluation as JSON in exactly this structure, then a short")
            lines.append("plain-English summary a student could read:")
            lines.append(json.dumps(output_template, indent=2))
            lines.append("")

    lines.append("I will paste one student response at a time. Wait for it.")
    return "\n".join(lines)


def summary(d):
    criteria = d.get("criteria") or []
    student_page = d.get("student_page") or {}
    return {
        "title": d.get("title"),
        "flavor": d.get("flavor"),
        "total_points": d.get("total_points"),
        "criteria": [
            {"name": c.get("name"), "points": c.get("points"), "ratings": len(c.get("ratings") or [])}
            for c in criteria
        ],
        "student_page_title": _text(student_page.get("title")),
    }