"""Push business logic extracted from routes/push.py.

Imported by routes/push.py. Keeping Canvas-API calls here makes them
unit-testable without HTTP and keeps route handlers thin.
"""
from .canvas_client import _canvas_get_all, _canvas_send


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


_CONTENT_PUSHERS = {
    "quick": _push_quick,
}
