"""Shared helpers for feedback tools route modules."""
import json
import os
from datetime import datetime

from api import feedback_vault, operational_log

from api.platform_services import config, workspace
from ..deps import list_rubric_files


def budget_error_message(budget: dict) -> str:
    model = budget.get("model") or config.get_openrouter_model()
    estimate = budget.get("estimated_cost")
    estimate_text = f" Estimated batch cost: ${estimate:.2f}." if estimate is not None else ""
    reasons = "; ".join(budget.get("reasons") or ["cost could not be verified"])
    return (
        f"OpenRouter model '{model}' cannot be used for teacher auto-scoring. "
        f"{reasons}.{estimate_text} Use Settings > AI assistance > DeepSeek V4 Pro."
    )


def vault():
    root = workspace.identity_vault_dir()
    return feedback_vault.Vault(os.path.join(root or ".", "vault.json"))


def ai_ta_name():
    return config.get_ai_ta_persona().get("name") or "your teaching assistant"


def drain_pipeline(gen):
    """Drain a pipeline generator into (log, folder)."""
    log, folder = [], None
    for line in gen:
        if line.startswith("FOLDER: "):
            folder = line[len("FOLDER: "):]
        else:
            log.append(line)
    return log, folder


def load_rubric_text(rubric_name):
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


def audit(entry: dict):
    """Append a content-free provenance line to _audit/audit.log."""
    path = os.path.join(workspace.audits_dir() or ".", "audit.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        operational_log.emit("powergrader.audit_write", "failed", error_class=type(exc))
