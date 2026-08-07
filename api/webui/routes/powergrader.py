"""PowerGrader route orchestration."""
import json
import os
import subprocess
import uuid
from datetime import datetime
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from api import openrouter_client as orc

from api.platform_services import config, workspace
from .. import mirror_service, source_materials
from api import course_scope, operational_log
from api.platform_services.canvas_client import canvas_get, canvas_get_all, _canvas_send
from ..deps import list_rubric_files, templates
from api.powergrader import (ai_workflow, assignment_refresh, blind_first, canvas_fetch, context,
                             estimates, import_results, late_catchup, privacy,
                             new_quiz_csv, new_quiz_grader,
                             session_actions, session_builder, session_store,
                             start_workflow, student_attachments, writing_timeline)
from .powergrader_helpers import (
    build_late_preview_payload,
    build_late_watch_state,
    build_start_error_payload,
    build_start_success_payload,
    normalize_mode,
)
from .powergrader_setup_support import (
    build_estimate_payload,
    build_queue_page_context,
    build_setup_page_context,
)
from .powergrader_late import (
    _late_watch_error as _late_watch_error_impl,
    _run_late_catchup_score as _run_late_catchup_score_impl,
)

from api.nq_report import html_to_text

router = APIRouter(tags=["powergrader"])

# Compatibility aliases so existing tests continue to work
_mode_label = session_store.mode_label
_load_session = session_store.load_session
_save_session = session_store.save_session

_privacy_step = privacy.privacy_step
_write_privacy_audit_file = privacy.write_privacy_audit_file

_vault = context.vault


def _powergrader_assignment_context(course_id: str, assignment_id: str):
    course_id, assignment_id = str(course_id or "").strip(), str(assignment_id or "").strip()
    if not course_id or not assignment_id:
        return None, "Select a course and assignment first."
    scope_error = course_scope.current_course_error(course_id, config.active_courses())
    if scope_error:
        return None, scope_error
    course_name = config.course_display_name(course_id) or course_id
    return (course_id, assignment_id, course_name), None


@router.post("/api/powergrader/refresh")
def pg_refresh(course_id: str = Form(""), assignment_id: str = Form("")):
    context_value, error = _powergrader_assignment_context(course_id, assignment_id)
    if error:
        return JSONResponse({"ok": False, "error": error})
    course_id, assignment_id, _ = context_value
    _, _, result = assignment_refresh.refresh_assignment(course_id, assignment_id, session_id=f"refresh-{uuid.uuid4()}")
    if result.get("error"):
        return JSONResponse({"ok": False, "error": "The focused refresh could not be completed.", "status": "unavailable"})
    return JSONResponse({"ok": True, "status": result.get("status", "incomplete")})


@router.post("/api/powergrader/open-assignment-folder")
def pg_open_assignment_folder(course_id: str = Form(""), assignment_id: str = Form("")):
    context_value, error = _powergrader_assignment_context(course_id, assignment_id)
    if error:
        return JSONResponse({"ok": False, "error": error})
    course_id, assignment_id, course_name = context_value
    path = workspace.grading_keys_assignment_folder(course_name, course_id, assignment_id, assignment_id)
    if not path or not workspace.path_within_workspace(path):
        return JSONResponse({"ok": False, "error": "The local assignment folder is unavailable."})
    try:
        os.makedirs(path, exist_ok=True)
        subprocess.Popen(["explorer", path])
        return JSONResponse({"ok": True})
    except OSError:
        return JSONResponse({"ok": False, "error": "The local assignment folder could not be opened."})


def _late_watch_error(session: dict, *, require_key: bool = False, require_source_context: bool = False) -> str | None:
    return _late_watch_error_impl(
        session,
        require_key=require_key,
        require_source_context=require_source_context,
    )


def _run_late_catchup_score(session: dict) -> dict:
    return _run_late_catchup_score_impl(session, save_session=_save_session)

