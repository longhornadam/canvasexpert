"""CanvasMirror scheduling service — heartbeat passes, write-through notify,
and the status payload for the mirror routes.

The heartbeat mirrors ``_routines_heartbeat``'s shape (daemon thread, launch
delay, try/except-never-die, gate on token) and is started from the server
lifespan. All real work lives in plain pass functions that tests drive
directly with an injected ``canvas_get_all`` and ``now=`` — the thread is
never started in tests.

Cadence (per Current course): a full pass when none has succeeded in
FULL_MAX_AGE_HOURS (this is both first-run backfill and the nightly
reconcile), otherwise a delta every tick plus a daily roster refresh.
"""
from __future__ import annotations

import threading
import time

from api.mirror import store, sync

from . import config, workspace
from .canvas_client import _canvas_get_all
from .routes.names import _vault as _identity_vault


LAUNCH_DELAY_SECONDS = 120        # after the routines heartbeat's 90 s
TICK_SECONDS = 900                # delta cadence while the app runs
FULL_MAX_AGE_HOURS = 24.0         # backfill + nightly reconcile
ROSTER_MAX_AGE_HOURS = 24.0
NOTIFY_DELAY_SECONDS = 15.0       # write-through settle delay


def due_passes(state: dict, now_iso: str) -> list[str]:
    """Which passes one course needs this tick."""
    full_age = store.age_hours(state["passes"]["full"]["last_success_at"], now_iso)
    if full_age is None or full_age >= FULL_MAX_AGE_HOURS:
        return ["full"]  # covers roster and resets watermarks
    passes = ["delta"]
    roster_age = store.age_hours(state["passes"]["roster"]["last_success_at"], now_iso)
    if roster_age is None or roster_age >= ROSTER_MAX_AGE_HOURS:
        passes.append("roster")
    return passes


_PASS_RUNNERS = {"full": sync.full_pass, "delta": sync.delta_pass,
                 "roster": sync.roster_pass}


def run_heartbeat_pass(*, canvas_get_all=None, now=None) -> list[dict]:
    """One tick: run whatever is due for every Current course. Never raises;
    per-course failures are recorded in that course's _sync envelope and
    reported in the returned summaries."""
    if not config.token_is_set() or not config.mirror_enabled():
        return []
    if workspace.workspace_root() is None:
        return []
    canvas_get_all = canvas_get_all or _canvas_get_all
    now_iso = now or store.now_iso()
    summaries = []
    for course in config.active_courses():
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        state = store.read_sync(course_id)
        for pass_name in due_passes(state, now_iso):
            try:
                result = _PASS_RUNNERS[pass_name](
                    course_id, canvas_get_all=canvas_get_all, now=now_iso)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            summaries.append({"course_id": course_id, "pass": pass_name, **result})
    return summaries


def sync_now(course_id: str | None = None, *, canvas_get_all=None, now=None) -> list[dict]:
    """Manual 'Sync now': a delta per requested course (falls back to a full
    pass automatically when the course has never been backfilled).

    This is the manual-diagnostic override (vision doc Sec 9.3): it bypasses
    any New Quiz metadata capability cooldown and always runs a full probe.
    The 15-minute heartbeat (``run_heartbeat_pass``) never does."""
    if not config.token_is_set():
        return [{"ok": False, "error": "No Canvas token saved — go to Settings."}]
    canvas_get_all = canvas_get_all or _canvas_get_all
    courses = [c for c in config.active_courses()
               if not course_id or str(c.get("id")) == str(course_id)]
    if not courses:
        return [{"ok": False, "error": "Not a Current course."}]
    summaries = []
    for course in courses:
        cid = str(course.get("id") or "")
        result = sync.delta_pass(cid, canvas_get_all=canvas_get_all, now=now,
                                 bypass_new_quiz_cooldown=True)
        summaries.append({"course_id": cid, "pass": "delta", **result})
    return summaries


def refresh_work_findings() -> None:
    """Recompute detected work findings from the (freshly synced) mirror and merge
    them into the local work registry, so Home's Attention/Continue cards stay
    current on the heartbeat instead of only on a manual Sync now.

    Best-effort background step: gated on the same conditions as a sync pass,
    reads mirror-first (cheap right after a pass), and never raises into the loop.
    """
    if not config.token_is_set() or not config.mirror_enabled():
        return
    if workspace.workspace_root() is None:
        return
    try:
        from api.work_registry import discovery
        result = discovery.scan_active_courses()
        if result.get("ok"):
            discovery.merge_into_registry(result)
    except Exception:
        pass


def notify_course_changed(course_id, *, delay_seconds: float = NOTIFY_DELAY_SECONDS):
    """Write-through hook: after CanvasExpert itself writes to Canvas, run a
    short-delay delta so the mirror learns its own actions without waiting
    for the next tick. Fire-and-forget; never raises into the caller."""
    def _run():
        try:
            if not config.token_is_set() or not config.mirror_enabled():
                return
            if workspace.workspace_root() is None:
                return
            sync.delta_pass(str(course_id), canvas_get_all=_canvas_get_all)
        except Exception:
            pass

    timer = threading.Timer(delay_seconds, _run)
    timer.daemon = True
    timer.start()
    return timer


def status() -> dict:
    courses = []
    for course in config.active_courses():
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        state = store.read_sync(course_id)
        courses.append({
            "course_id": course_id,
            "course_name": config.course_display_name(course_id),
            "passes": state["passes"],
            "watermarks": state["watermarks"],
        })
    return {
        "ok": True,
        "enabled": config.mirror_enabled(),
        "workspace_configured": workspace.workspace_root() is not None,
        "serve_max_age_hours": config.mirror_serve_max_age_hours(),
        "courses": courses,
        "vault_conflict": _vault_conflict_files(),
    }


def _vault_conflict_files() -> list[str]:
    """Basenames of any OneDrive vault conflict-copy artifacts, or [] when
    there's no workspace configured / no conflict / the vault can't be read.
    Never raises — a missing workspace must not break /api/mirror/status."""
    try:
        vault = _identity_vault()
        return vault.conflicts()
    except Exception:
        return []


def _mirror_heartbeat():
    time.sleep(LAUNCH_DELAY_SECONDS)
    while True:
        try:
            run_heartbeat_pass()
            refresh_work_findings()
        except Exception:
            pass
        time.sleep(TICK_SECONDS)
