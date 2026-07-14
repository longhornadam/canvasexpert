"""Feedback tools manual folder workflow, status, and OpenRouter scoring."""
import json
import os

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import feedback_pipeline as fp
import feedback_safety as safety
import openrouter_client as orc
from .. import config, workspace
from ..deps import list_rubric_files
from .feedback_common import (
    ai_ta_name,
    audit,
    budget_error_message,
    bundle_paths,
    drain_pipeline,
    load_rubric_text,
    vault,
)

router = APIRouter()


def _workflow_paths():
    """Use legacy inbox paths when present; otherwise use canonical aliases."""
    legacy = workspace.feedback_legacy_folder("1_Inbox")
    if legacy:
        return (
            legacy,
            workspace.feedback_legacy_folder("2_ForLLM"),
            workspace.feedback_legacy_folder("_archive"),
            workspace.feedback_legacy_folder("3_FromLLM"),
            workspace.feedback_legacy_folder("4_ToEnter"),
        )
    return (
        workspace.courses_root(), workspace.ai_packets_root(), workspace.archive_dir(),
        workspace.ai_packets_root(), workspace.courses_root(),
    )


@router.post("/persona")
def save_persona(name: str = Form(""), personality: str = Form("")):
    config.set_ai_ta_persona(name, personality)
    return JSONResponse({"ok": True})


@router.post("/process-inbox")
def process_inbox():
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    inbox, forllm, archive, _, _ = _workflow_paths()
    log, folder = drain_pipeline(fp.process_inbox(
        inbox, forllm, archive,
        vault(), ai_ta_name()))
    return JSONResponse({"ok": True, "folder": folder or forllm,
                         "log": log})


@router.post("/reidentify")
def reidentify():
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured — finish setup first."})
    workspace.ensure_workspace()
    _, _, _, fromllm, toenter = _workflow_paths()
    log, folder = drain_pipeline(fp.reidentify_dir(
        fromllm, toenter,
        vault()))
    return JSONResponse({"ok": True, "folder": folder or toenter,
                         "log": log})


@router.post("/openrouter-config")
def openrouter_config(api_key: str = Form(""), model: str = Form("")):
    if api_key.strip():
        config.set_openrouter_key(api_key.strip())
    if model.strip():
        config.set_openrouter_model(model.strip())
    return JSONResponse({"ok": True, "has_key": config.has_openrouter_key(),
                         "model": config.get_openrouter_model()})


@router.get("/status")
def status():
    """Return key/model state, rubrics, and per-bundle safety verdicts."""
    fb = workspace.workspace_root()
    bundles = []
    if fb:
        v = vault()
        for path in bundle_paths():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            verdict = safety.scan_payload(data, v)
            bundles.append({
                "name": os.path.basename(path),
                "green": verdict["green"],
                "hard": len(verdict["hard"]),
                "soft": len(verdict["soft"]),
                "soft_names": sorted({s["name"] for s in verdict["soft"]}),
                "tokens": orc.estimate_tokens(data),
            })
    return JSONResponse({
        "configured": bool(fb),
        "has_key": config.has_openrouter_key(),
        "model": config.get_openrouter_model(),
        "rubrics": [r["label"] for r in list_rubric_files()],
        "bundles": bundles,
    })


@router.post("/score-openrouter")
def score_openrouter(rubric_name: str = Form(""), bundle_name: str = Form("")):
    """Send pseudonymized bundles to OpenRouter, then re-identify locally."""
    if not workspace.workspace_root():
        return JSONResponse({"ok": False, "error": "No workspace configured."})
    if not config.has_openrouter_key():
        return JSONResponse({"ok": False, "error": "No OpenRouter API key saved."})

    v, persona = vault(), config.get_ai_ta_persona()
    model, api_key = config.get_openrouter_model(), config.get_openrouter_key()
    rubric_text = load_rubric_text(rubric_name)
    _, _, _, _, toenter = _workflow_paths()
    os.makedirs(toenter, exist_ok=True)

    paths = bundle_paths()
    if bundle_name:
        paths = [p for p in paths if os.path.basename(p) == bundle_name]
    if not paths:
        return JSONResponse({"ok": False, "error": "No bundles to score."})

    log = []
    for path in paths:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        verdict = safety.scan_payload(bundle, v)
        if not verdict["green"]:
            log.append(f"⛔ {name}: BLOCKED — not pseudonymized ({verdict['hard'][:1]}). Not sent.")
            audit({"action": "blocked", "bundle": name, "hard": len(verdict["hard"])})
            continue
        budget = orc.teacher_workflow_budget(
            bundle,
            rubric_text,
            model,
            student_count=len(bundle.get("students") or []),
        )
        if not budget["ok"]:
            log.append(f"⛔ {name}: BLOCKED — {budget_error_message(budget)}")
            audit({"action": "blocked_cost", "bundle": name, "model": model,
                   "tokens_est": budget.get("input_tokens")})
            continue
        try:
            results = orc.score(bundle, rubric_text, persona, api_key=api_key, model=model)
        except Exception as e:
            log.append(f"!! {name}: OpenRouter error — {e}")
            continue
        rows = fp.reidentify(results, v)
        stem = os.path.splitext(name)[0]
        dest = os.path.join(toenter, f"{stem}__to-enter.csv")
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(fp.reidentified_csv(rows))
        audit({"action": "scored", "bundle": name, "model": model,
               "responses": len(rows), "tokens_est": orc.estimate_tokens(bundle)})
        log.append(f"✓ {name}: scored {len(rows)} response(s) → ToEnter (review before posting)")

    return JSONResponse({"ok": True, "folder": toenter, "log": log})