@router.get("/powergrader", response_class=HTMLResponse)
def powergrader_setup(request: Request):
    source_dir = source_materials.ensure_source_folder()
    persona_dir = config.get_persona_folder()
    return templates.TemplateResponse(
        request,
        "powergrader_setup.html",
        build_setup_page_context(
            saved_courses=config.active_courses(),
            rubrics=[r["label"] for r in list_rubric_files()],
            personas=config.list_personas(),
            feedback_patterns=config.list_feedback_patterns(),
            has_openrouter=config.has_openrouter_key(),
            openrouter_model=config.get_openrouter_model(),
            default_openrouter_model=config.DEFAULT_OPENROUTER_MODEL,
            openrouter_model_presets=config.openrouter_model_presets(),
            has_workspace=bool(workspace.workspace_root()),
            rubrics_folder=workspace.library_folder("Rubrics"),
            ai_ta_folder=workspace.library_folder("AI Authoring"),
            persona_folder=persona_dir,
            source_materials_folder=source_dir,
            source_material_files=source_materials.list_source_files(),
            source_response_presets=source_materials.RESPONSE_PRESETS,
        ),
    )


@router.get("/powergrader/session/{session_id}", response_class=HTMLResponse)
def powergrader_queue(request: Request, session_id: str):
    session = _load_session(session_id)
    if not session:
        return HTMLResponse("<h2>Session not found.</h2>", status_code=404)
    return templates.TemplateResponse(
        request,
        "powergrader_queue.html",
        build_queue_page_context(
            session_id=session_id,
            session=session,
            canvas_base=config.get_canvas_base(),
            mode_label=_mode_label(session.get("mode", "fast")),
        ),
    )

@router.get("/api/powergrader/sessions")
def list_sessions():
    return JSONResponse({"sessions": session_store.list_session_summaries()})


