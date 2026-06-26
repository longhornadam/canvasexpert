"""SpeedGrader routes — keyboard-driven grading with optional AI assistance.

Modes:
  fast      Download → queue → keyboard-grade → bulk push
  assisted  Same + OpenRouter pre-fills score/feedback per student

Page routes:
  GET /speedgrader                     Setup screen
  GET /speedgrader/session/<id>        Queue screen

API routes:
  GET  /api/speedgrader/sessions           List workspace sessions
  POST /api/speedgrader/start              Create session (fetch + optional AI)
  GET  /api/speedgrader/session/<id>       Get session JSON
  POST /api/speedgrader/session/<id>/grade Save one student's grade
  POST /api/speedgrader/session/<id>/push  Push approved to Canvas
"""
import json
import os
import uuid
from datetime import datetime

import requests
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

import feedback_pipeline as fp
import feedback_safety as safety
import feedback_vault
import openrouter_client as orc

from .. import config, workspace
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_headers, _canvas_send
from ..deps import list_rubric_files, templates

router = APIRouter(tags=["speedgrader"])

_CODE_EXTS = {".py", ".html", ".htm", ".css", ".js", ".txt", ".md", ".json", ".csv"}
_MAX_CODE_BYTES = 256 * 1024


# --------------------------------------------------------------------------
# Session storage helpers
# --------------------------------------------------------------------------

def _sg_dir() -> str | None:
    root = workspace.workspace_root()
    if not root:
        return None
    d = os.path.join(root, "SpeedGrader")
    os.makedirs(d, exist_ok=True)
    return d


def _session_path(session_id: str) -> str | None:
    d = _sg_dir()
    if not d:
        return None
    # Guard against path traversal
    safe_id = "".join(c for c in session_id if c.isalnum() or c == "-")
    return os.path.join(d, f"{safe_id}_session.json")


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
        return feedback_vault.Vault(os.path.join(vpath, "vault.json"))
    root = workspace.workspace_root()
    fallback = os.path.join(root or ".", "SpeedGrader", "_vault")
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


# --------------------------------------------------------------------------
# Page routes
# --------------------------------------------------------------------------

@router.get("/speedgrader", response_class=HTMLResponse)
def speedgrader_setup(request: Request):
    return templates.TemplateResponse(request, "speedgrader_setup.html", {
        "nav_section":    "feedback",
        "saved_courses":  config.active_courses(),
        "rubrics":        [r["label"] for r in list_rubric_files()],
        "personas":       config.list_personas(),
        "has_openrouter": config.has_openrouter_key(),
        "has_workspace":  bool(workspace.workspace_root()),
    })


@router.get("/speedgrader/session/{session_id}", response_class=HTMLResponse)
def speedgrader_queue(request: Request, session_id: str):
    session = _load_session(session_id)
    if not session:
        return HTMLResponse("<h2>Session not found.</h2>", status_code=404)
    return templates.TemplateResponse(request, "speedgrader_queue.html", {
        "nav_section":      "feedback",
        "session_id":       session_id,
        "assignment_name":  session.get("assignment_name", ""),
        "course_id":        session.get("course_id", ""),
        "mode":             session.get("mode", "fast"),
        "student_count":    len(session.get("students", [])),
        "canvas_base":      config.get_canvas_base(),
    })


# --------------------------------------------------------------------------
# API routes
# --------------------------------------------------------------------------

@router.get("/api/speedgrader/sessions")
def list_sessions():
    d = _sg_dir()
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
            "total":           len(students),
            "approved":        sum(1 for st in students if st.get("status") == "approved"),
            "posted":          sum(1 for st in students if st.get("posted")),
        })
    sessions.sort(key=lambda x: x.get("created") or "", reverse=True)
    return JSONResponse({"sessions": sessions})


@router.post("/api/speedgrader/start")
def sg_start(
    course_id: str = Form(""),
    assignment_id: str = Form(""),
    mode: str = Form("fast"),
    rubric_name: str = Form(""),
    persona_id: str = Form("sage"),
):
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})

    # Fetch submissions
    subs, adata, err = _fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions found for this assignment."})

    assignment_name = adata.get("name") or assignment_id
    points_possible = float(adata.get("points_possible") or 100)

    # Filter to students who have actually submitted
    submitted = [
        s for s in subs
        if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
    ]
    if not submitted:
        return JSONResponse({"ok": False, "error": "No submitted work found for this assignment."})

    _enrich_with_code_files(submitted)

    # Pull roster context for all students
    roster_settings = config.get_roster_student_settings(course_id)
    tier_map = config.roster_tier_by_id(course_id)
    monitored = config.get_monitored_students()
    extra_time_list = config.get_extra_time(course_id)
    extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}

    # AI results (populated below for assisted mode)
    ai_by_uid: dict = {}

    if mode == "assisted" and config.has_openrouter_key():
        vault = _vault()
        bundle = fp.pseudonymize_submissions(submitted, vault, assignment_name)
        if bundle["students"]:
            vault.save()
            verdict = safety.scan_payload(bundle, vault)
            if not verdict["green"]:
                return JSONResponse({
                    "ok": False, "green": False,
                    "error": "PII safety gate blocked this batch — real names detected in submission text.",
                    "hard": verdict["hard"][:5],
                })
            rubric_text = _load_rubric_text(rubric_name)
            persona = config.get_persona(persona_id)
            patterns = config.list_feedback_patterns()
            fb_pattern = patterns[0] if patterns else None
            try:
                results = orc.score(
                    bundle, rubric_text, persona,
                    api_key=config.get_openrouter_key(),
                    model=config.get_openrouter_model(),
                    feedback_pattern=fb_pattern,
                )
                rows = fp.reidentify(results, vault)
                ai_by_uid = {row["canvas_id"]: row for row in rows if row.get("resolved")}
            except Exception as e:
                return JSONResponse({"ok": False, "error": f"OpenRouter error: {e}"})

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
    session = {
        "session_id":      session_id,
        "course_id":       course_id,
        "assignment_id":   assignment_id,
        "assignment_name": assignment_name,
        "points_possible": points_possible,
        "created":         datetime.now().isoformat(timespec="seconds"),
        "mode":            mode,
        "rubric_name":     rubric_name,
        "persona_id":      persona_id,
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
        "ai_scored":      len(ai_by_uid),
    })


@router.get("/api/speedgrader/session/{session_id}")
def sg_get_session(session_id: str):
    session = _load_session(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "Session not found."}, status_code=404)
    return JSONResponse({"ok": True, "session": session})


@router.post("/api/speedgrader/session/{session_id}/grade")
def sg_grade(
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


@router.post("/api/speedgrader/session/{session_id}/push")
def sg_push(
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
