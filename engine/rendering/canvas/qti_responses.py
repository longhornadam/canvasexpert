"""QTI response and interaction builders."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

from engine.core.questions import (
    CategorizationQuestion,
    EssayQuestion,
    FITBQuestion,
    FileUploadQuestion,
    MAQuestion,
    MCQuestion,
    MatchingQuestion,
    OrderingQuestion,
    Question,
    TFQuestion,
)
from .html_formatter import html_mattext, htmlize_choice, htmlize_item_text, plaintext_item_text


def build_response(question: Question, presentation: ET.Element):
    """Build the response interaction XML for a question."""
    if isinstance(question, MCQuestion):
        return _build_mc_response(question, presentation)
    if isinstance(question, TFQuestion):
        return _build_tf_response(question, presentation)
    if isinstance(question, MAQuestion):
        return _build_ma_response(question, presentation)
    if isinstance(question, MatchingQuestion):
        return _build_matching_response(question, presentation)
    if isinstance(question, FITBQuestion):
        return _build_fitb_response(question, presentation)
    if isinstance(question, EssayQuestion):
        _build_text_response(presentation)
        return None
    if isinstance(question, FileUploadQuestion):
        _build_text_response(presentation)
        return None
    if isinstance(question, OrderingQuestion):
        return _build_ordering_response(question, presentation)
    if isinstance(question, CategorizationQuestion):
        return _build_categorization_response(question, presentation)

    response_lid = ET.SubElement(presentation, "response_lid", {"ident": "response1", "rcardinality": "Single"})
    ET.SubElement(response_lid, "render_choice")
    return {"type": "generic"}


def _build_mc_response(question: MCQuestion, presentation: ET.Element):
    response_lid = ET.SubElement(presentation, "response_lid", {"ident": "response1", "rcardinality": "Single"})
    render_choice = ET.SubElement(response_lid, "render_choice")
    identifiers = [chr(ord("a") + i) for i in range(len(question.choices))]
    for ident, choice in zip(identifiers, question.choices):
        _add_choice(render_choice, ident, choice.text, render_mode=getattr(question, "render_mode", "verbatim"))
    correct_ident = identifiers[[index for index, choice in enumerate(question.choices) if choice.correct][0]]
    return {"type": "mc", "correct": correct_ident}


def _build_tf_response(question: TFQuestion, presentation: ET.Element):
    response_lid = ET.SubElement(presentation, "response_lid", {"ident": "response1", "rcardinality": "Single"})
    render_choice = ET.SubElement(response_lid, "render_choice")
    for ident, label_text in (("true", "True"), ("false", "False")):
        label = ET.SubElement(render_choice, "response_label", {"ident": ident})
        material = ET.SubElement(label, "material")
        material.append(html_mattext(f"<p>{label_text}</p>"))
    correct = "true" if question.answer_true else "false"
    return {"type": "tf", "correct": correct}


def _build_ma_response(question: MAQuestion, presentation: ET.Element):
    response_lid = ET.SubElement(presentation, "response_lid", {"ident": "response1", "rcardinality": "Multiple"})
    render_choice = ET.SubElement(response_lid, "render_choice")
    identifiers = [chr(ord("a") + i) for i in range(len(question.choices))]
    correct: list[str] = []
    for ident, choice in zip(identifiers, question.choices):
        _add_choice(render_choice, ident, choice.text, render_mode=getattr(question, "render_mode", "verbatim"))
        if choice.correct:
            correct.append(ident)
    return {"type": "ma", "choices": question.choices, "correct": correct}


def _build_matching_response(question: MatchingQuestion, presentation: ET.Element):
    answer_id_by_text: dict[str, str] = {}
    for pair in question.pairs:
        if pair.answer not in answer_id_by_text:
            answer_id_by_text[pair.answer] = str(uuid.uuid4())

    rlids: list[str] = []
    for pair in question.pairs:
        lid_ident = str(uuid.uuid4())
        rlids.append(lid_ident)
        response_lid = ET.SubElement(presentation, "response_lid", {"ident": lid_ident})
        matq = ET.SubElement(response_lid, "material")
        prompt_plain = plaintext_item_text(pair.prompt, render_mode=getattr(question, "render_mode", "verbatim"))
        matq.append(_plain_mattext(prompt_plain))
        render_choice = ET.SubElement(response_lid, "render_choice")
        for answer_text, answer_ident in answer_id_by_text.items():
            rl = ET.SubElement(render_choice, "response_label", {"ident": answer_ident})
            mat = ET.SubElement(rl, "material")
            answer_plain = plaintext_item_text(answer_text, render_mode=getattr(question, "render_mode", "verbatim"))
            mat.append(_plain_mattext(answer_plain))
    return {"type": "matching", "pairs": question.pairs, "rlids": rlids, "answers": answer_id_by_text}


def _build_fitb_response(question: FITBQuestion, presentation: ET.Element):
    token = question.blank_token or uuid.uuid4().hex
    mode = (getattr(question, "answer_mode", "open_entry") or "open_entry").lower()
    options = getattr(question, "options", []) or []
    variants = _normalize_variants(question.variants or [])
    variants_per_blank = [_normalize_variants(group) for group in (getattr(question, "variants_per_blank", []) or []) if isinstance(group, list)]

    if variants_per_blank:
        blank_tokens = question.blank_tokens or []
        num_blanks = len(variants_per_blank)
        if not blank_tokens or len(blank_tokens) != num_blanks:
            blank_tokens = [uuid.uuid4().hex for _ in range(num_blanks)]
        response_data = []
        for token_i, variants_i in zip(blank_tokens, variants_per_blank):
            if not variants_i:
                continue
            resp_lid = ET.SubElement(presentation, "response_lid", {"ident": f"response_{token_i}"})
            matq = ET.SubElement(resp_lid, "material")
            ET.SubElement(matq, "mattext").text = "Question"
            render_choice = ET.SubElement(resp_lid, "render_choice")
            for j, variant in enumerate(variants_i):
                resp_ident = f"{token_i}-{j}"
                label = ET.SubElement(
                    render_choice,
                    "response_label",
                    {
                        "scoring_algorithm": "TextContainsAnswer",
                        "answer_type": "openEntry",
                        "ident": resp_ident,
                    },
                )
                mat = ET.SubElement(label, "material")
                ET.SubElement(mat, "mattext", {"texttype": "text/plain"}).text = variant
            response_data.append({"token": token_i, "variants": variants_i})
        return {"type": "fitb_multi_open", "responses": response_data}

    response_lid = ET.SubElement(presentation, "response_lid", {"ident": f"response_{token}"})
    matq = ET.SubElement(response_lid, "material")
    ET.SubElement(matq, "mattext").text = "Question"
    render_choice = ET.SubElement(response_lid, "render_choice")

    if mode in {"dropdown", "wordbank"} and options:
        scoring_algorithm = "Equivalence" if mode == "dropdown" else "TextEquivalence"
        correct_ident = None
        for index, option in enumerate(options, start=1):
            resp_ident = f"{token}-{index}"
            attrs = {
                "scoring_algorithm": scoring_algorithm,
                "answer_type": mode,
                "ident": resp_ident,
            }
            if mode == "dropdown":
                attrs["position"] = str(index)
            label = ET.SubElement(render_choice, "response_label", attrs)
            mat = ET.SubElement(label, "material")
            ET.SubElement(mat, "mattext", {"texttype": "text/plain"}).text = option
            if correct_ident is None:
                for variant in variants:
                    if isinstance(variant, str) and variant.strip().lower() == str(option).strip().lower():
                        correct_ident = resp_ident
                        break
        if correct_ident is None and options:
            correct_ident = f"{token}-1"
        return {"type": "fitb_choice", "mode": mode, "token": token, "correct_ident": correct_ident}

    open_variants = variants or ["answer"]
    for index, variant in enumerate(open_variants):
        resp_ident = f"{token}-{index}"
        label = ET.SubElement(
            render_choice,
            "response_label",
            {
                "scoring_algorithm": "TextContainsAnswer",
                "answer_type": "openEntry",
                "ident": resp_ident,
            },
        )
        mat = ET.SubElement(label, "material")
        ET.SubElement(mat, "mattext", {"texttype": "text/plain"}).text = variant
    return {"type": "fitb_open", "token": token, "variants": open_variants}


def _build_text_response(presentation: ET.Element) -> None:
    response_str = ET.SubElement(presentation, "response_str", {"ident": "response1", "rcardinality": "Single"})
    render_fib = ET.SubElement(response_str, "render_fib")
    ET.SubElement(render_fib, "response_label", {"ident": "answer1"})


def _build_ordering_response(question: OrderingQuestion, presentation: ET.Element):
    response_lid = ET.SubElement(presentation, "response_lid", {"ident": "response1", "rcardinality": "Ordered"})
    render_extension = ET.SubElement(response_lid, "render_extension")
    if question.header:
        mat_top = ET.SubElement(render_extension, "material", {"position": "top"})
        header_html = htmlize_item_text(question.header, render_mode=getattr(question, "render_mode", "verbatim"))
        mat_top.append(html_mattext(_wrap_content(header_html)))

    ims_render = ET.SubElement(render_extension, "ims_render_object", {"shuffle": "Yes"})
    flow_label = ET.SubElement(ims_render, "flow_label")
    for item in question.items:
        response_label = ET.SubElement(flow_label, "response_label", {"ident": item.ident})
        material = ET.SubElement(response_label, "material")
        item_plain = plaintext_item_text(item.text, render_mode=getattr(question, "render_mode", "verbatim"))
        material.append(_plain_mattext(item_plain))

    mat_bottom = ET.SubElement(render_extension, "material", {"position": "bottom"})
    ET.SubElement(mat_bottom, "mattext").text = ""
    return {"type": "ordering", "items": question.items}


def _build_categorization_response(question: CategorizationQuestion, presentation: ET.Element):
    all_items = list(question.items)
    all_item_idents = {item.item_text: item.item_ident for item in all_items}
    for dist in question.distractors:
        all_item_idents[dist] = question.distractor_idents[dist]

    category_data = []
    for cat_name in question.categories:
        cat_ident = question.category_idents[cat_name]
        response_lid = ET.SubElement(presentation, "response_lid", {"ident": cat_ident, "rcardinality": "Multiple"})
        material = ET.SubElement(response_lid, "material")
        material.append(_plain_mattext(cat_name))
        render_choice = ET.SubElement(response_lid, "render_choice")

        for item_text, item_ident in all_item_idents.items():
            response_label = ET.SubElement(render_choice, "response_label", {"ident": item_ident})
            mat = ET.SubElement(response_label, "material")
            plain_text = plaintext_item_text(item_text, render_mode=getattr(question, "render_mode", "verbatim"))
            mat.append(_plain_mattext(plain_text))

        correct_items = [item.item_ident for item in all_items if item.category_name == cat_name]
        category_data.append({"category_ident": cat_ident, "category_name": cat_name, "correct_items": correct_items})

    return {"type": "categorization", "categories": category_data, "num_categories": len(question.categories)}


def _add_choice(render_choice: ET.Element, ident: str, text: str, *, render_mode: str) -> None:
    label = ET.SubElement(render_choice, "response_label", {"ident": ident})
    material = ET.SubElement(label, "material")
    material.append(html_mattext(htmlize_choice(text, render_mode=render_mode)))


def _normalize_variants(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen = set()
    for val in values:
        s = str(val).strip()
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            cleaned.append(s)
    return cleaned


def _plain_mattext(text: str) -> ET.Element:
    element = ET.Element("mattext", {"texttype": "text/plain"})
    element.text = text
    return element


def _wrap_content(html: str) -> str:
    block_elements = ["<pre", "<div", "<table", "<ul", "<ol", "<blockquote", "<h1", "<h2", "<h3", "<h4", "<h5", "<h6"]
    html_lower = html.lower()
    for elem in block_elements:
        if elem in html_lower:
            return html
    return f"<p>{html}</p>"
