"""Privacy pipeline helpers for PowerGrader.

Functions for building privacy step records, writing privacy audit files,
and writing OpenRouter debug files.
"""

import json
import os
import traceback
from datetime import datetime

import feedback_pipeline as fp
import openrouter_client as orc
from webui import workspace


def privacy_step(step_id: str, label: str, status: str,
                 detail: str = "", **extra) -> dict:
    item = {"id": step_id, "label": label, "status": status, "detail": detail}
    item.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return item


def feedback_artifact_dirs() -> tuple[str | None, str | None]:
    workspace.ensure_workspace()
    return workspace.feedback_folder("SAFE"), workspace.feedback_folder("PRIVATE")


def write_privacy_audit_file(
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


def write_openrouter_debug_file(
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