"""Late catch-up helpers for PowerGrader routes."""

from datetime import datetime

from .. import config
from api.powergrader import ai_workflow, canvas_fetch, late_catchup, session_builder

from api.nq_report import html_to_text


def _late_watch_error(session: dict, *, require_key: bool = False, require_source_context: bool = False) -> str | None:
    if not session:
        return "Session not found."
    mode = session.get("mode", "")
    if mode not in ("assisted", "packet"):
        return "Late catch-up requires Auto-Score With API or AI Chat mode."
    late_watch = session.get("late_watch") or {}
    if not late_watch:
        return "Late catch-up is not configured for this session."
    if not late_watch.get("enabled"):
        return late_watch.get("reason") or "Late catch-up is disabled for this session."
    if not late_watch.get("supported"):
        return late_watch.get("reason") or "Late catch-up is not supported for this session."
    if require_key and mode == "assisted" and not config.has_openrouter_key():
        return "No OpenRouter key is currently saved."
    if require_source_context and late_watch.get("source_context") is None:
        return "Saved source context is missing for this session."
    return None


def _build_late_catchup_students(
    *,
    course_id: str,
    assignment: dict,
    submitted: list[dict],
    ai_by_uid: dict,
    ai_failures: dict | None = None,
    batch_id: str,
) -> list[dict]:
    roster_settings = config.get_roster_student_settings(course_id)
    tier_map = config.roster_tier_by_id(course_id)
    monitored = config.get_monitored_students()
    extra_time_list = config.get_extra_time(course_id)
    extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}

    students = session_builder.build_students(
        submitted=submitted,
        ai_by_uid=ai_by_uid,
        ai_failures=ai_failures or {},
        roster_settings=roster_settings,
        tier_map=tier_map,
        monitored=monitored,
        extra_time_map=extra_time_map,
    )
    sweep_settings = config.get_sweep_settings()
    holidays = set(sweep_settings.get("holidays") or [])
    holidays.update(config.get_combined_calendar_for_range().get("no_count_dates") or [])
    missing_by_user_id: dict[str, dict] = {}
    for sub in submitted:
        uid = str(sub.get("user_id", ""))
        if not uid:
            continue
        meta = late_catchup.compute_late_meta(
            sub=sub,
            assignment=assignment or sub.get("assignment") or {},
            course_id=course_id,
            extra_time_days=int(extra_time_map.get(uid, 0) or 0),
            skip_weekends=bool(sweep_settings.get("skip_weekends", True)),
            holidays=holidays,
            batch_id=batch_id,
        )
        missing_by_user_id[uid] = meta
    return late_catchup.attach_late_meta(students, missing_by_user_id)


