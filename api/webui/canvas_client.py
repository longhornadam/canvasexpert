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


def _next_canvas_page_url(response) -> str | None:
    """Return Canvas's opaque ``rel=next`` URL, if this page has one."""
    for part in response.headers.get("Link", "").split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def _canvas_get_all_pages(path, params=None, timeout=30, *, complete_only: bool):
    """Fetch one Canvas collection with the shared Link-header traversal.

    The legacy public wrapper deliberately keeps its historical behavior.
    ``complete_only`` adds the stricter receipt needed before a caller lets a
    collection replace an existing membership index.
    """
    started = time.monotonic()
    hdrs, base = _canvas_headers()
    event = "canvas.get_all_complete" if complete_only else "canvas.get_all"
    if not hdrs:
        _emit_canvas(event, started, "unconfigured")
        return None, "No Canvas token saved — go to Settings.", False
    out, url = [], f"{base}{path}"
    visited_urls = set()
    while url:
        if complete_only:
            visited_urls.add(url)
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=timeout)
        except requests.RequestException as e:
            _emit_canvas(event, started, "failed", error_class=type(e))
            # RequestException text can include a configured URL.  The
            # complete receipt stays safe to return and persist as a code.
            return None, "connection" if complete_only else str(e), False
        successful = 200 <= r.status_code < 300 if complete_only else r.status_code == 200
        if not successful:
            _emit_canvas(event, started, "failed", status_code=r.status_code)
            if complete_only:
                return None, f"HTTP {r.status_code}", False
            hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
            return None, f"HTTP {r.status_code}: {r.text[:200]}{hint}", False
        try:
            data = r.json()
        except Exception as e:
            _emit_canvas(event, started, "failed", status_code=r.status_code, error_class=type(e))
            if complete_only:
                return None, "invalid_response", False
            raise
        if complete_only and not isinstance(data, list):
            _emit_canvas(event, started, "failed", status_code=r.status_code)
            return None, "invalid_response", False
        out.extend(data if isinstance(data, list) else [data])
        params = None
        url = _next_canvas_page_url(r)
        if complete_only and url in visited_urls:
            _emit_canvas(event, started, "failed", status_code=r.status_code)
            return None, "pagination_incomplete", False
    _emit_canvas(event, started, "ok", status_code=200, count=len(out))
    return out, None, True


def _canvas_get_all(path, params=None, timeout=30):
    """GET with Link-header pagination — returns the concatenated list."""
    rows, error, _complete = _canvas_get_all_pages(
        path, params=params, timeout=timeout, complete_only=False)
    return rows, error


def _canvas_get_all_complete(path, params=None, timeout=30):
    """GET a proven-complete Canvas list for destructive membership callers.

    Returns ``(rows, error, complete)``.  ``complete`` is true only for a
    fully traversed sequence of successful JSON-list pages.
    """
    return _canvas_get_all_pages(path, params=params, timeout=timeout,
                                 complete_only=True)


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
