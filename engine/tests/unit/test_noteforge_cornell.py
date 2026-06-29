from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from engine.rendering.physical.html_renderer import render_html
from engine.rendering.physical.note_adapter import parse_noteforge_json, to_printdoc
from engine.rendering.physical.note_spike import main as note_spike_main
from engine.rendering.physical.printdoc import CornellLayout, Slot
from engine.rendering.physical.redact import filled, iter_slots, redact


SAMPLE_CORNELL = """<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "cornell",
  "mode": "blank",
  "title": "Cornell: Photosynthesis",
  "topic": "How plants make food",
  "rows": [
    {
      "cue": "What is {{photosynthesis}}?",
      "note": "Plants make {{glucose}} using light energy."
    },
    {
      "cue": "Where does it happen?",
      "note": "Inside the {{chloroplast}}, using {{chlorophyll}}."
    }
  ],
  "summary": "Plants turn {{sunlight}} into food and release {{oxygen}}."
}
</NOTEFORGE_JSON>"""

TERMS = ["photosynthesis", "glucose", "chloroplast", "chlorophyll", "sunlight", "oxygen"]


def _printdoc():
    return to_printdoc(parse_noteforge_json(SAMPLE_CORNELL))


def test_cornell_adapter_builds_layout_and_stable_slot_ids():
    printdoc = _printdoc()
    layout = printdoc.blocks[0]

    assert isinstance(layout, CornellLayout)
    assert len(layout.rows) == 2
    assert layout.rows[0].cue[0] == "What is "
    assert isinstance(layout.rows[0].cue[1], Slot)
    assert layout.rows[0].cue[1].id == "bcue0s0"
    assert layout.rows[0].note[1].id == "bnote0s0"
    assert layout.rows[1].note[1].id == "bnote1s0"
    assert layout.rows[1].note[3].id == "bnote1s1"
    assert layout.summary[1].id == "bsums0"
    assert layout.summary[3].id == "bsums1"
    assert [slot.content_html for slot in iter_slots(printdoc)] == TERMS


def test_cornell_tiering_and_no_answer_leak():
    printdoc = _printdoc()
    support = redact(printdoc, "Support")
    extend = redact(printdoc, "Extend")

    assert sum(not slot.given for slot in iter_slots(support)) < sum(
        not slot.given for slot in iter_slots(extend)
    )

    support_html = render_html(support, variant="note", tier="Support")
    extend_html = render_html(extend, variant="note", tier="Extend")
    assert "cornell-table" in support_html
    assert "cornell-summary" in support_html
    assert sum(term in support_html for term in TERMS) > sum(term in extend_html for term in TERMS)

    for tier in ("Support", "Core", "Accelerate", "Extend"):
        redacted = redact(printdoc, tier)
        html = render_html(redacted, variant="note", tier=tier)
        for slot in iter_slots(redacted):
            if not slot.given:
                assert slot.content_html not in html


def test_cornell_key_and_exemplar_are_filled():
    key_html = render_html(filled(_printdoc()), variant="note")
    for term in TERMS:
        assert term in key_html

    exemplar = parse_noteforge_json(SAMPLE_CORNELL.replace('"mode": "blank"', '"mode": "exemplar"'))
    doc = filled(to_printdoc(exemplar))
    html = render_html(doc, variant="note")
    assert all(slot.given for slot in iter_slots(doc))
    assert 'class="slot-blank"' not in html


def test_cornell_note_spike_native_smoke_when_provisioned(tmp_path):
    _require_native_render_stack()

    input_path = tmp_path / "cornell.txt"
    input_path.write_text(SAMPLE_CORNELL, encoding="utf-8")
    output_dir = tmp_path / "out"

    assert note_spike_main(["--input", str(input_path), "--output", str(output_dir)]) == 0

    for label in ("Support", "Core", "Accelerate", "Extend", "KEY"):
        for suffix in (".docx", ".pdf"):
            path = output_dir / f"Cornell_Photosynthesis_{label}{suffix}"
            assert path.exists()
            assert path.stat().st_size > 0


def _require_native_render_stack() -> None:
    if importlib.util.find_spec("pypandoc") is None:
        pytest.skip("pypandoc/pypandoc-binary is not installed")
    if importlib.util.find_spec("playwright") is None:
        pytest.skip("playwright is not installed")

    import pypandoc

    try:
        pypandoc.get_pandoc_path()
    except OSError:
        pytest.skip("Pandoc binary is not available")

    from engine.rendering.physical.emit_pdf import edge_executable_path

    if edge_executable_path() is None:
        pytest.skip("Microsoft Edge is not installed")
