"""New Quiz Student Analysis JSON fetch and normalization for PowerGrader.

This module is deliberately the only PowerGrader owner of the quiz-LTI report
transport.  It never logs report payloads because they contain student work.
"""
from datetime import datetime, timezone
import time

import requests

try:
    from webui.canvas_client import _canvas_headers
    from nq_report import html_to_text
except ModuleNotFoundError:
    from api.webui.canvas_client import _canvas_headers
    from api.nq_report import html_to_text

POLL_LIMIT = 20
POLL_SECONDS = 1
REPORT_409_RETRIES = 3


def _error(status=None):
    if status in (401, 403):
        return "New Quiz responses are unavailable. Verify your active Canvas enrollment or use the Student Analysis CSV workflow."
    return "Could not load New Quiz written responses. Try again, or use the Student Analysis CSV workflow."


def _parse_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _progress(data):
    return data.get("progress") if isinstance(data, dict) and isinstance(data.get("progress"), dict) else data


def _json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _get_report(session, base, path, headers, sleep=time.sleep):
    for _ in range(REPORT_409_RETRIES + 1):
        response = session.get(path if path.startswith("http") else base + path, headers=headers, timeout=30)
        if response.status_code == 409:
            sleep(POLL_SECONDS)
            continue
        if response.status_code != 200:
            return None, _error(response.status_code)
        data = _json(response)
        return (data, None) if isinstance(data, list) else (None, _error())
    return None, _error()


def _create_report(session, base, course_id, assignment_id, headers, sleep=time.sleep):
    url = f"{base}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/reports"
    response = session.post(url, headers=headers, data={
        "quiz_report[report_type]": "student_analysis", "quiz_report[format]": "json",
    }, timeout=30)
    if response.status_code not in (200, 201):
        return None, _error(response.status_code)
    progress = _progress(_json(response))
    if not isinstance(progress, dict) or not progress.get("url"):
        return None, _error()
    progress_url = progress["url"]
    for _ in range(POLL_LIMIT):
        polled = session.get(progress_url, headers=headers, timeout=30)
        if polled.status_code == 409:
            sleep(POLL_SECONDS)
            continue
        if polled.status_code != 200:
            return None, _error(polled.status_code)
        progress = _progress(_json(polled))
        if not isinstance(progress, dict):
            return None, _error()
        progress_url = progress.get("url") or progress_url
        if str(progress.get("workflow_state") or progress.get("state") or "").lower() in {"failed", "error"}:
            return None, _error()
        results = progress.get("results") or {}
        if isinstance(results, dict) and results.get("url"):
            return _get_report(session, base, results["url"], headers, sleep)
        sleep(POLL_SECONDS)
    return None, _error()


def _item_map(items):
    out = {}
    for outer in items:
        for entry in outer.get("entry", []) if isinstance(outer.get("entry"), list) else [outer.get("entry")]:
            if isinstance(entry, dict) and entry.get("id") is not None:
                out[str(entry["id"])] = entry
    return out


def _attempt_time(row):
    student = row.get("student_data") or {}
    return student.get("submitted_at") or row.get("submitted_at") or row.get("updated_at")


def normalize(core_submissions, report_rows, items):
    """Join latest report attempts to Core submissions without exposing identity in errors."""
    latest = {}
    for row in report_rows:
        student = row.get("student_data") or {}
        uid = str(student.get("id") or "")
        try: attempt = float(student.get("attempt") if student.get("attempt") is not None else row.get("attempt"))
        except (TypeError, ValueError): continue
        if uid and (uid not in latest or attempt > latest[uid][0]): latest[uid] = (attempt, row)
    entries = _item_map(items)
    normalized = []
    for core in core_submissions:
        uid = str(core.get("user_id") or "")
        selected = latest.get(uid)
        if not uid or not selected or not core.get("submitted_at") or not _attempt_time(selected[1]):
            continue
        attempt, row = selected
        new_items = []
        for answer in row.get("item_responses") or []:
            item = entries.get(str(answer.get("item_id") or ""))
            if not item: continue
            kind = item.get("item_type") or item.get("type") or ""
            raw = answer.get("answer") or answer.get("response") or ""
            files = answer.get("files") or answer.get("attachments") or []
            new_items.append({"item_id": str(answer.get("item_id")), "type": kind,
                "prompt": item.get("item_body") or "", "raw_html_answer": raw,
                "possible": item.get("points_possible") or item.get("points") or 0,
                "earned_score": answer.get("score"),
                "files": [{"filename": f.get("filename") or f.get("display_name") or ""} for f in files if isinstance(f, dict)]})
        if not new_items: continue
        body = "\n\n".join(f"{html_to_text(x['prompt'])}\n{html_to_text(x['raw_html_answer'])}" for x in new_items)
        normalized.append({**core, "body": body, "attachments": [], "new_quiz_items": new_items,
            "new_quiz_attempt": int(attempt) if attempt.is_integer() else attempt,
            "new_quiz_reported_at": _attempt_time(row)})
    return normalized


def fetch(course_id, assignment_id, core_submissions, *, session=None, sleep=time.sleep):
    headers, base = _canvas_headers()
    if not headers or not base: return None, "No Canvas token saved — go to Settings."
    session = session or requests.Session()
    items_response = session.get(f"{base}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items", headers=headers, timeout=30)
    if items_response.status_code != 200: return None, _error(items_response.status_code)
    items = _json(items_response)
    if not isinstance(items, list): return None, _error()
    rows, err = _create_report(session, base, course_id, assignment_id, headers, sleep)
    if err: return None, err
    subs = normalize(core_submissions, rows, items)
    # One fail-closed refresh when Core is newer than the selected report.
    stale = any(_parse_time(s.get("submitted_at")) is None or _parse_time(s.get("new_quiz_reported_at")) is None or _parse_time(s["submitted_at"]) > _parse_time(s["new_quiz_reported_at"]) for s in subs)
    if stale:
        rows, err = _create_report(session, base, course_id, assignment_id, headers, sleep)
        if err: return None, err
        subs = normalize(core_submissions, rows, items)
        if any(_parse_time(s.get("submitted_at")) is None or _parse_time(s.get("new_quiz_reported_at")) is None or _parse_time(s["submitted_at"]) > _parse_time(s["new_quiz_reported_at"]) for s in subs):
            return None, "New Quiz report is still older than Canvas. Wait briefly and try again; no session was created."
    return subs, None
