"""Self-update: version comparison, download/verify/stage safety, routes, and
the applier's preserve-list-vs-.gitignore regression guard."""
from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import runtime_paths
from api.webui import self_update
from api.webui.routes import updates as updates_routes
from api.webui.server import app

ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, content=b"", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self._content = content
        self.headers = headers or {}
        self.closed = False

    def json(self):
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data

    def iter_content(self, chunk_size=65536):
        data = self._content
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    def close(self):
        self.closed = True


def _queue_gets(monkeypatch, responses):
    calls = []
    queue = iter(responses)

    def fake_get(url, *, headers, timeout, allow_redirects, stream):
        calls.append(url)
        return next(queue)

    monkeypatch.setattr(self_update.requests, "get", fake_get)
    return calls


def _sums_text(zip_name: str, zip_bytes: bytes) -> str:
    digest = hashlib.sha256(zip_bytes).hexdigest()
    return f"{digest}  {zip_name}\n"


# --------------------------------------------------------------------------
# Version comparison (D7)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1.0.0", (1, 0, 0, 1, 0)),
    ("v1.0.0", (1, 0, 0, 1, 0)),
    ("0.75.0-beta.0", (0, 75, 0, 0, 0)),
    ("0.75.0-rc.2", (0, 75, 0, 0, 2)),
    ("not-a-version", None),
    ("1.2", None),
])
def test_version_key_parses_and_ranks(text, expected):
    assert self_update._version_key(text) == expected


def test_final_release_ranks_above_prerelease_of_the_same_number():
    beta = self_update._version_key("0.75.0-beta.9")
    final = self_update._version_key("0.75.0")
    assert final > beta


def test_never_offers_a_downgrade():
    current = self_update._version_key("1.2.0")
    older = self_update._version_key("1.1.9")
    assert not (older > current)


# --------------------------------------------------------------------------
# status()
# --------------------------------------------------------------------------

