"""FeedbackExpert routes — the pseudonymized scoring/feedback pipeline.

Phase B: assignment-driven guided flow (SSE), persona library, feedback patterns.
Phase A (manual CSV-drop) preserved as secondary lane for NQ + own-tool users.
"""
import glob
import json
import os
from datetime import datetime

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse

import feedback_pipeline as fp
import feedback_safety as safety
import feedback_scrub
import feedback_vault
import openrouter_client as orc
from .. import config, workspace
from ..canvas_client import _canvas_get, _canvas_get_all
from ..deps import _sse, list_rubric_files

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


def _bundle_paths():
    forllm = workspace.feedback_folder("2_ForLLM")
    if not forllm or not os.path.isdir(forllm):
        return []
    return sorted(glob.glob(os.path.join(forllm, "*__bundle.json")))


# ======================================================================
# Phase A — preserved CSV-drop-folder workflow (New Quizzes + own tool)
# ======================================================================

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


# ======================================================================
# Phase B — Persona library endpoints
# ======================================================================

@router.get("/personas")
def list_personas():
    """Return all personas (built-in + custom)."""
    return JSONResponse({"personas": config.list_personas()})


@router.post("/personas/custom")
def add_custom_persona(persona_id: str = Form(""), name: str = Form(""),
                       personality: str = Form("")):
    config.save_custom_persona(persona_id.strip(), name.strip(), personality.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


@router.delete("/personas/custom")
def delete_custom_persona(persona_id: str = Form("")):
    config.remove_custom_persona(persona_id.strip())
    return JSONResponse({"ok": True, "personas": config.list_personas()})


# ======================================================================
# Phase B — Feedback Pattern endpoints
# ======================================================================

@router.get("/patterns")
def list_patterns():
    return JSONResponse({"patterns": config.list_feedback_patterns()})


@router.post("/patterns")
def save_patterns(patterns: str = Form()):
    """Replace all feedback patterns with the provided JSON list."""
    try:
        parsed = json.loads(patterns)
        if not isinstance(parsed, list):
            return JSONResponse({"ok": False, "error": "Must be a JSON array."})
        config.set_feedback_patterns(parsed)
        return JSONResponse({"ok": True, "patterns": config.list_feedback_patterns()})
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ======================================================================
# Phase B — Assignment-driven guided flow
#
# Two steps, so the paid OpenRouter call is gated on an explicit cost
# confirmation (an SSE stream can't pause mid-flight for a client OK):
#   1. /run/prepare (JSON): fetch → pseudonymize → HARD safety gate →
#      write pseudonymized bundle → return token estimate. Nothing paid yet.
#   2. /run/stream  (SSE): only after the teacher confirms the cost — load
#      the prepared bundle, re-scan (defense in depth), score, re-identify.
# ======================================================================

def _fetch_submissions(course_id: str, assignment_id: str):
    """Fetch one assignment's submissions (with user, for vault names). Narrowed
    server-side by assignment_ids[] so we don't pull the whole course. Returns
    (submissions, assignment_name, error)."""
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": ["all"], "assignment_ids[]": [assignment_id],
         "include[]": ["assignment", "user"], "per_page": 100},
    )
    if err:
        return None, "", err
    adata, _ = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    name = (adata or {}).get("name") or assignment_id
    return subs, name, None


