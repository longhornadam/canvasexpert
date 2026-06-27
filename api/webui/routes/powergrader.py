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
import traceback
import uuid
import zipfile
from datetime import datetime

import requests
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import feedback_pipeline as fp
import feedback_safety as safety
import feedback_vault
import openrouter_client as orc

from .. import config, source_materials, workspace
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_headers, _canvas_send
from ..deps import list_rubric_files, templates
try:
    from nq_report import html_to_text
except ModuleNotFoundError:
    from api.nq_report import html_to_text

router = APIRouter(tags=["powergrader"])

_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
_MAX_CODE_BYTES = 256 * 1024
AI_MODES = {"packet", "assisted"}


# --------------------------------------------------------------------------
# Session storage helpers
# --------------------------------------------------------------------------

def _pg_dir() -> str | None:
    root = workspace.workspace_root()
    if not root:
        return None
    d = os.path.join(root, "PowerGrader")
    os.makedirs(d, exist_ok=True)
    return d


def _session_path(session_id: str) -> str | None:
    d = _pg_dir()
    if not d:
        return None
    # Guard against path traversal
    safe_id = "".join(c for c in session_id if c.isalnum() or c == "-")
    return os.path.join(d, f"{safe_id}_session.json")


def _safe_session_id(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c == "-")


def _mode_label(mode: str) -> str:
    return {
        "fast": "Grade Myself",
        "packet": "Use My AI Chat",
        "assisted": "Auto-Score With API",
    }.get(mode or "", mode or "Grade Myself")


def _load_session(session_id: str) -> dict | None:
    path = _session_path(session_id)
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_session(session: dict):
    path = _session_path(session["session_id"])
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Canvas helpers (mirrors feedback.py — kept local to avoid circular imports)
# --------------------------------------------------------------------------

def _fetch_submissions(course_id: str, assignment_id: str):
    """Fetch submissions for one assignment. Returns (subs, assignment_obj, error)."""
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": ["all"], "assignment_ids[]": [assignment_id],
         "include[]": ["assignment", "user"], "per_page": 100},
    )
    if err:
        return None, None, err
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    return subs, adata or {}, None


