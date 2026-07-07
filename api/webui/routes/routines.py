"""Routines router for Canvas Expert.

Local automation: run on demand, on launch, and every 30 min.
No external scheduler (locked-down district machines), no cloud, ever.
"""
import json
import threading
import time as _time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from .. import config, activity
from ..canvas_client import _canvas_get, _canvas_get_all, _canvas_send
from ..schooldays import _school_days_late, _parse_iso_local
from . import powergrader as pg_routes
from powergrader import (
    ai_workflow,
    autopush_executor,
    autoscore_queue,
    canvas_fetch,
    late_catchup,
    privacy,
    session_builder,
    session_store,
)
from .routines_builtin import (
    _run_routine_sweep, _run_routine_download, _run_routine_curve,
    _run_routine_grading_debt, _run_routine_student_reports,
)

try:
    from nq_report import html_to_text
except ModuleNotFoundError:
    from api.nq_report import html_to_text

router = APIRouter(prefix="/api", tags=["routines"])

# --------------------------------------------------------------------------
# Routine definitions
# --------------------------------------------------------------------------

_ROUTINE_DEFS = {
    "sweep": {
        "label": "Auto-sweep late work",
        "writes": True,
        "default": {"enabled": False, "every_hours": 24,
                    "params": {"window_days": 30}},
    },
    "download": {
        "label": "Auto-download new student work",
        "writes": False,
        "default": {"enabled": False, "every_hours": 24,
                    "params": {"window_days": 14}},
    },
    "curve": {
        "label": "Auto-curve low assignment averages",
        "writes": True,
        "default": {"enabled": False, "every_hours": 168,
                    "params": {"floor": 80, "mode": "flag", "window_days": 30}},
    },
    "grading_debt": {
        "label": "Grading-debt report",
        "writes": False,
        "default": {"enabled": True, "every_hours": 24,
                    "params": {"school_days": 3}},
    },
    "student_reports": {
        "label": "Refresh monitored-student reports",
        "writes": False,
        "default": {"enabled": False, "every_hours": 168,
                    "params": {}},
    },
    "powergrader_scheduled_autoscore": {
        "label": "Scheduled PowerGrader Auto-Score",
        "writes": False,
        "default": {"enabled": False, "every_hours": 1,
                    "params": {"max_jobs": 10}},
    },
    "powergrader_late_catchup": {
        "label": "PowerGrader late catch-up",
        "writes": False,
        "default": {"enabled": False, "every_hours": 12,
                    "params": {"max_sessions": 10}},
    },
}

_ROUTINES_LOCK = threading.Lock()


def _routine_state(rid):
    saved = config.get_routine_states().get(rid, {})
    base = json.loads(json.dumps(_ROUTINE_DEFS[rid]["default"]))
    base["params"].update(saved.get("params", {}))
    for k in ("enabled", "every_hours", "last_run", "last_summary"):
        if k in saved:
            base[k] = saved[k]
    return base


def _routine_due(state):
    if not state.get("last_run"):
        return True
    try:
        last = datetime.fromisoformat(state["last_run"])
        hours = state.get("every_hours", 24)
        return datetime.now() >= last + timedelta(hours=hours)
    except (ValueError, TypeError):
        return True


# --------------------------------------------------------------------------
# PowerGrader scheduled routine wrappers
# --------------------------------------------------------------------------

from .routines_powergrader import (
    PowerGraderRoutineDeps,
    _autoscore_job_label, _autoscore_fetch_status, _autoscore_receipt_dir,
    _autoscore_canvas_states, _autoscore_session_is_fully_pushed,
    _autoscore_status_from_summary, _autoscore_summary_payload,
    _autoscore_decisions_payload, _parse_routine_dt,
    _run_routine_powergrader_scheduled_autoscore as _run_routine_powergrader_scheduled_autoscore_impl,
    _run_routine_powergrader_late_catchup as _run_routine_powergrader_late_catchup_impl,
)


def _powergrader_routine_deps():
    return PowerGraderRoutineDeps(
        config=config,
        html_to_text=html_to_text,
        canvas_send=_canvas_send,
        pg_routes=pg_routes,
        ai_workflow=ai_workflow,
        autopush_executor=autopush_executor,
        autoscore_queue=autoscore_queue,
        canvas_fetch=canvas_fetch,
        late_catchup=late_catchup,
        privacy=privacy,
        session_builder=session_builder,
        session_store=session_store,
    )


