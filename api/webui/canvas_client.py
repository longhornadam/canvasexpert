"""Canvas REST client — token-aware GET / paginated-GET / send wrappers.

Extracted verbatim from server.py's "# Helpers" block so routers and services
can share one Canvas client. No behavior change. Names keep their leading
underscore so existing call sites stay untouched.
"""
import requests
import time

from . import config

from api import operational_log


def _emit_canvas(event: str, started: float, outcome: str, *, status_code=None,
                 error_class=None, count=None) -> None:
    operational_log.emit(
        event,
        outcome,
        duration_ms=max(0, int(round((time.monotonic() - started) * 1000))),
        status_code=status_code,
        error_class=error_class,
        count=count,
    )


def _canvas_headers():
    token = config.get_token()
    if not token:
        return None, None
    return {"Authorization": f"Bearer {token}"}, config.get_canvas_base()


def _canvas_get(path, params=None, timeout=20):
    started = time.monotonic()
    hdrs, base = _canvas_headers()
    if not hdrs:
        _emit_canvas("canvas.get", started, "unconfigured")
        return None, "No Canvas token saved — go to Settings."
    try:
        r = requests.get(f"{base}{path}", headers=hdrs, params=params or {}, timeout=timeout)
    except requests.RequestException as e:
        _emit_canvas("canvas.get", started, "failed", error_class=type(e))
        return None, str(e)
    if r.status_code != 200:
        _emit_canvas("canvas.get", started, "failed", status_code=r.status_code)
        hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
        return None, f"HTTP {r.status_code}: {r.text[:200]}{hint}"
    try:
        data = r.json()
    except Exception as e:
        _emit_canvas("canvas.get", started, "failed", status_code=r.status_code, error_class=type(e))
        raise
    _emit_canvas("canvas.get", started, "ok", status_code=r.status_code)
    return data, None


def _canvas_get_all(path, params=None, timeout=30):
    """GET with Link-header pagination — returns the concatenated list."""
    started = time.monotonic()
    hdrs, base = _canvas_headers()
    if not hdrs:
        _emit_canvas("canvas.get_all", started, "unconfigured")
        return None, "No Canvas token saved — go to Settings."
    out, url = [], f"{base}{path}"
    while url:
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=timeout)
        except requests.RequestException as e:
            _emit_canvas("canvas.get_all", started, "failed", error_class=type(e))
            return None, str(e)
        if r.status_code != 200:
            _emit_canvas("canvas.get_all", started, "failed", status_code=r.status_code)
            hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
            return None, f"HTTP {r.status_code}: {r.text[:200]}{hint}"
        try:
            data = r.json()
        except Exception as e:
            _emit_canvas("canvas.get_all", started, "failed", status_code=r.status_code, error_class=type(e))
            raise
        out.extend(data if isinstance(data, list) else [data])
        params = None
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    _emit_canvas("canvas.get_all", started, "ok", status_code=200, count=len(out))
    return out, None


def _canvas_send(method, path, payload, timeout=30):
    """POST/PUT/PATCH a JSON payload to Canvas — returns (json, error).
    204 / empty bodies (e.g. late_policy PATCH) come back as {}."""
    started = time.monotonic()
    method_label = str(method or "unknown").strip().lower()
    if not method_label.isidentifier():
        method_label = "other"
    event = f"canvas.send.{method_label}"
    hdrs, base = _canvas_headers()
    if not hdrs:
        _emit_canvas(event, started, "unconfigured")
        return None, "No Canvas token saved — go to Settings."
    try:
        r = requests.request(method, f"{base}{path}", headers=hdrs,
                             json=payload, timeout=timeout)
    except requests.RequestException as e:
        _emit_canvas(event, started, "failed", error_class=type(e))
        return None, str(e)
    if r.status_code not in (200, 201, 204):
        _emit_canvas(event, started, "failed", status_code=r.status_code)
        hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
        return None, f"HTTP {r.status_code}: {r.text[:300]}{hint}"
    try:
        data = r.json()
    except ValueError:
        _emit_canvas(event, started, "ok", status_code=r.status_code)
        return {}, None
    _emit_canvas(event, started, "ok", status_code=r.status_code)
    return data, None
