"""Routines router for Canvas Expert.

Local automation: run on demand, on launch, and every 30 min.
No external scheduler (locked-down district machines), no cloud, ever.
"""
import glob
import json
import os
import threading
import time as _time
import traceback
import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import downloader
import student_packet
from .. import config, activity
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_send
from ..deps import _CUSTOM_DIR
from ..gradebook_service import (
    _load_curve_events, _save_curve_events, _apply_curve_model,
)
from ..schooldays import _school_days_late, _parse_iso_local

router = APIRouter(prefix="/api", tags=["routines"])

# --------------------------------------------------------------------------
# Routine definitions
# --------------------------------------------------------------------------

_ROUTINE_DEFS = {
    "sweep": {
        "label": "Auto-sweep late work",
        "writes": True,
        "default": {"enabled": False, "every_hours": 24,
                    "params": {"window_days": 30}},
    },
    "download": {
        "label": "Auto-download new student work",
        "writes": False,
        "default": {"enabled": False, "every_hours": 24,
                    "params": {"window_days": 14}},
    },
    "curve": {
        "label": "Auto-curve low assignment averages",
        "writes": True,
        "default": {"enabled": False, "every_hours": 168,
                    "params": {"floor": 80, "mode": "flag", "window_days": 30}},
    },
    "grading_debt": {
        "label": "Grading-debt report",
        "writes": False,
        "default": {"enabled": True, "every_hours": 24,
                    "params": {"school_days": 3}},
    },
    "student_reports": {
        "label": "Refresh monitored-student reports",
        "writes": False,
        "default": {"enabled": False, "every_hours": 168,
                    "params": {}},
    },
}

_ROUTINES_LOCK = threading.Lock()


def _routine_state(rid):
    saved = config.get_routine_states().get(rid, {})
    base = json.loads(json.dumps(_ROUTINE_DEFS[rid]["default"]))
    base["params"].update(saved.get("params", {}))
    for k in ("enabled", "every_hours", "last_run", "last_summary"):
        if k in saved:
            base[k] = saved[k]
    return base


def _routine_due(state):
    if not state.get("last_run"):
        return True
    try:
        last = datetime.fromisoformat(state["last_run"])
        hours = state.get("every_hours", 24)
        return datetime.now() >= last + timedelta(hours=hours)
    except (ValueError, TypeError):
        return True


# --------------------------------------------------------------------------
# Routine runners
# --------------------------------------------------------------------------

