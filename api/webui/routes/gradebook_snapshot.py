"""Gradebook whole-course snapshot route."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .gradebook_common import _course_assignments, _course_students, _course_submissions

router = APIRouter(tags=["gradebook"])


def build_snapshot(students, assignments, subs) -> dict:
    """Pure aggregation: per-assignment and per-student stats for a whole course.

    Student rows additionally carry ``user_id`` (string) so callers that need Canvas
    identity (e.g. the MCP gradebook tool, to key the pseudonym vault) can use it;
    the route below strips it before returning JSON so the wire shape is unchanged."""
    smap = {s["id"]: {"name": s.get("sortable_name") or s.get("name", ""),
                      "missing": 0, "late": 0, "ungraded": 0,
                      "score": 0.0, "possible": 0.0}
            for s in students}
    amap = {}
    for a in assignments:
        if not a.get("published", True):
            continue
        amap[a["id"]] = {
            "name":     a.get("name", ""),
            "due_at":   (a.get("due_at") or "")[:10],
            "points":   a.get("points_possible") or 0,
            "html_url": a.get("html_url", ""),
            "submitted": 0, "graded": 0, "missing": 0, "late": 0,
            "score_sum": 0.0, "score_n": 0,
        }

    for sub in subs:
        a = amap.get(sub.get("assignment_id"))
        s = smap.get(sub.get("user_id"))
        if not a or sub.get("excused"):
            continue
        state = sub.get("workflow_state", "")
        if sub.get("submitted_at"):
            a["submitted"] += 1
        if sub.get("missing"):
            a["missing"] += 1
            if s:
                s["missing"] += 1
        if sub.get("late"):
            a["late"] += 1
            if s:
                s["late"] += 1
        if state == "graded" and sub.get("score") is not None:
            a["graded"] += 1
            a["score_sum"] += sub["score"]
            a["score_n"] += 1
            if s and a["points"]:
                s["score"] += sub["score"]
                s["possible"] += a["points"]
        elif sub.get("submitted_at") and state in ("submitted", "pending_review"):
            if s:
                s["ungraded"] += 1

    out_assignments = []
    for aid, a in amap.items():
        avg = (round(a["score_sum"] / a["score_n"] / a["points"] * 100)
               if a["score_n"] and a["points"] else None)
        out_assignments.append({
            "id": str(aid), "name": a["name"], "due_at": a["due_at"],
            "points": a["points"], "html_url": a["html_url"],
            "submitted": a["submitted"], "graded": a["graded"],
            "missing": a["missing"], "late": a["late"], "avg_pct": avg,
        })
    out_assignments.sort(key=lambda a: a["due_at"] or "0000-00-00", reverse=True)

    out_students = []
    for sid, s in smap.items():
        pct = (round(s["score"] / s["possible"] * 100, 1)
               if s["possible"] else None)
        out_students.append({"name": s["name"], "user_id": str(sid),
                             "missing": s["missing"],
                             "late": s["late"], "ungraded": s["ungraded"],
                             "pct": pct})
    out_students.sort(key=lambda s: s["name"].lower())

    graded_pcts = [s["pct"] for s in out_students if s["pct"] is not None]
    class_avg = round(sum(graded_pcts) / len(graded_pcts), 1) if graded_pcts else None

    return {
        "ok": True,
        "class_avg": class_avg,
        "student_count": len(out_students),
        "total_missing": sum(s["missing"] for s in out_students),
        "total_ungraded": sum(a["submitted"] - a["graded"]
                              for a in out_assignments if a["submitted"] > a["graded"]),
        "assignments": out_assignments,
        "students": out_students,
    }


@router.get("/api/gradebook")
def api_gradebook(course_id: str):
    """Whole-course grading snapshot: per-assignment and per-student stats."""
    students, err = _course_students(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    assignments, err = _course_assignments(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    subs, err = _course_submissions(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})

    snapshot = build_snapshot(students, assignments, subs)
    snapshot["students"] = [
        {k: v for k, v in s.items() if k != "user_id"}
        for s in snapshot["students"]
    ]
    return JSONResponse(snapshot)
