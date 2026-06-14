import xml.etree.ElementTree as ET

from engine.core.questions import FITBQuestion
from engine.core.quiz import Quiz
from engine.rendering.canvas.qti_builder import build_assessment_xml


def _extract_labels(xml: str, ident: str):
    root = ET.fromstring(xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")}
    item = next(i for i in root.findall(".//qti:item", ns) if i.get("ident") == ident)
    labels = item.findall(".//qti:response_label", ns)
    return [l.get("ident") for l in labels], ["".join(l.itertext()) for l in labels]


def test_fitb_single_blank_multiple_accepts_exported():
    q = FITBQuestion(
        qtype="FITB",
        prompt="A search is [blank].",
        variants=["sequential search", "linear search", "sequential search", " linear "],
        blank_token="token123",
        answer_mode="open_entry",
        forced_ident="fitb_single",
    )
    quiz = Quiz(title="Test", questions=[q])

    xml = build_assessment_xml(quiz)
    idents, texts = _extract_labels(xml, "fitb_single")

    # Deduped and trimmed; all unique variants exported
    assert len(idents) == 3
    assert "sequential search" in texts
    assert "linear search" in texts
    assert "linear" in texts


def test_fitb_multi_blank_multiple_accepts_exported():
    q = FITBQuestion(
        qtype="FITB",
        prompt="First [blank1] then [blank2].",
        variants_per_blank=[[" red ", "RED", ""], ["blue", "blue"]],
        blank_tokens=["tokA", "tokB"],
        answer_mode="open_entry",
        forced_ident="fitb_multi",
    )
    quiz = Quiz(title="Test", questions=[q])

    xml = build_assessment_xml(quiz)
    root = ET.fromstring(xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")}
    items = [i for i in root.findall(".//qti:item", ns) if i.get("ident") == "fitb_multi"]
    assert len(items) == 1
    labels = items[0].findall(".//qti:response_label", ns)

    # Should emit one label per unique variant across both blanks (2 blanks, 2 unique answers)
    assert len(labels) == 2
    texts = ["".join(l.itertext()) for l in labels]
    assert "red" in texts or "RED" in texts
    assert "blue" in texts