@router.post("/api/powergrader/estimate")
def pg_estimate(
    course_id: str = Form(""),
    assignment_id: str = Form(""),
    rubric_name: str = Form(""),
    persona_id: str = Form("sage"),
    feedback_pattern_id: str = Form(""),
    model_id: str = Form(""),
    response_kind: str = Form("scr"),
    source_text: str = Form(""),
    source_files_json: str = Form(""),
    source_uploads: list[UploadFile] = File(None),
):
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "Select a course and assignment first."})

    adata, err = canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    adata = adata or {}
    assignment_name = adata.get("name") or assignment_id
    is_new_quiz = adata.get("is_quiz_lti_assignment") is True
    assignment_description = html_to_text(adata.get("description") or "")
    student_count, count_basis = estimates.assignment_student_count(adata)

    try:
        source_context = context.build_source_context(
            source_text, source_files_json, source_uploads, strict=False
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

    rubric_text = context.load_rubric_text(rubric_name)
    persona = config.get_persona(persona_id)
    patterns = config.list_feedback_patterns()
    fb_pattern = next((item for item in patterns if item.get("id") == feedback_pattern_id), None)
    fb_pattern = fb_pattern or (patterns[0] if patterns else None)
    preset = source_materials.response_preset(response_kind)
    bundle = estimates.estimate_bundle(
        assignment_name,
        assignment_description,
        source_context,
        student_count,
        response_kind,
    )
    model = (model_id or "").strip() or config.get_openrouter_model()
    budget = orc.teacher_workflow_budget(
        bundle,
        rubric_text,
        model,
        student_count=student_count,
        persona=persona,
        feedback_pattern=fb_pattern,
        output_tokens_per_student=preset["output_tokens_per_student"],
    )

    source_tokens = int(source_context.get("tokens_est") or 0)
    assignment_tokens = source_materials.estimate_text_tokens(assignment_description)
    rubric_tokens = source_materials.estimate_text_tokens(rubric_text)
    response_tokens_each = source_materials.estimate_text_tokens(
        source_materials.synthetic_student_response(response_kind)
    )
    warnings = source_materials.context_warnings(source_context)
    warnings.extend(source_context.get("errors") or [])
    if budget.get("warnings"):
        warnings.extend(budget.get("warnings") or [])
    if budget.get("reasons"):
        warnings.extend(budget.get("reasons") or [])

    return JSONResponse(build_estimate_payload(
        assignment_name=assignment_name,
        student_count=student_count,
        count_basis=count_basis,
        response_kind=response_kind,
        response_label=preset["label"],
        source_tokens=source_tokens,
        assignment_tokens=assignment_tokens,
        rubric_tokens=rubric_tokens,
        response_tokens_each=response_tokens_each,
        budget=budget,
        materials=source_context.get("materials", []),
        estimated_cost_label=estimates.cost_label(budget.get("estimated_cost")),
        warnings=warnings,
    ))


@router.post("/api/powergrader/start")
def pg_start(
    course_id: str = Form(""),
    assignment_id: str = Form(""),
    mode: str = Form("fast"),
    watch_late: str = Form("true"),
    auto_post: str = Form("false"),
    rubric_name: str = Form(""),
    persona_id: str = Form("sage"),
    feedback_pattern_id: str = Form(""),
    model_id: str = Form(""),
    response_kind: str = Form("scr"),
    source_text: str = Form(""),
    source_files_json: str = Form(""),
    source_uploads: list[UploadFile] = File(None),
):
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    mode = normalize_mode(mode)
    session_id = str(uuid.uuid4())
    course_name = config.course_display_name(course_id)

    # One focused owner acquires canonical local evidence before this session.
    subs, adata, refresh = assignment_refresh.refresh_assignment(course_id, assignment_id, session_id=session_id)
    if refresh.get("error"):
        return JSONResponse({"ok": False, "error": refresh["error"], "privacy_steps": []})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions found for this assignment.",
                             "privacy_steps": []})

    assignment_name = adata.get("name") or assignment_id
    assignment_description = html_to_text(adata.get("description") or "")
    points_possible = float(adata.get("points_possible") or 100)
    is_new_quiz = adata.get("is_quiz_lti_assignment") is True

    submitted = [
        s for s in subs
        if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
    ]
    if not submitted:
        return JSONResponse({"ok": False, "error": "No submitted work found for this assignment.",
                             "privacy_steps": []})
    writing_timeline_tracked = writing_timeline.is_tracked_assignment(adata)
    if writing_timeline_tracked:
        student_attachments.attach_writing_timelines(
            submitted,
            roster_submissions=subs,
        )

    initial_missing_user_ids = late_catchup.initial_missing_user_ids(subs or [])
    submitted_user_ids = sorted({str(s.get("user_id", "")) for s in submitted if s.get("user_id")})

    selected_model = (model_id or "").strip() or config.get_openrouter_model()
    late_watch = build_late_watch_state(
        mode=mode,
        watch_late=watch_late,
        has_openrouter_key=config.has_openrouter_key(),
        initial_missing_user_ids=initial_missing_user_ids,
        submitted_user_ids=submitted_user_ids,
        response_kind=response_kind,
        new_quiz_snapshot=is_new_quiz,
    )

    # AI workflow
    ai_result = ai_workflow.run_ai_workflow(
        mode=mode,
        submitted=submitted,
        assignment_name=assignment_name,
        assignment_description=assignment_description,
        course_id=course_id,
        course_name=course_name,
        assignment_id=assignment_id,
        session_id=session_id,
        rubric_name=rubric_name,
        persona_id=persona_id,
        feedback_pattern_id=feedback_pattern_id,
        selected_model=selected_model,
        response_kind=response_kind,
        source_text=source_text,
        source_files_json=source_files_json,
        source_uploads=source_uploads,
        has_openrouter_key=config.has_openrouter_key(),
    )
    if not ai_result["ok"]:
        return JSONResponse(build_start_error_payload(
            ai_result["error"],
            privacy_steps=ai_result["privacy_steps"],
            budget=ai_result.get("budget"),
            debug_path=ai_result.get("debug_path"),
        ))
    privacy_steps = ai_result["privacy_steps"]
    privacy_artifacts = ai_result["privacy_artifacts"]
    ai_by_uid = ai_result["ai_by_uid"]
    late_watch["source_context"] = ai_result.get("source_context") or {}

    # Roster context
    roster_settings = config.get_roster_student_settings(course_id)
    tier_map = config.roster_tier_by_id(course_id)
    monitored = config.get_monitored_students()
    extra_time_list = config.get_extra_time(course_id)
    extra_time_map = start_workflow.build_extra_time_map(extra_time_list)

    students = session_builder.build_students(
        submitted=submitted,
        ai_by_uid=ai_by_uid,
        ai_item_by_uid=ai_result.get("ai_item_by_uid") or {},
        ai_failures=ai_result.get("ai_failures") or {},
        roster_settings=roster_settings,
        tier_map=tier_map,
        monitored=monitored,
        extra_time_map=extra_time_map,
    )

    privacy_artifacts, privacy_steps = start_workflow.append_privacy_audit_step(
        privacy_artifacts=privacy_artifacts,
        assignment_name=assignment_name,
        session_id=session_id,
        course_id=course_id,
        assignment_id=assignment_id,
        mode=mode,
        selected_model=selected_model,
        privacy_steps=privacy_steps,
        write_privacy_audit_file=_write_privacy_audit_file,
        privacy_step=_privacy_step,
    )

    # Derive auto_post: enabled only for assisted/packet, not New Quiz, not fast
    auto_post_enabled = (
        str(auto_post).lower() in {"1", "true", "yes", "on"}
        and mode in ("assisted", "packet")
        and not is_new_quiz
    )

    session = start_workflow.build_start_session(
        build_session=session_builder.build_session,
        session_id=session_id,
        course_id=course_id,
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        points_possible=points_possible,
        mode=mode,
        rubric_name=rubric_name,
        persona_id=persona_id,
        selected_model=selected_model,
        assignment_description=assignment_description,
        response_kind=response_kind,
        privacy_steps=privacy_steps,
        privacy_artifacts=privacy_artifacts,
        students=students,
        mode_label=_mode_label(mode),
        copilot_packet=ai_result.get("copilot_packet"),
        late_watch=late_watch,
        canvas_writeback_supported=not is_new_quiz,
        comment_writeback_supported=is_new_quiz,
        new_quiz_item_finalization_supported=is_new_quiz,
        evidence_manifest=refresh.get("manifest_path"),
        evidence_status=refresh.get("status", "unknown"),
        auto_post_enabled=auto_post_enabled,
    )
    session["writing_timeline_tracked"] = writing_timeline_tracked
    _save_session(session)

    # For assisted mode with auto_post, run the initial trigger under the session lock
    auto_post_summary = None
    if auto_post_enabled and mode == "assisted":
        from api.powergrader.interactive_autopush import run_interactive_autopush
        with session_store.session_lock(session_id):
            session = _load_session(session_id)
            if session:
                trigger_result = run_interactive_autopush(
                    session=session,
                    trigger="assisted_start",
                    canvas_get_all=canvas_get_all,
                    canvas_get=canvas_get,
                    canvas_send=_canvas_send,
                    only_user_ids=None,
                )
                if trigger_result:
                    session["auto_post_summary"] = trigger_result["summary"]
                    session.setdefault("auto_post_log", []).append(trigger_result["log_entry"])
                    _save_session(session)
                    _notify_write_through(session, trigger_result["summary"].get("pushed"))
                    auto_post_summary = trigger_result["summary"]

    payload = build_start_success_payload(
        session_id=session_id,
        students=students,
        assignment_name=assignment_name,
        mode=mode,
        mode_label=_mode_label(mode),
        ai_by_uid=ai_by_uid,
        privacy_steps=privacy_steps,
        privacy_artifacts=privacy_artifacts,
        copilot_packet=ai_result.get("copilot_packet"),
        evidence_status=refresh.get("status", "unknown"),
    )
    if auto_post_summary:
        payload["auto_post_summary"] = auto_post_summary
    return JSONResponse(payload)