def test_status_reports_available_update(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    monkeypatch.setattr(self_update, "__version__", "0.75.0-beta.0")
    _queue_gets(monkeypatch, [FakeResponse(json_data=_release_json(tag="v1.0.0"))])

    result = self_update.status()
    assert result["ok"] is True
    assert result["available"] is True
    assert result["latest"] == "1.0.0"
    assert result["staged"] is None
    assert result["error"] is None


def test_status_reports_up_to_date_without_downgrade(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    monkeypatch.setattr(self_update, "__version__", "1.0.0")
    _queue_gets(monkeypatch, [FakeResponse(json_data=_release_json(tag="v0.9.0"))])

    result = self_update.status()
    assert result["ok"] is True
    assert result["available"] is False


def test_status_never_raises_on_network_failure(monkeypatch, tmp_path, _isolate_local_app_dir):

    def boom(*a, **k):
        raise self_update.requests.ConnectionError("no route to host")

    monkeypatch.setattr(self_update.requests, "get", boom)
    result = self_update.status()
    assert result == {
        "ok": False, "current": self_update.__version__, "latest": None,
        "available": False, "published_at": None, "notes_url": None,
        "staged": None, "error": "Could not reach the update server. Check your internet connection.",
    }


def test_status_never_raises_on_malformed_json(monkeypatch, tmp_path, _isolate_local_app_dir):
    _queue_gets(monkeypatch, [FakeResponse(status_code=200, json_data=None)])
    result = self_update.status()
    assert result["ok"] is False
    assert "did not return valid data" in result["error"]


def test_status_handles_unparseable_version(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    _queue_gets(monkeypatch, [FakeResponse(json_data=_release_json(tag="garbage"))])
    result = self_update.status()
    assert result["available"] is False
    assert result["ok"] is False
    assert result["error"]


def test_status_surfaces_staged_marker(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    pending = self_update._pending_path()
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps({"version": "1.0.0", "bytes": 42}), encoding="utf-8")
    _queue_gets(monkeypatch, [FakeResponse(json_data=_release_json(tag="v1.0.0"))])

    result = self_update.status()
    assert result["staged"] == {"version": "1.0.0", "bytes": 42}


# --------------------------------------------------------------------------
# Feed selection: loopback override honored, everything else ignored
# --------------------------------------------------------------------------

def test_non_loopback_feed_override_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_EXPERT_UPDATE_FEED", "https://evil.example.com/feed.json")
    url, loopback = self_update._active_feed()
    assert loopback is False
    assert url == self_update._FEED_URL


def test_loopback_feed_override_is_honored(monkeypatch):
    monkeypatch.setenv("CANVAS_EXPERT_UPDATE_FEED", "http://127.0.0.1:8123/feed.json")
    url, loopback = self_update._active_feed()
    assert loopback is True
    assert url == "http://127.0.0.1:8123/feed.json"


def test_localhost_feed_override_is_honored(monkeypatch):
    monkeypatch.setenv("CANVAS_EXPERT_UPDATE_FEED", "http://localhost:8123/feed.json")
    _, loopback = self_update._active_feed()
    assert loopback is True


def test_redirect_to_non_allowlisted_host_aborts(monkeypatch, tmp_path, _isolate_local_app_dir):
    _queue_gets(monkeypatch, [
        FakeResponse(status_code=302, headers={"Location": "https://not-github.example.com/x"}),
    ])
    with pytest.raises(self_update.UpdateError):
        self_update.fetch_latest_release()


def test_redirect_hop_through_allowlisted_hosts_is_followed(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    _queue_gets(monkeypatch, [
        FakeResponse(status_code=302, headers={"Location": "https://objects.githubusercontent.com/x"}),
        FakeResponse(json_data=_release_json()),
    ])
    data = self_update.fetch_latest_release()
    assert data["tag_name"] == "v1.0.0"


def test_too_many_redirects_aborts(monkeypatch, tmp_path, _isolate_local_app_dir):
    hop = FakeResponse(status_code=302, headers={"Location": "https://github.com/next"})
    _queue_gets(monkeypatch, [hop] * (self_update._MAX_REDIRECTS + 1))
    with pytest.raises(self_update.UpdateError, match="Too many redirects"):
        self_update.fetch_latest_release()


# --------------------------------------------------------------------------
# download_update(): hash check, extraction safety, atomic staging
# --------------------------------------------------------------------------

def test_download_update_stages_a_valid_release(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json, _make_zip):
    zip_path = tmp_path / "src.zip"
    zip_bytes = _make_zip(zip_path, {
        "Open Canvas Expert.bat": b"@echo off\r\n",
        "api/qf_ui.py": b"# fictional\r\n",
    })
    sums = _sums_text("CanvasExpert.zip", zip_bytes)

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=sums.encode("utf-8")),
        FakeResponse(content=zip_bytes),
    ])

    result = self_update.download_update()
    assert result == {"ok": True, "version": "1.0.0", "bytes": len(zip_bytes)}
    staged = self_update._staged_dir()
    assert (staged / "Open Canvas Expert.bat").read_bytes() == b"@echo off\r\n"
    assert (staged / "api" / "qf_ui.py").exists()
    pending = json.loads(self_update._pending_path().read_text(encoding="utf-8"))
    assert pending["version"] == "1.0.0"
    assert pending["bytes"] == len(zip_bytes)


def test_download_update_rejects_hash_mismatch(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json, _make_zip):
    zip_path = tmp_path / "src.zip"
    zip_bytes = _make_zip(zip_path, {"Open Canvas Expert.bat": b"ok"})
    wrong_sums = "0" * 64 + "  CanvasExpert.zip\n"

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=wrong_sums.encode("utf-8")),
        FakeResponse(content=zip_bytes),
    ])

    result = self_update.download_update()
    assert result["ok"] is False
    assert "checksum" in result["error"]
    assert not self_update._staged_dir().exists()


def test_download_update_rejects_missing_sums_entry(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json, _make_zip):
    zip_path = tmp_path / "src.zip"
    zip_bytes = _make_zip(zip_path, {"Open Canvas Expert.bat": b"ok"})
    sums = "deadbeef" * 8 + "  SomeOtherFile.zip\n"

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=sums.encode("utf-8")),
    ])

    result = self_update.download_update()
    assert result["ok"] is False
    assert not self_update._staged_dir().exists()


