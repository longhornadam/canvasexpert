from __future__ import annotations

from pathlib import Path

from api.operation_ledger.adapters import assignment as assignment_adapter


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
    monkeypatch.setattr(assignment_adapter, "_allowed_printable_roots", lambda: [str(allowed)])

    missing, err = assignment_adapter._validate_printable_pdf(str(allowed / "missing.pdf"))
    assert missing is None
    assert err == "printable PDF not found"

    text_file = allowed / "notes.txt"
    text_file.write_text("not a pdf", encoding="utf-8")
    bad_ext, err = assignment_adapter._validate_printable_pdf(str(text_file))
    assert bad_ext is None
    assert err == "printable attachment must be a PDF"

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF")
    disallowed, err = assignment_adapter._validate_printable_pdf(str(outside))
    assert disallowed is None
    assert err == "printable PDF is outside Canvas Expert export folders"


def test_upload_course_file_uploads_file_and_returns_file_json(monkeypatch, tmp_path):
    pdf = tmp_path / "Water_Cycle_Notes_Core.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(assignment_adapter, "_allowed_printable_roots", lambda: [str(tmp_path)])

    calls = {"send": [], "upload": []}

    def fake_canvas_send(method, path, payload, timeout=30):
        calls["send"].append((method, path, payload))
        assert method == "POST"
        assert path == "/api/v1/courses/42/files"
        return {
            "upload_url": "https://upload.invalid",
            "upload_params": {"key": "abc"},
        }, None

    def fake_upload(url, data, files, timeout=60):
        calls["upload"].append((url, data, files["file"][0]))
        return FakeResponse(payload={
            "id": 55,
            "display_name": "Water_Cycle_Notes_Core.pdf",
            "url": "https://canvas.invalid/files/55/download",
        })

    monkeypatch.setattr(assignment_adapter.canvas_client, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(assignment_adapter.requests, "post", fake_upload)

    result, err = assignment_adapter._upload_course_file("42", pdf)

    assert err is None
    assert result["id"] == 55
    assert calls["send"] == [(
        "POST",
        "/api/v1/courses/42/files",
        {
            "name": pdf.name,
            "size": pdf.stat().st_size,
            "content_type": "application/pdf",
            "parent_folder_path": "Canvas Expert Printables",
            "on_duplicate": "rename",
        },
    )]
    assert calls["upload"] == [("https://upload.invalid", {"key": "abc"}, pdf.name)]


def test_upload_course_file_fails_when_canvas_upload_fails(monkeypatch, tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(assignment_adapter, "_allowed_printable_roots", lambda: [str(tmp_path)])

    def fake_canvas_send(method, path, payload, timeout=30):
        assert method == "POST"
        assert path == "/api/v1/courses/42/files"
        return {
            "upload_url": "https://upload.invalid",
            "upload_params": {},
        }, None

    def failed_upload(url, data, files, timeout=60):
        return FakeResponse(status_code=500, text="upload failed")

    monkeypatch.setattr(assignment_adapter.canvas_client, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(assignment_adapter.requests, "post", failed_upload)

    result, err = assignment_adapter._upload_course_file("42", pdf)

    assert result is None
    assert "Canvas file upload failed: HTTP 500" in err