def _run_late_catchup_score(session: dict, *, save_session) -> dict:
    """Fetch, score, and append late catch-up submissions for one session.

    Returns appended_user_ids for auto-post scoping.
    """
    err = _late_watch_error(session, require_key=True, require_source_context=True)
    if err:
        return {"ok": False, "error": err, "status_code": 200, "privacy_steps": []}

    late_watch = session.get("late_watch") or {}
    course_id = str(session.get("course_id") or "")
    assignment_id = str(session.get("assignment_id") or "")
    mode = session.get("mode", "")
    subs, adata, fetch_err = canvas_fetch.fetch_submissions(course_id, assignment_id)
    if fetch_err:
        return {"ok": False, "error": fetch_err, "status_code": 200, "privacy_steps": []}

    new_subs = late_catchup.find_new_submissions(session, subs or [])
    now_iso = datetime.now().isoformat(timespec="seconds")
    if not new_subs:
        late_catchup.update_late_watch_after_preview(session, 0, now_iso)
        save_session(session)
        return {
            "ok": True,
            "appended": 0,
            "ai_scored": 0,
            "batch_id": "",
            "session_id": session.get("session_id", ""),
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_result": None,
            "appended_user_ids": [],
        }

    is_new_quiz = (adata or {}).get("is_quiz_lti_assignment") is True
    if not is_new_quiz:
        canvas_fetch.ingest_ordinary_attachments(
            new_subs,
            course_name=config.course_display_name(course_id),
            course_id=course_id,
            assignment_name=(adata or {}).get("name") or session.get("assignment_name") or assignment_id,
            assignment_id=assignment_id,
        )
    batch_id = late_catchup.make_late_batch_id()
    selected_model = session.get("model_id") or config.get_openrouter_model()
    response_kind = session.get("response_kind") or late_watch.get("response_kind") or "scr"
    assignment_name = adata.get("name") or session.get("assignment_name") or assignment_id
    assignment_description = session.get("assignment_description") or html_to_text(adata.get("description") or "")
    artifact_name = f"{assignment_name} - Late Catch-Up {batch_id}"

    ai_result = ai_workflow.run_ai_workflow(
        mode=mode,
        submitted=new_subs,
        assignment_name=assignment_name,
        assignment_description=assignment_description,
        course_id=course_id,
        course_name=config.course_display_name(course_id),
        assignment_id=assignment_id,
        session_id=session.get("session_id", ""),
        rubric_name=session.get("rubric_name", ""),
        persona_id=session.get("persona_id", "sage"),
        selected_model=selected_model,
        response_kind=response_kind,
        source_text="",
        source_files_json="",
        source_uploads=None,
        has_openrouter_key=config.has_openrouter_key() or mode == "packet",
        source_context_override=late_watch.get("source_context") or {},
        artifact_assignment_name=artifact_name,
        copilot_batch_prefix=batch_id,
    )
    if not ai_result["ok"]:
        return {
            "ok": False,
            "error": ai_result["error"],
            "status_code": ai_result.get("status_code", 200),
            "privacy_steps": ai_result.get("privacy_steps") or [],
            "privacy_artifacts": ai_result.get("privacy_artifacts") or {},
            "budget": ai_result.get("budget"),
            "debug_path": ai_result.get("debug_path"),
            "copilot_packet": ai_result.get("copilot_packet"),
            "appended_user_ids": [],
        }

    students = _build_late_catchup_students(
        course_id=course_id,
        assignment=adata or {},
        submitted=new_subs,
        ai_by_uid=ai_result.get("ai_by_uid") or {},
        ai_failures=ai_result.get("ai_failures") or {},
        batch_id=batch_id,
    )
    appended_user_ids = [str(st.get("user_id", "")) for st in students if st.get("user_id")]

    is_packet = mode == "packet"

    if is_packet:
        # Packet mode: append new unscored student rows before saving.
        # Their AI fields remain empty until import.
        for st in students:
            st["ai_score"] = None
            st["ai_feedback"] = None
        session.setdefault("students", []).extend(students)
        late_catchup.update_late_watch_after_generate(session, appended_user_ids, now_iso)
        generated_count = _merge_late_batches(session, ai_result, batch_id, artifact_name)
        session.setdefault("late_catchup_artifacts", []).append({
            "ts": now_iso,
            "late_batch_id": batch_id,
            "mode": "packet",
            "privacy_steps": ai_result.get("privacy_steps") or [],
            "privacy_artifacts": ai_result.get("privacy_artifacts") or {},
            "copilot_batches_added": generated_count,
        })
        late_watch["generated_user_ids"] = sorted(set(
            late_watch.get("generated_user_ids") or []
        ) | set(appended_user_ids))
        late_watch["last_generated"] = now_iso
        late_watch["known_user_ids"] = sorted(set(
            late_watch.get("known_user_ids") or []
        ) | set(appended_user_ids))
        generated_count_val = generated_count
    else:
        # Assisted mode: append students with AI scores
        session.setdefault("students", []).extend(students)
        late_catchup.update_late_watch_after_score(session, appended_user_ids, now_iso)
        generated_count_val = 0

    session.setdefault("late_catchup_log", []).append({
        "ts": now_iso,
        "batch_id": batch_id,
        "appended": len(students),
        "ai_scored": len(ai_result.get("ai_by_uid") or {}) if not is_packet else 0,
        "generated": len(students) if is_packet else 0,
        "copilot_batches_added": generated_count_val if is_packet else 0,
        "mode": mode,
        "errors": [],
    })
    save_session(session)
    out = {
        "ok": True,
        "appended": len(students),
        "batch_id": batch_id,
        "session_id": session.get("session_id", ""),
        "privacy_steps": ai_result.get("privacy_steps") or [],
        "privacy_artifacts": ai_result.get("privacy_artifacts") or {},
        "appended_user_ids": appended_user_ids,
    }
    if is_packet:
        out["ai_scored"] = 0
        out["generated"] = len(students)
        out["copilot_batches_added"] = generated_count_val
    else:
        out["ai_scored"] = len(ai_result.get("ai_by_uid") or {})
    return out


def _merge_late_batches(session: dict, ai_result: dict, batch_id: str, artifact_name: str) -> int:
    """Merge late batch Copilot batches into the session's copilot_packet."""
    copilot_info = ai_result.get("copilot_packet")
    if not copilot_info:
        return 0
    new_batches = copilot_info.get("batches") or []
    if not new_batches:
        return 0

    existing_packet = session.setdefault("copilot_packet", {})
    existing_batches = existing_packet.get("batches") or []

    for batch in new_batches:
        batch["late_catchup"] = True
        batch["late_batch_id"] = batch_id
        existing_batches.append(batch)

    # Recompute counts from merged arrays
    existing_packet["batches"] = existing_batches
    existing_packet["batch_count"] = len(existing_batches)
    existing_packet["student_count"] = sum(
        b.get("student_count", 0) for b in existing_batches
    )
    return len(new_batches)