@router.get("/run/prepare")
def feedback_run_prepare(
    course_id: str = Query(""),
    assignment_id: str = Query(""),
    rubric_name: str = Query(""),
):
    """Fetch + pseudonymize + HARD safety gate + write bundle. No paid call.
    Returns the token estimate so the client can confirm cost before /run/stream."""
    if not course_id or not assignment_id:
        return JSONResponse({"ok": False, "error": "course_id and assignment_id are required."})
    if not config.has_openrouter_key():
        return JSONResponse({"ok": False, "error": "No OpenRouter API key saved — configure in Settings."})

    subs, assignment_name, err = _fetch_submissions(course_id, assignment_id)
    if err:
        return JSONResponse({"ok": False, "error": err})
    if not subs:
        return JSONResponse({"ok": False, "error": "No submissions returned for this assignment."})

    vault = _vault()
    bundle = fp.pseudonymize_submissions(subs, vault, assignment_name)
    if not bundle["students"]:
        return JSONResponse({"ok": False, "error": "No written submissions to score for this assignment."})
    vault.save()

    verdict = safety.scan_payload(bundle, vault)
    if not verdict["green"]:
        _audit({"action": "blocked", "assignment": assignment_name,
                "course": course_id, "hard": len(verdict["hard"])})
        return JSONResponse({"ok": False, "green": False,
                             "error": "PII safety gate blocked this batch.",
                             "hard": verdict["hard"][:5]})

    # Write scrubbed SAFE bundle + PRIVATE copy + who-is-who
    protected = config.active_protected_names()
    result = fp.write_safe_and_private(
        bundle, vault,
        workspace.feedback_folder("SAFE"),
        workspace.feedback_folder("PRIVATE"),
        config.get_persona().get("name") or _ai_ta_name(),
        protected=protected,
        submissions=subs,
    )
    if not result["safe_bundle"]:
        return JSONResponse({"ok": False, "error": f"SAFE write failed: {result['log']}"})

    rubric_text = _load_rubric_text(rubric_name)
    tokens = orc.estimate_tokens(bundle, rubric_text)
    response_data = {"ok": True, "green": True, "soft": verdict["soft"],
                     "tokens": tokens, "students": len(bundle["students"]),
                     "bundle_name": os.path.basename(result["safe_bundle"]),
                     "assignment_name": assignment_name,
                     "attachment_only": result.get("attachment_only", [])}
    return JSONResponse(response_data)


@router.get("/run/stream")
def feedback_run_stream(
    bundle_name: str = Query(""),
    persona_id: str = Query("sage"),
    rubric_name: str = Query(""),
    pattern_id: str = Query("basic"),
):
    """SSE — score a bundle already prepared + cost-confirmed via /run/prepare.
    Re-scans safety (defense in depth), scores via OpenRouter, re-identifies →
    ToEnter CSV. Yields progress lines; final lines: 'FOLDER: <path>', '[exit 0]'."""
    if not bundle_name:
        return StreamingResponse(
            _sse(["!! No prepared bundle — run prepare first.", "[exit 1]"]),
            media_type="text/event-stream")
    if not config.has_openrouter_key():
        return StreamingResponse(
            _sse(["!! No OpenRouter API key saved — configure in Settings.", "[exit 1]"]),
            media_type="text/event-stream")

    def stream():
        try:
            forllm = workspace.feedback_folder("SAFE")
            bpath = os.path.join(forllm, os.path.basename(bundle_name))
            if not os.path.isfile(bpath):
                yield "!! Prepared bundle not found — run prepare again."
                yield "[exit 1]"
                return
            with open(bpath, encoding="utf-8") as f:
                bundle = json.load(f)

            vault = _vault()
            persona = config.get_persona(persona_id)
            patterns = config.list_feedback_patterns()
            fb_pattern = next((p for p in patterns if p["id"] == pattern_id),
                              patterns[0] if patterns else None)
            rubric_text = _load_rubric_text(rubric_name)
            assignment_name = bundle.get("quiz_title", "assignment")

            # Defense in depth: re-scan the bundle right before it leaves.
            yield "Re-checking PII safety gate…"
            verdict = safety.scan_payload(bundle, vault)
            if not verdict["green"]:
                yield f"⛔ SAFETY BLOCK: {verdict['hard'][:2]}"
                _audit({"action": "blocked", "assignment": assignment_name,
                        "hard": len(verdict["hard"])})
                yield "[exit 1]"
                return

            yield f"Scoring {len(bundle['students'])} student(s) via OpenRouter…"
            results = orc.score(
                bundle, rubric_text, persona,
                api_key=config.get_openrouter_key(),
                model=config.get_openrouter_model(),
                feedback_pattern=fb_pattern,
            )

            yield f"Re-identifying {len(results)} result(s)…"
            rows = fp.reidentify(results, vault)
            toenter = workspace.feedback_folder("PRIVATE")
            os.makedirs(toenter, exist_ok=True)
            stem = fp._safe(assignment_name)
            dest = os.path.join(toenter, f"{stem}__to-enter.csv")
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(fp.reidentified_csv(rows))
            unresolved = sum(1 for r in rows if not r["resolved"])
            note = f" ({unresolved} unresolved)" if unresolved else ""
            yield f"✓ {assignment_name}: {len(rows)} scored{note} → ToEnter (review before posting)"
            _audit({"action": "guided_score", "assignment": assignment_name,
                    "persona": persona_id, "pattern": pattern_id,
                    "responses": len(rows)})
            yield f"FOLDER: {toenter}"
            yield "[exit 0]"

        except Exception as e:
            yield f"!! Fatal: {e}"
            yield "[exit 1]"

    return StreamingResponse(_sse(stream()), media_type="text/event-stream")


