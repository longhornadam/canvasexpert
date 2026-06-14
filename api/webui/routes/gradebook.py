"""Gradebook routes for Canvas Expert.

APIRouter for gradebook operations: sweep, curves, extensions, and snapshot.

Routes:
    GET  /api/gradebook - whole-course grading snapshot
    POST /api/sweep/apply - apply late work sweep
    POST /api/sweep/preview - preview sweep results
    POST /api/curve/apply - apply curve
    GET  /api/curve/events - curve event history
    POST /api/curve/preview - preview curve
    POST /api/curve/revert - revert curve
    POST /api/extend-due - extend due date for students
    GET  /api/extra-time - extra time roster
    POST /api/extra-time - set extra time for students
    POST /api/late-policy - get/set late policy
    POST /api/late-policy/apply - apply late policy
"""
import json
import os
import threading
import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse

from .. import config, activity
from ..canvas_client import _canvas_get_all
from ..gradebook_service import (
    _load_curve_events, _save_curve_events, _apply_curve_model,
    _split_for_extra_time, _expand_variants_extra_time, _sweep_compute,
    CURVE_EVENTS_PATH,
)
from ..schooldays import (
    _parse_iso_local, _is_school_day, _school_days_late,
    _school_days_late_detail, _add_school_days,
)

router = APIRouter(tags=["gradebook"])


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/api/gradebook")
def api_gradebook(course_id: str):
    """Whole-course grading snapshot: per-assignment and per-student stats."""
    students, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    assignments, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100}, timeout=60)
    if err:
        return JSONResponse({"ok": False, "error": err})

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
            a["score_n"]  += 1
            if s and a["points"]:
                s["score"]    += sub["score"]
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
    for s in smap.values():
        pct = (round(s["score"] / s["possible"] * 100, 1)
               if s["possible"] else None)
        out_students.append({"name": s["name"], "missing": s["missing"],
                             "late": s["late"], "ungraded": s["ungraded"],
                             "pct": pct})
    out_students.sort(key=lambda s: s["name"].lower())

    graded_pcts = [s["pct"] for s in out_students if s["pct"] is not None]
    class_avg = round(sum(graded_pcts) / len(graded_pcts), 1) if graded_pcts else None

    return JSONResponse({
        "ok": True,
        "class_avg":     class_avg,
        "student_count": len(out_students),
        "total_missing": sum(s["missing"] for s in out_students),
        "total_ungraded": sum(a["submitted"] - a["graded"]
                              for a in out_assignments if a["submitted"] > a["graded"]),
        "assignments":   out_assignments,
        "students":      out_students,
    })


# --------------------------------------------------------------------------
# Late policy routes
# --------------------------------------------------------------------------

@router.get("/api/late-policy")
def get_late_policy(course_id: str):
    from ..canvas_client import _canvas_get
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/late_policy")
    if err and "404" in err:
        return JSONResponse({"ok": True, "policy": None})
    if err:
        return JSONResponse({"ok": False, "error": err})
    return JSONResponse({"ok": True, "policy": data.get("late_policy")})


@router.post("/api/late-policy/apply")
def apply_late_policy(courses: str = Form(...), policy: str = Form(...)):
    """Create or update the Canvas late policy in every target course."""
    from ..canvas_client import _canvas_get, _canvas_send
    try:
        targets = json.loads(courses)
        p = json.loads(policy)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not targets:
        return JSONResponse({"ok": False, "error": "no courses selected"})

    results = []
    for t in targets:
        cid   = str(t.get("id", ""))
        cname = t.get("name", f"course {cid}")
        existing, gerr = _canvas_get(f"/api/v1/courses/{cid}/late_policy")
        if gerr and "404" not in gerr:
            results.append({"course_name": cname, "ok": False, "error": gerr})
            continue
        method = "PATCH" if (existing and not gerr) else "POST"
        _, err = _canvas_send(method, f"/api/v1/courses/{cid}/late_policy",
                              {"late_policy": p})
        results.append({"course_name": cname, "ok": not err, "error": err,
                        "title": f"late policy {'updated' if method == 'PATCH' else 'created'}"})
    return JSONResponse({"ok": all(r["ok"] for r in results), "results": results})


# --------------------------------------------------------------------------
# Students + extra-time roster
# --------------------------------------------------------------------------

@router.get("/api/students/list")
def list_students(course_id: str):
    from ..canvas_client import _canvas_get_all
    students, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    out = sorted(
        ({"id": str(s["id"]),
          "name": s.get("sortable_name") or s.get("name", "")} for s in students),
        key=lambda s: s["name"].lower())
    return JSONResponse({"ok": True, "students": out})


@router.get("/api/extra-time")
def get_extra_time(course_id: str):
    return JSONResponse({"ok": True,
                         "students": config.get_extra_time(course_id),
                         "sweep_settings": config.get_sweep_settings()})


