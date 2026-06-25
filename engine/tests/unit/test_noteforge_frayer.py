from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from engine.rendering.physical.html_renderer import render_html
from engine.rendering.physical.note_adapter import parse_noteforge_json, to_printdoc
from engine.rendering.physical.note_spike import main as note_spike_main
from engine.rendering.physical.printdoc import FrayerGrid, Slot
from engine.rendering.physical.redact import filled, iter_slots, redact


SAMPLE_FRAYER = """<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "frayer",
  "mode": "blank",
  "title": "Vocabulary: Photosynthesis",
  "term": "Photosynthesis",
  "definition": "How plants make {{glucose}} from light, water, and CO2.",
  "characteristics": "Happens in the {{chloroplast}}; needs {{chlorophyll}}; releases {{oxygen}}.",
  "examples": "A fern in sunlight; {{algae}} in a pond.",
  "non_examples": "{{respiration}}; a rock; an animal eating."
}
</NOTEFORGE_JSON>"""

TERMS = ["glucose", "chloroplast", "chlorophyll", "oxygen", "algae", "respiration"]


def _printdoc():
    return to_printdoc(parse_noteforge_json(SAMPLE_FRAYER))


def test_frayer_adapter_builds_grid_and_stable_slot_ids():
    printdoc = _printdoc()
    grid = printdoc.blocks[0]

    assert isinstance(grid, FrayerGrid)
    assert grid.term == "Photosynthesis"
    assert isinstance(grid.definition[1], Slot)
    assert grid.definition[1].id == "bdefs0"
    assert grid.characteristics[1].id == "bchars0"
    assert grid.characteristics[3].id == "bchars1"
    assert grid.characteristics[5].id == "bchars2"
    assert grid.examples[1].id == "bexs0"
    assert grid.non_examples[0].id == "bnonexs0"
    assert [slot.content_html for slot in iter_slots(printdoc)] == TERMS


def test_frayer_tiering_and_no_answer_leak():
    printdoc = _printdoc()
    support = redact(printdoc, "Support")
    extend = redact(printdoc, "Extend")

    assert sum(not slot.given for slot in iter_slots(support)) < sum(
        not slot.given for slot in iter_slots(extend)
    )

    support_html = render_html(support, variant="note", tier="Support")
    extend_html = render_html(extend, variant="note", tier="Extend")
    assert "frayer-table" in support_html
    assert "Term:" in support_html
    assert "Photosynthesis" in extend_html
    assert sum(term in support_html for term in TERMS) > sum(term in extend_html for term in TERMS)

    for tier in ("Support", "Core", "Accelerate", "Extend"):
        redacted = redact(printdoc, tier)
        html = render_html(redacted, variant="note", tier=tier)
        for slot in iter_slots(redacted):
            if not slot.given:
                assert slot.content_html not in html


def test_frayer_key_and_exemplar_are_filled():
    key_html = render_html(filled(_printdoc()), variant="note")
    assert "Photosynthesis" in key_html
    for term in TERMS:
        assert term in key_html

    exemplar = parse_noteforge_json(SAMPLE_FRAYER.replace('"mode": "blank"', '"mode": "exemplar"'))
    doc = filled(to_printdoc(exemplar))
    html = render_html(doc, variant="note")
    assert all(slot.given for slot in iter_slots(doc))
    assert 'class="slot-blank"' not in html


def test_frayer_note_spike_native_smoke_when_provisioned(tmp_path):
    _require_native_render_stack()

    input_path = tmp_path / "frayer.txt"
    input_path.write_text(SAMPLE_FRAYER, encoding="utf-8")
    output_dir = tmp_path / "out"

    assert note_spike_main(["--input", str(input_path), "--output", str(output_dir)]) == 0

    for label in ("Support", "Core", "Accelerate", "Extend", "KEY"):
        for suffix in (".docx", ".pdf"):
            path = output_dir / f"Vocabulary_Photosynthesis_{label}{suffix}"
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

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Playwright Chromium is not installed")
