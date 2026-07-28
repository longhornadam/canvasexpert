"""Offline pagination receipts for the private-mirror assignment seam."""
from __future__ import annotations

from api.webui import canvas_client


class FakeResponse:
    def __init__(self, payload, *, status_code=200, link="", text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"Link": link}
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _client_with(monkeypatch, responses):
    calls = []
    queue = iter(responses)
    monkeypatch.setattr(canvas_client, "_canvas_headers",
                        lambda: ({"Authorization": "Bearer test"}, "https://canvas.test"))

    def get(url, *, headers, params, timeout):
        calls.append((url, params, timeout))
        return next(queue)

    monkeypatch.setattr(canvas_client.requests, "get", get)
    return calls


def test_complete_collection_accepts_an_empty_single_page(monkeypatch):
    calls = _client_with(monkeypatch, [FakeResponse([])])

    assert canvas_client._canvas_get_all_complete("/api/v1/courses/111/assignments",
                                                   {"per_page": 100}) == ([], None, True)
    assert calls == [("https://canvas.test/api/v1/courses/111/assignments",
                      {"per_page": 100}, 30)]


def test_complete_collection_follows_opaque_next_pages_without_reusing_params(monkeypatch):
    next_url = "https://canvas.test/api/v1/courses/111/assignments?opaque=two"
    calls = _client_with(monkeypatch, [
        FakeResponse([{"id": 1}], link=f'<{next_url}>; rel="next"'),
        FakeResponse([{"id": 2}]),
    ])

    rows, error, complete = canvas_client._canvas_get_all_complete(
        "/api/v1/courses/111/assignments", {"per_page": 100})

    assert rows == [{"id": 1}, {"id": 2}]
    assert error is None and complete is True
    assert calls == [
        ("https://canvas.test/api/v1/courses/111/assignments", {"per_page": 100}, 30),
        (next_url, None, 30),
    ]


def test_complete_collection_rejects_a_later_page_failure_without_raw_body(monkeypatch):
    next_url = "https://canvas.test/api/v1/courses/111/assignments?opaque=two"
    _client_with(monkeypatch, [
        FakeResponse([{"id": 1}], link=f'<{next_url}>; rel="next"'),
        FakeResponse([], status_code=503, text="private response body https://secret.example"),
    ])

    rows, error, complete = canvas_client._canvas_get_all_complete(
        "/api/v1/courses/111/assignments", {"per_page": 100})

    assert rows is None and error == "HTTP 503" and complete is False
    assert "private" not in error and "https://" not in error


def test_complete_collection_rejects_non_list_roots(monkeypatch):
    _client_with(monkeypatch, [FakeResponse({"id": 1})])

    assert canvas_client._canvas_get_all_complete("/api/v1/courses/111/assignments") == (
        None, "invalid_response", False)


def test_complete_collection_rejects_a_repeated_next_link(monkeypatch):
    next_url = "https://canvas.test/api/v1/courses/111/assignments?opaque=two"
    calls = _client_with(monkeypatch, [
        FakeResponse([{"id": 1}], link=f'<{next_url}>; rel="next"'),
        FakeResponse([{"id": 2}], link=f'<{next_url}>; rel="next"'),
    ])

    assert canvas_client._canvas_get_all_complete("/api/v1/courses/111/assignments") == (
        None, "pagination_incomplete", False)
    assert [url for url, _params, _timeout in calls] == [
        "https://canvas.test/api/v1/courses/111/assignments", next_url]


def test_legacy_collection_client_keeps_its_two_value_contract(monkeypatch):
    next_url = "https://canvas.test/api/v1/courses/111/assignments?opaque=two"
    _client_with(monkeypatch, [
        FakeResponse([{"id": 1}], link=f'<{next_url}>; rel="next"'),
        FakeResponse([{"id": 2}]),
    ])

    result = canvas_client._canvas_get_all("/api/v1/courses/111/assignments",
                                            {"per_page": 100})
    assert result == ([{"id": 1}, {"id": 2}], None)


