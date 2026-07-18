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
