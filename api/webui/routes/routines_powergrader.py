"""PowerGrader scheduled autoscore and late-catchup routine runners.

Moved out of routines.py for maintainability.
Dependencies are passed in explicitly so the module stays easy to exercise
through the canonical `api.webui...` package path.
"""
import json
import os
import sys
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from api.powergrader import scheduled_autoscore_support as autoscore_support
from api.powergrader.push_context import build_scheduled_push_context

_autoscore_job_label = autoscore_support.autoscore_job_label
_autoscore_fetch_status = autoscore_support.autoscore_fetch_status
_autoscore_receipt_dir = autoscore_support.autoscore_receipt_dir
_autoscore_canvas_states = autoscore_support.autoscore_canvas_states
_autoscore_session_is_fully_pushed = autoscore_support.autoscore_session_is_fully_pushed
_autoscore_status_from_summary = autoscore_support.autoscore_status_from_summary
_autoscore_summary_payload = autoscore_support.autoscore_summary_payload
_autoscore_decisions_payload = autoscore_support.autoscore_decisions_payload
_parse_routine_dt = autoscore_support.parse_routine_dt


# --------------------------------------------------------------------------
# Dependency bundle
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerGraderRoutineDeps:
    config: Any
    html_to_text: Callable[[str], str]
    canvas_send: Callable[..., Any]
    pg_routes: Any
    ai_workflow: Any
    autopush_executor: Any
    autoscore_queue: Any
    canvas_fetch: Any
    late_catchup: Any
    privacy: Any
    session_builder: Any
    session_store: Any


# --------------------------------------------------------------------------
# Scheduled autoscore
# --------------------------------------------------------------------------

def _queue_transactional(func):
    @wraps(func)
    def wrapped(params, deps):
        with deps.autoscore_queue.queue_transaction() as queue:
            return func(params, deps, queue)
    return wrapped