@router.post("/api/extra-time")
def save_extra_time(course_id: str = Form(...), students: str = Form(...)):
    try:
        config.set_extra_time(course_id, json.loads(students))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------
# Tier display tags
# --------------------------------------------------------------------------

@router.get("/api/tier-tags")
def get_tier_tags_route():
    return JSONResponse({"ok": True, "tier_tags": config.get_tier_tags()})


@router.post("/api/tier-tags")
def save_tier_tags(tags: str = Form(...)):
    try:
        config.set_tier_tags(json.loads(tags))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    return JSONResponse({"ok": True, "tier_tags": config.get_tier_tags()})


# --------------------------------------------------------------------------
# Extensions (assignment overrides)
# --------------------------------------------------------------------------

@router.post("/api/extend-due")
def extend_due(course_id: str = Form(...), assignment_id: str = Form(...),
               student_ids: str = Form(...), days: int = Form(...),
               skip_weekends: str = Form("true"), holidays: str = Form("[]")):
    """Give specific students +N school days on one assignment."""
    from ..canvas_client import _canvas_get, _canvas_send
    try:
        sids = json.loads(student_ids)
        hols = set(json.loads(holidays))
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not sids:
        return JSONResponse({"ok": False, "error": "no students selected"})
    skip_we = skip_weekends.lower() in ("true", "1", "yes")
    hols.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])

    a, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    due = _parse_iso_local(a.get("due_at"))
    if not due:
        return JSONResponse({"ok": False,
                             "error": "assignment has no due date — set one in Canvas first"})

    new_due = _add_school_days(due, days, skip_we, hols)
    resp, err = _canvas_send(
        "POST", f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
        {"assignment_override": {
            "student_ids": sids,
            "title":       f"Extra time (+{days} school day{'s' if days != 1 else ''})",
            "due_at":      new_due.isoformat(),
        }})
    if err:
        hint = (" (a student can only be in one override per assignment — "
                "check existing overrides in Canvas)" if "400" in err else "")
        return JSONResponse({"ok": False, "error": err + hint})
    return JSONResponse({"ok": True,
                         "assignment": a.get("name", ""),
                         "new_due": new_due.isoformat(),
                         "count": len(sids)})


# --------------------------------------------------------------------------
# Sweep (late work sweep)
# --------------------------------------------------------------------------

@router.post("/api/sweep/preview")
def sweep_preview(course_id: str = Form(...), settings: str = Form(...)):
    """Dry run — compute every late deduction + the comment text, change nothing."""
    try:
        s = json.loads(settings)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    config.set_sweep_settings(s)
    entries, skipped, err = _sweep_compute(course_id, s)
    if err:
        return JSONResponse({"ok": False, "error": err})
    return JSONResponse({"ok": True, "entries": entries, "skipped": skipped})


@router.post("/api/sweep/apply")
def sweep_apply(course_id: str = Form(...), entries: str = Form(...)):
    """Push seconds_late_override to Canvas for selected late submissions."""
    from ..canvas_client import _canvas_send
    try:
        rows = json.loads(entries)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not rows:
        return JSONResponse({"ok": False, "error": "no rows selected"})

    results = []
    for r in rows:
        _, err = _canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{r['assignment_id']}/submissions/{r['user_id']}",
            {"submission": {
                "late_policy_status": "late",
                "seconds_late_override": r["seconds_override"],
            }})
        results.append({
            "student": r.get("student_name", r["user_id"]),
            "assignment": r.get("assignment_name", r["assignment_id"]),
            "school_days": r["school_days"],
            "ok": not err, "error": err,
        })
    return JSONResponse({"ok": all(x["ok"] for x in results), "results": results})


# --------------------------------------------------------------------------
# Curves
# --------------------------------------------------------------------------

@router.get("/api/curve/assignments")
def curve_assignments(course_id: str):
    from ..canvas_client import _canvas_get_all
    assignments, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})
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
    from ..canvas_client import _canvas_get, _canvas_get_all
    try:
        s = json.loads(settings)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})

    a, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    pts = a.get("points_possible") or 0
    aname = a.get("name", assignment_id)

    students, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    name_by_id = {str(st["id"]): (st.get("sortable_name") or st.get("name", ""))
                  for st in students}

    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100})
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
    from ..canvas_client import _canvas_get, _canvas_send
    try:
        s = json.loads(settings)
        rows = json.loads(results)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not rows:
        return JSONResponse({"ok": False, "error": "no rows to apply"})

    a, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})

    current_subs, _ = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"per_page": 100})
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
    activity.log_event("curve_apply", a.get("name", assignment_id),
                       [course_id], all_ok, detail=f"{curve_type}, {len(push_results)} students")
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
    from ..canvas_client import _canvas_get, _canvas_send
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
    return JSONResponse({"ok": all_ok, "results": push_results})