def _enrich_with_code_files(subs):
    """Download plain-text uploads (.py/.html/…) into s['code_files']."""
    hdrs, _ = _canvas_headers()
    if not hdrs:
        return
    sess = requests.Session()
    sess.headers.update(hdrs)
    for s in subs:
        files = []
        for att in (s.get("attachments") or []):
            fn = att.get("filename") or att.get("display_name") or ""
            if os.path.splitext(fn)[1].lower() not in _CODE_EXTS:
                continue
            if (att.get("size") or 0) > _MAX_CODE_BYTES:
                continue
            url = att.get("url")
            if not url:
                continue
            try:
                r = sess.get(url, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and len(r.content) <= _MAX_CODE_BYTES:
                files.append({"filename": fn, "text": r.text})
        if files:
            s["code_files"] = files


def _vault():
    vpath = workspace.feedback_folder("_vault")
    if vpath:
        os.makedirs(vpath, exist_ok=True)
        return feedback_vault.Vault(os.path.join(vpath, "vault.json"))
    root = workspace.workspace_root()
    fallback = os.path.join(root or ".", "PowerGrader", "_vault")
    os.makedirs(fallback, exist_ok=True)
    return feedback_vault.Vault(os.path.join(fallback, "vault.json"))


def _load_rubric_text(rubric_name: str) -> str:
    if not rubric_name:
        return ""
    for r in list_rubric_files():
        if r["label"] == rubric_name or os.path.basename(r["path"]) == rubric_name:
            try:
                with open(r["path"], encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return ""
    return ""


def _folder_file_names(source_files_json: str) -> list[str]:
    return source_materials.parse_source_files_json(source_files_json or "")


def _uploads_list(source_uploads) -> list:
    if not source_uploads:
        return []
    if isinstance(source_uploads, list):
        return [u for u in source_uploads if getattr(u, "filename", "")]
    if getattr(source_uploads, "filename", ""):
        return [source_uploads]
    return []


def _build_source_context(
    source_text: str,
    source_files_json: str,
    source_uploads,
    *,
    strict: bool,
) -> dict:
    return source_materials.build_source_context(
        pasted_text=source_text or "",
        folder_files=_folder_file_names(source_files_json),
        uploaded_files=_uploads_list(source_uploads),
        strict=strict,
    )


def _apply_shared_context(bundle: dict, assignment_description: str, source_context: dict) -> dict:
    """Move common assignment/source context out of per-student responses."""
    assignment_description = (assignment_description or "").strip()
    materials = [
        {
            "title": m.get("title") or "Source material",
            "source": m.get("source") or "",
            "text": m.get("text") or "",
        }
        for m in (source_context or {}).get("materials", [])
        if (m.get("text") or "").strip()
    ]
    if assignment_description or materials:
        bundle["shared_context"] = {
            "assignment_description": assignment_description,
            "materials": materials,
            "note": (
                "Shared assignment/source context. Use for every response in this "
                "PowerGrader batch."
            ),
        }
    if assignment_description:
        for student in bundle.get("students") or []:
            for response in student.get("responses") or []:
                if (response.get("prompt") or "").strip() == assignment_description:
                    response["prompt"] = ""
    return bundle


def _assignment_student_count(assignment: dict) -> tuple[int, str]:
    for key, label in (
        ("needs_grading_count", "Canvas needs_grading_count"),
        ("has_submitted_submissions", "Canvas submitted count"),
    ):
        value = assignment.get(key)
        if isinstance(value, bool):
            continue
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n, label
    return 30, "default estimate"


def _estimate_bundle(
    assignment_name: str,
    assignment_description: str,
    source_context: dict,
    student_count: int,
    response_kind: str,
) -> dict:
    response = source_materials.synthetic_student_response(response_kind)
    bundle = {
        "contract_version": fp.CONTRACT_VERSION,
        "quiz_title": assignment_name or "Assignment",
        "source": "powergrader_estimate",
        "review_required": True,
        "students": [
            {
                "pseudonym": f"Student {i + 1}",
                "responses": [{
                    "item_id": "estimate",
                    "prompt": "",
                    "response": response,
                    "possible": 5,
                }],
            }
            for i in range(max(1, int(student_count or 1)))
        ],
    }
    return _apply_shared_context(bundle, assignment_description, source_context)


def _cost_label(cost) -> str:
    if cost is None:
        return "unavailable"
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return "unavailable"
    if value < 0.01:
        return "<$0.01"
    return f"${value:.2f}"


def _privacy_step(step_id: str, label: str, status: str,
                  detail: str = "", **extra) -> dict:
    item = {"id": step_id, "label": label, "status": status, "detail": detail}
    item.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return item


def _feedback_artifact_dirs() -> tuple[str | None, str | None]:
    workspace.ensure_workspace()
    return workspace.feedback_folder("SAFE"), workspace.feedback_folder("PRIVATE")


def _write_privacy_audit_file(
    private_folder: str,
    assignment_name: str,
    session_id: str,
    course_id: str,
    assignment_id: str,
    model_id: str,
    privacy_steps: list[dict],
    privacy_artifacts: dict,
) -> str | None:
    try:
        os.makedirs(private_folder, exist_ok=True)
        path = os.path.join(private_folder, f"{fp._safe(assignment_name)}__powergrader-privacy-audit.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "course_id": course_id,
                "assignment_id": assignment_id,
                "assignment_name": assignment_name,
                "model_id": model_id,
                "created": datetime.now().isoformat(timespec="seconds"),
                "privacy_steps": privacy_steps,
                "privacy_artifacts": privacy_artifacts,
            }, f, indent=2, ensure_ascii=False)
        return path
    except Exception:
        return None


def _write_openrouter_debug_file(
    private_folder: str | None,
    assignment_name: str,
    *,
    session_id: str,
    course_id: str,
    assignment_id: str,
    model_id: str,
    safe_students: int,
    packet_info: dict | None,
    budget: dict | None,
    privacy_steps: list[dict],
    exc: Exception,
) -> str | None:
    if not private_folder:
        return None
    try:
        os.makedirs(private_folder, exist_ok=True)
        path = os.path.join(private_folder, f"{fp._safe(assignment_name)}__openrouter-debug.json")
        payload = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "course_id": course_id,
            "assignment_id": assignment_id,
            "assignment_name": assignment_name,
            "openrouter": {
                "endpoint": orc.ENDPOINT,
                "model_id": model_id,
                "safe_student_count": safe_students,
                "packet_zip": (packet_info or {}).get("packet_zip"),
                "packet_folder": (packet_info or {}).get("packet_folder"),
            },
            "budget": budget or {},
            "exception": {
                "type": type(exc).__name__,
                "message": str(exc),
                "context": getattr(exc, "context", ""),
                "status_code": getattr(exc, "status_code", ""),
                "response_snippet": getattr(exc, "response_snippet", ""),
                "traceback": traceback.format_exception_only(type(exc), exc),
            },
            "privacy_steps": privacy_steps,
            "notes": [
                "No OpenRouter API key is written to this debug file.",
                "Raw real-name student submissions are not written here; inspect the Safe AI Packet and Private decoder files if needed.",
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return path
    except Exception:
        return None


def _safe_ai_packet_name(assignment_name: str) -> str:
    return f"Safe AI Packet - {fp._safe(assignment_name, max_len=60)}"


def _packet_paths(safe_dir: str, assignment_name: str) -> dict:
    packet_name = _safe_ai_packet_name(assignment_name)
    return {
        "name": packet_name,
        "dir": os.path.join(safe_dir, packet_name),
        "zip": os.path.join(safe_dir, f"{packet_name}.zip"),
    }


def _shared_context_text(bundle: dict) -> str:
    shared = (bundle or {}).get("shared_context") or {}
    chunks: list[str] = []
    assignment_description = (shared.get("assignment_description") or "").strip()
    if assignment_description:
        chunks.append("Assignment directions/context\n" + "=" * 32 + "\n" + assignment_description)
    for material in shared.get("materials") or []:
        if not isinstance(material, dict):
            continue
        title = material.get("title") or "Source material"
        source = material.get("source") or ""
        text = (material.get("text") or "").strip()
        if not text:
            continue
        header = title + (f"\nFrom: {source}" if source else "")
        chunks.append(header + "\n" + "=" * 32 + "\n" + text)
    return "\n\n".join(chunks).strip()


def _readable_responses_text(bundle: dict) -> str:
    lines = [
        "Student Responses - readable",
        "=" * 32,
        "These are fake-name copies. Do not ask the AI to identify students.",
        "",
    ]
    for student in (bundle or {}).get("students") or []:
        lines.append(f"Student: {student.get('pseudonym', 'Unknown')}")
        lines.append("-" * 32)
        for response in student.get("responses") or []:
            if response.get("item_id"):
                lines.append(f"Item ID: {response.get('item_id')}")
            if response.get("possible") is not None:
                lines.append(f"Possible points: {response.get('possible')}")
            if response.get("prompt"):
                lines.append("\nPrompt:")
                lines.append(str(response.get("prompt") or ""))
            lines.append("\nResponse:")
            lines.append(str(response.get("response") or ""))
            lines.append("")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _paste_format_text(bundle: dict) -> str:
    first_student = ((bundle or {}).get("students") or [{}])[0]
    first_response = ((first_student.get("responses") or [{}])[0])
    pseudonym = first_student.get("pseudonym") or "<copy pseudonym exactly>"
    item_id = first_response.get("item_id") or "<copy item_id exactly>"
    sample = [{
        "pseudonym": pseudonym,
        "item_id": str(item_id),
        "score": 1,
        "feedback": (
            "Brief rubric-based feedback. End with the disclosure sentence exactly once. "
            "Drafted by <persona name> (AI), reviewed by your teacher."
        ),
        "disclosure": "Drafted by <persona name> (AI), reviewed by your teacher.",
    }]
    return (
        "Paste Results Back Here - Format\n"
        "================================\n\n"
        "After your AI chat scores the packet, paste ONLY the JSON array or a JSON "
        "object with a results array back into PowerGrader.\n\n"
        "Required shape:\n\n"
        + json.dumps(sample, indent=2, ensure_ascii=False)
        + "\n\nRules:\n"
        "- Copy pseudonym and item_id exactly from Student Responses.json.\n"
        "- score may be a number or null for comment-only feedback.\n"
        "- feedback must be non-empty.\n"
        "- PowerGrader validates this before adding AI suggestions to the session.\n"
    )


def _build_safe_ai_packet(
    assignment_name: str,
    safe_dir: str,
    write_result: dict,
    llm_bundle: dict,
) -> dict:
    """Create a teacher-facing packet folder + ZIP from the SAFE artifacts."""
    paths = _packet_paths(safe_dir, assignment_name)
    packet_dir = paths["dir"]
    os.makedirs(packet_dir, exist_ok=True)

    files: list[str] = []

    def write_packet_file(name: str, text: str):
        path = os.path.join(packet_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)

    how_to_path = write_result.get("how_to_score")
    if how_to_path and os.path.isfile(how_to_path):
        with open(how_to_path, encoding="utf-8") as f:
            instructions = f.read()
    else:
        instructions = fp.build_contract_text("your AI teaching assistant")
    write_packet_file("START HERE - Instructions for your AI.txt", instructions)

    bundle_path = os.path.join(packet_dir, "Student Responses.json")
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(llm_bundle, f, indent=2, ensure_ascii=False)
    files.append(bundle_path)

    write_packet_file("Student Responses - readable.txt", _readable_responses_text(llm_bundle))

    shared_text = _shared_context_text(llm_bundle)
    write_packet_file(
        "Source Materials.txt",
        shared_text or "No separate source material was included in this packet.\n",
    )
    write_packet_file("Paste Results Back Here - Format.txt", _paste_format_text(llm_bundle))

    for student_txt in write_result.get("student_txts") or []:
        if os.path.isfile(student_txt):
            dest = os.path.join(packet_dir, os.path.basename(student_txt))
            with open(student_txt, "rb") as src, open(dest, "wb") as out:
                out.write(src.read())
            files.append(dest)

    with zipfile.ZipFile(paths["zip"], "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=os.path.basename(path))

    return {
        "packet_name": paths["name"],
        "packet_folder": packet_dir,
        "packet_zip": paths["zip"],
        "packet_files": files,
    }


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
    d = _pg_dir()
    if not d:
        return JSONResponse({"sessions": []})
    sessions = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith("_session.json"):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        students = s.get("students", [])
        sessions.append({
            "session_id":      s.get("session_id"),
            "assignment_name": s.get("assignment_name"),
            "course_id":       s.get("course_id"),
            "assignment_id":   s.get("assignment_id"),
            "created":         s.get("created"),
            "mode":            s.get("mode"),
            "mode_label":      _mode_label(s.get("mode", "fast")),
            "total":           len(students),
            "approved":        sum(1 for st in students if st.get("status") == "approved"),
            "posted":          sum(1 for st in students if st.get("posted")),
        })
    sessions.sort(key=lambda x: x.get("created") or "", reverse=True)
    return JSONResponse({"sessions": sessions})


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
    student_count, count_basis = _assignment_student_count(adata)

    try:
        source_context = _build_source_context(
            source_text, source_files_json, source_uploads, strict=False
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

    rubric_text = _load_rubric_text(rubric_name)
    persona = config.get_persona(persona_id)
    patterns = config.list_feedback_patterns()
    fb_pattern = patterns[0] if patterns else None
    preset = source_materials.response_preset(response_kind)
    bundle = _estimate_bundle(
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
        "estimated_cost_label": _cost_label(budget.get("estimated_cost")),
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
    privacy_steps: list[dict] = []
    privacy_artifacts: dict = {}

    # Fetch submissions
    subs, adata, err = _fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err, "privacy_steps": privacy_steps})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions found for this assignment.",
                             "privacy_steps": privacy_steps})

    assignment_name = adata.get("name") or assignment_id
    assignment_description = html_to_text(adata.get("description") or "")
    points_possible = float(adata.get("points_possible") or 100)

    # Filter to students who have actually submitted
    submitted = [
        s for s in subs
        if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
    ]
    if not submitted:
        return JSONResponse({"ok": False, "error": "No submitted work found for this assignment.",
                             "privacy_steps": privacy_steps})

    _enrich_with_code_files(submitted)
    privacy_steps.append(_privacy_step(
        "download", "Downloaded submitted work from Canvas", "ok",
        f"{len(submitted)} submitted student(s) loaded locally.",
    ))

    # Pull roster context for all students
    roster_settings = config.get_roster_student_settings(course_id)
    tier_map = config.roster_tier_by_id(course_id)
    monitored = config.get_monitored_students()
    extra_time_list = config.get_extra_time(course_id)
    extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}

    # AI results (populated below for assisted mode)
    ai_by_uid: dict = {}
    selected_model = (model_id or "").strip() or config.get_openrouter_model()

    if mode in AI_MODES and (mode != "assisted" or config.has_openrouter_key()):
        workspace.ensure_workspace()
        try:
            source_context = _build_source_context(
                source_text, source_files_json, source_uploads, strict=True
            )
        except Exception as e:
            return JSONResponse({
                "ok": False,
                "error": f"Could not read selected source material: {e}",
                "privacy_steps": privacy_steps,
            })
        source_warning_text = "; ".join(source_materials.context_warnings(source_context))
        if source_context.get("materials"):
            privacy_steps.append(_privacy_step(
                "source_context", "Loaded shared source material", "warn" if source_warning_text else "ok",
                (
                    f"{len(source_context['materials'])} source item(s), "
                    f"~{source_context.get('tokens_est', 0):,} input token(s)."
                    + (f" {source_warning_text}" if source_warning_text else "")
                ),
            ))
        vault = _vault()
        bundle = fp.pseudonymize_submissions(submitted, vault, assignment_name)
        bundle = _apply_shared_context(bundle, assignment_description, source_context)
        if bundle["students"]:
            vault.save()
            privacy_steps.append(_privacy_step(
                "pseudonymize", "Assigned pseudonyms and separated identities", "ok",
                f"{len(bundle['students'])} pseudonymized student bundle(s); real names remain in the local vault.",
            ))
            verdict = safety.scan_payload(bundle, vault)
            if not verdict["green"]:
                privacy_steps.append(_privacy_step(
                    "safety_scan", "Checked pseudonymized payload for real names", "warn",
                    (
                        "Potential real-name text was found before the deeper packet scrub. "
                        "The packet writer will scrub again and exclude any unsafe student from the LLM payload."
                    ),
                ))
            else:
                privacy_steps.append(_privacy_step(
                    "safety_scan", "Checked pseudonymized payload for real names", "ok",
                    "No hard PII matches found before the file-writing step.",
                ))
            rubric_text = _load_rubric_text(rubric_name)
            persona = config.get_persona(persona_id)
            patterns = config.list_feedback_patterns()
            fb_pattern = patterns[0] if patterns else None
            model = selected_model

            safe_dir, private_dir = _feedback_artifact_dirs()
            if not safe_dir or not private_dir:
                privacy_steps.append(_privacy_step(
                    "safe_private", "Wrote Safe AI Packet and Private decoder artifacts", "failed",
                    "Workspace folders were unavailable. Nothing was sent to the LLM.",
                ))
                return JSONResponse({
                    "ok": False,
                    "error": "Could not resolve Safe AI Packet / Private decoder folders — finish workspace setup first.",
                    "privacy_steps": privacy_steps,
                })
            write_result = fp.write_safe_and_private(
                bundle,
                vault,
                safe_dir,
                private_dir,
                ai_ta_name=persona.get("name") or "your AI teaching assistant",
                protected=config.active_protected_names(),
                submissions=submitted,
                rubric_text=rubric_text,
            )
            if not write_result.get("safe_bundle"):
                privacy_steps.append(_privacy_step(
                    "safe_private", "Wrote Safe AI Packet and Private decoder artifacts", "failed",
                    "The deeper scrub found hard violations. Nothing was sent to the LLM.",
                    log=write_result.get("log", []),
                ))
                return JSONResponse({
                    "ok": False,
                    "error": "Safe AI Packet write failed — privacy gate blocked this batch.",
                    "privacy_steps": privacy_steps,
                })
            privacy_artifacts = {
                "safe_folder": safe_dir,
                "private_folder": private_dir,
                "safe_bundle": write_result.get("safe_bundle"),
                "private_bundle": write_result.get("private_bundle"),
                "who_is_who": write_result.get("who_is_who"),
                "how_to_score": write_result.get("how_to_score"),
                "shared_context": write_result.get("shared_context"),
                "shared_context_excluded": write_result.get("shared_context_excluded"),
                "student_txt_count": len(write_result.get("student_txts") or []),
                "attachment_only_count": len(write_result.get("attachment_only") or []),
                "excluded_count": len(write_result.get("excluded") or []),
            }
            privacy_steps.append(_privacy_step(
                "safe_private", "Wrote inspectable Safe AI Packet and Private decoder files", "ok",
                (
                    f"Fake-name bundle, {privacy_artifacts['student_txt_count']} readable text file(s), "
                    "private raw bundle, and who-is-who decoder saved."
                ),
                safe_folder=safe_dir,
                private_folder=private_dir,
            ))
            manual_count = privacy_artifacts["attachment_only_count"] + privacy_artifacts["excluded_count"]
            if manual_count:
                privacy_steps.append(_privacy_step(
                    "manual_review", "Flagged work that needs teacher/manual handling", "warn",
                    (
                        f"{manual_count} item(s) were kept local for manual review "
                        "instead of being sent to the LLM."
                    ),
                ))
            if privacy_artifacts.get("shared_context_excluded"):
                privacy_steps.append(_privacy_step(
                    "source_context_safe", "Checked shared source context after scrubbing", "warn",
                    (
                        "The shared source context was kept out of the Safe AI Packet because a real "
                        "roster identifier survived scrubbing."
                    ),
                ))

            try:
                with open(write_result["safe_bundle"], encoding="utf-8") as f:
                    llm_bundle = json.load(f)
            except Exception as e:
                privacy_steps.append(_privacy_step(
                    "safe_payload", "Loaded Safe AI Packet for LLM scoring", "failed",
                    f"Could not reload the Safe AI Packet: {e}. Nothing was sent.",
                ))
                return JSONResponse({"ok": False, "error": f"Could not load Safe AI Packet: {e}",
                                     "privacy_steps": privacy_steps})
            safe_students = len(llm_bundle.get("students") or [])
            packet_info = _build_safe_ai_packet(assignment_name, safe_dir, write_result, llm_bundle)
            privacy_artifacts.update(packet_info)
            privacy_steps.append(_privacy_step(
                "safe_ai_packet", "Created Safe AI Packet", "ok",
                (
                    "Packet ZIP includes fake-name student responses, source material, "
                    "rubric instructions, and the paste-back JSON format."
                ),
                path=packet_info.get("packet_zip"),
            ))
            if safe_students == 0:
                privacy_steps.append(_privacy_step(
                    "llm_send", "Prepared Safe AI Packet for scoring", "warn",
                    "No students passed the packet writer for automated scoring. Grade this batch by hand.",
                ))
                privacy_steps.append(_privacy_step(
                    "reidentify", "Reattached real names locally", "warn",
                    "No AI results were generated, so there was nothing to reattach.",
                ))
            elif mode == "packet":
                privacy_steps.append(_privacy_step(
                    "manual_ai_chat", "Ready for your AI chat", "ok",
                    "Canvas Expert stopped before any API send. Use the Safe AI Packet with your own AI chat, then paste JSON results back here.",
                ))
            else:
                privacy_steps.append(_privacy_step(
                    "safe_payload", "Loaded Safe AI Packet for LLM scoring", "ok",
                    f"{safe_students} fake-name student response(s) selected for OpenRouter.",
                ))

                budget = orc.teacher_workflow_budget(
                    llm_bundle,
                    rubric_text,
                    model,
                    student_count=safe_students,
                    persona=persona,
                    feedback_pattern=fb_pattern,
                    output_tokens_per_student=source_materials.response_preset(response_kind)["output_tokens_per_student"],
                )
                if not budget["ok"]:
                    estimate = budget.get("estimated_cost")
                    estimate_text = f" Estimated batch cost: ${estimate:.2f}." if estimate is not None else ""
                    privacy_steps.append(_privacy_step(
                        "price_check", "Verified model price before sending", "failed",
                        "; ".join(budget.get("reasons") or ["cost could not be verified"]) + estimate_text,
                    ))
                    return JSONResponse({
                        "ok": False,
                        "error": (
                            f"OpenRouter model '{model}' cannot be used for teacher auto-scoring. "
                            + "; ".join(budget.get("reasons") or ["cost could not be verified"])
                            + estimate_text
                        ),
                        "budget": budget,
                        "privacy_steps": privacy_steps,
                    })
                estimate = budget.get("estimated_cost")
                warning = "; ".join(budget.get("warnings") or [])
                privacy_steps.append(_privacy_step(
                    "price_check", "Verified model price before sending", "warn" if warning else "ok",
                    (
                        f"Model {model}; estimated batch cost "
                        + (f"${estimate:.2f}" if estimate is not None else "available after provider billing")
                        + (f". {warning}" if warning else ".")
                        + " Estimate assumes fresh input; provider prompt caching is not guaranteed."
                    ),
                ))
                try:
                    results = orc.score(
                        llm_bundle, rubric_text, persona,
                        api_key=config.get_openrouter_key(),
                        model=model,
                        feedback_pattern=fb_pattern,
                    )
                    privacy_steps.append(_privacy_step(
                        "llm_send", "Sent only the Safe AI Packet to OpenRouter", "ok",
                        f"{safe_students} pseudonymized student bundle(s) sent; real names were not included.",
                    ))
                    rows = fp.reidentify(results, vault)
                    unresolved = sum(1 for row in rows if not row.get("resolved"))
                    privacy_steps.append(_privacy_step(
                        "reidentify", "Reattached real names locally", "warn" if unresolved else "ok",
                        (
                            f"{len(rows)} AI result(s) joined back to local Canvas IDs."
                            + (f" {unresolved} unresolved result(s) need review." if unresolved else "")
                        ),
                    ))
                    ai_by_uid = {row["canvas_id"]: row for row in rows if row.get("resolved")}
                except Exception as e:
                    debug_path = _write_openrouter_debug_file(
                        private_dir,
                        assignment_name,
                        session_id=session_id,
                        course_id=course_id,
                        assignment_id=assignment_id,
                        model_id=model,
                        safe_students=safe_students,
                        packet_info=packet_info,
                        budget=budget,
                        privacy_steps=privacy_steps,
                        exc=e,
                    )
                    privacy_steps.append(_privacy_step(
                        "llm_send", "Sent only the Safe AI Packet to OpenRouter", "failed",
                        f"OpenRouter error: {e}",
                        path=debug_path,
                        action_label="Open OpenRouter debug file",
                    ))
                    return JSONResponse({
                        "ok": False,
                        "error": f"OpenRouter error: {e}",
                        "privacy_steps": privacy_steps,
                        "debug_path": debug_path,
                    })
    elif mode == "assisted":
        privacy_steps.append(_privacy_step(
            "llm_send", "Sent Safe AI Packet to selected LLM", "warn",
            "No OpenRouter key is saved, so PowerGrader stayed local and did not send anything.",
        ))
    else:
        privacy_steps.append(_privacy_step(
            "fast_mode", "Grade Myself selected", "warn",
            "Grade Myself selected. No AI packet or API call was requested.",
        ))

    # Build student list, sorted by name
    students = []
    for s in submitted:
        uid = str(s.get("user_id", ""))
        user = s.get("user") or {}
        real_name = user.get("name") or user.get("sortable_name") or uid

        # Roster context
        rst = roster_settings.get(uid, {})
        tier_id = rst.get("tier_id") or ""
        tier = tier_map.get(tier_id, {})
        mon = monitored.get(uid)
        extra_days = extra_time_map.get(uid, 0)

        # Submission content (kept minimal — no raw HTML in session to keep file size down)
        body = s.get("body") or ""
        attachments = [
            {"filename": a.get("filename") or a.get("display_name", ""), "size": a.get("size", 0)}
            for a in (s.get("attachments") or [])
            if a.get("filename") or a.get("display_name")
        ]
        code_files = [
            {"filename": cf.get("filename", ""), "text": cf.get("text", "")}
            for cf in (s.get("code_files") or [])
        ]

        ai = ai_by_uid.get(uid, {})
        students.append({
            "user_id":       uid,
            "real_name":     real_name,
            "body":          body,
            "attachments":   attachments,
            "code_files":    code_files,
            "current_score": s.get("score"),
            "status":        "pending",
            "ai_score":      ai.get("score"),
            "ai_feedback":   ai.get("feedback"),
            "teacher_score": None,
            "teacher_feedback": "",
            "posted":        False,
            "tier_id":       tier_id,
            "tier_label":    tier.get("teacher_label", ""),
            "tier_alias":    tier.get("alias", ""),
            "is_monitored":  bool(mon),
            "monitored_note": (mon or {}).get("note", ""),
            "extra_time_days": extra_days,
        })

    students.sort(key=lambda x: x["real_name"].lower())

    session_id = str(uuid.uuid4())
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
    session = {
        "session_id":      session_id,
        "course_id":       course_id,
        "assignment_id":   assignment_id,
        "assignment_name": assignment_name,
        "points_possible": points_possible,
        "created":         datetime.now().isoformat(timespec="seconds"),
        "mode":            mode,
        "mode_label":      _mode_label(mode),
        "rubric_name":     rubric_name,
        "persona_id":      persona_id,
        "model_id":        selected_model if mode == "assisted" else "",
        "privacy_steps":   privacy_steps,
        "privacy_artifacts": privacy_artifacts,
        "students":        students,
        "push_log":        [],
    }
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
    })


