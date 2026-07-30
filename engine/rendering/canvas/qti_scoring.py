"""QTI scoring builders."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from engine.core.questions import MCChoice, Question


def build_scoring(question: Question, item: ET.Element, response_info) -> None:
    """Build the <resprocessing> element with scoring rules."""
    resprocessing = ET.SubElement(item, "resprocessing")
    outcomes = ET.SubElement(resprocessing, "outcomes")
    ET.SubElement(outcomes, "decvar", {"maxvalue": "100", "minvalue": "0", "varname": "SCORE", "vartype": "Decimal"})

    response_type = response_info["type"]
    if response_type in {"mc", "tf"}:
        _score_single_choice(resprocessing, response_info["correct"])
        return
    if response_type == "ma":
        _score_multiple_answers(resprocessing, response_info["choices"])
        return
    if response_type == "matching":
        _score_matching(resprocessing, response_info["pairs"], response_info["rlids"], response_info["answers"])
        return
    if response_type in {"fitb", "fitb_open"}:
        _score_fitb_open(resprocessing, response_info["token"], response_info["variants"])
        return
    if response_type == "fitb_choice":
        _score_fitb_choice(resprocessing, response_info["token"], response_info["correct_ident"])
        return
    if response_type == "fitb_multi_open":
        _score_fitb_multi_open(resprocessing, response_info["responses"])
        return
    if response_type == "ordering":
        _score_ordering(resprocessing, response_info["items"])
        return
    if response_type == "categorization":
        _score_categorization(resprocessing, response_info["categories"], response_info["num_categories"])
        return


def _score_single_choice(resprocessing: ET.Element, correct_ident: str) -> None:
    respcondition = ET.SubElement(resprocessing, "respcondition", {"continue": "No"})
    conditionvar = ET.SubElement(respcondition, "conditionvar")
    varequal = ET.SubElement(conditionvar, "varequal", {"respident": "response1"})
    varequal.text = correct_ident
    ET.SubElement(respcondition, "setvar", {"action": "Set", "varname": "SCORE"}).text = "100"


def _score_multiple_answers(resprocessing: ET.Element, choices: list[MCChoice]) -> None:
    correct_indices = [index for index, choice in enumerate(choices) if choice.correct]
    num_correct = len(correct_indices) or 1
    per = round(100.0 / num_correct, 2)
    running = 0.0
    for idx, choice_index in enumerate(correct_indices):
        add_value = per
        if idx == len(correct_indices) - 1:
            add_value = round(100.0 - running, 2)
        respcondition = ET.SubElement(resprocessing, "respcondition", {"continue": "Yes"})
        conditionvar = ET.SubElement(respcondition, "conditionvar")
        varequal = ET.SubElement(conditionvar, "varequal", {"respident": "response1"})
        varequal.text = chr(ord("a") + choice_index)
        ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = f"{add_value:.2f}"
        running += add_value


def _score_matching(resprocessing: ET.Element, pairs, rlids, answer_map) -> None:
    num_pairs = max(1, len(pairs))
    per = round(100.0 / num_pairs, 2)
    running = 0.0
    for idx, pair in enumerate(pairs):
        add_value = per
        if idx == len(pairs) - 1:
            add_value = round(100.0 - running, 2)
        respident = rlids[idx]
        correct_label = answer_map[pair.answer]
        respcondition = ET.SubElement(resprocessing, "respcondition")
        conditionvar = ET.SubElement(respcondition, "conditionvar")
        varequal = ET.SubElement(conditionvar, "varequal", {"respident": respident})
        varequal.text = correct_label
        ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = f"{add_value:.2f}"
        running += add_value


def _score_fitb_open(resprocessing: ET.Element, token: str, variants) -> None:
    for index, _ in enumerate(variants):
        respcondition = ET.SubElement(resprocessing, "respcondition")
        conditionvar = ET.SubElement(respcondition, "conditionvar")
        varequal = ET.SubElement(conditionvar, "varequal", {"respident": f"response_{token}"})
        varequal.text = f"{token}-{index}"
        ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = "100.00"


def _score_fitb_choice(resprocessing: ET.Element, token: str, correct_ident: str) -> None:
    respcondition = ET.SubElement(resprocessing, "respcondition")
    conditionvar = ET.SubElement(respcondition, "conditionvar")
    varequal = ET.SubElement(conditionvar, "varequal", {"respident": f"response_{token}"})
    varequal.text = correct_ident
    ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = "100.00"


def _score_fitb_multi_open(resprocessing: ET.Element, responses) -> None:
    num_blanks = max(1, len(responses))
    per = round(100.0 / num_blanks, 2)
    running = 0.0
    for idx, resp in enumerate(responses):
        token = resp["token"]
        variants = resp["variants"]
        add_value = per if idx < num_blanks - 1 else round(100.0 - running, 2)
        for j, _ in enumerate(variants):
            respcondition = ET.SubElement(resprocessing, "respcondition")
            conditionvar = ET.SubElement(respcondition, "conditionvar")
            varequal = ET.SubElement(conditionvar, "varequal", {"respident": f"response_{token}"})
            varequal.text = f"{token}-{j}"
            ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = f"{add_value:.2f}"
        running += add_value


def _score_ordering(resprocessing: ET.Element, items) -> None:
    respcondition = ET.SubElement(resprocessing, "respcondition", {"continue": "No"})
    conditionvar = ET.SubElement(respcondition, "conditionvar")
    for item in items:
        varequal = ET.SubElement(conditionvar, "varequal", {"respident": "response1"})
        varequal.text = item.ident
    ET.SubElement(respcondition, "setvar", {"action": "Set", "varname": "SCORE"}).text = "100"


def _score_categorization(resprocessing: ET.Element, categories, num_categories: int) -> None:
    points_per_category = round(100.0 / num_categories, 2)
    running = 0.0

    for idx, cat_data in enumerate(categories):
        if idx == len(categories) - 1:
            add_value = round(100.0 - running, 2)
        else:
            add_value = points_per_category

        respcondition = ET.SubElement(resprocessing, "respcondition")
        conditionvar = ET.SubElement(respcondition, "conditionvar")
        for item_ident in cat_data["correct_items"]:
            varequal = ET.SubElement(conditionvar, "varequal", {"respident": cat_data["category_ident"]})
            varequal.text = item_ident
        ET.SubElement(respcondition, "setvar", {"action": "Add", "varname": "SCORE"}).text = f"{add_value:.2f}"
        running += add_value
