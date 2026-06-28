"""Canvas submission fetching helpers for PowerGrader.

Fetch submissions from Canvas, enrich with code-file downloads.
"""

import os

import requests

from webui.canvas_client import _canvas_get, _canvas_get_all, _canvas_headers


_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
_MAX_CODE_BYTES = 256 * 1024


def fetch_submissions(course_id: str, assignment_id: str):
    """Fetch submissions for one assignment. Returns (subs, assignment_obj, error)."""
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": ["all"], "assignment_ids[]": [assignment_id],
         "include[]": ["assignment", "user"], "per_page": 100},
    )
    if err:
        return None, None, err
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    return subs, adata or {}, None


def enrich_with_code_files(subs):
    """Download plain-text uploads (.py/.html/...) into s['code_files']."""
    hdrs, _ = _canvas_headers()
    if not hdrs:
        return
    sess = requests.Session()
    sess.headers.update(hdrs)
    for s in subs:
        files = []
        for att in (s.get("attachments") or []):
            fn = att.get("filename") or att.get("display_name") or ""
            if os.path.splitext(fn)[1].lower() not in _CODE_EXTS:
                continue
            if (att.get("size") or 0) > _MAX_CODE_BYTES:
                continue
            url = att.get("url")
            if not url:
                continue
            try:
                r = sess.get(url, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and len(r.content) <= _MAX_CODE_BYTES:
                files.append({"filename": fn, "text": r.text})
        if files:
            s["code_files"] = files