def _run_routine_sweep(params):
    from ..schooldays import _school_days_late_detail
    skip_we = params.get("skip_weekends", True)
    hols = set(params.get("holidays", []))
    hols.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])
    window = int(params.get("window_days", 30))
    cutoff = (datetime.now().date() - timedelta(days=window)).isoformat()

    lines, ok, total = [], True, 0
    for c in config.active_courses():
        cid = str(c["id"])
        asgns, err = _canvas_get_all(f"/api/v1/courses/{cid}/assignments", {"per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        amap = {a["id"]: a for a in (asgns or [])
                if a.get("published", True) and (a.get("points_possible") or 0) > 0
                and ((a.get("due_at") or "")[:10] >= cutoff)}
        if not amap:
            lines.append(f"· {c['nickname']}: nothing due in window")
            continue

        subs, err = _canvas_get_all(f"/api/v1/courses/{cid}/students/submissions",
                                    {"student_ids[]": "all", "per_page": 100}, timeout=90)
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue

        students, err = _canvas_get_all(f"/api/v1/courses/{cid}/users",
                                        {"enrollment_type[]": "student", "per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        name_by_id = {str(s["id"]): (s.get("sortable_name") or s.get("name", ""))
                      for s in students}

        extra = {str(e["id"]): int(e.get("days", 1))
                 for e in config.get_extra_time(cid)} if params.get("honor_extra_time", True) else {}

        for sub in (subs or []):
            if sub.get("excused") or not sub.get("submitted_at"):
                continue
            a = amap.get(sub.get("assignment_id"))
            if not a:
                continue
            due = _parse_iso_local(sub.get("cached_due_date") or a.get("due_at"))
            submitted = _parse_iso_local(sub.get("submitted_at"))
            if not due or not submitted:
                continue
            raw_days, excluded = _school_days_late_detail(due, submitted, skip_we, hols)
            if raw_days <= 0:
                continue
            uid = str(sub.get("user_id"))
            school_days = max(raw_days - extra.get(uid, 0), 0)
            if school_days <= 0:
                continue

            _, err = _canvas_send("PUT",
                f"/api/v1/courses/{cid}/assignments/{a['id']}/submissions/{uid}",
                {"submission": {"late_policy_status": "late",
                                "seconds_late_override": school_days * 86400}})
            if err:
                lines.append(f"✗ {name_by_id.get(uid, uid)}/{a.get('name','')}: {err}")
                ok = False
            else:
                total += 1
            lines.append(f"✓ {name_by_id.get(uid, uid)}/{a.get('name','')}: {school_days} school days late")

    return {"ok": ok, "lines": lines,
            "summary": f"{total} late submission(s) corrected"}


def _run_routine_download(params):
    window = int(params.get("window_days", 14))
    cutoff = (datetime.now().date() - timedelta(days=window)).isoformat()
    token, base, root = config.get_token(), config.get_canvas_base(), config.get_download_root()
    if not token:
        return {"ok": False, "lines": ["✗ no Canvas token saved"], "summary": "no token"}
    DOWNLOADABLE = {"online_text_entry", "online_upload", "online_url", "discussion_topic"}
    lines, ok, total = [], True, 0
    for c in config.active_courses():
        asgns, err = _canvas_get_all(f"/api/v1/courses/{c['id']}/assignments", {"per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        ids = [str(a["id"]) for a in (asgns or [])
               if (a.get("due_at") or "")[:10] >= cutoff
               and set(a.get("submission_types") or []) & DOWNLOADABLE]
        if not ids:
            lines.append(f"· {c['nickname']}: nothing due in window")
            continue
        errs = 0
        for line in downloader.run_download(str(c["id"]), c["name"], ids, base, token, root):
            if line.strip().startswith("!!"):
                errs += 1
        total += len(ids)
        if errs:
            ok = False
        lines.append(f"✓ {c['nickname']}: refreshed {len(ids)} assignment folder(s)"
                     + (f" ({errs} error(s))" if errs else ""))
    return {"ok": ok, "lines": lines,
            "summary": f"{total} assignment folder(s) refreshed"}


def _run_routine_curve(params):
    floor = float(params.get("floor", 80))
    mode = params.get("mode", "flag")
    window = int(params.get("window_days", 30))
    cutoff = (datetime.now().date() - timedelta(days=window)).isoformat()
    curved_already = {(e["course_id"], e["assignment_id"])
                      for e in _load_curve_events() if not e.get("reverted")}
    lines, ok, flagged, applied = [], True, 0, 0
    for c in config.active_courses():
        cid = str(c["id"])
        asgns, err = _canvas_get_all(f"/api/v1/courses/{cid}/assignments", {"per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        for a in (asgns or []):
            pts = a.get("points_possible") or 0
            if not a.get("published", True) or pts <= 0:
                continue
            if (a.get("due_at") or "")[:10] < cutoff:
                continue
            aid = str(a["id"])
            if (cid, aid) in curved_already:
                continue
            subs, err = _canvas_get_all(f"/api/v1/courses/{cid}/assignments/{aid}/submissions",
                                        {"per_page": 100})
            if err:
                continue
            scores = [s_.get("score") for s_ in (subs or [])
                      if s_.get("workflow_state") == "graded" and s_.get("score") is not None]
            if len(scores) < 3:
                continue
            avg_pct = sum(scores) / len(scores) / pts * 100
            if avg_pct >= floor:
                continue
            flagged += 1
            if mode != "apply":
                lines.append(f"⚑ {c['nickname']}: \"{a.get('name','')}\" avg {avg_pct:.1f}% < {floor:g}%")
                continue
            students, err = _canvas_get_all(f"/api/v1/courses/{cid}/users",
                                            {"enrollment_type[]": "student", "per_page": 100})
            name_by_id = {str(st["id"]): (st.get("sortable_name") or st.get("name", ""))
                          for st in (students or [])}
            scored = [{"user_id": str(s_["user_id"]),
                       "student_name": name_by_id.get(str(s_["user_id"]), str(s_["user_id"])),
                       "score": s_.get("score")}
                      for s_ in (subs or []) if s_.get("workflow_state") == "graded"]
            settings = {"target_avg_pct": floor, "do_no_harm": True}
            rows = _apply_curve_model(scored, "target_average", settings, pts)
            rows = [r for r in rows if r["changed"]]
            if not rows:
                continue
            all_ok, event_id, _ = _curve_apply_core(cid, aid, "target_average", settings, rows)
            ok = ok and all_ok
            applied += 1
            lines.append(f"✓ {c['nickname']}: curved \"{a.get('name','')}\" {avg_pct:.1f}% → {floor:g}% ({len(rows)} students)")
    summary = f"{applied} assignment(s) curved" if mode == "apply" else f"{flagged} assignment(s) flagged below {floor:g}%"
    return {"ok": ok, "lines": lines or ["· all assignment averages at or above the floor"], "summary": summary}


def _run_routine_grading_debt(params):
    min_days = int(params.get("school_days", 3))
    sweep_s = config.get_sweep_settings()
    hols = set(sweep_s.get("holidays") or [])
    hols.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])
    now_dt = datetime.now().astimezone()
    lines, ok, total = [], True, 0
    for c in config.active_courses():
        cid = str(c["id"])
        amap_raw, err = _canvas_get_all(f"/api/v1/courses/{cid}/assignments", {"per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        aname = {str(a["id"]): a.get("name", "") for a in (amap_raw or [])}
        subs, err = _canvas_get_all(f"/api/v1/courses/{cid}/students/submissions",
                                    {"student_ids[]": "all", "per_page": 100})
        if err:
            lines.append(f"✗ {c['nickname']}: {err}")
            ok = False
            continue
        debts = []
        for s_ in (subs or []):
            if s_.get("workflow_state") != "submitted" or not s_.get("submitted_at"):
                continue
            sub_dt = _parse_iso_local(s_["submitted_at"])
            if not sub_dt:
                continue
            days = _school_days_late(sub_dt, now_dt, sweep_s.get("skip_weekends", True), hols)
            if days >= min_days:
                debts.append((days, aname.get(str(s_.get("assignment_id")), "?")))
        total += len(debts)
        if debts:
            debts.sort(reverse=True)
            oldest = ", ".join(f"\"{n}\" ({d}d)" for d, n in debts[:3])
            lines.append(f"⚑ {c['nickname']}: {len(debts)} ungraded > {min_days} school days — oldest: {oldest}")
        else:
            lines.append(f"✓ {c['nickname']}: no grading debt")
    return {"ok": ok, "lines": lines,
            "summary": f"{total} ungraded submission(s) older than {min_days} school days"}


def _run_routine_student_reports(params):
    mon = config.get_monitored_students()
    if not mon:
        return {"ok": True, "lines": ["· no monitored students"], "summary": "0 students"}
    base, token = config.get_canvas_base(), config.get_token()
    if not token:
        return {"ok": False, "lines": ["✗ no token"], "summary": "no token"}
    root = config.get_student_reports_root()
    courses = [{"id": c["id"], "name": c["name"]} for c in config.active_courses()]
    events = _load_curve_events()
    lines, ok, n = [], True, 0
    for uid, v in mon.items():
        try:
            for line in student_packet.build_packet(uid, v["name"], student_packet.SECTIONS, courses,
                                                    base, token, root, events, skip_unchanged=True):
                if line.startswith("FOLDER:"):
                    continue
                if line.startswith("!!"):
                    ok = False
                lines.append("  " + line)
            n += 1
        except Exception as e:
            ok = False
            lines.append(f"✗ {v['name']}: {e}")
    return {"ok": ok, "lines": lines, "summary": f"{n} monitored student packet(s) refreshed"}


# --------------------------------------------------------------------------
# Curve helpers (routines-specific: apply core + revert)
# --------------------------------------------------------------------------

def _curve_apply_core(course_id, assignment_id, curve_type, settings, rows):
    a, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return False, None, [{"error": err}]
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
        push_results.append({"student": r.get("student_name", uid),
                             "original": r["original_score"],
                             "curved": curved, "ok": not err, "error": err})
        event_students.append({"user_id": uid, "student_name": r.get("student_name", uid),
                               "original_score": r["original_score"], "curved_score": curved,
                               "score_at_apply_time": current_score_by_uid.get(uid),
                               "changed": r.get("changed", True)})
    events = _load_curve_events()
    events.append({"id": event_id, "course_id": str(course_id),
                   "assignment_id": str(assignment_id),
                   "assignment_name": a.get("name", assignment_id),
                   "curve_type": curve_type, "curve_settings": settings,
                   "applied_at": datetime.now().isoformat(timespec="seconds"),
                   "reverted": False, "students": event_students})
    _save_curve_events(events)
    all_ok = all(r["ok"] for r in push_results)
    activity.log_event("curve_apply", a.get("name", assignment_id), [course_id], all_ok,
                       detail=f"{curve_type}, {len(push_results)} students")
    return all_ok, event_id, push_results


# --------------------------------------------------------------------------
# Custom routine loader
# --------------------------------------------------------------------------

def routine(rid, label, writes=False, default=None):
    def deco(fn):
        if rid in _ROUTINE_DEFS:
            print(f"[routines] custom '{rid}' collides with a built-in — skipped")
            return fn
        _ROUTINE_DEFS[rid] = {"label": label, "writes": bool(writes),
                              "default": default or {"enabled": False, "every_hours": 24, "params": {}}, "custom": True}
        _ROUTINE_RUNNERS[rid] = fn
        return fn
    return deco

_ROUTINE_RUNNERS = {
    "sweep": _run_routine_sweep, "download": _run_routine_download,
    "curve": _run_routine_curve, "grading_debt": _run_routine_grading_debt,
    "student_reports": _run_routine_student_reports,
}


def _routine_sdk():
    return {"routine": routine, "canvas_get": _canvas_get, "canvas_get_all": _canvas_get_all,
            "canvas_send": _canvas_send, "active_courses": config.active_courses,
            "sweep_settings": config.get_sweep_settings,
            "combined_calendar": config.get_combined_calendar_for_range,
            "school_days_late": _school_days_late, "parse_iso_local": _parse_iso_local,
            "datetime": datetime, "timedelta": timedelta}


def _load_custom_routines():
    if not os.path.isdir(_CUSTOM_DIR):
        return
    for path in sorted(glob.glob(os.path.join(_CUSTOM_DIR, "*.py"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
            g = _routine_sdk()
            g["__name__"] = "custom_routine_" + os.path.splitext(os.path.basename(path))[0]
            g["__file__"] = path
            exec(compile(src, path, "exec"), g)
        except Exception:
            print(f"[routines] failed to load {os.path.basename(path)}:\n" + traceback.format_exc())


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/routines")
def api_routines():
    out = []
    for rid, meta in _ROUTINE_DEFS.items():
        st = _routine_state(rid)
        out.append({"id": rid, "label": meta["label"], "writes": meta["writes"],
                    "custom": meta.get("custom", False), "enabled": st["enabled"],
                    "every_hours": st["every_hours"], "params": st["params"],
                    "last_run": st.get("last_run"), "last_summary": st.get("last_summary"),
                    "due": _routine_due(st)})
    return JSONResponse({"ok": True, "routines": out})


@router.post("/routines/save")
def api_routines_save(routine_id: str = Form(...), patch: str = Form(...)):
    if routine_id not in _ROUTINE_DEFS:
        return JSONResponse({"ok": False, "error": "unknown routine"})
    try:
        p = json.loads(patch)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad patch: {e}"})
    allowed = {k: v for k, v in p.items() if k in ("enabled", "every_hours", "params")}
    config.set_routine_state(routine_id, allowed)
    return JSONResponse({"ok": True})


@router.post("/routines/run")
def api_routines_run(ids: str = Form(""), force: bool = Form(False)):
    id_list = [i.strip() for i in ids.split(",") if i.strip()] or None
    if not _ROUTINES_LOCK.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "a routine run is already in progress"})
    try:
        report = {"ok": True, "ran": [], "skipped": []}
        for rid, meta in _ROUTINE_DEFS.items():
            if id_list is not None and rid not in id_list:
                continue
            state = _routine_state(rid)
            if not force and (not state["enabled"] or not _routine_due(state)):
                report["skipped"].append({"id": rid, "label": meta["label"],
                                          "reason": "disabled" if not state["enabled"] else "not due"})
                continue
            try:
                res = _ROUTINE_RUNNERS[rid](state["params"])
            except Exception as e:
                res = {"ok": False, "lines": [f"✗ crashed: {e}"], "summary": str(e)}
            report["ok"] = report["ok"] and res["ok"]
            report["ran"].append({"id": rid, "label": meta["label"], **res})
            config.set_routine_state(rid, {"last_run": datetime.now().isoformat(timespec="seconds"),
                                           "last_summary": res["summary"]})
            activity.log_event("routine", meta["label"], ["(all active)"], res["ok"], detail=res["summary"])
        return JSONResponse(report)
    finally:
        _ROUTINES_LOCK.release()


# --------------------------------------------------------------------------
# Background thread
# --------------------------------------------------------------------------

def _routines_heartbeat():
    _time.sleep(90)
    while True:
        try:
            if config.token_is_set():
                _run_routines_bg()
        except Exception:
            pass
        _time.sleep(1800)


def _run_routines_bg():
    for rid, meta in _ROUTINE_DEFS.items():
        if not meta.get("custom"):
            state = _routine_state(rid)
            if state["enabled"] and _routine_due(state):
                try:
                    res = _ROUTINE_RUNNERS[rid](state["params"])
                    config.set_routine_state(rid, {"last_run": datetime.now().isoformat(timespec="seconds"),
                                                   "last_summary": res["summary"]})
                except Exception:
                    pass