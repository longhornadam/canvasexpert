"""Name Manager API — the vault-editor surface behind the Name Manager screen.

Roster sync, nicknames, pseudonyms, protected (literary) names, collision
detection, live scrub-test, and who-is-who / vault-backup export. All local;
these endpoints touch the vault (PII), which lives synced-private and never
leaves the machine. Split out of routes/feedback.py — distinct surface, its own
`names_router`.
"""
import csv
import json
import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from api import feedback_scrub, feedback_vault
from api import roster_service
from .. import config, workspace
from ..canvas_client import _canvas_get_all

names_router = APIRouter(prefix="/api/names", tags=["names"])


def _vault():
    root = workspace.identity_vault_dir()
    return feedback_vault.Vault(os.path.join(root or ".", "vault.json"))


_fetch_students = roster_service.fetch_students
_upsert_roster = roster_service.upsert_roster



@names_router.get("/roster")
def names_roster(course_id: str = Query("")):
    """Sync roster from Canvas, upsert into vault, return entries joined with
    real name/section. Reuses the existing users fetch pattern."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    vault = _vault()
    users, err = _fetch_students(course_id)
    if err:
        # Maybe the user already has cached/offline entries
        with vault.transaction():
            return JSONResponse({"ok": True, "entries": vault.entries(),
                                 "vault_conflict": vault.conflicts(),
                                 "note": f"Canvas fetch failed: {err}"})

    with vault.transaction():
        _upsert_roster(vault, users)
        return JSONResponse({"ok": True, "entries": vault.entries(),
                             "vault_conflict": vault.conflicts()})


@names_router.post("/nickname")
def set_nickname(canvas_id: str = Form(""), nicknames: str = Form("")):
    """Set nicknames for a student (comma-separated)."""
    vault = _vault()
    with vault.transaction():
        vault.set_nicknames(canvas_id, [n.strip() for n in nicknames.split(",") if n.strip()])
    return JSONResponse({"ok": True})


@names_router.post("/pseudonym")
def set_pseudonym(canvas_id: str = Form(""), first: str = Form(""), last: str = Form("")):
    """Manual pseudonym override."""
    vault = _vault()
    with vault.transaction():
        vault.set_pseudonym(canvas_id, first, last)
    return JSONResponse({"ok": True})


@names_router.post("/pseudonym/regenerate")
def regenerate_pseudonym(canvas_id: str = Form("")):
    """Regenerate a random non-colliding fake name."""
    vault = _vault()
    with vault.transaction():
        vault.regenerate_pseudonym(canvas_id)
        pseudonym = vault.get_or_assign(canvas_id)
    return JSONResponse({"ok": True, "pseudonym": pseudonym})


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


@names_router.get("/collisions")
def get_collisions(course_id: str = Query("")):
    """Compute name collisions for the current vault. course_id is optional
    (used to sync roster first if empty vault)."""
    vault = _vault()
    with vault.transaction():
        if not vault.entries() and course_id:
            # Auto-sync if vault is empty and we have a course
            users, err = _fetch_students(course_id)
            if not err:
                _upsert_roster(vault, users)
        protected = config.active_protected_names()
        collisions = feedback_scrub.find_collisions(vault.entries(), protected)
    return JSONResponse({"ok": True, "collisions": collisions})


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


@names_router.post("/backup-vault")
def backup_vault():
    """Back up vault.json to _system/vault/backups/."""
    vault = _vault()
    vault_path = vault.path
    if not os.path.isfile(vault_path):
        return JSONResponse({"ok": False, "error": "No vault file found."})
    backup_dir = os.path.join(os.path.dirname(vault_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = os.path.join(backup_dir, f"vault-{date_str}.json")
    shutil.copy2(vault_path, backup_path)
    return JSONResponse({"ok": True, "path": backup_path, "entries": len(vault)})
