"""Gradebook curve routes.

Read-path boundary (locked decision 1, CanvasMirror v3): only the assignment
picker list in ``curve_assignments`` may be mirror-served. ``curve_preview``,
``curve_apply``, ``revert_curve``, ``list_curve_events``, and everything in
``api/operation_ledger/adapters/curve.py`` read score baselines that feed a
Canvas grade write (``posted_grade``) — those reads MUST stay live. Do not
"helpfully" flip them to the mirror in a future edit.
"""
import json
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import mirror_service
from ..canvas_client import _canvas_get, _canvas_send
from ..gradebook_service import _apply_curve_model, _load_curve_events, _save_curve_events
from ..mirror_reads import assignments_or_live
from .gradebook_common import _assignment, _assignment_submissions, _course_assignments, _course_students

router = APIRouter(tags=["gradebook"])

# Test seam preserved (same pattern as gradebook_snapshot.py / mcp_server/tools.py):
# the mirror-first path is only taken when the module-level seam is still the
# original binding. A monkeypatched seam means a test wants the live path
# exercised directly, so we honor that instead of silently detouring through
# the mirror.
_ORIGINAL_COURSE_ASSIGNMENTS = _course_assignments


@router.get("/api/curve/assignments")
def curve_assignments(course_id: str):
    if _course_assignments is _ORIGINAL_COURSE_ASSIGNMENTS:
        assignments, err, _source = assignments_or_live(course_id)
    else:
        assignments, err = _course_assignments(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    out = [{"id": str(a["id"]), "name": a.get("name", ""),
            "points": a.get("points_possible") or 0,
            "due_at": (a.get("due_at") or "")[:10]}
           for a in (assignments or [])
           if a.get("published", True) and (a.get("points_possible") or 0) > 0]
    out.sort(key=lambda a: a["due_at"] or "0000-00-00", reverse=True)
    return JSONResponse({"ok": True, "assignments": out})


@router.post("/api/curve/preview")
def curve_preview(course_id: str = Form(...), assignment_id: str = Form(...),
                  curve_type: str = Form(...), settings: str = Form(...)):
    try:
        s = json.loads(settings)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})

    a, err = _assignment(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    pts = a.get("points_possible") or 0
    aname = a.get("name", assignment_id)

    students, err = _course_students(course_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    name_by_id = {str(st["id"]): (st.get("sortable_name") or st.get("name", ""))
                  for st in students}

    subs, err = _assignment_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})

    scored = [{"user_id": str(sub["user_id"]),
               "student_name": name_by_id.get(str(sub["user_id"]), f"user {sub['user_id']}"),
               "score": sub.get("score")}
              for sub in (subs or []) if sub.get("workflow_state") == "graded"]

    results = _apply_curve_model(scored, curve_type, s, pts)

    def _avg(lst): return round(sum(lst) / len(lst), 1) if lst else None

    orig = [r["original_score"] for r in results]
    curv = [r["curved_score"] for r in results]
    summary = {
        "assignment_name": aname, "points": pts, "n": len(results),
        "original_avg": _avg(orig), "curved_avg": _avg(curv),
        "original_min": min(orig) if orig else None,
        "original_max": max(orig) if orig else None,
        "curved_min": min(curv) if curv else None,
        "curved_max": max(curv) if curv else None,
        "helped": sum(1 for r in results if r["curved_score"] > r["original_score"]),
        "lowered": sum(1 for r in results if r["curved_score"] < r["original_score"]),
        "unchanged": sum(1 for r in results if r["curved_score"] == r["original_score"]),
        "ungraded": len([sub for sub in (subs or [])
                         if sub.get("workflow_state") != "graded" and sub.get("submitted_at")]),
    }
    results.sort(key=lambda r: r["student_name"].lower())
    return JSONResponse({"ok": True, "results": results, "summary": summary})


@router.post("/api/curve/apply")
def curve_apply(course_id: str = Form(...), assignment_id: str = Form(...),
                curve_type: str = Form(...), settings: str = Form(...),
                results: str = Form(...)):
    try:
        s = json.loads(settings)
        rows = json.loads(results)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not rows:
        return JSONResponse({"ok": False, "error": "no rows to apply"})

    a, err = _assignment(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})

    current_subs, _ = _assignment_submissions(course_id, assignment_id)
    current_score_by_uid = {str(sub["user_id"]): sub.get("score")
                            for sub in (current_subs or [])}

    event_id = f"curve_{_uuid.uuid4().hex[:8]}"
    event_students, push_results = [], []

    for r in rows:
        uid = str(r["user_id"])
        curved = r["curved_score"]
        _, err = _canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{uid}",
            {"submission": {"posted_grade": str(curved)}})
        push_results.append({
            "student": r.get("student_name", uid),
            "original": r["original_score"],
            "curved": curved,
            "ok": not err, "error": err,
        })
        event_students.append({
            "user_id": uid, "student_name": r.get("student_name", uid),
            "original_score": r["original_score"], "curved_score": curved,
            "score_at_apply_time": current_score_by_uid.get(uid),
            "changed": r.get("changed", True),
        })

    events = _load_curve_events()
    events.append({
        "id": event_id, "course_id": str(course_id),
        "assignment_id": str(assignment_id), "assignment_name": a.get("name", assignment_id),
        "curve_type": curve_type, "curve_settings": s,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "reverted": False, "students": event_students,
    })
    _save_curve_events(events)
    all_ok = all(r["ok"] for r in push_results)
    if any(r["ok"] for r in push_results):
        try:
            mirror_service.notify_course_changed(course_id)
        except Exception:
            pass
    return JSONResponse({"ok": all_ok, "event_id": event_id, "results": push_results})


@router.get("/api/curve/events")
def list_curve_events(course_id: str, assignment_id: str = ""):
    events = [e for e in _load_curve_events()
              if e["course_id"] == str(course_id)
              and (not assignment_id or e["assignment_id"] == str(assignment_id))
              and not e.get("reverted")]
    events.sort(key=lambda e: e["applied_at"], reverse=True)
    return JSONResponse({"ok": True, "events": [{k: v for k, v in e.items() if k != "students"} for e in events]})


@router.post("/api/curve/revert")
def revert_curve(event_id: str = Form(...), course_id: str = Form(...),
                 user_ids: str = Form("[]")):
    try:
        target_uids = set(json.loads(user_ids)) or None
    except json.JSONDecodeError:
        target_uids = None

    events = _load_curve_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        return JSONResponse({"ok": False, "error": f"event {event_id!r} not found"})

    aid = event["assignment_id"]
    push_results = []

    for st in event["students"]:
        uid = str(st["user_id"])
        if target_uids and uid not in target_uids:
            continue
        current_sub, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{aid}/submissions/{uid}")
        current_score = current_sub.get("score") if current_sub else None
        drifted = (current_score is not None and st.get("curved_score") is not None
                   and abs(float(current_score) - float(st["curved_score"])) > 0.01)
        _, err = _canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{aid}/submissions/{uid}",
            {"submission": {"posted_grade": str(st["original_score"])}})
        push_results.append({
            "student": st["student_name"], "reverted_to": st["original_score"],
            "score_was": current_score, "warned_drift": drifted, "ok": not err, "error": err,
        })

    all_ok = all(r["ok"] for r in push_results)
    if all_ok and not target_uids:
        for e in events:
            if e["id"] == event_id:
                e["reverted"] = True
    _save_curve_events(events)
    if any(r["ok"] for r in push_results):
        try:
            mirror_service.notify_course_changed(course_id)
        except Exception:
            pass
    return JSONResponse({"ok": all_ok, "results": push_results})
