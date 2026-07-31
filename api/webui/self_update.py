"""Self-update: check, download, verify, and stage a newer Canvas Expert build.

Teacher-initiated only. Nothing here runs on a timer, at launch, or in the
background -- every function is called from a Settings button click by way
of ``routes/updates.py``. The version check is a bare, unauthenticated GET
with no query parameters and no identifying header beyond a plain user
agent: no teacher, course, or machine identifier ever leaves this computer.

The only outbound host this module ever talks to is the pinned public
GitHub repository below (or, for local testing only, a loopback feed -- see
``_env_feed_url``). The repository slug is a module constant, never
configuration a teacher can edit.

Update sequence (the part this module owns):
  1. Fetch the latest release's metadata (``status``).
  2. Download the release ZIP and its ``SHA256SUMS.txt``, verify the hash,
     walk every ZIP entry by hand for path/symlink safety, and extract to a
     sibling temp directory before an atomic rename to ``staged``
     (``download_update``).
  3. On "Restart and update", the route asks the running server to exit
     with code 7. ``Open Canvas Expert.bat`` and ``api/scripts/apply_update.cmd``
     (outside this module -- see their own comments) do the actual file swap
     once the app folder is completely closed.

What the hash check does and does not buy: comparing the downloaded ZIP's
SHA256 against a same-release ``SHA256SUMS.txt`` catches a truncated or
corrupted download and a swapped/tampered asset that doesn't match its own
release's checksum file. It does not prove the release itself is what the
maintainer intended -- that would need code signing (an explicit non-goal of
this slice; worth doing later).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from api import __version__, runtime_paths

# --------------------------------------------------------------------------
# Pinned source. Not configuration -- a teacher cannot point this anywhere
# else. See _env_feed_url() for the one narrow, loopback-only exception used
# for local testing.
# --------------------------------------------------------------------------
REPO_SLUG = "longhornadam/canvasexpert"
_FEED_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
_GITHUB_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}

_MAX_REDIRECTS = 5
_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
_MAX_SUMS_BYTES = 1_000_000
_CHUNK = 64 * 1024
_TIMEOUT = (30, 30)  # (connect, read) seconds
_USER_AGENT = "CanvasExpert-SelfUpdate/1 (+local, no telemetry)"

_SUMS_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$")
_VERSION_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-(beta|rc)\.(\d+))?$")
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")


class UpdateError(Exception):
    """A plain-English update failure, safe to show a teacher as-is."""


# --------------------------------------------------------------------------
# Paths -- resolved at call time (never cached at import time) so tests can
# monkeypatch runtime_paths.local_app_dir() and so a workspace-less first run
# still works correctly.
# --------------------------------------------------------------------------

def _update_root() -> Path:
    return runtime_paths.local_app_dir() / "update"


def _staged_dir() -> Path:
    return _update_root() / "staged"


def _pending_path() -> Path:
    return _update_root() / "pending.json"


# --------------------------------------------------------------------------
# Version comparison (D7)
# --------------------------------------------------------------------------

def _version_key(text: str):
    """Rank a version string for comparison, or None if unparseable.

    A final release ranks above any prerelease of the same
    major.minor.patch: (major, minor, patch, 1, 0) for final,
    (major, minor, patch, 0, n) for -beta.N / -rc.N. Tolerates a leading v.
    """
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    major, minor, patch, kind, n = match.groups()
    if kind is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, int(n))


def _display_version(tag: str) -> str:
    tag = (tag or "").strip()
    if len(tag) > 1 and tag[0] in "vV" and tag[1].isdigit():
        return tag[1:]
    return tag


# --------------------------------------------------------------------------
# Feed selection -- pinned GitHub source, or a loopback override for local
# testing only (D5). The override is honored ONLY when its host is loopback;
# any other value is silently ignored, never surfaced as an error, so a
# stray environment variable can never redirect a teacher's real update
# anywhere but GitHub.
#
# The loopback override also relaxes the HTTPS-only and GitHub-host-only
# rules for that host alone: `py -m http.server` cannot easily serve TLS,
# and traffic that never leaves 127.0.0.1 has no network path for HTTPS to
# protect. Every other rule -- size cap, timeouts, extraction safety, and
# especially the hash check -- still applies in full to whatever a loopback
# feed serves.
# --------------------------------------------------------------------------

def _env_feed_url() -> str | None:
    value = (os.environ.get("CANVAS_EXPERT_UPDATE_FEED") or "").strip()
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.hostname not in _LOOPBACK_HOSTS:
        return None
    return value


def _active_feed() -> tuple[str, bool]:
    """Return (url, loopback_mode)."""
    override = _env_feed_url()
    if override:
        return override, True
    return _FEED_URL, False


def _allowed_hosts(loopback: bool) -> set[str]:
    return _GITHUB_HOSTS | _LOOPBACK_HOSTS if loopback else set(_GITHUB_HOSTS)


def _allowed_schemes(loopback: bool) -> tuple[str, ...]:
    return ("http", "https") if loopback else ("https",)


# --------------------------------------------------------------------------
# Networking -- manual redirect following with a host allowlist checked on
# every hop (D5). requests' own allow_redirects=True only validates the
# final URL, which is not sufficient here.
# --------------------------------------------------------------------------

def _safe_get(url: str, *, loopback: bool):
    allowed_hosts = _allowed_hosts(loopback)
    allowed_schemes = _allowed_schemes(loopback)
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        if parts.scheme not in allowed_schemes:
            raise UpdateError("Refused a non-secure download location; nothing was staged.")
        if parts.hostname not in allowed_hosts:
            raise UpdateError("Refused a download from an unexpected host; nothing was staged.")
        try:
            response = requests.get(
                current,
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as error:
            raise UpdateError(
                "Could not reach the update server. Check your internet connection."
            ) from error
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise UpdateError("The update server sent a redirect with no destination.")
            current = urljoin(current, location)
            continue
        return response
    raise UpdateError("Too many redirects while checking for updates.")


def _fetch_capped(url: str, loopback: bool, max_bytes: int) -> bytes:
    response = _safe_get(url, loopback=loopback)
    try:
        if response.status_code != 200:
            raise UpdateError(f"The update server returned HTTP {response.status_code}.")
        total = 0
        chunks = []
        for chunk in response.iter_content(chunk_size=_CHUNK):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise UpdateError("The downloaded file was larger than expected; nothing was staged.")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        response.close()


def _fetch_to_file(url: str, loopback: bool, dest: Path, max_bytes: int) -> tuple[int, str]:
    response = _safe_get(url, loopback=loopback)
    digest = hashlib.sha256()
    total = 0
    try:
        if response.status_code != 200:
            raise UpdateError(f"The update server returned HTTP {response.status_code}.")
        with open(dest, "wb") as handle:
            for chunk in response.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise UpdateError(
                        "The update download exceeded the size limit; nothing was staged."
                    )
                digest.update(chunk)
                handle.write(chunk)
    finally:
        response.close()
    return total, digest.hexdigest()


def fetch_latest_release() -> dict:
    """GET the pinned (or loopback-override) feed and return its parsed JSON.

    Raises UpdateError with a plain-English message, or lets a
    requests.RequestException propagate (the caller decides how to phrase
    that -- status() and download_update() both catch it).
    """
    feed_url, loopback = _active_feed()
    response = _safe_get(feed_url, loopback=loopback)
    try:
        if response.status_code != 200:
            raise UpdateError(f"The update feed returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as error:
            raise UpdateError("The update feed did not return valid data.") from error
    finally:
        response.close()
    if not isinstance(data, dict):
        raise UpdateError("The update feed returned an unexpected shape.")
    return data


# --------------------------------------------------------------------------
# Staged-update marker
# --------------------------------------------------------------------------

def staged_info() -> dict | None:
    """{"version", "bytes"} for a currently-staged download, or None."""
    path = _pending_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    size = data.get("bytes")
    if not version or not isinstance(size, int):
        return None
    return {"version": version, "bytes": size}


def _payload_root(staged_dir: Path) -> Path | None:
    """Resolve the actual app root inside `staged`, at depth 0 or depth 1.

    The release ZIP wraps its payload in a single top-level folder (see
    .github/workflows/release.yml), so this mirrors
    api/scripts/apply_update.cmd's own resolution -- the Python-side staged
    check must agree with what the applier will actually find.
    """
    if (staged_dir / "Open Canvas Expert.bat").exists():
        return staged_dir
    if not staged_dir.is_dir():
        return None
    for child in sorted(staged_dir.iterdir()):
        if child.is_dir() and (child / "Open Canvas Expert.bat").exists():
            return child
    return None


def is_staged() -> bool:
    return _payload_root(_staged_dir()) is not None


# --------------------------------------------------------------------------
# Status (GET /api/update/status)
# --------------------------------------------------------------------------

def status() -> dict:
    """Never raises. Unreachable host, timeout, rate limit, and malformed
    JSON all come back as {"ok": False, "error": "<plain sentence>"}."""
    result = {
        "ok": True,
        "current": __version__,
        "latest": None,
        "available": False,
        "published_at": None,
        "notes_url": None,
        "staged": staged_info(),
        "error": None,
    }
    try:
        data = fetch_latest_release()
    except UpdateError as error:
        return {**result, "ok": False, "error": str(error)}
    except Exception:
        return {**result, "ok": False, "error": "Could not check for updates right now."}

    tag = str(data.get("tag_name") or "").strip()
    current_key = _version_key(__version__)
    latest_key = _version_key(tag)
    if current_key is None or latest_key is None:
        result["latest"] = _display_version(tag) or None
        result["ok"] = False
        result["error"] = "Could not compare versions."
        return result

    result.update({
        "latest": _display_version(tag) or None,
        "available": latest_key > current_key,
        "published_at": data.get("published_at"),
        "notes_url": data.get("html_url"),
    })
    return result


# --------------------------------------------------------------------------
# Extraction safety (D5) -- entries are walked and validated by hand before
# anything is written; the first bad entry rejects the whole archive.
# --------------------------------------------------------------------------

def _safe_relative_path(name: str) -> Path | None:
    if not name:
        return None
    candidate = name.replace("\\", "/")
    if candidate.startswith("/"):
        return None
    if _DRIVE_LETTER_RE.match(candidate):
        return None
    parts = [p for p in candidate.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return Path(*parts)


def _entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return bool(mode) and stat.S_ISLNK(mode)


def _extract_safely(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        planned = []
        for info in archive.infolist():
            if _entry_is_symlink(info):
                raise UpdateError(
                    "The update package contained a symlink; nothing was staged."
                )
            relative = _safe_relative_path(info.filename)
            if relative is None:
                raise UpdateError(
                    "The update package contained an unsafe file path; nothing was staged."
                )
            planned.append((info, relative))
        for info, relative in planned:
            target = dest_dir / relative
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as dest:
                shutil.copyfileobj(source, dest)


def _parse_sha256sums(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SUMS_LINE_RE.match(line)
        if not match:
            continue
        out[match.group(2)] = match.group(1).lower()
    return out


# --------------------------------------------------------------------------
# Download + verify + stage (POST /api/update/download)
# --------------------------------------------------------------------------

def _download_update_inner() -> dict:
    data = fetch_latest_release()
    tag = str(data.get("tag_name") or "").strip()
    if _version_key(tag) is None:
        raise UpdateError("The release version could not be understood; nothing was staged.")
    latest_display = _display_version(tag)

    assets = data.get("assets")
    assets = assets if isinstance(assets, list) else []
    zip_asset = next(
        (a for a in assets if isinstance(a, dict) and str(a.get("name", "")).lower().endswith(".zip")),
        None,
    )
    sums_asset = next(
        (a for a in assets if isinstance(a, dict) and str(a.get("name", "")) == "SHA256SUMS.txt"),
        None,
    )
    if not zip_asset or not sums_asset:
        raise UpdateError(
            "This release is missing an update package or its checksum file; nothing was staged."
        )
    zip_url = str(zip_asset.get("browser_download_url") or "")
    sums_url = str(sums_asset.get("browser_download_url") or "")
    zip_name = str(zip_asset.get("name") or "")
    if not zip_url or not sums_url or not zip_name:
        raise UpdateError("This release's download links were missing; nothing was staged.")

    _, loopback = _active_feed()

    sums_text = _fetch_capped(sums_url, loopback, _MAX_SUMS_BYTES).decode("utf-8", errors="replace")
    expected = _parse_sha256sums(sums_text)
    if zip_name not in expected:
        raise UpdateError(
            "This release's checksum file did not list the update package; nothing was staged."
        )

    update_root = _update_root()
    update_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="download-", dir=str(update_root)))
    try:
        zip_path = work_dir / zip_name
        size, digest = _fetch_to_file(zip_url, loopback, zip_path, _MAX_DOWNLOAD_BYTES)
        if digest.lower() != expected[zip_name]:
            raise UpdateError(
                "The downloaded file did not match its expected checksum; nothing was staged."
            )

        extract_dir = Path(tempfile.mkdtemp(prefix="staged-", dir=str(update_root)))
        try:
            _extract_safely(zip_path, extract_dir)
        except Exception:
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise

        staged_dir = _staged_dir()
        if staged_dir.exists():
            shutil.rmtree(staged_dir)
        os.replace(str(extract_dir), str(staged_dir))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    _pending_path().write_text(
        json.dumps({
            "version": latest_display,
            "bytes": size,
            "asset_name": zip_name,
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "version": latest_display, "bytes": size}


def download_update() -> dict:
    """Never raises. Returns {"ok": True, "version", "bytes"} or
    {"ok": False, "error"}."""
    try:
        return _download_update_inner()
    except UpdateError as error:
        return {"ok": False, "error": str(error)}
    except requests.RequestException:
        return {"ok": False, "error": "Could not reach the update server. Check your internet connection."}
    except Exception:
        return {"ok": False, "error": "The update could not be downloaded."}


def cancel_staged() -> dict:
    staged_dir = _staged_dir()
    if staged_dir.exists():
        shutil.rmtree(staged_dir, ignore_errors=True)
    pending = _pending_path()
    if pending.exists():
        try:
            pending.unlink()
        except OSError:
            pass
    return {"ok": True}
