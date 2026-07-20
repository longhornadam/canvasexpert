"""QTI assessment XML builders."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from engine.core.questions import NumericalQuestion, Question, StimulusItem
from engine.core.quiz import Quiz
from engine.utils.text_utils import rand8

from .html_formatter import html_mattext, htmlize_prompt, serialize_element
from .numerical_renderer import build_numerical_item
from .qti_metadata import add_item_metadata
from .qti_responses import build_response
from .qti_scoring import build_scoring


def build_assessment_xml(quiz: Quiz) -> str:
    """Build the main QTI 1.2 assessment XML document."""
    root = ET.Element("questestinterop")
    assessment_ident = f"assessment_{rand8()}"
    assessment = ET.SubElement(root, "assessment", {"ident": assessment_ident, "title": quiz.title})

    metadata = ET.SubElement(assessment, "qtimetadata")
    metadata_field = ET.SubElement(metadata, "qtimetadatafield")
    ET.SubElement(metadata_field, "fieldlabel").text = "cc_maxattempts"
    ET.SubElement(metadata_field, "fieldentry").text = "1"

    section = ET.SubElement(assessment, "section", {"ident": "root_section"})
    for index, question in enumerate(quiz.questions, start=1):
        section.append(_build_item(question, index))

    xml_body = serialize_element(root)
    open_tag = "<questestinterop>"
    ns_tag = (
        '<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.imsglobal.org/xsd/ims_qtiasiv1p2 http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd">'
    )
    xml_body = xml_body.replace(open_tag, ns_tag, 1)
    return "<?xml version=\"1.0\"?>\n" + xml_body + "\n"


def _build_item(question: Question, index: int) -> ET.Element:
    """Build a single QTI <item> element from a Question."""
    if isinstance(question, NumericalQuestion):
        return build_numerical_item(question, index)

    item_ident = question.forced_ident or f"item_q{index:02d}_{rand8()}"
    item = ET.Element("item", {"ident": item_ident, "title": f"Q{index:02d}"})

    add_item_metadata(item, question)

    presentation = ET.SubElement(item, "presentation")
    _add_prompt_material(presentation, question)

    if isinstance(question, StimulusItem):
        return item

    response_info = build_response(question, presentation)
    if response_info is None:
        return item

    build_scoring(question, item, response_info)
    return item


def _add_prompt_material(presentation: ET.Element, question: Question) -> None:
    material = ET.SubElement(presentation, "material")
    if isinstance(question, StimulusItem):
        orientation = "left" if getattr(question, "layout", "below") == "right" else "top"
        material.set("orientation", orientation)

    enable_excerpt_numbering = isinstance(question, StimulusItem)
    material.append(
        html_mattext(
            htmlize_prompt(
                question.prompt,
                excerpt_numbering=enable_excerpt_numbering,
                render_mode=getattr(question, "render_mode", "verbatim"),
            )
        )
    )
