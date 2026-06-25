from __future__ import annotations

from pathlib import Path

import api.webui.push_service as push_service


class FakeResponse:
    def __init__(self, status_code=201, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_validate_printable_pdf_rejects_bad_paths(monkeypatch, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(push_service, "_allowed_printable_roots", lambda: [str(allowed)])

    missing, err = push_service._validate_printable_pdf(str(allowed / "missing.pdf"))
    assert missing is None
    assert err == "printable PDF not found"

    text_file = allowed / "notes.txt"
    text_file.write_text("not a pdf", encoding="utf-8")
    bad_ext, err = push_service._validate_printable_pdf(str(text_file))
    assert bad_ext is None
    assert err == "printable attachment must be a PDF"

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF")
    disallowed, err = push_service._validate_printable_pdf(str(outside))
    assert disallowed is None
    assert err == "printable PDF is outside Canvas Expert export folders"


def test_push_printable_assignment_uploads_file_and_creates_assignment(monkeypatch, tmp_path):
    pdf = tmp_path / "Water_Cycle_Notes_Core.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(push_service, "_allowed_printable_roots", lambda: [str(tmp_path)])

    calls = {"send": [], "upload": []}

    def fake_canvas_send(method, path, payload, timeout=30):
        calls["send"].append((method, path, payload))
        if path.endswith("/files"):
            return {
                "upload_url": "https://upload.invalid",
                "upload_params": {"key": "abc"},
            }, None
        if path.endswith("/assignments"):
            return {
                "id": 123,
                "name": payload["assignment"]["name"],
                "html_url": "https://canvas.invalid/courses/42/assignments/123",
            }, None
        return {}, None

    def fake_upload(url, data, files, timeout=60):
        calls["upload"].append((url, data, files["file"][0]))
        return FakeResponse(payload={
            "id": 55,
            "display_name": "Water_Cycle_Notes_Core.pdf",
            "url": "https://canvas.invalid/files/55/download",
        })

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(push_service.requests, "post", fake_upload)

    notes = []
    ok, title, url, err = push_service._push_printable_assignment(
        "42",
        {
            "pdf_path": str(pdf),
            "name": "Water Cycle Notes",
            "description": "<p>Use these in class.</p>",
            "points": 0,
        },
        notes,
    )

    assert (ok, title, url, err) == (
        True,
        "Water Cycle Notes",
        "https://canvas.invalid/courses/42/assignments/123",
        None,
    )
    assert calls["upload"] == [("https://upload.invalid", {"key": "abc"}, pdf.name)]
    assignment_payload = calls["send"][1][2]["assignment"]
    assert assignment_payload["submission_types"] == ["none"]
    assert assignment_payload["points_possible"] == 0
    assert "https://canvas.invalid/files/55/download" in assignment_payload["description"]
    assert notes == ["uploaded file 'Water_Cycle_Notes_Core.pdf'"]


def test_push_printable_assignment_stops_when_upload_fails(monkeypatch, tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(push_service, "_allowed_printable_roots", lambda: [str(tmp_path)])
    sent_paths = []

    def fake_canvas_send(method, path, payload, timeout=30):
        sent_paths.append(path)
        if path.endswith("/files"):
            return {
                "upload_url": "https://upload.invalid",
                "upload_params": {},
            }, None
        return {"id": 1}, None

    def failed_upload(url, data, files, timeout=60):
        return FakeResponse(status_code=500, text="upload failed")

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(push_service.requests, "post", failed_upload)

    ok, title, url, err = push_service._push_printable_assignment(
        "42",
        {"pdf_path": str(pdf), "name": "Notes"},
        [],
    )

    assert ok is False
    assert title == "Notes"
    assert url is None
    assert "Canvas file upload failed: HTTP 500" in err
    assert sent_paths == ["/api/v1/courses/42/files"]
