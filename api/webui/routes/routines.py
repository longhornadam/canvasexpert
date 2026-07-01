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
from datetime import datetime, timedelta, timezone

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
from . import powergrader as pg_routes
from powergrader import (
    ai_workflow,
    autopush_executor,
    autoscore_queue,
    canvas_fetch,
    late_catchup,
    privacy,
    session_builder,
    session_store,
)

try:
    from nq_report import html_to_text
except ModuleNotFoundError:
    from api.nq_report import html_to_text

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
    "powergrader_scheduled_autoscore": {
        "label": "Scheduled PowerGrader Auto-Score",
        "writes": False,
        "default": {"enabled": False, "every_hours": 1,
                    "params": {"max_jobs": 10}},
    },
    "powergrader_late_catchup": {
        "label": "PowerGrader late catch-up",
        "writes": False,
        "default": {"enabled": False, "every_hours": 12,
                    "params": {"max_sessions": 10}},
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


def _autoscore_job_label(job: dict) -> str:
    course = str(job.get("course_name") or job.get("course_id") or "").strip()
    assignment = str(job.get("assignment_name") or job.get("assignment_id") or "").strip()
    return " / ".join(part for part in (course, assignment) if part)


def _autoscore_fetch_status(error: str) -> tuple[str | None, str]:
    text = (error or "").lower()
    if any(token in text for token in ("404", "not found", "403", "forbidden", "unauthorized")):
        return "failed", "Canvas assignment is no longer available."
    return None, "Could not refresh the Canvas assignment right now."


def _autoscore_receipt_dir(job: dict) -> str | None:
    root = session_store.pg_dir()
    if not root:
        return None
    job_id = str(job.get("job_id") or job.get("assignment_id") or "scheduled-job")
    return os.path.join(root, "_private", "autopush_receipts", job_id)


def _autoscore_canvas_states(submissions: list[dict] | None) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for sub in submissions or []:
        uid = str(sub.get("user_id") or "").strip()
        if not uid:
            continue
        state: dict = {}
        if sub.get("score") is not None:
            state["existing_score"] = sub.get("score")
        comments = []
        for key in ("submission_comments", "comments"):
            raw = sub.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, dict):
                    text = item.get("comment") or item.get("text_comment") or item.get("body") or item.get("message")
                else:
                    text = item
                text = str(text or "").strip()
                if text:
                    comments.append(text)
        if comments:
            state["existing_comments"] = comments
        states[uid] = state
    return states


def _autoscore_session_is_fully_pushed(session: dict) -> bool:
    students = session.get("students") or []
    if not students:
        return False
    for student in students:
        if student.get("posted") is not True:
            return False
        if not str(student.get("autopush_idempotency_key") or "").strip():
            return False
    return True


def _autoscore_status_from_summary(result: dict, current_status: str) -> str:
    pushed = int(result.get("pushed") or 0)
    needs_review = int(result.get("needs_review") or 0)
    blocked = int(result.get("blocked") or 0)
    errors = list(result.get("errors") or [])
    student_results = list(result.get("student_results") or [])
    if pushed and not needs_review and not blocked and not errors:
        return "auto_pushed"
    if not pushed and student_results and all(r.get("reason") == "already_pushed" for r in student_results):
        return "auto_pushed"
    if pushed and (needs_review or blocked or errors):
        return "partial_auto_pushed"
    if not pushed and needs_review:
        return "needs_review"
    if not pushed and errors:
        return "failed"
    return current_status or "session_ready"


def _autoscore_summary_payload(result: dict) -> dict:
    return {
        "pushed": int(result.get("pushed") or 0),
        "needs_review": int(result.get("needs_review") or 0),
        "blocked": int(result.get("blocked") or 0),
        "errors": [
            {"user_id": err.get("user_id"), "reason": err.get("reason")}
            for err in (result.get("errors") or [])
            if isinstance(err, dict)
        ],
    }


def _autoscore_decisions_payload(result: dict) -> list[dict]:
    out = []
    for row in result.get("student_results") or []:
        if not isinstance(row, dict):
            continue
        out.append({
            "user_id": row.get("user_id"),
            "decision": row.get("decision"),
            "reason": row.get("reason"),
            "receipt_id": row.get("receipt_id"),
            "idempotency_key": row.get("idempotency_key"),
        })
    return out


