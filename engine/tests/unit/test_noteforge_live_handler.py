from __future__ import annotations

from pathlib import Path

from engine.packagers.note_handler import generate_note_outputs


SAMPLE_NOTE = {
    "version": "1.0-json",
    "type": "guided_notes",
    "title": "Water Cycle Notes",
    "topic": "How water moves through Earth systems",
    "mode": "blank",
    "body": [
        {"type": "heading", "text": "Main Processes"},
        {
            "type": "paragraph",
            "text": "Water changes from liquid to gas during {{evaporation}}.",
        },
        {
            "type": "bullets",
            "items": [
                "Water falling from clouds is {{precipitation}}.",
                "Water soaking into soil is {{infiltration}}.",
            ],
        },
    ],
}


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


def test_generate_note_outputs_emits_tiers_and_key(monkeypatch, tmp_path):
    _mock_emitters(monkeypatch)

    results = generate_note_outputs(SAMPLE_NOTE, str(tmp_path))

    assert set(results) == {"artifacts", "log_path"}
    assert set(results["artifacts"]) == {"Support", "Core", "Accelerate", "Extend", "KEY"}
    for label, artifact in results["artifacts"].items():
        assert artifact["docx_path"].endswith(f"Water_Cycle_Notes_{label}.docx")
        assert artifact["pdf_path"].endswith(f"Water_Cycle_Notes_{label}.pdf")
        assert Path(artifact["docx_path"]).exists()
        assert Path(artifact["pdf_path"]).exists()
    assert Path(results["log_path"]).exists()


def test_generate_note_outputs_logs_converter_warnings(monkeypatch, tmp_path):
    import engine.rendering.physical.emit_docx as emit_docx
    import engine.rendering.physical.emit_pdf as emit_pdf

    def missing_docx(html: str, reference_docx: str, out_path: str) -> str:
        raise RuntimeError("Pandoc unavailable")

    def missing_pdf(html: str, css_path: str, out_path: str) -> str:
        raise RuntimeError("Microsoft Edge unavailable")

    monkeypatch.setattr(emit_docx, "html_to_docx", missing_docx)
    monkeypatch.setattr(emit_pdf, "html_to_pdf", missing_pdf)

    results = generate_note_outputs(SAMPLE_NOTE, str(tmp_path))

    for artifact in results["artifacts"].values():
        assert artifact == {"docx_path": "", "pdf_path": ""}
    log_text = Path(results["log_path"]).read_text(encoding="utf-8")
    assert "PHYSICAL RENDER WARNING [note Support docx]: Pandoc unavailable" in log_text
    assert "PHYSICAL RENDER WARNING [note KEY pdf]: Microsoft Edge unavailable" in log_text


def test_generate_note_outputs_exemplar_mode_emits_exemplar_and_key(monkeypatch, tmp_path):
    _mock_emitters(monkeypatch)
    note = {**SAMPLE_NOTE, "mode": "exemplar"}

    results = generate_note_outputs(note, str(tmp_path))

    assert set(results["artifacts"]) == {"Exemplar", "KEY"}
    for label in ("Exemplar", "KEY"):
        assert Path(results["artifacts"][label]["docx_path"]).exists()
        assert Path(results["artifacts"][label]["pdf_path"]).exists()
