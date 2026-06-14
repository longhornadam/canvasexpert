"""FeedbackExpert routes — the pseudonymized scoring/feedback pipeline.

Phase A (manual): configure the AI-TA persona, process the Inbox into pseudonymized
LLM bundles, and re-identify dropped LLM results. No LLM key, no Canvas write-back yet.
Only pseudonymized payloads ever leave; the vault stays in the synced workspace.
"""
import glob
import json
import os
from datetime import datetime

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import feedback_pipeline as fp
import feedback_safety as safety
import feedback_vault
import openrouter_client as orc
from .. import config, workspace
from ..deps import list_rubric_files

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


# --------------------------------------------------------------------------
# OpenRouter (optional automated lane) — gated hard on pseudonymization
# --------------------------------------------------------------------------

def _bundle_paths():
    forllm = workspace.feedback_folder("2_ForLLM")
    if not forllm or not os.path.isdir(forllm):
        return []
    return sorted(glob.glob(os.path.join(forllm, "*__bundle.json")))


def _load_rubric_text(rubric_name):
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


def _audit(entry: dict):
    """Append a content-free provenance line to _audit/audit.log (pseudonymous only)."""
    path = os.path.join(workspace.feedback_folder("_audit") or ".", "audit.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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
    """Drives the UI: key/model presence, available rubrics, and per-bundle red/green
    safety verdicts + token estimates for the ForLLM folder."""
    fb = workspace.feedback_root()
    bundles = []
    if fb:
        vault = _vault()
        for path in _bundle_paths():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            verdict = safety.scan_payload(data, vault)
            bundles.append({
                "name": os.path.basename(path),
                "green": verdict["green"],
                "hard": len(verdict["hard"]),
                "soft": len(verdict["soft"]),
                "soft_names": sorted({s["name"] for s in verdict["soft"]}),
                "tokens": orc.estimate_tokens(data),
            })
    return JSONResponse({
        "configured":  bool(fb),
        "has_key":     config.has_openrouter_key(),
        "model":       config.get_openrouter_model(),
        "rubrics":     [r["label"] for r in list_rubric_files()],
        "bundles":     bundles,
    })


@router.post("/score-openrouter")
def score_openrouter(rubric_name: str = Form(""), bundle_name: str = Form("")):
    """Send pseudonymized bundles to OpenRouter, re-identify results to ToEnter.
    HARD-GATED: a bundle that fails the safety scan is NEVER sent (defense in depth —
    the UI also disables the button, but the server refuses regardless)."""
    if not workspace.feedback_root():
        return JSONResponse({"ok": False, "error": "No workspace configured."})
    if not config.has_openrouter_key():
        return JSONResponse({"ok": False, "error": "No OpenRouter API key saved."})

    vault, persona = _vault(), config.get_ai_ta_persona()
    model, api_key = config.get_openrouter_model(), config.get_openrouter_key()
    rubric_text = _load_rubric_text(rubric_name)
    toenter = workspace.feedback_folder("4_ToEnter")
    os.makedirs(toenter, exist_ok=True)

    paths = _bundle_paths()
    if bundle_name:
        paths = [p for p in paths if os.path.basename(p) == bundle_name]
    if not paths:
        return JSONResponse({"ok": False, "error": "No bundles to score."})

    log = []
    for path in paths:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        verdict = safety.scan_payload(bundle, vault)
        if not verdict["green"]:
            log.append(f"⛔ {name}: BLOCKED — not pseudonymized ({verdict['hard'][:1]}). Not sent.")
            _audit({"action": "blocked", "bundle": name, "hard": len(verdict["hard"])})
            continue
        try:
            results = orc.score(bundle, rubric_text, persona, api_key=api_key, model=model)
        except Exception as e:
            log.append(f"!! {name}: OpenRouter error — {e}")
            continue
        rows = fp.reidentify(results, vault)
        stem = os.path.splitext(name)[0]
        dest = os.path.join(toenter, f"{stem}__to-enter.csv")
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(fp.reidentified_csv(rows))
        _audit({"action": "scored", "bundle": name, "model": model,
                "responses": len(rows), "tokens_est": orc.estimate_tokens(bundle)})
        log.append(f"✓ {name}: scored {len(rows)} response(s) → ToEnter (review before posting)")

    return JSONResponse({"ok": True, "folder": toenter, "log": log})