@_queue_transactional
def _run_routine_powergrader_scheduled_autoscore(params, deps: PowerGraderRoutineDeps, queue):
    jobs = deps.autoscore_queue.due_jobs(queue)
    if not jobs:
        return {"ok": True, "lines": ["· no scheduled PowerGrader jobs are due"], "summary": "0 scheduled jobs due"}

    current_ids = {
        str(course.get("id") or "").strip()
        for course in deps.config.active_courses()
        if str(course.get("id") or "").strip()
    }
    runnable_jobs = [job for job in jobs if str(job.get("course_id") or "").strip() in current_ids]
    paused = len(jobs) - len(runnable_jobs)
    max_jobs = int(params.get("max_jobs", 10) or 10)
    lines, ok, processed = [], True, 0
    if paused:
        lines.append(f"· {paused} scheduled PowerGrader job(s) paused because their courses are Previous")
    worker_id = deps.autoscore_queue.machine_id()
    now_dt = datetime.now(timezone.utc)

    for job in runnable_jobs[:max_jobs]:
        label = autoscore_support.autoscore_job_label(job) or str(job.get("job_id") or "scheduled job")
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        claimed, job_ref = deps.autoscore_queue.claim_job(queue, job_id, worker_id=worker_id, now=now_dt)
        if not claimed or not job_ref:
            lines.append(f"· {label}: already claimed elsewhere")
            continue
        processed += 1
        session_guard = None
        try:
            course_id = str(job_ref.get("course_id") or "")
            assignment_id = str(job_ref.get("assignment_id") or "")
            session_id = str(job_ref.get("session_id") or "")
            if not session_id:
                session_id = str(_uuid.uuid4())
            candidate_guard = deps.session_store.session_lock(session_id)
            candidate_guard.__enter__()
            session_guard = candidate_guard

            subs, adata, fetch_err = deps.canvas_fetch.fetch_submissions(course_id, assignment_id)
            if fetch_err:
                status, reason = autoscore_support.autoscore_fetch_status(fetch_err)
                if status:
                    deps.autoscore_queue.update_job(queue, job_id, status=status, reason=reason, last_error=reason, now=now_dt)
                    if status == "failed":
                        ok = False
                else:
                    deps.autoscore_queue.update_job(queue, job_id, status="scheduled", last_error=reason, now=now_dt)
                lines.append(f"{'✗' if status == 'failed' else '·'} {label}: {reason}")
                continue

            reconciled = deps.autoscore_queue.reconcile_due_date(job_ref, adata, now=now_dt)
            job_ref.clear()
            job_ref.update(reconciled)

            if job_ref.get("status") == "needs_attention" or job_ref.get("eligibility") != "eligible":
                deps.autoscore_queue.update_job(queue, job_id, status=job_ref.get("status"), reason=job_ref.get("reason"), last_error="", now=now_dt)
                lines.append(f"⚑ {label}: {job_ref.get('reason') or 'needs attention'}")
                continue

            scheduled_at = autoscore_support.parse_routine_dt(job_ref.get("scheduled_at"))
            if scheduled_at and scheduled_at > now_dt:
                deps.autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="", now=now_dt)
                lines.append(f"· {label}: rescheduled for {job_ref.get('scheduled_at')}")
                continue

            submitted = [
                s for s in (subs or [])
                if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
            ]
            if not submitted:
                deps.autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="No submitted work found yet.", now=now_dt)
                lines.append(f"· {label}: no submitted work found yet")
                continue

            if not deps.config.has_openrouter_key():
                deps.autoscore_queue.update_job(queue, job_id, status="scheduled", last_error="Waiting for an OpenRouter key.", now=now_dt)
                lines.append(f"· {label}: waiting for an OpenRouter key")
                continue

            session = deps.session_store.load_session(session_id)
            course_name = deps.config.course_display_name(course_id)
            if not session and (adata or {}).get("is_quiz_lti_assignment") is not True:
                deps.canvas_fetch.ingest_ordinary_attachments(
                    submitted,
                    course_name=course_name,
                    course_id=course_id,
                    assignment_name=adata.get("name") or job_ref.get("assignment_name") or assignment_id,
                    assignment_id=assignment_id,
                )
            settings = job_ref.get("settings") or {}
            selected_model = str(settings.get("model_id") or deps.config.get_openrouter_model()).strip() or deps.config.get_openrouter_model()
            persona_id = str(settings.get("persona_id") or "sage").strip() or "sage"
            response_kind = str(settings.get("response_kind") or "scr").strip() or "scr"
            rubric_name = str(settings.get("rubric_name") or "").strip()
            watch_late_enabled = bool(settings.get("watch_late", True))
            submitted_user_ids = sorted({str(s.get("user_id", "")) for s in submitted if s.get("user_id")})
            late_watch = {
                "enabled": watch_late_enabled,
                "supported": True,
                "reason": "" if watch_late_enabled else "Late catch-up is disabled for this session.",
                "initial_missing_user_ids": deps.late_catchup.initial_missing_user_ids(subs or []),
                "known_user_ids": submitted_user_ids,
                "scored_user_ids": [],
                "last_checked": None,
                "last_scored": None,
                "last_summary": "",
                "source_context": {},
                "response_kind": response_kind,
            }
            assignment_name = adata.get("name") or job_ref.get("assignment_name") or assignment_id
            assignment_description = deps.html_to_text(adata.get("description") or "")
            points_possible = float(adata.get("points_possible") or 100)
            created_session = False
            if not session:
                session_ai = deps.ai_workflow.run_ai_workflow(
                    mode="assisted",
                    submitted=submitted,
                    assignment_name=assignment_name,
                    assignment_description=assignment_description,
                    course_id=course_id,
                    course_name=course_name,
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
                    deps.autoscore_queue.update_job(queue, job_id, status="failed", reason=reason, last_error=reason, now=now_dt)
                    lines.append(f"✗ {label}: {reason}")
                    ok = False
                    continue

                roster_settings = deps.config.get_roster_student_settings(course_id)
                tier_map = deps.config.roster_tier_by_id(course_id)
                monitored = deps.config.get_monitored_students()
                extra_time_list = deps.config.get_extra_time(course_id)
                extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}
                privacy_steps = session_ai.get("privacy_steps") or []
                privacy_artifacts = session_ai.get("privacy_artifacts") or {}
                late_watch["source_context"] = session_ai.get("source_context") or {}
                students = deps.session_builder.build_students(
                    submitted=submitted,
                    ai_by_uid=session_ai.get("ai_by_uid") or {},
                    ai_failures=session_ai.get("ai_failures") or {},
                    roster_settings=roster_settings,
                    tier_map=tier_map,
                    monitored=monitored,
                    extra_time_map=extra_time_map,
                )
                session = deps.session_builder.build_session(
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
                    audit_path = deps.privacy.write_privacy_audit_file(
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
                        privacy_steps.append(deps.privacy.privacy_step(
                            "privacy_audit", "Saved PowerGrader privacy audit", "ok",
                            "Private decoder folder includes a JSON record of these privacy steps.",
                            path=audit_path,
                        ))
                    else:
                        privacy_steps.append(deps.privacy.privacy_step(
                            "privacy_audit", "Saved PowerGrader privacy audit", "warn",
                            "Could not write the optional privacy audit JSON; session still records these steps.",
                        ))
                deps.session_store.save_session(session)
                created_session = True
            else:
                late_watch["source_context"] = session.get("late_watch", {}).get("source_context") or {}
                if not _autoscore_session_is_fully_pushed(session):
                    session.setdefault("late_watch", {})

            session_action = "created" if created_session else "loaded"
            push_context = build_scheduled_push_context(job_ref)
            auto_push_enabled = bool(push_context.get("auto_push")) and bool((push_context.get("push_policy") or {}).get("enabled"))
            if auto_push_enabled and session:
                if autoscore_support.autoscore_session_is_fully_pushed(session):
                    deps.autoscore_queue.update_job(
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
                    receipt_dir = autoscore_support.autoscore_receipt_dir(job_ref, deps.session_store)
                    canvas_states_by_user = autoscore_support.autoscore_canvas_states(subs)
                    autopush_result = deps.autopush_executor.run_autopush_for_session(
                        context=push_context,
                        session=session,
                        assignment=adata,
                        canvas_states_by_user=canvas_states_by_user,
                        canvas_send=deps.canvas_send,
                        receipt_dir=receipt_dir,
                        now=now_dt,
                    )
                    deps.session_store.save_session(session)
                    status = autoscore_support.autoscore_status_from_summary(autopush_result, job_ref.get("status") or "session_ready")
                    last_error = ""
                    errors = autopush_result.get("errors") or []
                    if errors:
                        last_error = errors[0].get("message") or errors[0].get("reason") or ""
                    deps.autoscore_queue.update_job(
                        queue,
                        job_id,
                        status=status,
                        session_id=session["session_id"],
                        last_error=last_error,
                        push_summary=autoscore_support.autoscore_summary_payload(autopush_result),
                        student_decisions=autoscore_support.autoscore_decisions_payload(autopush_result),
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
                deps.autoscore_queue.update_job(queue, job_id, status="session_ready", session_id=session["session_id"], last_error="", now=now_dt)
                if created_session:
                    lines.append(f"✓ {label}: created PowerGrader draft session")
                else:
                    lines.append(f"✓ {label}: loaded PowerGrader draft session")
        finally:
            deps.autoscore_queue.release_job(queue, job_id, worker_id=worker_id, now=now_dt)
            if session_guard is not None:
                session_guard.__exit__(*sys.exc_info())

    summary = f"{processed} scheduled job(s) processed; {paused} paused for Previous courses"
    return {"ok": ok, "lines": lines, "summary": summary}


# --------------------------------------------------------------------------
# Late catch-up
# --------------------------------------------------------------------------

def _run_routine_powergrader_late_catchup(params, deps: PowerGraderRoutineDeps):
    if not deps.config.has_openrouter_key():
        return {"ok": False, "lines": ["✗ no OpenRouter key saved"], "summary": "no OpenRouter key saved"}

    current_courses = deps.config.active_courses()
    current_ids = {
        str(course.get("id") or "").strip()
        for course in current_courses
        if str(course.get("id") or "").strip()
    }
    max_sessions = int(params.get("max_sessions", 10) or 10)
    seen: set[str] = set()
    lines, ok, processed, paused = [], True, 0, 0
    course_name = {str(c["id"]): (c.get("nickname") or c.get("name") or str(c["id"]))
                   for c in current_courses}

    for summary in deps.session_store.list_session_summaries():
        if processed >= max_sessions:
            break
        session_id = str(summary.get("session_id") or "")
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        if summary.get("mode") != "assisted":
            continue
        if str(summary.get("course_id") or "").strip() not in current_ids:
            paused += 1
            continue
        with deps.session_store.session_lock(session_id):
            session = deps.session_store.load_session(session_id)
            if not session:
                continue
            late_watch = session.get("late_watch") or {}
            if not late_watch.get("enabled") or not late_watch.get("supported"):
                continue
            result = deps.pg_routes._run_late_catchup_score(session)
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

    if paused:
        lines.append(f"· {paused} PowerGrader late-watch session(s) paused because their courses are Previous")
    summary = f"{processed} PowerGrader session(s) checked; {paused} paused for Previous courses; uses OpenRouter"
    return {"ok": ok, "lines": lines or ["· no watched PowerGrader sessions"], "summary": summary}
