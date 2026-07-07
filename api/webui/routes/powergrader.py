"""PowerGrader routes — keyboard-driven grading with optional AI assistance.

Modes:
  fast      Download → queue → keyboard-grade → bulk push
  assisted  Same + OpenRouter pre-fills score/feedback per student

Page routes:
  GET /powergrader                     Setup screen
  GET /powergrader/session/<id>        Queue screen

API routes:
  GET  /api/powergrader/sessions           List workspace sessions
  POST /api/powergrader/start              Create session (fetch + optional AI)
  GET  /api/powergrader/session/<id>       Get session JSON
  POST /api/powergrader/session/<id>/grade Save one student's grade
  POST /api/powergrader/session/<id>/push  Push approved to Canvas
"""
import json
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import openrouter_client as orc

from .. import config, source_materials, workspace
from ..canvas_client import _canvas_get, _canvas_send
from ..deps import list_rubric_files, templates
from powergrader import (ai_workflow, canvas_fetch, context, estimates,
                         import_results, late_catchup, packet, privacy,
                         session_actions, session_builder, session_store)
from .powergrader_late import (
    _build_late_catchup_students as _build_late_catchup_students_impl,
    _late_watch_error as _late_watch_error_impl,
    _run_late_catchup_score as _run_late_catchup_score_impl,
)

try:
    from nq_report import html_to_text
except ModuleNotFoundError:
    from api.nq_report import html_to_text

router = APIRouter(tags=["powergrader"])

# Compatibility aliases so existing tests continue to work
_pg_dir = session_store.pg_dir
_session_path = session_store.session_path
_safe_session_id = session_store.safe_session_id
_mode_label = session_store.mode_label
_load_session = session_store.load_session
_save_session = session_store.save_session

_privacy_step = privacy.privacy_step
_feedback_artifact_dirs = privacy.feedback_artifact_dirs
_write_privacy_audit_file = privacy.write_privacy_audit_file
_write_openrouter_debug_file = privacy.write_openrouter_debug_file

_build_safe_ai_packet = packet.build_safe_ai_packet
_vault = context.vault

_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
AI_MODES = {"packet", "assisted"}


def _late_watch_error(session: dict, *, require_key: bool = False, require_source_context: bool = False) -> str | None:
    return _late_watch_error_impl(
        session,
        require_key=require_key,
        require_source_context=require_source_context,
    )


def _build_late_catchup_students(
    *,
    course_id: str,
    assignment: dict,
    submitted: list[dict],
    ai_by_uid: dict,
    batch_id: str,
) -> list[dict]:
    return _build_late_catchup_students_impl(
        course_id=course_id,
        assignment=assignment,
        submitted=submitted,
        ai_by_uid=ai_by_uid,
        batch_id=batch_id,
    )


def _run_late_catchup_score(session: dict) -> dict:
    return _run_late_catchup_score_impl(session, save_session=_save_session)


# --------------------------------------------------------------------------
# Page routes
# --------------------------------------------------------------------------

@router.get("/powergrader", response_class=HTMLResponse)
def powergrader_setup(request: Request):
    source_dir = source_materials.ensure_source_folder()
    persona_dir = config.get_persona_folder()
    return templates.TemplateResponse(request, "powergrader_setup.html", {
        "nav_section":    "feedback",
        "saved_courses":  config.active_courses(),
        "rubrics":        [r["label"] for r in list_rubric_files()],
        "personas":       config.list_personas(),
        "has_openrouter": config.has_openrouter_key(),
        "openrouter_model": config.get_openrouter_model(),
        "default_openrouter_model": config.DEFAULT_OPENROUTER_MODEL,
        "openrouter_model_presets": config.openrouter_model_presets(),
        "has_workspace":  bool(workspace.workspace_root()),
        "rubrics_folder": workspace.folder("Rubrics"),
        "ai_ta_folder": workspace.folder("AI-TA"),
        "persona_folder": persona_dir,
        "source_materials_folder": source_dir,
        "source_material_files": source_materials.list_source_files(),
        "source_response_presets": source_materials.RESPONSE_PRESETS,
    })


@router.get("/powergrader/session/{session_id}", response_class=HTMLResponse)
def powergrader_queue(request: Request, session_id: str):
    session = _load_session(session_id)
    if not session:
        return HTMLResponse("<h2>Session not found.</h2>", status_code=404)
    return templates.TemplateResponse(request, "powergrader_queue.html", {
        "nav_section":      "feedback",
        "session_id":       session_id,
        "assignment_name":  session.get("assignment_name", ""),
        "course_id":        session.get("course_id", ""),
        "mode":             session.get("mode", "fast"),
        "mode_label":       session.get("mode_label") or _mode_label(session.get("mode", "fast")),
        "student_count":    len(session.get("students", [])),
        "canvas_base":      config.get_canvas_base(),
    })


