"""FeedbackExpert routes — the pseudonymized scoring/feedback pipeline.

Phase A (manual): configure the AI-TA persona, process the Inbox into pseudonymized
LLM bundles, and re-identify dropped LLM results. No LLM key, no Canvas write-back yet.
Only pseudonymized payloads ever leave; the vault stays in the synced workspace.
"""
import os

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import feedback_pipeline as fp
import feedback_vault
from .. import config, workspace

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _vault():
    return feedback_vault.Vault(os.path.join(workspace.feedback_folder("_vault"), "vault.json"))


def _ai_ta_name():
    return config.get_ai_ta_persona().get("name") or "your AI teaching assistant"


def _run(gen):
    """Drain a pipeline generator into (log, folder)."""
    log, folder = [], None
    for line in gen:
        if line.startswith("FOLDER: "):
            folder = line[len("FOLDER: "):]
        else:
            log.append(line)
    return log, folder


@router.post("/persona")
def save_persona(name: str = Form(""), personality: str = Form("")):
    config.set_ai_ta_persona(name, personality)
    return JSONResponse({"ok": True})


@router.post("/process-inbox")
def process_inbox():
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    log, folder = _run(fp.process_inbox(
        workspace.feedback_folder("1_Inbox"),
        workspace.feedback_folder("2_ForLLM"),
        workspace.feedback_folder("_archive"),
        _vault(), _ai_ta_name()))
    return JSONResponse({"ok": True, "folder": folder or workspace.feedback_folder("2_ForLLM"),
                         "log": log})


@router.post("/reidentify")
def reidentify():
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    log, folder = _run(fp.reidentify_dir(
        workspace.feedback_folder("3_FromLLM"),
        workspace.feedback_folder("4_ToEnter"),
        _vault()))
    return JSONResponse({"ok": True, "folder": folder or workspace.feedback_folder("4_ToEnter"),
                         "log": log})
