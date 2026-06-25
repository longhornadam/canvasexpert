from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from engine.rendering.physical.note_adapter import parse_noteforge_json, to_printdoc
from engine.rendering.physical.note_spike import main as note_spike_main
from engine.rendering.physical.printdoc import BulletList, Heading, Para, Slot
from engine.rendering.physical.html_renderer import render_html
from engine.rendering.physical.redact import filled, iter_slots, redact


SAMPLE_NOTE = """<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "guided_notes",
  "title": "Water Cycle Notes",
  "topic": "How water moves through Earth systems",
  "mode": "blank",
  "body": [
    { "type": "heading", "text": "Main Processes" },
    {
      "type": "paragraph",
      "text": "Water changes from liquid to gas during {{evaporation}} and returns to liquid during {{condensation}}."
    },
    {
      "type": "bullets",
      "items": [
        "Water falling from clouds is {{precipitation}}.",
        "Water soaking into soil is {{infiltration}}.",
        "Water flowing over land is {{runoff}}.",
        "Plants release water vapor through {{transpiration}}."
      ]
    }
  ]
}
</NOTEFORGE_JSON>"""

ANSWER_TERMS = [
    "evaporation",
    "condensation",
    "precipitation",
    "infiltration",
    "runoff",
    "transpiration",
]


def _printdoc():
    return to_printdoc(parse_noteforge_json(SAMPLE_NOTE))


def test_adapter_converts_guided_cloze_to_printdoc_slots():
    printdoc = _printdoc()

    assert printdoc.title == "Water Cycle Notes"
    assert printdoc.instructions == "How water moves through Earth systems"
    assert isinstance(printdoc.blocks[0], Heading)
    assert isinstance(printdoc.blocks[1], Para)
    assert isinstance(printdoc.blocks[2], BulletList)

    paragraph_runs = printdoc.blocks[1].runs
    assert paragraph_runs[0] == "Water changes from liquid to gas during "
    assert isinstance(paragraph_runs[1], Slot)
    assert paragraph_runs[1].id == "b1s0"
    assert paragraph_runs[1].content_html == "evaporation"
    assert paragraph_runs[1].key is True
    assert paragraph_runs[2] == " and returns to liquid during "
    assert paragraph_runs[3].id == "b1s1"

    bullet_slots = [run for item in printdoc.blocks[2].items for run in item if isinstance(run, Slot)]
    assert [slot.id for slot in bullet_slots] == ["b2-0s0", "b2-1s0", "b2-2s0", "b2-3s0"]
    assert [slot.content_html for slot in iter_slots(printdoc)] == ANSWER_TERMS


def test_tiered_html_blanks_more_slots_and_does_not_leak_blanked_answers():
    printdoc = _printdoc()
    support = redact(printdoc, "Support")
    extend = redact(printdoc, "Extend")

    support_blanked = [slot for slot in iter_slots(support) if not slot.given]
    extend_blanked = [slot for slot in iter_slots(extend) if not slot.given]
    assert len(support_blanked) < len(extend_blanked)

    support_html = render_html(support, variant="note", tier="Support")
    extend_html = render_html(extend, variant="note", tier="Extend")
    assert sum(term in support_html for term in ANSWER_TERMS) > sum(
        term in extend_html for term in ANSWER_TERMS
    )

    for tier in ("Support", "Core", "Accelerate", "Extend"):
        redacted = redact(printdoc, tier)
        html = render_html(redacted, variant="note", tier=tier)
        for slot in iter_slots(redacted):
            if not slot.given:
                assert slot.content_html not in html


def test_answer_key_html_contains_every_answer_term():
    key_html = render_html(filled(_printdoc()), variant="note")

    for term in ANSWER_TERMS:
        assert term in key_html
    assert "Water Cycle Notes" in key_html


def test_exemplar_mode_renders_filled_slots_without_redaction():
    note = parse_noteforge_json(SAMPLE_NOTE.replace('"mode": "blank"', '"mode": "exemplar"'))
    printdoc = filled(to_printdoc(note))
    html = render_html(printdoc, variant="note")

    assert all(slot.given for slot in iter_slots(printdoc))
    for term in ANSWER_TERMS:
        assert term in html
    assert 'class="slot-blank"' not in html


def test_note_spike_native_smoke_when_provisioned(tmp_path):
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

    input_path = tmp_path / "water-cycle-note.txt"
    input_path.write_text(SAMPLE_NOTE, encoding="utf-8")
    output_dir = tmp_path / "out"

    assert note_spike_main(["--input", str(input_path), "--output", str(output_dir)]) == 0

    expected_labels = ["Support", "Core", "Accelerate", "Extend", "KEY"]
    for label in expected_labels:
        for suffix in (".docx", ".pdf"):
            path = output_dir / f"Water_Cycle_Notes_{label}{suffix}"
            assert path.exists()
            assert path.stat().st_size > 0