def _parse_routine_dt(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _run_routine_powergrader_scheduled_autoscore(params):
    queue = autoscore_queue.load_queue()
    jobs = autoscore_queue.due_jobs(queue)
    if not jobs:
        return {"ok": True, "lines": ["· no scheduled PowerGrader jobs are due"], "summary": "0 scheduled jobs due"}

    max_jobs = int(params.get("max_jobs", 10) or 10)
    lines, ok, processed = [], True, 0
    worker_id = autoscore_queue.machine_id()
    now_dt = datetime.now(timezone.utc)

    for job in jobs[:max_jobs]:
        label = _autoscore_job_label(job) or str(job.get("job_id") or "scheduled job")
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        claimed, job_ref = autoscore_queue.claim_job(queue, job_id, worker_id=worker_id, now=now_dt)
        if not claimed or not job_ref:
            lines.append(f"· {label}: already claimed elsewhere")
            continue
        autoscore_queue.save_queue(queue)
        processed += 1
        try:
            course_id = str(job_ref.get("course_id") or "")
            assignment_id = str(job_ref.get("assignment_id") or "")
            session_id = str(job_ref.get("session_id") or "")
            if not session_id:
                session_id = str(_uuid.uuid4())

            subs, adata, fetch_err = canvas_fetch.fetch_submissions(course_id, assignment_id)
            if fetch_err:
                status, reason = _autoscore_fetch_status(fetch_err)
                if status:
                    autoscore_queue.update_job(queue, job_id, status=status, reason=reason, last_error=reason, now=now_dt)
                    if status == "failed":
                        ok = False
                else:
                    autoscore_queue.update_job(queue, job_id, status="scheduled", last_error=reason, now=now_dt)
                lines.append(f"{'✗' if status == 'failed' else '·'} {label}: {reason}")
                continue

            reconciled = autoscore_queue.reconcile_due_date(job_ref, adata, now=now_dt)
            job_ref.clear()
            job_ref.update(reconciled)

            if job_ref.get("status") == "needs_attention" or job_ref.get("eligibility") != "eligible":
                autoscore_queue.update_job(queue, job_id, status=job_ref.get("status"), reason=job_ref.get("reason"), last_error="", now=now_dt)
                lines.append(f"⚑ {label}: {job_ref.get('reason') or 'needs attention'}")
                continue

            scheduled_at = _parse_routine_dt(job_ref.get("scheduled_at"))
            if scheduled_at and scheduled_at > now_dt:
                autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="", now=now_dt)
                lines.append(f"· {label}: rescheduled for {job_ref.get('scheduled_at')}")
                continue

            submitted = [
                s for s in (subs or [])
                if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
            ]
            if not submitted:
                autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="No submitted work found yet.", now=now_dt)
                lines.append(f"· {label}: no submitted work found yet")
                continue

            if not config.has_openrouter_key():
                autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="Waiting for an OpenRouter key.", now=now_dt)
                lines.append(f"· {label}: waiting for an OpenRouter key")
                continue

            canvas_fetch.enrich_with_code_files(submitted)
            settings = job_ref.get("settings") or {}
            selected_model = str(settings.get("model_id") or config.get_openrouter_model()).strip() or config.get_openrouter_model()
            persona_id = str(settings.get("persona_id") or "sage").strip() or "sage"
            response_kind = str(settings.get("response_kind") or "scr").strip() or "scr"
            rubric_name = str(settings.get("rubric_name") or "").strip()
            watch_late_enabled = bool(settings.get("watch_late", True))
            submitted_user_ids = sorted({str(s.get("user_id", "")) for s in submitted if s.get("user_id")})
            late_watch = {
                "enabled": watch_late_enabled,
                "supported": True,
                "reason": "" if watch_late_enabled else "Late catch-up is disabled for this session.",
                "initial_missing_user_ids": late_catchup.initial_missing_user_ids(subs or []),
                "known_user_ids": submitted_user_ids,
                "scored_user_ids": [],
                "last_checked": None,
                "last_scored": None,
                "last_summary": "",
                "source_context": {},
                "response_kind": response_kind,
            }
            assignment_name = adata.get("name") or job_ref.get("assignment_name") or assignment_id
            assignment_description = html_to_text(adata.get("description") or "")
            points_possible = float(adata.get("points_possible") or 100)
            session = session_store.load_session(session_id)
            created_session = False
            if not session:
                session_ai = ai_workflow.run_ai_workflow(
                    mode="assisted",
                    submitted=submitted,
                    assignment_name=assignment_name,
                    assignment_description=assignment_description,
                    course_id=course_id,
                    assignment_id=assignment_id,
                    session_id=session_id,
                    rubric_name=rubric_name,
                    persona_id=persona_id,
                    selected_model=selected_model,
                    response_kind=response_kind,
                    source_text="",
                    source_files_json="",
                    source_uploads=None,
                    has_openrouter_key=True,
                )
                if not session_ai["ok"]:
                    reason = session_ai.get("error") or "PowerGrader draft session creation failed"
                    autoscore_queue.update_job(queue, job_id, status="failed", reason=reason, last_error=reason, now=now_dt)
                    lines.append(f"✗ {label}: {reason}")
                    ok = False
                    continue

                roster_settings = config.get_roster_student_settings(course_id)
                tier_map = config.roster_tier_by_id(course_id)
                monitored = config.get_monitored_students()
                extra_time_list = config.get_extra_time(course_id)
                extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}
                privacy_steps = session_ai.get("privacy_steps") or []
                privacy_artifacts = session_ai.get("privacy_artifacts") or {}
                late_watch["source_context"] = session_ai.get("source_context") or {}
                students = session_builder.build_students(
                    submitted=submitted,
                    ai_by_uid=session_ai.get("ai_by_uid") or {},
                    roster_settings=roster_settings,
                    tier_map=tier_map,
                    monitored=monitored,
                    extra_time_map=extra_time_map,
                )
                session = session_builder.build_session(
                    session_id=session_id,
                    course_id=course_id,
                    assignment_id=assignment_id,
                    assignment_name=assignment_name,
                    points_possible=points_possible,
                    mode="assisted",
                    rubric_name=rubric_name,
                    persona_id=persona_id,
                    selected_model=selected_model,
                    assignment_description=assignment_description,
                    response_kind=response_kind,
                    privacy_steps=privacy_steps,
                    privacy_artifacts=privacy_artifacts,
                    students=students,
                    mode_label="Auto-Score With API",
                    copilot_packet=session_ai.get("copilot_packet"),
                    late_watch=late_watch,
                )
                if privacy_artifacts.get("private_folder"):
                    audit_path = privacy.write_privacy_audit_file(
                        privacy_artifacts["private_folder"],
                        assignment_name,
                        session_id,
                        course_id,
                        assignment_id,
                        selected_model,
                        privacy_steps,
                        privacy_artifacts,
                    )
                    if audit_path:
                        privacy_artifacts["privacy_audit"] = audit_path
                        privacy_steps.append(privacy.privacy_step(
                            "privacy_audit", "Saved PowerGrader privacy audit", "ok",
                            "Private decoder folder includes a JSON record of these privacy steps.",
                            path=audit_path,
                        ))
                    else:
                        privacy_steps.append(privacy.privacy_step(
                            "privacy_audit", "Saved PowerGrader privacy audit", "warn",
                            "Could not write the optional privacy audit JSON; session still records these steps.",
                        ))
                session_store.save_session(session)
                created_session = True
            else:
                late_watch["source_context"] = session.get("late_watch", {}).get("source_context") or {}
                if not _autoscore_session_is_fully_pushed(session):
                    session.setdefault("late_watch", {})

            session_action = "created" if created_session else "loaded"
            auto_push_enabled = bool(job_ref.get("auto_push")) and bool((job_ref.get("push_policy") or {}).get("enabled"))
            if auto_push_enabled and session:
                if _autoscore_session_is_fully_pushed(session):
                    autoscore_queue.update_job(
                        queue,
                        job_id,
                        status="auto_pushed",
                        session_id=session["session_id"],
                        last_error="",
                        push_summary={
                            "pushed": len(session.get("students") or []),
                            "needs_review": 0,
                            "blocked": 0,
                            "errors": [],
                        },
                        student_decisions=[],
                        reason=job_ref.get("reason") or "",
                        now=now_dt,
                    )
                    lines.append(f"✓ {label}: {session_action} PowerGrader draft session already fully pushed")
                else:
                    receipt_dir = _autoscore_receipt_dir(job_ref)
                    canvas_states_by_user = _autoscore_canvas_states(subs)
                    autopush_result = autopush_executor.run_autopush_for_session(
                        job=job_ref,
                        session=session,
                        assignment=adata,
                        canvas_states_by_user=canvas_states_by_user,
                        canvas_send=_canvas_send,
                        receipt_dir=receipt_dir,
                        now=now_dt,
                    )
                    session_store.save_session(session)
                    status = _autoscore_status_from_summary(autopush_result, job_ref.get("status") or "session_ready")
                    last_error = ""
                    errors = autopush_result.get("errors") or []
                    if errors:
                        last_error = errors[0].get("message") or errors[0].get("reason") or ""
                    autoscore_queue.update_job(
                        queue,
                        job_id,
                        status=status,
                        session_id=session["session_id"],
                        last_error=last_error,
                        push_summary=_autoscore_summary_payload(autopush_result),
                        student_decisions=_autoscore_decisions_payload(autopush_result),
                        reason=job_ref.get("reason") or "",
                        now=now_dt,
                    )
                    if status == "failed":
                        ok = False
                        lines.append(f"✗ {label}: auto-push failed")
                    else:
                        lines.append(
                            f"✓ {label}: {session_action} PowerGrader draft session"
                            + f" and auto-pushed {autopush_result.get('pushed', 0)} student(s)"
                            + (f" ({autopush_result.get('needs_review', 0)} need review)" if autopush_result.get("needs_review") else "")
                        )
                    if autopush_result.get("needs_review"):
                        lines.append(f"⚑ {label}: {autopush_result.get('needs_review')} student(s) need review")
                    if autopush_result.get("blocked") and not autopush_result.get("pushed"):
                        lines.append(f"· {label}: {autopush_result.get('blocked')} student(s) blocked")
            else:
                autoscore_queue.update_job(queue, job_id, status="session_ready", session_id=session["session_id"], last_error="", now=now_dt)
                if created_session:
                    lines.append(f"✓ {label}: created PowerGrader draft session")
                else:
                    lines.append(f"✓ {label}: loaded PowerGrader draft session")
        finally:
            autoscore_queue.release_job(queue, job_id, worker_id=worker_id, now=now_dt)
            autoscore_queue.save_queue(queue)

    summary = f"{processed} scheduled job(s) processed"
    return {"ok": ok, "lines": lines, "summary": summary}