@router.get("/api/powergrader/session/{session_id}")
def pg_get_session(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    return JSONResponse({"ok": True, "session": session})


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
):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    if not results.strip():
        return JSONResponse({"ok": False, "error": "Paste the AI result JSON first."})

    artifacts = session.get("privacy_artifacts") or {}
    safe_bundle = artifacts.get("safe_bundle") or ""
    if not safe_bundle or not os.path.isfile(safe_bundle):
        return JSONResponse({"ok": False, "error": "Safe AI Packet student response bundle is missing."})

    try:
        parsed = fp.parse_results(results)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Could not parse JSON: {e}"})
    try:
        with open(safe_bundle, encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Could not load Safe AI Packet bundle: {e}"})

    vault = _vault()
    verdict = fp.validate_results(parsed, bundle, vault)
    if not verdict["ok"]:
        return JSONResponse({
            "ok": False,
            "error": "Validation failed. Fix the JSON and paste again.",
            "validation": verdict,
        })

    rows = fp.reidentify(parsed, vault)
    by_uid = {str(row.get("canvas_id") or ""): row for row in rows if row.get("resolved")}
    updated = 0
    for st in session.get("students") or []:
        row = by_uid.get(str(st.get("user_id") or ""))
        if not row:
            continue
        st["ai_score"] = row.get("score")
        st["ai_feedback"] = row.get("feedback")
        updated += 1

    session.setdefault("ai_import_log", []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "updated": updated,
        "validation": verdict,
    })
    _save_session(session)
    return JSONResponse({
        "ok": True,
        "updated": updated,
        "validation": verdict,
        "unresolved": sum(1 for row in rows if not row.get("resolved")),
    })


