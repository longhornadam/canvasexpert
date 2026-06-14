"""Course and group API routes for Canvas Expert.

One APIRouter; 3 routes for listing courses, course detail, and group sets.

Routes: GET /api/courses
        GET /api/course-detail
        GET /api/groups
"""
import requests

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_headers

router = APIRouter(tags=["courses"])


@router.get("/api/courses")
def list_all_courses():
    """All courses the saved token can see (used by both settings and dashboard)."""
    data, err = _canvas_get("/api/v1/courses", {"per_page": 100, "state[]": "available"})
    if err:
        return JSONResponse({"ok": False, "error": err})
    courses = [{"id": str(c["id"]), "name": c.get("name", f"course {c['id']}")}
               for c in data if "id" in c]
    courses.sort(key=lambda c: c["name"].lower())
    return JSONResponse({"ok": True, "courses": courses})


@router.get("/api/course-detail")
def course_detail(course_id: str):
    """Everything the Course Info page shows: roster, group sets with member
    names, modules, and upcoming assignments. Several Canvas calls — local
    app, small courses, acceptable latency."""
    students, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100, "include[]": "email"})
    if err:
        return JSONResponse({"ok": False, "error": err})
    name_by_id = {s["id"]: s.get("name", f"user {s['id']}") for s in students}

    cats, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/group_categories", {"per_page": 50})
    group_sets = []
    for cat in cats or []:
        groups, _ = _canvas_get_all(
            f"/api/v1/group_categories/{cat['id']}/groups", {"per_page": 100})
        out = []
        for g in groups or []:
            members, _ = _canvas_get_all(
                f"/api/v1/groups/{g['id']}/memberships", {"per_page": 200})
            out.append({
                "name":    g["name"],
                "members": sorted(name_by_id.get(m["user_id"], f"user {m['user_id']}")
                                  for m in (members or [])),
            })
        group_sets.append({"name": cat["name"], "groups": out})

    modules, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    assignments, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})

    return JSONResponse({
        "ok": True,
        "students": sorted(
            ({"name":          s.get("name", ""),
              "sortable_name": s.get("sortable_name", s.get("name", "")),
              "email":         s.get("email") or ""} for s in students),
            key=lambda s: s["sortable_name"].lower()),
        "group_sets": group_sets,
        "modules": [{"id":          str(m["id"]),
                     "name":        m.get("name", ""),
                     "items_count": m.get("items_count", 0),
                     "published":   m.get("published", True)}
                    for m in (modules or [])],
        "assignments": [{"id":        str(a["id"]),
                         "name":      a.get("name", ""),
                         "due_at":    (a.get("due_at") or "")[:10],
                         "points":    a.get("points_possible"),
                         "published": a.get("published", False),
                         "html_url":  a.get("html_url", "")}
                        for a in (assignments or [])],
    })


@router.get("/api/groups")
def list_groups(course_id: str):
    """Group sets + groups + member IDs for a course (used by diff panel).

    Canvas note (confirmed live 2026-06): teacher PATs may get 403 on every
    /group_categories endpoint (district permission), while
    /courses/:id/groups still returns the same groups with their
    group_category_id. So: try group_categories for proper set names, fall
    back to bucketing /courses/:id/groups by category id.
    """
    hdrs, base = _canvas_headers()
    if not hdrs:
        return JSONResponse({"ok": False, "error": "No token saved."})

    def get(path, params=None):
        try:
            r = requests.get(f"{base}{path}", headers=hdrs,
                             params=params or {}, timeout=20)
            return (r.status_code, r.json() if r.status_code == 200 else None)
        except Exception as e:
            return (0, None)

    def member_ids(group_id):
        st, members = get(f"/api/v1/groups/{group_id}/memberships", {"per_page": 200})
        return [m["user_id"] for m in (members or [])]

    # Preferred path: real group sets with names.
    st, cats = get(f"/api/v1/courses/{course_id}/group_categories", {"per_page": 50})
    if st == 200 and cats:
        result = []
        for cat in cats:
            _, groups_raw = get(f"/api/v1/group_categories/{cat['id']}/groups", {"per_page": 100})
            groups_out = [{
                "id":          str(grp["id"]),
                "name":        grp["name"],
                "student_ids": member_ids(grp["id"]),
            } for grp in (groups_raw or [])]
            result.append({"category_id":   str(cat["id"]),
                           "category_name": cat["name"],
                           "groups":        groups_out})
        return JSONResponse({"ok": True, "categories": result})

    # Fallback: course groups bucketed by category id (category names 403-gated).
    st2, groups_raw = get(f"/api/v1/courses/{course_id}/groups", {"per_page": 100})
    if st2 != 200:
        return JSONResponse({"ok": False,
                             "error": f"Canvas returned {st or st2} for course groups "
                                      f"(group_categories: {st}; groups: {st2})."})
    if not groups_raw:
        return JSONResponse({"ok": True, "categories": [],
                             "message": "No group sets found in this course."})

    buckets = {}
    for grp in groups_raw:
        buckets.setdefault(str(grp.get("group_category_id") or "0"), []).append(grp)
    result = []
    for i, (cat_id, grps) in enumerate(sorted(buckets.items()), start=1):
        result.append({
            "category_id":   cat_id,
            "category_name": "Group set" if len(buckets) == 1 else f"Group set {i}",
            "groups": [{
                "id":          str(grp["id"]),
                "name":        grp["name"],
                "student_ids": member_ids(grp["id"]),
            } for grp in grps],
        })
    return JSONResponse({"ok": True, "categories": result})