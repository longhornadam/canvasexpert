"""Local-only CSRF guard for Work Registry mutation routes."""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


_CSRF_TOKEN = secrets.token_urlsafe(32)


def csrf_token() -> str:
    return _CSRF_TOKEN


def _forbidden():
    raise HTTPException(status_code=403, detail="local mutation rejected")


def _request_parts(request: Request):
    parsed = urlsplit(str(request.url))
    return parsed.scheme, parsed.hostname, parsed.port


def _host_parts(host: str):
    if not host or host != host.strip():
        return None
    try:
        parsed = urlsplit(f"//{host}")
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            return None
        return parsed.hostname, parsed.port
    except ValueError:
        return None


def _valid_loopback_host(request: Request) -> bool:
    scheme, hostname, request_port = _request_parts(request)
    host_parts = _host_parts(request.headers.get("host", ""))
    if not host_parts or hostname not in {"127.0.0.1", "::1"}:
        return False
    host, port = host_parts
    return host == hostname and port is not None and request_port is not None and port == request_port


def _valid_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
        scheme, hostname, port = _request_parts(request)
        if not parsed.scheme or not parsed.hostname or parsed.port is None:
            return False
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        return parsed.scheme == scheme and parsed.hostname == hostname and parsed.port == port
    except ValueError:
        return False


def require_local_mutation(request: Request) -> None:
    """Reject mutations unless CSRF, loopback Host, and same-origin checks pass."""
    if request.headers.get("X-CanvasExpert-CSRF") != _CSRF_TOKEN:
        _forbidden()
    if not _valid_loopback_host(request) or not _valid_origin(request):
        _forbidden()
