"""Process-local readiness probes for the Desk/Workbench confidence strip."""

import importlib
import os
import tempfile
import threading
from datetime import datetime, timezone

from . import config, workspace
from .canvas_client import _canvas_get
from .routes.settings import _probe_openrouter_key


_LOCK = threading.RLock()
_LAST_PROBE = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _component(status: str, code: str = "") -> dict:
    result = {"status": status}
    if code:
        result["code"] = code
    return result


def _code(error: str, status_code: int | None = None) -> str:
    text = str(error or "").lower()
    if status_code == 401 or "401" in text or "unauthorized" in text:
        return "unauthorized"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "unavailable" in text or "network" in text or "connection" in text:
        return "network"
    return "network"


def _probe_canvas() -> dict:
    if not config.token_is_set() or not config.get_canvas_base():
        return _component("unconfigured", "unconfigured")
    data, error = _canvas_get("/api/v1/users/self/profile", timeout=5)
    if data is not None:
        return _component("ready")
    return _component("degraded", _code(error))


def _probe_openrouter() -> dict:
    key = config.get_openrouter_key()
    if not key or not config.has_openrouter_key():
        return _component("unconfigured", "unconfigured")
    result = _probe_openrouter_key(key, timeout=5)
    if result.get("valid"):
        return _component("ready")
    return _component("degraded", _code(result.get("error")))


def _probe_privacy() -> dict:
    root = workspace.workspace_root()
    if not root:
        return _component("unconfigured", "unconfigured")
    system = os.path.join(root, "FeedbackExpert", "_system")
    probe_path = None
    try:
        os.makedirs(system, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=system,
            prefix=".readiness-", suffix=".probe", delete=False,
        ) as probe:
            probe.write("ok")
            probe.flush()
            os.fsync(probe.fileno())
            probe_path = probe.name
        importlib.import_module("api.feedback_safety")
        importlib.import_module("api.feedback_scrub")
        return _component("ready")
    except OSError:
        return _component("degraded", "workspace_unwritable")
    except Exception:
        return _component("degraded", "protection_unavailable")
    finally:
        if probe_path:
            try:
                os.unlink(probe_path)
            except OSError:
                pass


def _overall(components: dict) -> str:
    statuses = [item["status"] for item in components.values()]
    if any(status == "unknown" for status in statuses):
        return "unknown"
    if all(status == "unconfigured" for status in statuses):
        return "unconfigured"
    if all(status == "ready" for status in statuses):
        return "ready"
    return "degraded"


def _public(components: dict, checked_at: str | None) -> dict:
    return {
        "ok": True,
        "status": _overall(components),
        "checked_at": checked_at,
        "configured_model": config.get_openrouter_model(),
        "components": components,
    }


def snapshot() -> dict:
    with _LOCK:
        if _LAST_PROBE is None:
            unknown = {name: _component("unknown") for name in ("canvas", "openrouter", "privacy")}
            return _public(unknown, None)
        return _public(_LAST_PROBE["components"], _LAST_PROBE["checked_at"])


def probe(force: bool = False) -> dict:
    global _LAST_PROBE
    with _LOCK:
        if _LAST_PROBE is not None and not force:
            return snapshot()
        components = {
            "canvas": _probe_canvas(),
            "openrouter": _probe_openrouter(),
            "privacy": _probe_privacy(),
        }
        _LAST_PROBE = {"checked_at": _now(), "components": components}
        return snapshot()


def _reset_for_tests() -> None:
    global _LAST_PROBE
    with _LOCK:
        _LAST_PROBE = None
