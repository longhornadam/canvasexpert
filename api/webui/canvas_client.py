"""Canvas REST client — token-aware GET / paginated-GET / send wrappers.

Extracted verbatim from server.py's "# Helpers" block so routers and services
can share one Canvas client. No behavior change. Names keep their leading
underscore so existing call sites stay untouched.
"""
import requests

from . import config


def _canvas_headers():
    token = config.get_token()
    if not token:
        return None, None
    return {"Authorization": f"Bearer {token}"}, config.get_canvas_base()


def _canvas_get(path, params=None, timeout=20):
    hdrs, base = _canvas_headers()
    if not hdrs:
        return None, "No Canvas token saved — go to Settings."
    try:
        r = requests.get(f"{base}{path}", headers=hdrs, params=params or {}, timeout=timeout)
    except requests.RequestException as e:
        return None, str(e)
    if r.status_code != 200:
        hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
        return None, f"HTTP {r.status_code}: {r.text[:200]}{hint}"
    return r.json(), None


def _canvas_get_all(path, params=None, timeout=30):
    """GET with Link-header pagination — returns the concatenated list."""
    hdrs, base = _canvas_headers()
    if not hdrs:
        return None, "No Canvas token saved — go to Settings."
    out, url = [], f"{base}{path}"
    while url:
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=timeout)
        except requests.RequestException as e:
            return None, str(e)
        if r.status_code != 200:
            hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
            return None, f"HTTP {r.status_code}: {r.text[:200]}{hint}"
        data = r.json()
        out.extend(data if isinstance(data, list) else [data])
        params = None
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    return out, None


def _canvas_send(method, path, payload, timeout=30):
    """POST/PUT/PATCH a JSON payload to Canvas — returns (json, error).
    204 / empty bodies (e.g. late_policy PATCH) come back as {}."""
    hdrs, base = _canvas_headers()
    if not hdrs:
        return None, "No Canvas token saved — go to Settings."
    try:
        r = requests.request(method, f"{base}{path}", headers=hdrs,
                             json=payload, timeout=timeout)
    except requests.RequestException as e:
        return None, str(e)
    if r.status_code not in (200, 201, 204):
        hint = " (Token missing or expired on this machine — mint a fresh one in Settings)" if r.status_code == 401 else ""
        return None, f"HTTP {r.status_code}: {r.text[:300]}{hint}"
    try:
        return r.json(), None
    except ValueError:
        return {}, None