# --------------------------------------------------------------------------
# API routes
# --------------------------------------------------------------------------

@router.get("/api/powergrader/sessions")
def list_sessions():
    return JSONResponse({"sessions": session_store.list_session_summaries()})


@router.post("/api/powergrader/estimate")
def pg_estimate(
    course_id: str = Form(""),
    assignment_id: str = Form(""),
    rubric_name: str = Form(""),
    persona_id: str = Form("sage"),
    model_id: str = Form(""),
    response_kind: str = Form("scr"),
    source_text: str = Form(""),
    source_files_json: str = Form(""),
    source_uploads: list[UploadFile] = File(None),
):
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "Select a course and assignment first."})

    adata, err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if err:
        return JSONResponse({"ok": False, "error": err})
    adata = adata or {}
    assignment_name = adata.get("name") or assignment_id
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
    fb_pattern = patterns[0] if patterns else None
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

    return JSONResponse({
        "ok": True,
        "assignment_name": assignment_name,
        "student_count": student_count,
        "count_basis": count_basis,
        "response_kind": response_kind,
        "response_label": preset["label"],
        "tokens": {
            "source_materials": source_tokens,
            "assignment_context": assignment_tokens,
            "rubric": rubric_tokens,
            "student_response_each": response_tokens_each,
            "estimated_input": budget.get("input_tokens"),
            "estimated_output": budget.get("estimated_output_tokens"),
        },
        "materials": [
            {
                "title": m.get("title"),
                "source": m.get("source"),
                "tokens_est": m.get("tokens_est"),
                "chars": m.get("chars"),
            }
            for m in source_context.get("materials", [])
        ],
        "budget": budget,
        "estimated_cost_label": estimates.cost_label(budget.get("estimated_cost")),
        "warnings": warnings,
        "caching_note": (
            "Estimate assumes fresh input. Some OpenRouter providers may discount "
            "cached prompt reads, but Canvas Expert does not count on that."
        ),
    })


@router.post("/api/powergrader/start")
def pg_start(
    course_id: str = Form(""),
    assignment_id: str = Form(""),
    mode: str = Form("fast"),
    watch_late: str = Form("true"),
    rubric_name: str = Form(""),
    persona_id: str = Form("sage"),
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
    if mode not in {"fast", "packet", "assisted"}:
        mode = "fast"
    session_id = str(uuid.uuid4())

    # Fetch submissions
    subs, adata, err = canvas_fetch.fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err, "privacy_steps": []})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions found for this assignment.",
                             "privacy_steps": []})

    assignment_name = adata.get("name") or assignment_id
    assignment_description = html_to_text(adata.get("description") or "")
    points_possible = float(adata.get("points_possible") or 100)

    submitted = [
        s for s in subs
        if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
    ]
    if not submitted:
        return JSONResponse({"ok": False, "error": "No submitted work found for this assignment.",
                             "privacy_steps": []})

    initial_missing_user_ids = late_catchup.initial_missing_user_ids(subs or [])
    submitted_user_ids = sorted({str(s.get("user_id", "")) for s in submitted if s.get("user_id")})

    canvas_fetch.enrich_with_code_files(submitted)

    selected_model = (model_id or "").strip() or config.get_openrouter_model()
    watch_late_enabled = str(watch_late).lower() in {"1", "true", "yes", "on"}
    late_supported = mode == "assisted" and config.has_openrouter_key()
    late_reason = ""
    if not watch_late_enabled:
        late_reason = "Late catch-up is disabled for this session."
    elif mode != "assisted":
        late_reason = "Late catch-up requires Auto-Score With API."
        watch_late_enabled = False
    elif not late_supported:
        late_reason = "Late catch-up requires Auto-Score With API and a saved OpenRouter key."
        watch_late_enabled = False

    late_watch = {
        "enabled": watch_late_enabled,
        "supported": late_supported,
        "reason": late_reason,
        "initial_missing_user_ids": initial_missing_user_ids,
        "known_user_ids": submitted_user_ids,
        "scored_user_ids": [],
        "last_checked": None,
        "last_scored": None,
        "last_summary": "",
        "source_context": {},
        "response_kind": response_kind,
    }

    # AI workflow
    ai_result = ai_workflow.run_ai_workflow(
        mode=mode,
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
        source_text=source_text,
        source_files_json=source_files_json,
        source_uploads=source_uploads,
        has_openrouter_key=config.has_openrouter_key(),
    )
    if not ai_result["ok"]:
        return JSONResponse({
            "ok": False,
            "error": ai_result["error"],
            "privacy_steps": ai_result["privacy_steps"],
            **({"budget": ai_result["budget"]} if ai_result.get("budget") else {}),
            **({"debug_path": ai_result["debug_path"]} if ai_result.get("debug_path") else {}),
        })
    privacy_steps = ai_result["privacy_steps"]
    privacy_artifacts = ai_result["privacy_artifacts"]
    ai_by_uid = ai_result["ai_by_uid"]
    late_watch["source_context"] = ai_result.get("source_context") or {}

    # Roster context
    roster_settings = config.get_roster_student_settings(course_id)
    tier_map = config.roster_tier_by_id(course_id)
    monitored = config.get_monitored_students()
    extra_time_list = config.get_extra_time(course_id)
    extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}

    students = session_builder.build_students(
        submitted=submitted,
        ai_by_uid=ai_by_uid,
        roster_settings=roster_settings,
        tier_map=tier_map,
        monitored=monitored,
        extra_time_map=extra_time_map,
    )

    if privacy_artifacts.get("private_folder"):
        audit_path = _write_privacy_audit_file(
            privacy_artifacts["private_folder"],
            assignment_name,
            session_id,
            course_id,
            assignment_id,
            selected_model if mode == "assisted" else "",
            privacy_steps,
            privacy_artifacts,
        )
        if audit_path:
            privacy_artifacts["privacy_audit"] = audit_path
            privacy_steps.append(_privacy_step(
                "privacy_audit", "Saved PowerGrader privacy audit", "ok",
                "Private decoder folder includes a JSON record of these privacy steps.",
                path=audit_path,
            ))
        else:
            privacy_steps.append(_privacy_step(
                "privacy_audit", "Saved PowerGrader privacy audit", "warn",
                "Could not write the optional privacy audit JSON; session still records these steps.",
            ))

    session = session_builder.build_session(
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
    )
    _save_session(session)

    return JSONResponse({
        "ok":             True,
        "session_id":     session_id,
        "student_count":  len(students),
        "assignment_name": assignment_name,
        "mode":           mode,
        "mode_label":     _mode_label(mode),
        "ai_scored":      len(ai_by_uid),
        "privacy_steps":   privacy_steps,
        "packet_zip":      privacy_artifacts.get("packet_zip"),
        "copilot_batch_count": (ai_result.get("copilot_packet") or {}).get("batch_count", 0),
        "copilot_packet_folder": (ai_result.get("copilot_packet") or {}).get("packet_folder"),
    })


