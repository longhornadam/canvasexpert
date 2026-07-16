"""Canvas submission fetching and authenticated ordinary-upload ingestion.

New Quiz signed storage has a separate transport in ``new_quiz_fetch``.  This
module owns only Canvas-authenticated ordinary assignment downloads and hands
completed local originals to the shared attachment router.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from api.webui import config, workspace
from api.webui.canvas_client import _canvas_get, _canvas_get_all, _canvas_headers
from api.powergrader import student_attachments


REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
CANVAS_AUTH_HEADERS = {
    "authorization", "cookie", "proxy-authorization", "x-csrf-token", "x-api-key",
}


def fetch_submissions(course_id: str, assignment_id: str, *, session_id: str | None = None,
                      new_quiz_files=True, byte_budget=None, evidence_path=None, reusable_records=None):
    """Fetch submissions for one assignment. Returns ``(subs, assignment, error)``."""
    subs, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": ["all"], "assignment_ids[]": [assignment_id],
         "include[]": ["assignment", "user"], "per_page": 100},
    )
    if err:
        return None, None, err
    adata, assignment_err = _canvas_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    if assignment_err:
        return None, None, assignment_err
    adata = adata or {}
    if adata.get("is_quiz_lti_assignment") is True:
        from api.powergrader import new_quiz_fetch
        if evidence_path == "managed":
            def evidence_path(target, value, filename, attempt):
                user = target.get("user") or {}
                evidence_id = value.get("id") or value.get("file_id") or value.get("uuid")
                return workspace.managed_evidence_path(
                    config.course_display_name(course_id) or course_id, course_id,
                    assignment_id, assignment_id,
                    user.get("sortable_name") or user.get("name") or target.get("user_id"), target.get("user_id"),
                    attempt, evidence_id, filename,
                )
        normalized, nq_err = new_quiz_fetch.fetch(
            course_id,
            assignment_id,
            subs or [],
            session_id=session_id,
            course_name=config.course_display_name(course_id),
            assignment_name=adata.get("name") or assignment_id,
            materialize_files=new_quiz_files,
            byte_budget=byte_budget,
            evidence_path=evidence_path,
            reusable_records=reusable_records,
        )
        return normalized, adata, nq_err
    if adata.get("quiz_id") or "online_quiz" in (adata.get("submission_types") or []):
        return None, adata, "Classic Quizzes are not supported in PowerGrader."
    return subs, adata, None


def _filename(attachment: dict) -> str:
    return os.path.basename(str(
        attachment.get("filename") or attachment.get("display_name") or attachment.get("name") or "attachment"
    )) or "attachment"


def _attempt(submission: dict) -> int | float:
    value = submission.get("attempt")
    if value is None:
        value = submission.get("submission_attempt")
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return number if number > 0 else 1


def _generic_failure(code: str, message: str, *, filename: str, attempt, item_id="") -> dict:
    return {
        "filename": filename,
        "declared_size": None,
        "actual_size": None,
        "attempt": attempt,
        "item_id": str(item_id or ""),
        "item_link": str(item_id or ""),
        "download_status": "failed",
        "extraction_status": "failed",
        "ai_eligible": False,
        "local_only": False,
        "warnings": [],
        "error_code": code,
        "error_message": message,
    }


def _host_key(url: str):
    parsed = urlparse(str(url or ""))
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return hostname, port


def _off_host_request_headers(client) -> dict:
    """Remove credential-bearing session defaults from an off-host request."""
    defaults = getattr(client, "headers", {}) or {}
    return {
        str(name): None
        for name in defaults
        if str(name).lower() in CANVAS_AUTH_HEADERS
    }


def _close_response(response):
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _download_canvas_attachment(url: str, dest: str, *, declared_size=None,
                               http_session=None, canvas_base: str = "") -> dict:
    """Stream one Canvas attachment to an atomic final path.

    The first request and same-host redirects retain Canvas credentials.  An
    HTTPS redirect to another host is allowed for Canvas CDN-style downloads,
    but credentials are explicitly removed and never reattached afterward.
    """
    raw_url = str(url or "")
    parsed = urlparse(raw_url)
    base = str(canvas_base or "").rstrip("/")
    if not parsed.scheme:
        raw_url = urljoin(base + "/", raw_url.lstrip("/"))
        parsed = urlparse(raw_url)
    base_key = _host_key(base)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or _host_key(raw_url) != base_key:
        raise ValueError("ordinary attachment URL was not on the configured Canvas host")
    try:
        expected = int(declared_size) if declared_size not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("attachment size metadata was malformed") from exc
    if expected is not None and expected < 0:
        raise ValueError("attachment size metadata was negative")
    parent = os.path.dirname(os.path.abspath(dest))
    os.makedirs(parent, exist_ok=True)
    free_space = shutil.disk_usage(parent).free
    if expected is not None and expected > free_space:
        raise OSError("insufficient local storage")
    partial = dest + ".partial"
    client = http_session or requests.Session()
    try:
        if os.path.exists(partial):
            os.unlink(partial)
        current_url = raw_url
        on_canvas_host = True
        for redirect_count in range(MAX_REDIRECTS + 1):
            request_kwargs = {
                "stream": True,
                "allow_redirects": False,
                "timeout": DOWNLOAD_TIMEOUT,
            }
            if not on_canvas_host:
                request_kwargs["headers"] = _off_host_request_headers(client)
            response = client.get(current_url, **request_kwargs)
            status = int(getattr(response, "status_code", 0) or 0)
            if status in REDIRECT_STATUSES:
                try:
                    if redirect_count >= MAX_REDIRECTS:
                        raise ValueError("Canvas attachment redirect limit was exceeded")
                    response_headers = getattr(response, "headers", {}) or {}
                    location = response_headers.get("Location") or response_headers.get("location")
                    if not location:
                        raise ValueError("Canvas attachment redirect had no location")
                    next_url = urljoin(current_url, str(location))
                    next_parsed = urlparse(next_url)
                    next_scheme = next_parsed.scheme.lower()
                    next_key = _host_key(next_url)
                    if next_scheme not in {"http", "https"} or not next_key:
                        raise ValueError("Canvas attachment redirect target was invalid")
                    if next_key == base_key:
                        # Once a redirect leaves Canvas, never reattach Canvas
                        # credentials even if the chain points back.
                        next_on_canvas_host = on_canvas_host
                    else:
                        if next_scheme != "https":
                            raise ValueError("off-host Canvas attachment redirects must use HTTPS")
                        next_on_canvas_host = False
                    current_url = next_url
                    on_canvas_host = next_on_canvas_host
                finally:
                    _close_response(response)
                continue
            if status < 200 or status >= 300:
                _close_response(response)
                raise ValueError("Canvas attachment download returned an HTTP error")
            final_url = str(getattr(response, "url", "") or current_url)
            final_parsed = urlparse(final_url)
            final_key = _host_key(final_url)
            if not final_key:
                _close_response(response)
                raise ValueError("Canvas attachment response URL was invalid")
            if final_key != base_key and (final_parsed.scheme.lower() != "https" or on_canvas_host):
                _close_response(response)
                raise ValueError("off-host Canvas attachment responses must use HTTPS without Canvas credentials")
            actual = 0
            try:
                with open(partial, "wb") as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        actual += len(chunk)
                        if actual > free_space:
                            raise OSError("insufficient local storage")
                        output.write(chunk)
                if expected is not None and actual != expected:
                    raise ValueError("download size did not match Canvas metadata")
                os.replace(partial, dest)
                return {"actual_size": actual, "declared_size": expected}
            finally:
                _close_response(response)
        raise ValueError("Canvas attachment redirect processing failed")
    finally:
        try:
            if os.path.exists(partial):
                os.unlink(partial)
        except OSError:
            pass


def _target_path(*, course_name: str, course_id: str, assignment_name: str,
                 assignment_id: str, submission: dict, filename: str):
    user = submission.get("user") or {}
    student_name = user.get("sortable_name") or user.get("name") or submission.get("user_id") or "student"
    attempt = _attempt(submission)
    attempt_dir = workspace.attempt_folder(
        course_name or course_id,
        course_id,
        assignment_name or assignment_id,
        assignment_id,
        student_name,
        submission.get("user_id"),
        attempt,
    )
    if not attempt_dir:
        return None, attempt
    os.makedirs(attempt_dir, exist_ok=True)
    safe_name = workspace.safe_component(filename, 150)
    stem, ext = os.path.splitext(safe_name)
    dest = os.path.join(attempt_dir, safe_name)
    number = 2
    while os.path.exists(dest) or os.path.exists(dest + ".partial"):
        dest = os.path.join(attempt_dir, f"{stem} ({number}){ext}")
        number += 1
    return dest, attempt


def ingest_ordinary_attachments(
    submissions: list[dict],
    *,
    course_name: str,
    course_id: str,
    assignment_name: str,
    assignment_id: str,
    http_session=None,
    download=None,
    byte_budget=None,
    target_path=None,
    reusable_records=None,
    require_identity=False,
) -> list[dict]:
    """Preserve and route every ordinary Canvas upload exactly once per input.

    The returned submission objects contain only local evidence metadata.  The
    source URL is used for transport and is intentionally never copied into the
    returned records.
    """
    headers, canvas_base = _canvas_headers()
    client = http_session or requests.Session()
    if headers:
        client.headers.update(headers)
    downloader = download or _download_canvas_attachment
    for submission in submissions or []:
        source_attachments = list(submission.get("attachments") or [])
        submission["expected_attachment_count"] = len(source_attachments)
        records: list[dict] = []
        for source in source_attachments:
            if not isinstance(source, dict):
                records.append(_generic_failure(
                    "attachment_malformed", "The upload metadata was malformed.",
                    filename="attachment", attempt=_attempt(submission),
                ))
                continue
            filename = _filename(source)
            declared_size = source.get("size")
            item_id = source.get("item_id") or source.get("id") or ""
            meta = {
                "filename": filename,
                "declared_size": declared_size,
                "actual_size": None,
                "attempt": _attempt(submission),
                "item_id": str(item_id),
                "item_link": str(item_id),
                "download_status": "failed",
                "extraction_status": "not_attempted",
                "ai_eligible": False,
                "local_only": False,
                "warnings": [],
                "content_indicator": {key: source.get(key) for key in ("size", "updated_at", "modified_at", "created_at", "uuid", "md5") if source.get(key) not in (None, "")},
            }
            if not headers or not canvas_base:
                meta.update({
                    "extraction_status": "failed",
                    "error_code": "canvas_auth_unavailable",
                    "error_message": "The Canvas download could not be authenticated.",
                })
                records.append(meta)
                continue
            url = source.get("url")
            dest, attempt = (target_path(submission, source, filename, _attempt(submission))
                            if target_path else _target_path(
                course_name=course_name,
                course_id=course_id,
                assignment_name=assignment_name,
                assignment_id=assignment_id,
                submission=submission,
                filename=filename,
            ))
            meta["attempt"] = attempt
            evidence_id = source.get("id") or source.get("file_id") or source.get("attachment_id")
            if require_identity and not evidence_id:
                meta.update({"extraction_status": "failed", "error_code": "missing_evidence_identity",
                             "error_message": "Canvas did not provide a stable identity for this upload."})
                records.append(meta)
                continue
            reuse = (reusable_records or {}).get(str(evidence_id))
            if (reuse and reuse.get("content_indicator") == meta["content_indicator"]
                    and reuse.get("local_path") and os.path.isfile(reuse["local_path"])):
                meta.update({key: value for key, value in reuse.items() if key not in {"url", "headers", "signed_url"}})
                meta["download_status"] = "reused"
                records.append(meta)
                continue
            if not dest:
                meta.update({
                    "extraction_status": "failed",
                    "error_code": "destination_unavailable",
                    "error_message": "The local workspace destination was unavailable.",
                })
                records.append(meta)
                continue
            if not url:
                meta.update({
                    "extraction_status": "failed",
                    "error_code": "missing_attachment_url",
                    "error_message": "Canvas did not provide an attachment download location.",
                })
                records.append(meta)
                continue
            try:
                declared = int(declared_size)
            except (TypeError, ValueError):
                declared = None
            if declared is None or declared < 0:
                meta.update({"extraction_status": "failed", "error_code": "size_unavailable",
                             "error_message": "Canvas did not provide a usable file size; review it in Canvas."})
                records.append(meta)
                continue
            if byte_budget is not None and not byte_budget.reserve(declared):
                meta.update({"extraction_status": "failed", "error_code": "refresh_budget_exceeded",
                             "error_message": "This upload exceeds the focused refresh limit; review it in Canvas."})
                records.append(meta)
                continue
            try:
                result = downloader(
                    url,
                    dest,
                    declared_size=declared_size,
                    http_session=client,
                    canvas_base=canvas_base,
                ) or {}
                meta.update({k: v for k, v in result.items() if k not in {"url", "headers", "signed_url"}})
                meta["local_path"] = dest
                meta["download_status"] = "downloaded"
                routed = student_attachments.ingest_local_file(
                    dest,
                    attempt_dir=os.path.dirname(dest),
                    original_filename=filename,
                    declared_size=declared_size,
                    attempt=attempt,
                    item_id=item_id,
                )
                for key in (
                    "detected_media_type", "actual_size", "extraction_status",
                    "extracted_text_path", "ai_eligible", "local_only", "warnings",
                ):
                    if key in routed:
                        meta[key] = routed[key]
                meta["local_path"] = dest
            except requests.RequestException:
                meta.update({
                    "extraction_status": "failed",
                    "error_code": "download_network",
                    "error_message": "The upload could not be downloaded from Canvas.",
                })
            except Exception as exc:
                meta.update({
                    "extraction_status": "failed",
                    "error_code": getattr(exc, "code", "download_failed"),
                    "error_message": "The upload could not be preserved or validated locally.",
                })
            records.append(meta)
        submission["attachments"] = records
        # New sessions must never depend on the retired extension-only lane.
        submission.pop("code_files", None)
    return submissions


def enrich_with_code_files(subs):
    """Deprecated compatibility reader for old callers and old sessions.

    Production PowerGrader start, late catch-up, and scheduled autoscore flows
    use ``ingest_ordinary_attachments`` instead and do not populate ``code_files``.
    """
    hdrs, _ = _canvas_headers()
    if not hdrs:
        return
    sess = requests.Session()
    sess.headers.update(hdrs)
    for submission in subs or []:
        files = []
        for attachment in (submission.get("attachments") or []):
            path = attachment.get("local_path")
            if not path or not os.path.isfile(path):
                continue
            try:
                text = Path(path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            files.append({"filename": attachment.get("filename", ""), "text": text})
        if files:
            submission["code_files"] = files
