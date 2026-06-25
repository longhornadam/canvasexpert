from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.webui.server import app
import api.webui.routes.push as push_routes


client = TestClient(app)

SAMPLE_NOTE = """<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "guided_notes",
  "title": "Water Cycle Notes",
  "topic": "How water moves through Earth systems",
  "mode": "blank",
  "body": [
    { "type": "paragraph", "text": "Water vapor cools during {{condensation}}." },
    { "type": "paragraph", "text": "Water falls as {{precipitation}}." }
  ]
}
</NOTEFORGE_JSON>"""


def _mock_emitters(monkeypatch):
    import engine.rendering.physical.emit_docx as emit_docx
    import engine.rendering.physical.emit_pdf as emit_pdf

    def fake_docx(html: str, reference_docx: str, out_path: str) -> str:
        Path(out_path).write_bytes(b"docx")
        return out_path

    def fake_pdf(html: str, css_path: str, out_path: str) -> str:
        Path(out_path).write_bytes(b"%PDF")
        return out_path

    monkeypatch.setattr(emit_docx, "html_to_docx", fake_docx)
    monkeypatch.setattr(emit_pdf, "html_to_pdf", fake_pdf)


def test_nf_validate_summarizes_note(tmp_path):
    note_path = tmp_path / "note.txt"
    note_path.write_text(SAMPLE_NOTE, encoding="utf-8")

    response = client.post("/api/nf/validate", data={"path": str(note_path)})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["summary"] == {
        "type": "guided_notes",
        "title": "Water Cycle Notes",
        "mode": "blank",
        "slot_count": 2,
    }


def test_physical_note_route_generates_artifacts(monkeypatch, tmp_path):
    _mock_emitters(monkeypatch)
    note_path = tmp_path / "note.txt"
    note_path.write_text(SAMPLE_NOTE, encoding="utf-8")
    export_root = tmp_path / "exports"
    monkeypatch.setattr(push_routes, "_exports_dir", lambda: str(export_root))
    monkeypatch.setattr(push_routes, "_workspace_folder", lambda name: str(export_root) if name == "Exports" else None)

    response = client.post("/api/physical/note", data={"path": str(note_path)})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["fallback"] is False
    assert data["title"] == "Water Cycle Notes"
    assert data["primary_pdf"].endswith("Water_Cycle_Notes_Core.pdf")
    assert set(data["artifacts"]) == {"Support", "Core", "Accelerate", "Extend", "KEY"}
    assert "Water_Cycle_Notes_Core.pdf" in data["files"]
    assert Path(data["artifacts"]["Core"]["docx_path"]).exists()
    assert Path(data["artifacts"]["Core"]["pdf_path"]).exists()
