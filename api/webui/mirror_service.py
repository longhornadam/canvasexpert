"""CanvasMirror scheduling service — heartbeat passes, write-through notify,
and the status payload for the mirror routes.

The heartbeat mirrors ``_routines_heartbeat``'s shape (daemon thread, launch
delay, try/except-never-die, gate on token) and is started from the server
lifespan. All real work lives in plain pass functions that tests drive
directly with injected legacy and complete-only collection clients plus
``now=`` — the thread is never started in tests.

Cadence (per Current course): a full pass when none has succeeded in
FULL_MAX_AGE_HOURS (this is both first-run backfill and the nightly
reconcile), otherwise a delta every tick plus a daily roster refresh.
"""
from __future__ import annotations

import threading
import time

from api.mirror import course_context, store, sync

from . import config, workspace
from .canvas_client import _canvas_get, _canvas_get_all, _canvas_get_all_complete
from .routes.courses import load_group_categories
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


def _refresh_groups_on_maintenance(course_id: str, *, load_groups, now: str) -> dict:
    """Best-effort private group refresh nested under roster/full maintenance."""
    try:
        categories, error, _message = load_groups(course_id)
        if error:
            document = store.mark_groups_stale(course_id, attempted_at=now)
            return {"state": document["state"] if document else "unavailable",
                    "error_code": "refresh_failed"}
        store.write_groups(course_id, categories, attempted_at=now)
        return {"state": "current", "error_code": ""}
    except Exception:
        try:
            document = store.mark_groups_stale(course_id, attempted_at=now)
        except Exception:
            document = None
        return {"state": document["state"] if document else "unavailable",
                "error_code": "refresh_failed"}


def run_heartbeat_pass(*, canvas_get=None, canvas_get_all=None,
                       canvas_get_all_complete=None, load_groups=None,
                       now=None) -> list[dict]:
    """One tick: run whatever is due for every Current course. Never raises;
    per-course failures are recorded in that course's _sync envelope and
    reported in the returned summaries."""
    if not config.token_is_set() or not config.mirror_enabled():
        return []
    if workspace.workspace_root() is None:
        return []
    canvas_get = canvas_get or _canvas_get
    canvas_get_all = canvas_get_all or _canvas_get_all
    canvas_get_all_complete = canvas_get_all_complete or _canvas_get_all_complete
    load_groups = load_groups or load_group_categories
    now_iso = now or store.now_iso()
    summaries = []
    for course in config.active_courses():
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        try:
            context = course_context.ensure_course_context(
                course_id, canvas_get=canvas_get, canvas_get_all=canvas_get_all,
                now=now_iso)
        except Exception:
            # Context is advisory scheduling state; an unexpected local
            # storage problem must degrade to ordinary mirror cadence, not
            # stop the heartbeat for this or later configured courses.
            context = store.read_course_context(course_id)
        state = store.read_sync(course_id)
        pass_names = due_passes(state, now_iso)
        concluded = (context["lifecycle"] == "concluded"
                     and context["state"] in {"current", "stale"})
        if concluded and "full" not in pass_names:
            # The daily full reconcile is the concluded course's only normal
            # heartbeat work.  Explicit manual Sync remains a live diagnostic.
            continue
        for pass_name in pass_names:
            try:
                kwargs = {"canvas_get_all": canvas_get_all, "now": now_iso}
                if pass_name in {"full", "delta"}:
                    kwargs["canvas_get_all_complete"] = canvas_get_all_complete
                    kwargs["course_name"] = course.get("name")
                if concluded and pass_name == "full":
                    kwargs["skip_new_quiz_metadata"] = True
                result = _PASS_RUNNERS[pass_name](course_id, **kwargs)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            if result.get("ok") and pass_name in {"full", "roster"}:
                result = {**result, "groups": _refresh_groups_on_maintenance(
                    course_id, load_groups=load_groups, now=now_iso)}
            summaries.append({"course_id": course_id, "pass": pass_name, **result})
    return summaries


def sync_now(course_id: str | None = None, *, canvas_get=None, canvas_get_all=None,
             canvas_get_all_complete=None, now=None) -> list[dict]:
    """Manual 'Sync now': a delta per requested course (falls back to a full
    pass automatically when the course has never been backfilled).

    This is the manual-diagnostic override (vision doc Sec 9.3): it bypasses
    any New Quiz metadata capability cooldown and always runs a full probe.
    The 15-minute heartbeat (``run_heartbeat_pass``) never does."""
    if not config.token_is_set():
        return [{"ok": False, "error": "No Canvas token saved — go to Settings."}]
    canvas_get = canvas_get or _canvas_get
    canvas_get_all = canvas_get_all or _canvas_get_all
    canvas_get_all_complete = canvas_get_all_complete or _canvas_get_all_complete
    courses = [c for c in config.active_courses()
               if not course_id or str(c.get("id")) == str(course_id)]
    if not courses:
        return [{"ok": False, "error": "Not a Current course."}]
    summaries = []
    for course in courses:
        cid = str(course.get("id") or "")
        # Manual sync is deliberately not cadence-limited.  Context is helpful
        # status evidence, but its refresh failure must never suppress the
        # existing full/delta fallback or the New Quiz cooldown override.
        try:
            course_context.refresh_course_context(
                cid, canvas_get=canvas_get, canvas_get_all=canvas_get_all, now=now)
        except Exception:
            pass
        result = sync.delta_pass(cid, canvas_get_all=canvas_get_all,
                                 canvas_get_all_complete=canvas_get_all_complete, now=now,
                                 bypass_new_quiz_cooldown=True,
                                 course_name=course.get("name"))
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


def notify_course_changed(course_id, *, delay_seconds: float = NOTIFY_DELAY_SECONDS,
                          canvas_get_all_complete=None):
    """Write-through hook for a narrow post-write submission refresh.

    The ordinary heartbeat still owns the full delta pass.  This delayed,
    fire-and-forget hook must not imply structure or New Quiz freshness.
    ``canvas_get_all_complete`` remains an accepted compatibility seam for
    existing callers, but targeted submission refresh does not use it.
    """

    def _run():
        try:
            if not config.token_is_set() or not config.mirror_enabled():
                return
            if workspace.workspace_root() is None:
                return
            sync.refresh_submissions_course_delta(
                str(course_id), canvas_get_all=_canvas_get_all)
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
            "context": store.read_course_context(course_id),
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
