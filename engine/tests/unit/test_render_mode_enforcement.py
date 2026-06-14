import io
import zipfile
import xml.etree.ElementTree as ET

from engine.core.questions import MCChoice, MCQuestion
from engine.core.quiz import Quiz
from engine.rendering.canvas.canvas_packager import CanvasPackager
from engine.validation.validator import QuizValidator, ValidationStatus


def _extract_first_prompt_text(assessment_xml: str) -> str:
    root = ET.fromstring(assessment_xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")}
    mt = root.find(".//qti:item/qti:presentation/qti:material/qti:mattext", ns)
    assert mt is not None
    return mt.text or ""


def test_verbatim_preserves_backslash_through_canvas_packager():
    q = MCQuestion(
        qtype="MC",
        prompt=r"A\nB",
        render_mode="verbatim",
        choices=[MCChoice(text=r"A\nB", correct=True), MCChoice(text="other")],
        forced_ident="q1",
    )
    quiz = Quiz(title="Verbatim", questions=[q])

    result = QuizValidator().validate(quiz)
    assert result.status in (ValidationStatus.PASS, ValidationStatus.WEAK_PASS)

    zip_bytes, guid = CanvasPackager().package(quiz)

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        assessment_xml = zf.read(f"{guid}/{guid}.xml").decode("utf-8")

    prompt_text = _extract_first_prompt_text(assessment_xml)
    assert prompt_text == r"A\nB"
    assert len(prompt_text) == 4