@pytest.mark.parametrize("bad_name", ["../evil.txt", "/etc/passwd", "C:/Windows/evil.txt", "sub/../../evil.txt"])
def test_download_update_rejects_unsafe_zip_entries(monkeypatch, tmp_path, bad_name, _isolate_local_app_dir, _release_json, _make_zip):
    zip_path = tmp_path / "src.zip"
    zip_bytes = _make_zip(zip_path, {
        "Open Canvas Expert.bat": b"ok",
        bad_name: b"malicious",
    })
    sums = _sums_text("CanvasExpert.zip", zip_bytes)

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=sums.encode("utf-8")),
        FakeResponse(content=zip_bytes),
    ])

    result = self_update.download_update()
    assert result["ok"] is False
    assert "unsafe" in result["error"]
    assert not self_update._staged_dir().exists()


def test_download_update_rejects_symlink_entry(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    zip_path = tmp_path / "src.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("Open Canvas Expert.bat", b"ok")
        info = zipfile.ZipInfo("sneaky-link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    zip_bytes = zip_path.read_bytes()
    sums = _sums_text("CanvasExpert.zip", zip_bytes)

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=sums.encode("utf-8")),
        FakeResponse(content=zip_bytes),
    ])

    result = self_update.download_update()
    assert result["ok"] is False
    assert "symlink" in result["error"]
    assert not self_update._staged_dir().exists()


def test_download_update_rejects_oversized_download(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json, _make_zip):
    monkeypatch.setattr(self_update, "_MAX_DOWNLOAD_BYTES", 10)
    zip_path = tmp_path / "src.zip"
    zip_bytes = _make_zip(zip_path, {"Open Canvas Expert.bat": b"much longer than ten bytes"})
    sums = _sums_text("CanvasExpert.zip", zip_bytes)

    _queue_gets(monkeypatch, [
        FakeResponse(json_data=_release_json()),
        FakeResponse(content=sums.encode("utf-8")),
        FakeResponse(content=zip_bytes),
    ])

    result = self_update.download_update()
    assert result["ok"] is False
    assert "size limit" in result["error"]
    assert not self_update._staged_dir().exists()


def test_download_update_never_raises_on_network_failure(monkeypatch, tmp_path, _isolate_local_app_dir):

    def boom(*a, **k):
        raise self_update.requests.Timeout("timed out")

    monkeypatch.setattr(self_update.requests, "get", boom)
    result = self_update.download_update()
    assert result["ok"] is False
    assert "internet connection" in result["error"]


def test_download_update_is_missing_a_release_asset(monkeypatch, tmp_path, _isolate_local_app_dir, _release_json):
    payload = _release_json()
    payload["assets"] = [payload["assets"][0]]  # drop SHA256SUMS.txt
    _queue_gets(monkeypatch, [FakeResponse(json_data=payload)])
    result = self_update.download_update()
    assert result["ok"] is False
    assert "missing" in result["error"]


# --------------------------------------------------------------------------
# Staged-payload resolution (depth 0 / depth 1 wrapper) and cancel
# --------------------------------------------------------------------------

def test_is_staged_true_at_depth_zero(monkeypatch, tmp_path, _isolate_local_app_dir):
    staged = self_update._staged_dir()
    staged.mkdir(parents=True)
    (staged / "Open Canvas Expert.bat").write_text("ok", encoding="utf-8")
    assert self_update.is_staged() is True


def test_is_staged_true_at_depth_one_wrapper_folder(monkeypatch, tmp_path, _isolate_local_app_dir):
    staged = self_update._staged_dir()
    wrapper = staged / "CanvasExpert"
    wrapper.mkdir(parents=True)
    (wrapper / "Open Canvas Expert.bat").write_text("ok", encoding="utf-8")
    assert self_update.is_staged() is True


def test_is_staged_false_when_nothing_staged(monkeypatch, tmp_path, _isolate_local_app_dir):
    assert self_update.is_staged() is False