@router.get("/api/powergrader/session/{session_id}")
def pg_get_session(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    return JSONResponse({"ok": True, "session": session})


@router.post("/api/powergrader/session/{session_id}/late-watch")
def pg_late_watch(
    session_id: str,
    enabled: str = Form("true"),
):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    if session.get("mode") != "assisted":
        return JSONResponse({"ok": False, "error": "Late catch-up requires Auto-Score With API."})
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
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    err = _late_watch_error(session)
    if err:
        return JSONResponse({"ok": False, "error": err})

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
    students = [
        {
            "user_id": str(sub.get("user_id", "")),
            "name": (sub.get("user") or {}).get("name")
                     or (sub.get("user") or {}).get("sortable_name")
                     or str(sub.get("user_id", "")),
            "submitted_at": sub.get("submitted_at") or "",
        }
        for sub in new_subs
    ]
    message = f"{len(new_subs)} new late submission(s) found."
    return JSONResponse({
        "ok": True,
        "new_count": len(new_subs),
        "students": students,
        "message": message,
    })


@router.post("/api/powergrader/session/{session_id}/late-score")
def pg_late_score(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    result = _run_late_catchup_score(session)
    if not result["ok"]:
        return JSONResponse(result)
    return JSONResponse({
        "ok": True,
        "appended": result["appended"],
        "ai_scored": result["ai_scored"],
        "batch_id": result["batch_id"],
        "session_id": result["session_id"],
    })


@router.get("/api/powergrader/session/{session_id}/packet")
def pg_download_packet(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    artifacts = session.get("privacy_artifacts") or {}
    packet_zip = artifacts.get("packet_zip") or ""
    if not packet_zip or not os.path.isfile(packet_zip):
        return JSONResponse({"ok": False, "error": "Safe AI Packet ZIP not found."}, status_code=404)
    filename = os.path.basename(packet_zip)
    return FileResponse(packet_zip, media_type="application/zip", filename=filename)


@router.post("/api/powergrader/session/{session_id}/import-results")
def pg_import_results(
    session_id: str,
    results: str = Form(""),
    batch_id: str = Form(""),
):
    payload, status_code = import_results.import_results_into_session(
        session_id,
        results,
        batch_id=batch_id if isinstance(batch_id, str) else "",
        load_session=_load_session,
        save_session=_save_session,
        vault_factory=_vault,
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


@router.post("/api/powergrader/session/{session_id}/push")
def pg_push(
    session_id: str,
    user_ids: str = Form(""),
):
    payload, status_code = session_actions.push_grades(
        session_id,
        user_ids=user_ids,
        load_session=_load_session,
        save_session=_save_session,
        canvas_send=_canvas_send,
    )
    return JSONResponse(payload, status_code=status_code)