@router.post("/api/powergrader/new-quiz-csv")
async def pg_new_quiz_csv(
    course_id: str = Form(""), assignment_id: str = Form(""),
    assignment_name: str = Form(""), csv_upload: UploadFile = File(None),
):
    context_value, error = _powergrader_assignment_context(course_id, assignment_id)
    if error:
        return JSONResponse({"ok": False, "error": error})
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    if not csv_upload:
        return JSONResponse({"ok": False, "error": "Choose a Student Analysis CSV first."})
    raw = await csv_upload.read()
    try:
        session = new_quiz_csv.make_csv_session(
            session_id=str(uuid.uuid4()), course_id=course_id, assignment_id=assignment_id,
            assignment_name=assignment_name or assignment_id, raw=raw,
        )
    except new_quiz_csv.CsvProvenanceError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})
    _save_session(session)
    return JSONResponse({"ok": True, "session_id": session["session_id"],
                         "student_count": len(session["students"]), "review_only": True})


@router.get("/api/powergrader/session/{session_id}")
def pg_get_session(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    # Blind-first withholds unrevealed AI scores here rather than in the browser.
    # A value the page received has already had its chance to anchor the teacher.
    return JSONResponse({
        "ok": True,
        "session": blind_first.project_session(session),
        "blind_first": blind_first.summary(session),
    })


@router.get("/api/powergrader/session/{session_id}/staged")
def pg_get_staged(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    marker = session.get("assistant_staged")
    marker = marker if isinstance(marker, dict) else {}
    scored = sum(1 for student in (session.get("students") or [])
                 if student.get("ai_score") is not None)
    return JSONResponse({
        "ok": True,
        "staged_at": marker.get("staged_at") or marker.get("ts"),
        "updated": marker.get("updated", 0),
        "scored": scored,
    })


@router.post("/api/powergrader/session/{session_id}/late-watch")
def pg_late_watch(
    session_id: str,
    enabled: str = Form("true"),
):
    with session_store.session_lock(session_id):
        session = _load_session(session_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
        session_actions.invalidate_pending_review(session)
        if session.get("mode") not in ("assisted", "packet"):
            return JSONResponse({"ok": False, "error": "Late catch-up requires Auto-score with AI or AI chat mode."})
        if not (session.get("late_watch") or {}).get("supported"):
            return JSONResponse({"ok": False, "error": (session.get("late_watch") or {}).get("reason") or "Late catch-up is not supported for this session."})
        late_watch = session.get("late_watch") or {}
        late_watch["enabled"] = str(enabled).lower() in {"1", "true", "yes", "on"}
        if not late_watch["enabled"]:
            late_watch["reason"] = late_watch.get("reason") or "Late catch-up is disabled for this session."
        else:
            if late_watch.get("supported"):
                late_watch["reason"] = ""
        session["late_watch"] = late_watch
        _save_session(session)
    return JSONResponse({"ok": True, "late_watch": late_watch})


@router.post("/api/powergrader/session/{session_id}/late-preview")
def pg_late_preview(session_id: str):
    with session_store.session_lock(session_id):
        session = _load_session(session_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
        session_actions.invalidate_pending_review(session)
        err = _late_watch_error(session)
        if err:
            return JSONResponse({"ok": False, "error": err})
        if not (session.get("late_watch") or {}).get("supported"):
            return JSONResponse({"ok": False, "error": (session.get("late_watch") or {}).get("reason") or "Late catch-up is not supported for this session."})

        subs, adata, fetch_err = canvas_fetch.fetch_submissions(
            str(session.get("course_id") or ""),
            str(session.get("assignment_id") or ""),
        )
        if fetch_err:
            return JSONResponse({"ok": False, "error": fetch_err})

        new_subs = late_catchup.find_new_submissions(session, subs or [])
        now_iso = datetime.now().isoformat(timespec="seconds")
        late_catchup.update_late_watch_after_preview(session, len(new_subs), now_iso)
        _save_session(session)
    return JSONResponse(build_late_preview_payload(new_subs))


@router.post("/api/powergrader/session/{session_id}/late-score")
def pg_late_score(session_id: str):
    with session_store.session_lock(session_id):
        session = _load_session(session_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
        session_actions.invalidate_pending_review(session)
        err = _late_watch_error(session)
        if err:
            return JSONResponse({"ok": False, "error": err})
        if not (session.get("late_watch") or {}).get("supported"):
            return JSONResponse({"ok": False, "error": (session.get("late_watch") or {}).get("reason") or "Late catch-up is not supported for this session."})
        result = _run_late_catchup_score(session)
        if not result["ok"]:
            return JSONResponse(result)
        appended_user_ids = result.get("appended_user_ids") or []
        # Auto-post trigger for assisted mode
        if appended_user_ids and (session.get("auto_post") or {}).get("enabled") and session.get("mode") == "assisted":
            from api.powergrader.interactive_autopush import run_interactive_autopush
            trigger_result = run_interactive_autopush(
                session=session,
                trigger="assisted_late",
                canvas_get_all=canvas_get_all,
                canvas_get=canvas_get,
                canvas_send=_canvas_send,
                only_user_ids=set(appended_user_ids),
            )
            if trigger_result:
                session["auto_post_summary"] = trigger_result["summary"]
                session.setdefault("auto_post_log", []).append(trigger_result["log_entry"])
                _save_session(session)
                _notify_write_through(session, trigger_result["summary"].get("pushed"))
        else:
            _save_session(session)
    return JSONResponse({
        "ok": True,
        "appended": result["appended"],
        "ai_scored": result["ai_scored"],
        "batch_id": result["batch_id"],
        "session_id": result["session_id"],
    })


@router.post("/api/powergrader/session/{session_id}/import-results")
def pg_import_results(
    session_id: str,
    results: str = Form(""),
    batch_id: str = Form(""),
):
    with session_store.session_lock(session_id):
        session = _load_session(session_id)
        if session:
            session_actions.invalidate_pending_review(session)
            _save_session(session)
        payload, status_code = import_results.import_results_into_session(
            session_id,
            results,
            batch_id=batch_id if isinstance(batch_id, str) else "",
            load_session=_load_session,
            save_session=_save_session,
            vault_factory=_vault,
        )
        # If auto-post is enabled, run the trigger scoped to exact updated users
        if payload.get("ok") and payload.get("updated", 0) > 0:
            session = _load_session(session_id)
            if session and (session.get("auto_post") or {}).get("enabled"):
                from api.powergrader.interactive_autopush import run_interactive_autopush
                updated_user_ids = set(payload.get("updated_user_ids") or [])
                if updated_user_ids:
                    trigger_result = run_interactive_autopush(
                        session=session,
                        trigger="packet_import",
                        canvas_get_all=canvas_get_all,
                        canvas_get=canvas_get,
                        canvas_send=_canvas_send,
                        only_user_ids=updated_user_ids,
                    )
                    if trigger_result:
                        session["auto_post_summary"] = trigger_result["summary"]
                        session.setdefault("auto_post_log", []).append(trigger_result["log_entry"])
                        _save_session(session)
                        _notify_write_through(session, trigger_result["summary"].get("pushed"))
                        payload["auto_post_summary"] = trigger_result["summary"]
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/powergrader/session/{session_id}/auto-post-disable")
def pg_auto_post_disable(session_id: str):
    with session_store.session_lock(session_id):
        session = _load_session(session_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
        auto_post = session.get("auto_post") or {}
        if not auto_post.get("enabled"):
            return JSONResponse({"ok": True, "auto_post": auto_post, "message": "Already disabled."})
        from datetime import datetime, timezone
        auto_post["enabled"] = False
        auto_post["disabled_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        session["auto_post"] = auto_post
        _save_session(session)
    return JSONResponse({
        "ok": True,
        "auto_post": auto_post,
        "auto_post_summary": session.get("auto_post_summary"),
    })


@router.post("/api/powergrader/session/{session_id}/blind-first")
def pg_blind_first(
    session_id: str,
    enabled: str = Form("true"),
    threshold: str = Form(""),
):
    payload, status_code = blind_first.set_enabled(
        session_id,
        enabled=enabled,
        threshold=threshold,
        load_session=_load_session,
        save_session=_save_session,
    )
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/powergrader/session/{session_id}/blind-reveal")
def pg_blind_reveal(
    session_id: str,
    user_id: str = Form(""),
    blind_score: str = Form(""),
    blind_feedback: str = Form(""),
):
    payload, status_code = blind_first.reveal(
        session_id,
        user_id=user_id,
        blind_score=blind_score,
        blind_feedback=blind_feedback,
        load_session=_load_session,
        save_session=_save_session,
    )
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/powergrader/session/{session_id}/grade")
def pg_grade(
    session_id: str,
    user_id: str = Form(""),
    teacher_score: str = Form(""),
    teacher_feedback: str = Form(""),
    status: str = Form("approved"),
):
    payload, status_code = session_actions.save_grade(
        session_id,
        user_id=user_id,
        teacher_score=teacher_score,
        teacher_feedback=teacher_feedback,
        status=status,
        load_session=_load_session,
        save_session=_save_session,
    )
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/powergrader/session/{session_id}/push-review")
def pg_push_review(
    session_id: str,
    user_ids: str = Form(""),
):
    payload, status_code = session_actions.review_push(
        session_id,
        user_ids=user_ids,
        load_session=_load_session,
        save_session=_save_session,
        canvas_get=canvas_get,
    )
    return JSONResponse(payload, status_code=status_code)


def _notify_write_through(session, pushed) -> None:
    """Converge the submission mirror after a verified grade-write batch.

    Fires the delayed, fire-and-forget write-through refresh so mirror-backed
    reads pick up the just-posted grades. Best-effort: mirror_service already
    guards on token/mirror-enabled/workspace and swallows its own errors.
    """
    try:
        course_id = (session or {}).get("course_id")
        if course_id and pushed:
            mirror_service.notify_course_changed(course_id)
    except Exception as exc:
        operational_log.emit("mirror.notify_course_changed", "failed", error_class=type(exc))


@router.post("/api/powergrader/session/{session_id}/push")
def pg_push(
    session_id: str,
    user_ids: str = Form(""),
    review_token: str = Form(""),
):
    payload, status_code = session_actions.push_grades(
        session_id,
        user_ids=user_ids,
        review_token=review_token,
        load_session=_load_session,
        save_session=_save_session,
        canvas_send=_canvas_send,
        canvas_get=canvas_get,
    )
    if status_code == 200 and payload.get("pushed"):
        _notify_write_through(_load_session(session_id), payload.get("pushed"))
    return JSONResponse(payload, status_code=status_code)


def _new_quiz_preflight(session: dict, student: dict, decisions: list[dict]) -> dict:
    return new_quiz_grader.preflight(
        canvas_base=config.get_canvas_base(), token=config.get_token(),
        assignment_id=str(session["assignment_id"]), user_id=str(student["user_id"]),
        decisions=decisions,
    )


def _new_quiz_apply(session: dict, student: dict, decisions: list[dict], pending: dict) -> dict:
    return new_quiz_grader.apply(
        canvas_base=config.get_canvas_base(), token=config.get_token(),
        assignment_id=str(session["assignment_id"]), user_id=str(student["user_id"]),
        decisions=decisions, baseline=pending,
    )


def _resolve_new_quiz_csv(session: dict, student: dict, row: dict) -> dict:
    return new_quiz_grader.resolve_csv_provenance(
        canvas_base=config.get_canvas_base(), token=config.get_token(),
        assignment_id=str(session["assignment_id"]), user_id=str(student["user_id"]),
        attempt=int(row["attempt"]), item_ids=list(row["item_ids"]),
    )


@router.post("/api/powergrader/session/{session_id}/new-quiz-csv-resolve")
def pg_new_quiz_csv_resolve(session_id: str, user_id: str = Form("")):
    payload, status_code = session_actions.resolve_new_quiz_csv_provenance(
        session_id, user_id=user_id, load_session=_load_session, save_session=_save_session,
        resolver=_resolve_new_quiz_csv,
    )
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/powergrader/session/{session_id}/new-quiz-review")
def pg_new_quiz_review(session_id: str, user_id: str = Form(""), item_decisions: str = Form("")):
    payload, status_code = session_actions.review_new_quiz_finalization(
        session_id, user_id=user_id, decisions_json=item_decisions,
        load_session=_load_session, save_session=_save_session, preflight=_new_quiz_preflight,
    )
    return JSONResponse(payload, status_code=status_code)


def _converge_new_quiz_after_finalize(session, user_id) -> None:
    """After a verified New Quiz finalize, converge both freshness surfaces:
    the gradebook submission (write-through refresh) and the separate New Quiz
    response snapshot (stale-invalidate so the next read re-fetches live via the
    existing native chain). Best-effort; never fails the finalize that landed.
    """
    _notify_write_through(session, [user_id])
    try:
        course_id = (session or {}).get("course_id")
        assignment_id = (session or {}).get("assignment_id")
        if course_id and assignment_id:
            from api.mirror import new_quizzes
            new_quizzes.invalidate_responses(course_id, assignment_id)
    except Exception as exc:
        operational_log.emit("new_quizzes.response_invalidate", "failed", error_class=type(exc))


@router.post("/api/powergrader/session/{session_id}/new-quiz-finalize")
def pg_new_quiz_finalize(session_id: str, user_id: str = Form(""), review_token: str = Form(""), item_decisions: str = Form("")):
    payload, status_code = session_actions.finalize_new_quiz(
        session_id, user_id=user_id, review_token=review_token, decisions_json=item_decisions,
        load_session=_load_session, save_session=_save_session, apply=_new_quiz_apply,
    )
    if status_code == 200 and payload.get("status") == "finalized":
        _converge_new_quiz_after_finalize(_load_session(session_id), user_id)
    return JSONResponse(payload, status_code=status_code)