def test_cancel_staged_clears_staging(monkeypatch, tmp_path, _isolate_local_app_dir):
    staged = self_update._staged_dir()
    staged.mkdir(parents=True)
    (staged / "Open Canvas Expert.bat").write_text("ok", encoding="utf-8")
    self_update._pending_path().write_text("{}", encoding="utf-8")

    result = self_update.cancel_staged()
    assert result == {"ok": True}
    assert not staged.exists()
    assert not self_update._pending_path().exists()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_status_route_returns_json(monkeypatch, tmp_path, client, _isolate_local_app_dir):
    monkeypatch.setattr(self_update, "status", lambda: {"ok": True, "current": "0.75.0-beta.0",
                                                          "latest": None, "available": False,
                                                          "published_at": None, "notes_url": None,
                                                          "staged": None, "error": None})
    response = client.get("/api/update/status")
    assert response.status_code == 200
    assert response.json()["current"] == "0.75.0-beta.0"


def test_download_route_returns_json(monkeypatch, client):
    monkeypatch.setattr(self_update, "download_update", lambda: {"ok": True, "version": "1.0.0", "bytes": 5})
    response = client.post("/api/update/download")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": "1.0.0", "bytes": 5}


def test_apply_route_refuses_when_nothing_staged(monkeypatch, client):
    monkeypatch.setattr(self_update, "is_staged", lambda: False)
    response = client.post("/api/update/apply")
    assert response.status_code == 409
    assert response.json()["ok"] is False


def test_apply_route_refuses_without_the_launcher_seam(monkeypatch, client):
    """Acceptance criterion 6: an app constructed without the launcher (e.g.
    every test in this suite, and the MCP server path) has no
    app.state.request_restart. The route must refuse with 409 and must not
    exit the process."""
    monkeypatch.setattr(self_update, "is_staged", lambda: True)
    assert not hasattr(app.state, "request_restart")
    response = client.post("/api/update/apply")
    assert response.status_code == 409
    assert "restart itself" in response.json()["error"]


def test_apply_route_triggers_restart_when_launcher_seam_present(monkeypatch, client):
    monkeypatch.setattr(self_update, "is_staged", lambda: True)
    calls = []
    monkeypatch.setattr(app.state, "request_restart", lambda code: calls.append(code), raising=False)

    class ImmediateTimer:
        """Fires immediately instead of after 0.5s, so the test doesn't wait."""

        def __init__(self, interval, fn, args=()):
            self._fn = fn
            self._args = args

        def start(self):
            self._fn(*self._args)

    monkeypatch.setattr(updates_routes.threading, "Timer", ImmediateTimer)

    response = client.post("/api/update/apply")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "restarting": True}
    assert calls == [7]


def test_cancel_route_returns_json(monkeypatch, client):
    monkeypatch.setattr(self_update, "cancel_staged", lambda: {"ok": True})
    response = client.post("/api/update/cancel")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --------------------------------------------------------------------------
# Applier preserve-list vs .gitignore regression guard (D4)
# --------------------------------------------------------------------------

def _extract_set_value(cmd_text: str, var_name: str) -> list[str]:
    match = re.search(rf'set\s+"{re.escape(var_name)}=([^"]*)"', cmd_text)
    assert match, f"{var_name} is not defined in apply_update.cmd"
    return match.group(1).split()


def test_apply_update_preserve_list_covers_every_gitignored_runtime_path():
    """The applier's exclude lists must never drift behind .gitignore's
    machine-local/runtime sections -- that gap is exactly how a teacher would
    silently lose a setting during a self-update."""
    gitignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    applier_text = (ROOT / "api" / "scripts" / "apply_update.cmd").read_text(encoding="utf-8")

    xf_tokens = set(_extract_set_value(applier_text, "PRESERVE_XF"))
    xd_tokens = set(_extract_set_value(applier_text, "PRESERVE_XD"))

    headers = ("# Canvas token + machine-local config (NEVER commit)", "# Runtime / user data")
    lines = gitignore_text.splitlines()
    checked = 0
    i = 0
    while i < len(lines):
        if lines[i].strip() in headers:
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                entry = lines[i].strip()
                bare = entry.rstrip("/")
                name = bare.rsplit("/", 1)[-1]
                pool = xd_tokens if entry.endswith("/") else xf_tokens
                assert name in pool, f"{entry!r} from .gitignore is not preserved by apply_update.cmd"
                checked += 1
                i += 1
            continue
        i += 1
    assert checked >= 8, "expected to find gitignore runtime entries to check"
