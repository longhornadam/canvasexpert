"""Name Manager API — the vault-editor surface behind the Name Manager screen.

Protected (literary) names, live scrub-test, and who-is-who / vault-backup
export. All local; these endpoints touch the vault (PII), which lives
synced-private and never leaves the machine. Split out of routes/feedback.py
— distinct surface, its own `names_router`.

Roster sync, nicknames, pseudonym set/regenerate, and collision detection are
owned by the Roster Console (`GET /api/roster`, `POST /api/roster/student`,
see `roster.py` and `roster_updates.py`) and its MCP adapter; the equivalent
Name Manager routes were dead (zero production callers) and were deleted
rather than ported to the schema-v3 one-word pseudonym contract.
"""
import csv
import json
import os
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from api import feedback_scrub, feedback_vault
from api import roster_service
from api.platform_services import config, workspace

names_router = APIRouter(prefix="/api/names", tags=["names"])


def _vault():
    root = workspace.identity_vault_dir()
    return feedback_vault.Vault(os.path.join(root or ".", "vault.json"))


# Re-exported for `api/tests/test_feedback_pipeline.py`, which exercises
# roster upsert (preferred-name-as-nickname capture) through this module path.
_upsert_roster = roster_service.upsert_roster


@names_router.get("/protected")
def get_protected():
    """Return protected packs + custom names."""
    return JSONResponse({
        "packs": config.list_protected_packs(),
        "custom": config.get_custom_protected_names(),
        "active": sorted(config.active_protected_names()),
    })


@names_router.post("/protected")
def set_protected(data: str = Form("")):
    """Set pack enabled states and custom names. Expects JSON:
    {"packs": {"outsiders": true, ...}, "custom": ["Name1", "Name2"]}"""
    try:
        parsed = json.loads(data) if data.strip() else {}
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "Invalid JSON."})
    packs = parsed.get("packs", {})
    for pack_id, enabled in packs.items():
        config.set_pack_enabled(pack_id, bool(enabled))
    custom = parsed.get("custom", [])
    config.set_custom_protected_names(custom)
    return JSONResponse({"ok": True})


@names_router.post("/scrub-test")
def scrub_test(text: str = Form(""), course_id: str = Form("")):
    """Live scrub preview: scrub the input using current vault + protected names."""
    vault = _vault()
    protected = config.active_protected_names()
    rmap = feedback_scrub.build_replacement_map(vault.entries(), protected)
    result = feedback_scrub.scrub_text(text, rmap)
    return JSONResponse({"ok": True, "original": text, "scrubbed": result})


@names_router.post("/who-is-who")
def export_who_is_who(course_id: str = Form("")):
    """Write a who-is-who.csv to Student Work/Grading Keys/ and return the path."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    vault = _vault()
    private_dir = workspace.grading_keys_root()
    if not private_dir:
        return JSONResponse({"ok": False, "error": "No workspace configured."})
    os.makedirs(private_dir, exist_ok=True)
    stem = f"course_{course_id}"
    who_path = os.path.join(private_dir, f"{stem}__who-is-who.csv")
    with open(who_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Real Name", "Canvas ID", "SIS ID", "Pseudonym", "Nicknames"])
        for e in vault.entries():
            w.writerow([
                e.get("real_name", ""),
                e.get("canvas_id", ""),
                e.get("sis_id", ""),
                e.get("pseudonym", ""),
                ", ".join(e.get("nicknames", [])),
            ])
    return JSONResponse({"ok": True, "path": who_path})


@names_router.get("/vault-conflict")
def vault_conflict():
    """List any OneDrive-forked vault*.json copies beside the canonical vault,
    with enough to help the teacher judge which is current. Never reads their
    contents (student identity), only filesystem metadata."""
    vault = _vault()
    folder = os.path.dirname(vault.path) or "."
    files = []
    for name in vault.conflicts():
        path = os.path.join(folder, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        files.append({
            "name": name,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            "size_bytes": stat.st_size,
        })
    return JSONResponse({"ok": True, "folder": folder, "files": files})


@names_router.post("/backup-vault")
def backup_vault():
    """Back up vault.json to _system/vault/backups/."""
    vault = _vault()
    vault_path = vault.path
    if not os.path.isfile(vault_path):
        return JSONResponse({"ok": False, "error": "No vault file found."})
    backup_dir = os.path.join(os.path.dirname(vault_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"vault-{workspace.run_stamp()}.json")
    shutil.copy2(vault_path, backup_path)
    return JSONResponse({"ok": True, "path": backup_path, "entries": len(vault)})