def _run_routine_powergrader_late_catchup(params):
    if not config.has_openrouter_key():
        return {"ok": False, "lines": ["✗ no OpenRouter key saved"], "summary": "no OpenRouter key saved"}

    max_sessions = int(params.get("max_sessions", 10) or 10)
    seen: set[str] = set()
    lines, ok, processed = [], True, 0
    course_name = {str(c["id"]): (c.get("nickname") or c.get("name") or str(c["id"]))
                   for c in config.active_courses()}

    for summary in session_store.list_session_summaries():
        if processed >= max_sessions:
            break
        session_id = str(summary.get("session_id") or "")
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        if summary.get("mode") != "assisted":
            continue
        session = session_store.load_session(session_id)
        if not session:
            continue
        late_watch = session.get("late_watch") or {}
        if not late_watch.get("enabled") or not late_watch.get("supported"):
            continue
        result = pg_routes._run_late_catchup_score(session)
        processed += 1
        label = f"{course_name.get(str(session.get('course_id')), session.get('course_id', ''))} / {session.get('assignment_name', '')}".strip(" /")
        if not result.get("ok"):
            ok = False
            lines.append(f"✗ {label}: {result.get('error', 'late catch-up failed')}")
            continue
        appended = int(result.get("appended") or 0)
        if appended:
            lines.append(f"✓ {label}: {appended} late submission(s) added to review")
        else:
            lines.append(f"· {label}: no new late submissions")

    summary = f"{processed} PowerGrader session(s) checked; uses OpenRouter"
    return {"ok": ok, "lines": lines or ["· no watched PowerGrader sessions"], "summary": summary}


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
    "powergrader_scheduled_autoscore": _run_routine_powergrader_scheduled_autoscore,
    "powergrader_late_catchup": _run_routine_powergrader_late_catchup,
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