def _run_routine_powergrader_scheduled_autoscore(params):
    return _run_routine_powergrader_scheduled_autoscore_impl(params, _powergrader_routine_deps())


def _run_routine_powergrader_late_catchup(params):
    return _run_routine_powergrader_late_catchup_impl(params, _powergrader_routine_deps())

def _routine(rid, label, writes=False, default=None):
    def deco(fn):
        if rid in _ROUTINE_DEFS:
            print(f"[routines] custom '{rid}' collides with a built-in — skipped")
            return fn
        _ROUTINE_DEFS[rid] = {"label": label, "writes": bool(writes),
                              "default": default or {"enabled": False, "every_hours": 24, "params": {}}, "custom": True}
        _ROUTINE_RUNNERS[rid] = fn
        return fn
    return deco

_ROUTINE_RUNNERS = {
    "sweep": _run_routine_sweep, "download": _run_routine_download,
    "curve": _run_routine_curve, "grading_debt": _run_routine_grading_debt,
    "student_reports": _run_routine_student_reports,
    "powergrader_scheduled_autoscore": _run_routine_powergrader_scheduled_autoscore,
    "powergrader_late_catchup": _run_routine_powergrader_late_catchup,
}


from .routines_custom import load_custom_routines as _load_custom_routines_

def _load_custom_routines():
    _load_custom_routines_(_routine, _ROUTINE_DEFS, _ROUTINE_RUNNERS)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/routines")
def api_routines():
    out = []
    for rid, meta in _ROUTINE_DEFS.items():
        st = _routine_state(rid)
        out.append({"id": rid, "label": meta["label"], "writes": meta["writes"],
                    "custom": meta.get("custom", False), "enabled": st["enabled"],
                    "every_hours": st["every_hours"], "params": st["params"],
                    "last_run": st.get("last_run"), "last_summary": st.get("last_summary"),
                    "due": _routine_due(st)})
    return JSONResponse({"ok": True, "routines": out})


@router.post("/routines/save")
def api_routines_save(routine_id: str = Form(...), patch: str = Form(...)):
    if routine_id not in _ROUTINE_DEFS:
        return JSONResponse({"ok": False, "error": "unknown routine"})
    try:
        p = json.loads(patch)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad patch: {e}"})
    allowed = {k: v for k, v in p.items() if k in ("enabled", "every_hours", "params")}
    config.set_routine_state(routine_id, allowed)
    return JSONResponse({"ok": True})


@router.post("/routines/run")
def api_routines_run(ids: str = Form(""), force: bool = Form(False)):
    id_list = [i.strip() for i in ids.split(",") if i.strip()] or None
    if not _ROUTINES_LOCK.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "a routine run is already in progress"})
    try:
        report = {"ok": True, "ran": [], "skipped": []}
        for rid, meta in _ROUTINE_DEFS.items():
            if id_list is not None and rid not in id_list:
                continue
            state = _routine_state(rid)
            if not force and (not state["enabled"] or not _routine_due(state)):
                report["skipped"].append({"id": rid, "label": meta["label"],
                                          "reason": "disabled" if not state["enabled"] else "not due"})
                continue
            try:
                res = _ROUTINE_RUNNERS[rid](state["params"])
            except Exception as e:
                res = {"ok": False, "lines": [f"✗ crashed: {e}"], "summary": str(e)}
            report["ok"] = report["ok"] and res["ok"]
            report["ran"].append({"id": rid, "label": meta["label"], **res})
            config.set_routine_state(rid, {"last_run": datetime.now().isoformat(timespec="seconds"),
                                           "last_summary": res["summary"]})
            activity.log_event("routine", meta["label"], ["(all active)"], res["ok"], detail=res["summary"])
        return JSONResponse(report)
    finally:
        _ROUTINES_LOCK.release()


# --------------------------------------------------------------------------
# Background thread
# --------------------------------------------------------------------------

def _routines_heartbeat():
    _time.sleep(90)
    while True:
        try:
            if config.token_is_set():
                _run_routines_bg()
        except Exception:
            pass
        _time.sleep(1800)


def _run_routines_bg():
    for rid, meta in _ROUTINE_DEFS.items():
        if not meta.get("custom"):
            state = _routine_state(rid)
            if state["enabled"] and _routine_due(state):
                try:
                    res = _ROUTINE_RUNNERS[rid](state["params"])
                    config.set_routine_state(rid, {"last_run": datetime.now().isoformat(timespec="seconds"),
                                                   "last_summary": res["summary"]})
                except Exception:
                    pass
