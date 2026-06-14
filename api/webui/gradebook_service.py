"""Gradebook business logic extracted from routes/gradebook.py.

Imported by routes/gradebook.py, routes/push.py, and routes/routines.py.
Keeping service functions here breaks circular-import risk and makes them
unit-testable without HTTP.
"""
import json
import os

from . import config
from .canvas_client import _canvas_get_all
from .deps import WEBUI_DIR
from .schooldays import _parse_iso_local, _add_school_days, _school_days_late_detail

CURVE_EVENTS_PATH = os.path.join(WEBUI_DIR, "curve_events.json")


def _load_curve_events():
    try:
        with open(CURVE_EVENTS_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("events", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_curve_events(events):
    with open(CURVE_EVENTS_PATH, "w", encoding="utf-8") as fh:
        json.dump({"events": events}, fh, indent=2)


def _apply_curve_model(scored_students, curve_type, settings, points_possible):
    pts = float(points_possible or 100)
    valid = [(s["user_id"], s["student_name"], float(s["score"]))
             for s in scored_students if s.get("score") is not None]
    results = []

    if curve_type == "flat_bump":
        bump = float(settings.get("bump", 0))
        cap = float(settings.get("cap", pts)) if settings.get("cap") not in (None, "") else pts
        do_no_harm = bool(settings.get("do_no_harm", False))
        for uid, name, score in valid:
            new_s = min(score + bump, cap)
            if do_no_harm:
                new_s = max(new_s, score)
            new_s = round(new_s, 2)
            results.append({"user_id": uid, "student_name": name,
                            "original_score": score, "curved_score": new_s,
                            "changed": new_s != score})

    elif curve_type == "target_average":
        if not valid:
            return []
        target = pts * float(settings.get("target_avg_pct", 75)) / 100
        cap = float(settings.get("cap", pts)) if settings.get("cap") not in (None, "") else pts
        do_no_harm = bool(settings.get("do_no_harm", True))
        current_avg = sum(s for _, _, s in valid) / len(valid)
        bump = target - current_avg
        for uid, name, score in valid:
            new_s = min(score + bump, cap)
            if do_no_harm:
                new_s = max(new_s, score)
            new_s = round(new_s, 2)
            results.append({"user_id": uid, "student_name": name,
                            "original_score": score, "curved_score": new_s,
                            "changed": new_s != score})

    elif curve_type == "proportional":
        if not valid:
            return []
        target = pts * float(settings.get("target_avg_pct", 75)) / 100
        cap = float(settings.get("cap", pts)) if settings.get("cap") not in (None, "") else pts
        do_no_harm = bool(settings.get("do_no_harm", True))
        current_avg = sum(s for _, _, s in valid) / len(valid)
        total_lift = (target - current_avg) * len(valid)
        max_score = max(s for _, _, s in valid) or 1
        weights = [max_score - s + 1 for _, _, s in valid]
        total_w = sum(weights)
        for (uid, name, score), w in zip(valid, weights):
            lift = (w / total_w * total_lift) if total_w else 0
            new_s = min(score + lift, cap)
            if do_no_harm:
                new_s = max(new_s, score)
            new_s = round(new_s, 2)
            results.append({"user_id": uid, "student_name": name,
                            "original_score": score, "curved_score": new_s,
                            "changed": new_s != score})

    elif curve_type == "floor_cap":
        floor_pts = float(settings.get("floor", 0))
        cap_pts = float(settings.get("cap", pts)) if settings.get("cap") not in (None, "") else pts
        for uid, name, score in valid:
            new_s = round(max(min(score, cap_pts), floor_pts), 2)
            results.append({"user_id": uid, "student_name": name,
                            "original_score": score, "curved_score": new_s,
                            "changed": new_s != score})
    return results


def _split_for_extra_time(course_id, student_ids, base_due_iso, base_lock_iso=None):
    """Partition a tier's student_ids by the course extra-time roster."""
    roster = {str(e["id"]): int(e.get("days", 1))
              for e in config.get_extra_time(course_id)}
    base_due = _parse_iso_local(base_due_iso) if base_due_iso else None
    if not roster or not base_due:
        return {"standard": list(student_ids), "extended": []}

    skip_we = True
    hols = set(config.get_combined_calendar_for_range().get("no_count_dates") or [])
    base_lock = _parse_iso_local(base_lock_iso) if base_lock_iso else None

    standard, buckets = [], {}
    for sid in student_ids:
        days = roster.get(str(sid))
        if days:
            buckets.setdefault(days, []).append(sid)
        else:
            standard.append(sid)

    extended = []
    for days in sorted(buckets):
        ext = {"days": days, "student_ids": buckets[days],
               "due_at": _add_school_days(base_due, days, skip_we, hols).isoformat()}
        if base_lock:
            ext["lock_at"] = _add_school_days(base_lock, days, skip_we, hols).isoformat()
        extended.append(ext)
    return {"standard": standard, "extended": extended}


def _expand_variants_extra_time(course_id, entries, settings):
    """Bake per-student extra-time overrides into a push_tiers manifest."""
    try:
        s = json.loads(settings) if settings else {}
    except json.JSONDecodeError:
        s = {}
    base_due, base_lock = s.get("due_at"), s.get("lock_at")
    for e in entries:
        sids = e.get("student_ids") or []
        if not sids:
            continue
        split = _split_for_extra_time(course_id, sids, base_due, base_lock)
        if not split["extended"]:
            continue
        label = e.get("label", "tier")
        overrides = []
        if split["standard"]:
            overrides.append({"student_ids": split["standard"],
                              "title": f"{label} group"})
        for ext in split["extended"]:
            ov = {"student_ids": ext["student_ids"],
                  "title": f"{label} +{ext['days']}d",
                  "due_at": ext["due_at"]}
            if ext.get("lock_at"):
                ov["lock_at"] = ext["lock_at"]
            overrides.append(ov)
        e["overrides"] = overrides
    return entries


def _sweep_compute(course_id, settings):
    """Core late-work sweep computation."""
    skip_we = settings.get("skip_weekends", True)
    hols = set(settings.get("holidays", []))
    hols.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])

    assignments, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})
    if err:
        return [], [], err

    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100}, timeout=60)
    if err:
        return [], [], err

    students, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return [], [], err

    name_by_id = {str(s["id"]): (s.get("sortable_name") or s.get("name", ""))
                  for s in students}
    amap = {a["id"]: a for a in assignments if a.get("published", True)}

    entries, skipped = [], []
    for sub in subs:
        if sub.get("excused") or not sub.get("submitted_at"):
            continue
        aid = sub.get("assignment_id")
        a = amap.get(aid)
        if not a:
            continue
        uid = sub.get("user_id")
        if sub.get("workflow_state", "") != "late":
            continue

        due = _parse_iso_local(a.get("due_at"))
        subd = _parse_iso_local(sub.get("submitted_at"))
        if not due or not subd:
            continue

        canvas_days, school_days, extra_days, excluded = _school_days_late_detail(
            due, subd, skip_we, hols)
        if excluded:
            skipped.append({"student_name": name_by_id.get(str(uid), uid),
                            "assignment_name": a.get("name", aid),
                            "reason": "excluded"})
            continue

        entries.append({
            "user_id": uid, "student_name": name_by_id.get(str(uid), uid),
            "assignment_id": aid, "assignment_name": a.get("name", aid),
            "due": due.strftime("%m/%d"), "submitted": subd.strftime("%m/%d"),
            "canvas_days": canvas_days, "school_days": school_days,
            "extra_days": extra_days,
            "seconds_override": school_days * 86400,
        })
    return entries, skipped, None
