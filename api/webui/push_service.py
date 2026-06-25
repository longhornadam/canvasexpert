"""Push business logic extracted from routes/push.py.

Imported by routes/push.py. Keeping Canvas-API calls here makes them
unit-testable without HTTP and keeps route handlers thin.
"""
import html
import mimetypes
import os
from pathlib import Path

import requests

from . import workspace
from .canvas_client import _canvas_get_all, _canvas_send
from .deps import REPO_ROOT, TEMP_DIR, _exports_dir


def _find_assignment_group(course_id, name):
    data, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignment_groups", {"per_page": 100})
    if err:
        return None
    for g in data or []:
        if str(g.get("name", "")).strip().lower() == name.strip().lower():
            return g.get("id")
    return None


def _find_or_create_module_id(course_id, name, notes):
    data, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    if not err:
        for m in data:
            if str(m.get("name", "")).strip().lower() == name.strip().lower():
                return m.get("id")
    created, cerr = _canvas_send(
        "POST", f"/api/v1/courses/{course_id}/modules", {"module": {"name": name}})
    if cerr:
        notes.append(f"module '{name}' could not be created ({cerr})")
        return None
    notes.append(f"created module '{name}'")
    return created.get("id")


def _add_module_item(course_id, module_id, item, notes):
    _, err = _canvas_send(
        "POST", f"/api/v1/courses/{course_id}/modules/{module_id}/items",
        {"module_item": item})
    if err:
        notes.append(f"could not add to module ({err})")


def _push_assignment(cid, p, notes):
    a = {"name": (p.get("name") or "").strip() or "Untitled assignment",
         "submission_types": p.get("submission_types") or ["none"]}
    if p.get("description"):
        a["description"] = p["description"]
    if p.get("points") is not None:
        a["points_possible"] = p["points"]
    for k in ("due_at", "unlock_at", "lock_at"):
        if p.get(k):
            a[k] = p[k]
    if p.get("post_to_sis"):
        a["post_to_sis"] = True
    if p.get("published"):
        a["published"] = True
    if p.get("assignment_group_name"):
        ag = _find_assignment_group(cid, p["assignment_group_name"])
        if ag:
            a["assignment_group_id"] = ag
        else:
            notes.append(
                f"category '{p['assignment_group_name']}' not in this course — using default")
    resp, err = _canvas_send("POST", f"/api/v1/courses/{cid}/assignments", {"assignment": a})
    if err:
        return False, a["name"], None, err
    if p.get("module_name"):
        mid = _find_or_create_module_id(cid, p["module_name"], notes)
        if mid:
            _add_module_item(cid, mid, {"title": a["name"], "type": "Assignment",
                                        "content_id": resp["id"]}, notes)
    return True, resp.get("name", a["name"]), resp.get("html_url"), None


def _push_page(cid, p, notes):
    title = (p.get("title") or "").strip() or "Untitled page"
    wp = {"title": title, "body": p.get("body") or "",
          "published": bool(p.get("published"))}
    resp, err = _canvas_send("POST", f"/api/v1/courses/{cid}/pages", {"wiki_page": wp})
    if err:
        return False, title, None, err
    if p.get("module_name"):
        mid = _find_or_create_module_id(cid, p["module_name"], notes)
        if mid:
            _add_module_item(cid, mid, {"title": title, "type": "Page",
                                        "page_url": resp.get("url")}, notes)
    return True, resp.get("title", title), resp.get("html_url"), None


def _push_quick(cid, p, notes):
    """Minimal assignment push."""
    name = (p.get("name") or "").strip() or "Untitled"
    a = {"name": name,
         "submission_types": [p.get("submission_type") or "none"],
         "points_possible": float(p.get("points") or 100)}
    if p.get("due_at"):
        a["due_at"] = p["due_at"]
    if p.get("published"):
        a["published"] = True
    if p.get("assignment_group_name"):
        ag = _find_assignment_group(cid, p["assignment_group_name"])
        if ag:
            a["assignment_group_id"] = ag
        else:
            notes.append(
                f"category '{p['assignment_group_name']}' not in this course — using default")
    resp, err = _canvas_send("POST", f"/api/v1/courses/{cid}/assignments", {"assignment": a})
    if err:
        return False, name, None, err
    return True, resp.get("name", name), resp.get("html_url"), None