@router.post("/api/powergrader/session/{session_id}/grade")
def pg_grade(
    session_id: str,
    user_id: str = Form(""),
    teacher_score: str = Form(""),
    teacher_feedback: str = Form(""),
    status: str = Form("approved"),
):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)

    score_val = None
    if teacher_score.strip():
        try:
            score_val = float(teacher_score.strip())
        except ValueError:
            return JSONResponse({"ok": False, "error": "Invalid score value."})

    updated = False
    for st in session["students"]:
        if st["user_id"] == user_id:
            st["teacher_score"] = score_val
            st["teacher_feedback"] = teacher_feedback.strip()
            st["status"] = status if status in ("approved", "skipped", "pending") else "approved"
            updated = True
            break

    if not updated:
        return JSONResponse({"ok": False, "error": "Student not found in session."})

    _save_session(session)
    approved = sum(1 for s in session["students"] if s.get("status") == "approved")
    return JSONResponse({"ok": True, "approved": approved})


@router.post("/api/powergrader/session/{session_id}/push")
def pg_push(
    session_id: str,
    user_ids: str = Form(""),
):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)

    course_id = session["course_id"]
    assignment_id = session["assignment_id"]

    # Determine which students to push
    if user_ids.strip():
        try:
            target_ids = set(json.loads(user_ids))
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid user_ids JSON."})
    else:
        # Push all approved, not yet posted
        target_ids = {
            st["user_id"] for st in session["students"]
            if st.get("status") == "approved" and not st.get("posted")
        }

    pushed, errors = 0, []
    for st in session["students"]:
        if st["user_id"] not in target_ids:
            continue
        score = st.get("teacher_score")
        feedback = (st.get("teacher_feedback") or "").strip()
        payload: dict = {}
        if score is not None:
            payload["submission"] = {"posted_grade": str(score)}
        if feedback:
            payload["comment"] = {"text_comment": feedback}
        if not payload:
            errors.append(f"{st['real_name']}: nothing to push (no score or feedback).")
            continue

        _, err = _canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{st['user_id']}",
            payload,
        )
        if err:
            errors.append(f"{st['real_name']}: {err}")
        else:
            st["posted"] = True
            st["status"] = "posted"
            pushed += 1

    if pushed or errors:
        session["push_log"].append({
            "ts":     datetime.now().isoformat(timespec="seconds"),
            "pushed": pushed,
            "errors": errors,
        })
        _save_session(session)

    return JSONResponse({"ok": not errors, "pushed": pushed, "errors": errors})
