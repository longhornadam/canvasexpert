"""Focused tests for `api/submission_transport.py::fetch_submission`.

`fetch_submission` is a single, focused Canvas call for exactly one student's
one submission — it must never raise, degrading to `None` on any transport or
HTTP failure so a missing/failed focused fetch drops one work sample instead of
aborting the whole Student Report.
"""
from __future__ import annotations

import requests

from api import submission_transport


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        if self._exc is not None:
            raise self._exc
        return self._response


def test_fetch_submission_hits_the_single_submission_endpoint_and_returns_json():
    payload = {"id": "1", "attachments": [{"filename": "essay.docx"}]}
    session = _FakeSession(response=_FakeResponse(200, payload))
    result = submission_transport.fetch_submission(
        session, "https://canvas.test", "111", "700010", "900001")
    assert result == payload
    [(url, timeout)] = session.calls
    assert url == (
        "https://canvas.test/api/v1/courses/111/assignments/700010/submissions/900001"
    )
    assert timeout == 30


def test_fetch_submission_returns_none_on_http_error_not_a_raise():
    session = _FakeSession(response=_FakeResponse(404))
    result = submission_transport.fetch_submission(
        session, "https://canvas.test", "111", "700010", "900001")
    assert result is None


def test_fetch_submission_returns_none_on_transport_exception_not_a_raise():
    session = _FakeSession(exc=requests.ConnectionError("boom"))
    result = submission_transport.fetch_submission(
        session, "https://canvas.test", "111", "700010", "900001")
    assert result is None


def test_fetch_submission_returns_none_on_unexpected_exception_not_a_raise():
    session = _FakeSession(exc=ValueError("malformed json"))
    result = submission_transport.fetch_submission(
        session, "https://canvas.test", "111", "700010", "900001")
    assert result is None