def _allowed_printable_roots():
    roots = [
        _exports_dir(),
        os.path.join(REPO_ROOT, "Finished_Exports"),
        workspace.workspace_root(),
        TEMP_DIR,
    ]
    out = []
    for root in roots:
        if not root:
            continue
        try:
            out.append(os.path.realpath(root))
        except OSError:
            continue
    return out


def _validate_printable_pdf(path):
    if not path:
        return None, "pdf_path is required"
    candidate = os.path.realpath(path)
    if not os.path.isfile(candidate):
        return None, "printable PDF not found"
    if Path(candidate).suffix.lower() != ".pdf":
        return None, "printable attachment must be a PDF"

    for root in _allowed_printable_roots():
        try:
            if os.path.commonpath([candidate, root]) == root:
                return Path(candidate), None
        except ValueError:
            continue
    return None, "printable PDF is outside Canvas Expert export folders"


def _upload_course_file(course_id, pdf_path):
    pdf, err = _validate_printable_pdf(pdf_path)
    if err:
        return None, err

    filename = pdf.name
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    init_payload = {
        "name": filename,
        "size": pdf.stat().st_size,
        "content_type": content_type,
        "parent_folder_path": "Canvas Expert Printables",
        "on_duplicate": "rename",
    }
    init, err = _canvas_send("POST", f"/api/v1/courses/{course_id}/files", init_payload)
    if err:
        return None, err

    upload_url = (init or {}).get("upload_url")
    upload_params = (init or {}).get("upload_params") or {}
    if not upload_url:
        return None, "Canvas did not return a file upload URL"

    try:
        with pdf.open("rb") as fh:
            response = requests.post(
                upload_url,
                data=upload_params,
                files={"file": (filename, fh, content_type)},
                timeout=60,
            )
    except requests.RequestException as exc:
        return None, str(exc)

    if response.status_code not in (200, 201):
        return None, f"Canvas file upload failed: HTTP {response.status_code}: {response.text[:300]}"
    try:
        return response.json(), None
    except ValueError:
        return None, "Canvas file upload returned a non-JSON response"


def _file_link_html(uploaded_file):
    label = html.escape(
        uploaded_file.get("display_name")
        or uploaded_file.get("filename")
        or "Printable PDF"
    )
    url = uploaded_file.get("url") or uploaded_file.get("html_url") or ""
    if not url and uploaded_file.get("id"):
        url = f"/files/{uploaded_file['id']}/download?download_frd=1"
    if not url:
        return f"<p><strong>{label}</strong> uploaded to course files.</p>"
    return f'<p><a href="{html.escape(str(url), quote=True)}">{label}</a></p>'


def _coerce_points(value):
    if value in (None, ""):
        return 0
    try:
        points = float(value)
    except (TypeError, ValueError):
        return 0
    return int(points) if points.is_integer() else points


def _push_printable_assignment(cid, p, notes):
    pdf_path = p.get("pdf_path") or ""
    fallback_name = Path(pdf_path).stem.replace("_", " ").strip() if pdf_path else ""
    name = (p.get("name") or fallback_name or "Printable notes").strip()

    uploaded, err = _upload_course_file(cid, pdf_path)
    if err:
        return False, name, None, err
    uploaded_name = uploaded.get("display_name") or uploaded.get("filename") or Path(pdf_path).name
    notes.append(f"uploaded file '{uploaded_name}'")

    description = str(p.get("description") or "").strip()
    file_link = _file_link_html(uploaded)
    assignment = {
        "name": name,
        "description": "\n".join(part for part in (description, file_link) if part),
        "submission_types": ["none"],
        "points": _coerce_points(p.get("points")),
        "published": bool(p.get("published")),
    }
    for key in ("due_at", "unlock_at", "lock_at", "assignment_group_name", "module_name"):
        if p.get(key):
            assignment[key] = p[key]

    return _push_assignment(cid, assignment, notes)


_CONTENT_PUSHERS = {
    "quick": _push_quick,
    "printable": _push_printable_assignment,
}