def test_get_retries_only_429_with_capped_numeric_retry_after(monkeypatch):
    throttled = FakeResponse([], status_code=429)
    throttled.headers["Retry-After"] = "99"
    _client_with(monkeypatch, [throttled, FakeResponse({"id": 1})])
    sleeps = []
    monkeypatch.setattr(canvas_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    # The synthetic first response asks for a long pause; it is capped.
    assert canvas_client._canvas_get("/api/v1/courses/111") == ({"id": 1}, None)
    assert sleeps == [30.0]


def test_get_telemetry_keeps_scope_priority_and_actual_queue_wait_identifier_free(monkeypatch):
    _client_with(monkeypatch, [FakeResponse({"id": 1})])
    records = []
    monkeypatch.setattr(canvas_client.operational_log, "emit", lambda *args, **kwargs: records.append(kwargs))
    with canvas_client.canvas_get_telemetry("course.refresh", "post_write", queue_wait_ms=17):
        assert canvas_client._canvas_get("/api/v1/courses/111") == ({"id": 1}, None)
    record = records[-1]
    assert record["scope"] == "course.refresh"
    assert record["priority"] == "post_write"
    assert record["queue_wait_ms"] >= 17
    assert "url" not in record and "course_id" not in record


# --- streamed file download -------------------------------------------------
#
# The writing record reads an uploaded Word document through this seam rather
# than through a session of its own, so that a class-wide unattended loop
# inherits this layer's 429 retry and coordinator yield. These tests are what
# make that inheritance a fact rather than a claim in a docstring.

class FakeStreamResponse:
    def __init__(self, chunks, *, status_code=200):
        self._chunks = chunks
        self.status_code = status_code
        self.headers = {}
        self.text = ""
        self.closed = False
        self.consumed = False

    @property
    def content(self):  # pragma: no cover - reaching this is the bug
        raise AssertionError("a streamed body must not be read by the client")

    def iter_content(self, chunk_size=16_384):
        self.consumed = True
        yield from self._chunks

    def close(self):
        self.closed = True


def _stream_client_with(monkeypatch, responses, *, token=True):
    calls = []
    queue = iter(responses)
    monkeypatch.setattr(canvas_client, "_canvas_headers", lambda: (
        ({"Authorization": "Bearer test"}, "https://canvas.test") if token
        else (None, None)))

    def get(url, *, headers, params, timeout, **kwargs):
        calls.append({"url": url, "timeout": timeout, "headers": headers, **kwargs})
        return next(queue)

    monkeypatch.setattr(canvas_client.requests, "get", get)
    return calls


def test_stream_get_asks_for_a_stream_and_hands_the_body_over_unread(monkeypatch):
    response = FakeStreamResponse([b"PK\x03\x04", b"rest"])
    calls = _stream_client_with(monkeypatch, [response])

    got, error = canvas_client.canvas_stream_get("https://files.canvas.test/1/download")

    assert (got, error) == (response, None)
    assert calls[0]["stream"] is True
    assert calls[0]["headers"] == {"Authorization": "Bearer test"}
    assert calls[0]["timeout"] == 120
    # Unread: byte accounting and closing belong to the bounded reader.
    assert response.consumed is False
    assert response.closed is False


def test_stream_get_closes_a_failed_response_instead_of_returning_it(monkeypatch):
    response = FakeStreamResponse([], status_code=404)
    _stream_client_with(monkeypatch, [response])

    got, error = canvas_client.canvas_stream_get("https://files.canvas.test/1/download")

    assert got is None
    assert error == "HTTP 404"
    assert response.closed is True


def test_stream_get_shares_the_429_retry_discipline(monkeypatch):
    throttled = FakeStreamResponse([], status_code=429)
    throttled.headers["Retry-After"] = "2"
    ok = FakeStreamResponse([b"bytes"])
    _stream_client_with(monkeypatch, [throttled, ok])
    sleeps = []
    monkeypatch.setattr(canvas_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    got, error = canvas_client.canvas_stream_get("https://files.canvas.test/1/download")

    assert (got, error) == (ok, None)
    assert sleeps == [2.0]


def test_stream_get_refuses_without_a_token_and_never_calls_out(monkeypatch):
    calls = _stream_client_with(monkeypatch, [], token=False)

    got, error = canvas_client.canvas_stream_get("https://files.canvas.test/1/download")

    assert got is None
    assert "No Canvas token" in error
    assert calls == []


def test_stream_get_does_not_count_an_unread_body_in_telemetry(monkeypatch):
    _stream_client_with(monkeypatch, [FakeStreamResponse([b"12345"])])
    with canvas_client.canvas_get_telemetry("dailywriting.ingest", "manual") as telemetry:
        canvas_client.canvas_stream_get("https://files.canvas.test/1/download")
    assert telemetry.physical_count == 1
    assert telemetry.byte_count == 0
