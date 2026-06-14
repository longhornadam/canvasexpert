"""QTI round-trip verification.

This module parses generated QTI XML and verifies student-visible strings are
bit-for-bit identical (text + length) to the in-memory authoring source.

This is a hard-stop safety check.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Tuple

from engine.core.questions import (
    CategorizationQuestion,
    FITBQuestion,
    MAQuestion,
    MatchingQuestion,
    MCQuestion,
    OrderingQuestion,
    Question,
    StimulusItem,
)
from engine.core.quiz import Quiz


_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_visible_text(value: str) -> str:
    # Remove HTML tags inserted by the formatter/builder.
    # Canvas QTI stores HTML in XML-escaped form (&lt;p&gt; not <p>).
    # First unescape XML entities, then remove HTML tags.
    import html
    unescaped = html.unescape(value)
    # Remove HTML tags - intentionally minimal: do not normalize whitespace
    return _TAG_RE.sub("", unescaped)


def _mattext_value(elem: ET.Element) -> str:
    text = elem.text or ""
    texttype = elem.attrib.get("texttype", "")
    if texttype == "text/html":
        return _html_to_visible_text(text)
    return text


def _expected_for_question(question: Question) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []

    prompt = getattr(question, "prompt", "")
    render_mode = getattr(question, "render_mode", "executable")
    if isinstance(prompt, str):
        # If render_mode is executable, the prompt goes through htmlize_prompt which may add HTML tags.
        # We need to apply the same transformation here, then strip HTML for text comparison.
        if render_mode == "executable":
            from .html_formatter import htmlize_prompt
            # Apply the same HTML formatting that happens during QTI generation
            enable_excerpt_numbering = isinstance(question, StimulusItem)
            rendered_prompt = htmlize_prompt(prompt, excerpt_numbering=enable_excerpt_numbering, render_mode=render_mode)
            # Now strip HTML tags for comparison (since QTI will have HTML-escaped version)
            prompt = _html_to_visible_text(rendered_prompt)
        out.append(("prompt", prompt))

    if isinstance(question, (MCQuestion, MAQuestion)):
        for idx, choice in enumerate(getattr(question, "choices", []) or [], 1):
            text = getattr(choice, "text", "")
            if isinstance(text, str):
                # Apply same transformation as QTI builder (htmlize_choice) then strip HTML
                if render_mode == "executable":
                    from .html_formatter import htmlize_choice
                    rendered_text = htmlize_choice(text, render_mode=render_mode)
                    text = _html_to_visible_text(rendered_text)
                out.append((f"choice[{idx}]", text))

    if isinstance(question, MatchingQuestion):
        # Prompts plus answer options for each prompt (Canvas repeats the option list per pair).
        # Match renderer order: insertion order of unique answers.
        answers_in_order: List[str] = []
        seen = set()
        for pair in getattr(question, "pairs", []) or []:
            ans = getattr(pair, "answer", "")
            if isinstance(ans, str) and ans not in seen:
                seen.add(ans)
                answers_in_order.append(ans)

        for pidx, pair in enumerate(getattr(question, "pairs", []) or [], 1):
            left = getattr(pair, "prompt", "")
            if isinstance(left, str):
                out.append((f"pair[{pidx}].left", left))
            for aidx, ans in enumerate(answers_in_order, 1):
                out.append((f"pair[{pidx}].option[{aidx}]", ans))

    if isinstance(question, OrderingQuestion):
        header = getattr(question, "header", None)
        if isinstance(header, str) and header:
            out.append(("header", header))
        for idx, item in enumerate(getattr(question, "items", []) or [], 1):
            text = getattr(item, "text", "")
            if isinstance(text, str):
                out.append((f"item[{idx}]", text))

    if isinstance(question, CategorizationQuestion):
        items_in_order: List[str] = []
        for entry in getattr(question, "items", []) or []:
            text = getattr(entry, "item_text", "")
            if isinstance(text, str):
                items_in_order.append(text)
        for dist in getattr(question, "distractors", []) or []:
            if isinstance(dist, str):
                items_in_order.append(dist)

        for cidx, cat in enumerate(getattr(question, "categories", []) or [], 1):
            if isinstance(cat, str):
                out.append((f"category[{cidx}]", cat))
            for iidx, item_text in enumerate(items_in_order, 1):
                out.append((f"category[{cidx}].pool[{iidx}]", item_text))

    if isinstance(question, FITBQuestion):
        mode = (getattr(question, "answer_mode", "open_entry") or "open_entry")
        if isinstance(mode, str) and mode.lower() in {"dropdown", "wordbank"}:
            for idx, opt in enumerate(getattr(question, "options", []) or [], 1):
                if isinstance(opt, str):
                    out.append((f"option[{idx}]", opt))

    return out


def _extract_for_item(item_elem: ET.Element, ns: dict, question: Question) -> List[str]:
    extracted: List[str] = []

    # Prompt
    prompt_mt = item_elem.find(".//qti:presentation/qti:material/qti:mattext", ns)
    extracted.append(_mattext_value(prompt_mt) if prompt_mt is not None else "")

    if isinstance(question, (MCQuestion, MAQuestion)):
        mts = item_elem.findall(".//qti:response_label/qti:material/qti:mattext", ns)
        for mt in mts:
            extracted.append(_mattext_value(mt))

    elif isinstance(question, MatchingQuestion):
        response_lids = item_elem.findall(".//qti:presentation/qti:response_lid", ns)
        for lid in response_lids:
            left_mt = lid.find("./qti:material/qti:mattext", ns)
            extracted.append(_mattext_value(left_mt) if left_mt is not None else "")
            option_mts = lid.findall(".//qti:response_label/qti:material/qti:mattext", ns)
            for mt in option_mts:
                extracted.append(_mattext_value(mt))

    elif isinstance(question, OrderingQuestion):
        header_mt = item_elem.find(".//qti:render_extension/qti:material[@position='top']/qti:mattext", ns)
        if getattr(question, "header", None):
            extracted.append(_mattext_value(header_mt) if header_mt is not None else "")
        item_mts = item_elem.findall(".//qti:flow_label/qti:response_label/qti:material/qti:mattext", ns)
        for mt in item_mts:
            extracted.append(_mattext_value(mt))

    elif isinstance(question, CategorizationQuestion):
        response_lids = item_elem.findall(".//qti:presentation/qti:response_lid", ns)
        for lid in response_lids:
            cat_mt = lid.find("./qti:material/qti:mattext", ns)
            extracted.append(_mattext_value(cat_mt) if cat_mt is not None else "")
            pool_mts = lid.findall(".//qti:response_label/qti:material/qti:mattext", ns)
            for mt in pool_mts:
                extracted.append(_mattext_value(mt))

    elif isinstance(question, FITBQuestion):
        mode = (getattr(question, "answer_mode", "open_entry") or "open_entry")
        if isinstance(mode, str) and mode.lower() in {"dropdown", "wordbank"}:
            mts = item_elem.findall(".//qti:response_label/qti:material/qti:mattext", ns)
            for mt in mts:
                extracted.append(_mattext_value(mt))

    return extracted


def verify_qti_round_trip(quiz: Quiz, assessment_xml: str) -> None:
    root = ET.fromstring(assessment_xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {"qti": ""}

    items = root.findall(".//qti:item", ns) if ns["qti"] else root.findall(".//item")
    if len(items) != len(quiz.questions):
        raise ValueError(f"QTI round-trip mismatch: item count {len(items)} != question count {len(quiz.questions)}")

    for q_index, (question, item_elem) in enumerate(zip(quiz.questions, items), 1):
        expected_pairs = _expected_for_question(question)
        expected_values = [v for _, v in expected_pairs]
        extracted_values = _extract_for_item(item_elem, ns, question)

        if len(expected_values) != len(extracted_values):
            raise ValueError(
                "QTI round-trip mismatch: extracted field count differs "
                f"(q#{q_index} expected {len(expected_values)} got {len(extracted_values)})\n"
                f"expected_keys={[k for k,_ in expected_pairs]}"
            )

        for field_idx, (key, original) in enumerate(expected_pairs):
            mutated = extracted_values[field_idx]
            if original != mutated or len(original) != len(mutated):
                raise ValueError(
                    "QTI round-trip mutation detected "
                    f"(q#{q_index} {key})\n"
                    f"original={repr(original)}\n"
                    f"mutated={repr(mutated)}"
                )