# ======================================================================
# Name Manager API — vault roster, nicknames, pseudonyms, protected names,
# collisions, scrub test, who-is-who export
# ======================================================================

names_router = APIRouter(prefix="/api/names", tags=["names"])


def _upsert_roster(vault, users):
    """Upsert Canvas users into the vault with collision-safe fake names, and capture
    each student's preferred/short name as a nickname so it gets scrubbed too.

    The short_name is the single most-overlooked leak vector: a student whose legal
    `name` is "Joseph" may go by "Joey" (short_name) and sign their work that way. If
    we don't record it, the scrub never sees it. We add it as a nickname unless it's
    already covered by the legal-name tokens. roster_tokens spans name + sortable +
    short so a fake name never collides with any form a real student uses."""
    roster_tokens: set = set()
    for u in (users or []):
        for src in (u.get("name"), u.get("sortable_name"), u.get("short_name")):
            for token in (src or "").split():
                roster_tokens.add(token.lower())

    for u in (users or []):
        cid = str(u.get("id", ""))
        if not cid:
            continue
        name = u.get("name") or u.get("sortable_name") or ""
        sis = str(u.get("sis_user_id") or "")
        vault.get_or_assign(cid, name, sis, roster_names=roster_tokens)
        short = (u.get("short_name") or "").strip()
        name_tokens = {t.lower() for t in name.split()}
        if short and short.lower() != name.lower() and short.lower() not in name_tokens:
            vault.add_nicknames(cid, [short])
    vault.save()


@names_router.get("/roster")
def names_roster(course_id: str = Query("")):
    """Sync roster from Canvas, upsert into vault, return entries joined with
    real name/section. Reuses the existing users fetch pattern."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    vault = _vault()
    # Fetch enrolled students
    users, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": ["student"], "include[]": ["enrollments"], "per_page": 100},
    )
    if err:
        # Maybe the user already has cached/offline entries
        return JSONResponse({"ok": True, "entries": vault.entries(),
                             "note": f"Canvas fetch failed: {err}"})

    _upsert_roster(vault, users)
    return JSONResponse({"ok": True, "entries": vault.entries()})


@names_router.post("/nickname")
def set_nickname(canvas_id: str = Form(""), nicknames: str = Form("")):
    """Set nicknames for a student (comma-separated)."""
    vault = _vault()
    vault.set_nicknames(canvas_id, [n.strip() for n in nicknames.split(",") if n.strip()])
    vault.save()
    return JSONResponse({"ok": True})


@names_router.post("/pseudonym")
def set_pseudonym(canvas_id: str = Form(""), first: str = Form(""), last: str = Form("")):
    """Manual pseudonym override."""
    vault = _vault()
    vault.set_pseudonym(canvas_id, first, last)
    vault.save()
    return JSONResponse({"ok": True})


@names_router.post("/pseudonym/regenerate")
def regenerate_pseudonym(canvas_id: str = Form("")):
    """Regenerate a random non-colliding fake name."""
    vault = _vault()
    vault.regenerate_pseudonym(canvas_id)
    vault.save()
    return JSONResponse({"ok": True, "pseudonym": vault.get_or_assign(canvas_id)})


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
    if not vault.entries() and course_id:
        # Auto-sync if vault is empty and we have a course
        users, err = _canvas_get_all(
            f"/api/v1/courses/{course_id}/users",
            {"enrollment_type[]": ["student"], "include[]": ["enrollments"], "per_page": 100},
        )
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
    """Write a who-is-who.csv to PRIVATE/ and return the path."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    vault = _vault()
    private_dir = workspace.feedback_folder("PRIVATE")
    if not private_dir:
        return JSONResponse({"ok": False, "error": "No workspace configured."})
    os.makedirs(private_dir, exist_ok=True)
    stem = f"course_{course_id}"
    who_path = os.path.join(private_dir, f"{stem}__who-is-who.csv")
    import csv
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
    from datetime import datetime
    backup_dir = os.path.join(os.path.dirname(vault_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = os.path.join(backup_dir, f"vault-{date_str}.json")
    import shutil
    shutil.copy2(vault_path, backup_path)
    return JSONResponse({"ok": True, "path": backup_path, "entries": len(vault)})
