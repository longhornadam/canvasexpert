import xml.etree.ElementTree as ET

from engine.core.questions import (
    CategoryMapping,
    MCChoice,
    MCQuestion,
    MAQuestion,
    MatchingPair,
    MatchingQuestion,
    OrderingItem,
    OrderingQuestion,
    CategorizationQuestion,
    StimulusItem,
)
from engine.core.quiz import Quiz
from engine.rendering.canvas.qti_builder import build_assessment_xml


def _root(xml: str):
    root = ET.fromstring(xml)
    ns = {"qti": root.tag.split("}")[0].strip("{")}
    return root, ns


def _item(root: ET.Element, ns: dict, ident: str) -> ET.Element:
    return next(elem for elem in root.findall(".//qti:item", ns) if elem.get("ident") == ident)


def _metadata_fields(item: ET.Element, ns: dict) -> dict[str, str]:
    fields = {}
    for field in item.findall(".//qti:itemmetadata/qti:qtimetadata/qti:qtimetadatafield", ns):
        label = field.findtext("./qti:fieldlabel", default="", namespaces=ns)
        entry = field.findtext("./qti:fieldentry", default="", namespaces=ns)
        fields[label] = entry
    return fields


def test_mc_response_and_scoring_use_response1():
    quiz = Quiz(
        title="MC",
        questions=[
            MCQuestion(
                qtype="MC",
                prompt="Pick one",
                choices=[MCChoice(text="Correct", correct=True), MCChoice(text="Wrong")],
                forced_ident="mc_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "mc_item")

    response_lids = item.findall(".//qti:presentation/qti:response_lid", ns)
    assert len(response_lids) == 1
    assert response_lids[0].get("ident") == "response1"
    assert response_lids[0].get("rcardinality") == "Single"

    varequals = item.findall(".//qti:resprocessing/qti:respcondition/qti:conditionvar/qti:varequal", ns)
    assert [elem.text for elem in varequals] == ["a"]


def test_ma_scoring_uses_add_for_each_correct_choice():
    quiz = Quiz(
        title="MA",
        questions=[
            MAQuestion(
                qtype="MA",
                prompt="Select all correct",
                choices=[
                    MCChoice(text="Alpha", correct=True),
                    MCChoice(text="Beta", correct=False),
                    MCChoice(text="Gamma", correct=True),
                ],
                forced_ident="ma_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "ma_item")

    response_lid = item.find(".//qti:presentation/qti:response_lid", ns)
    assert response_lid is not None
    assert response_lid.get("ident") == "response1"
    assert response_lid.get("rcardinality") == "Multiple"

    respconditions = item.findall(".//qti:resprocessing/qti:respcondition", ns)
    assert len(respconditions) == 2
    assert all(cond.get("continue") == "Yes" for cond in respconditions)
    assert all(cond.find("./qti:setvar", ns).get("action") == "Add" for cond in respconditions)
    assert [cond.findtext("./qti:conditionvar/qti:varequal", default="", namespaces=ns) for cond in respconditions] == ["a", "c"]


def test_matching_scoring_uses_generated_answer_labels():
    quiz = Quiz(
        title="Match",
        questions=[
            MatchingQuestion(
                qtype="MATCHING",
                prompt="Match pairs",
                pairs=[
                    MatchingPair(prompt="Dog", answer="Bark"),
                    MatchingPair(prompt="Cat", answer="Meow"),
                ],
                forced_ident="matching_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "matching_item")

    response_lids = item.findall(".//qti:presentation/qti:response_lid", ns)
    assert len(response_lids) == 2

    label_idents = {
        label.get("ident")
        for label in item.findall(".//qti:presentation/qti:response_lid/qti:render_choice/qti:response_label", ns)
    }
    assert len(label_idents) == 2

    respcondition_pairs = item.findall(".//qti:resprocessing/qti:respcondition", ns)
    assert len(respcondition_pairs) == 2
    assert {cond.findtext("./qti:conditionvar/qti:varequal", default="", namespaces=ns) for cond in respcondition_pairs} == label_idents
    assert {cond.find("./qti:conditionvar/qti:varequal", ns).get("respident") for cond in respcondition_pairs} == {lid.get("ident") for lid in response_lids}


def test_ordering_response_and_scoring_are_ordered():
    quiz = Quiz(
        title="Order",
        questions=[
            OrderingQuestion(
                qtype="ORDER",
                prompt="Put in order",
                header="Arrange first",
                items=[
                    OrderingItem(text="One", ident="step_1"),
                    OrderingItem(text="Two", ident="step_2"),
                    OrderingItem(text="Three", ident="step_3"),
                ],
                forced_ident="ordering_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "ordering_item")

    response_lid = item.find(".//qti:presentation/qti:response_lid", ns)
    assert response_lid is not None
    assert response_lid.get("rcardinality") == "Ordered"

    varequals = item.findall(".//qti:resprocessing/qti:respcondition/qti:conditionvar/qti:varequal", ns)
    assert [elem.text for elem in varequals] == ["step_1", "step_2", "step_3"]


def test_categorization_builds_category_lids_and_scoring():
    quiz = Quiz(
        title="Category",
        questions=[
            CategorizationQuestion(
                qtype="CAT",
                prompt="Sort items",
                categories=["Fruit", "Animal"],
                category_idents={"Fruit": "cat_fruit", "Animal": "cat_animal"},
                items=[
                    CategoryMapping(item_text="Apple", item_ident="item_apple", category_name="Fruit"),
                    CategoryMapping(item_text="Dog", item_ident="item_dog", category_name="Animal"),
                ],
                distractors=["Rock"],
                distractor_idents={"Rock": "item_rock"},
                forced_ident="categorization_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "categorization_item")

    response_lids = item.findall(".//qti:presentation/qti:response_lid", ns)
    assert [lid.get("ident") for lid in response_lids] == ["cat_fruit", "cat_animal"]
    assert all(lid.get("rcardinality") == "Multiple" for lid in response_lids)

    label_texts = [
        "".join(label.itertext())
        for label in item.findall(".//qti:presentation/qti:response_lid/qti:render_choice/qti:response_label", ns)
    ]
    assert "Apple" in label_texts
    assert "Dog" in label_texts
    assert "Rock" in label_texts

    respconditions = item.findall(".//qti:resprocessing/qti:respcondition", ns)
    assert len(respconditions) == 2
    scoring = {
        cond.find("./qti:conditionvar/qti:varequal", ns).get("respident"): [elem.text for elem in cond.findall("./qti:conditionvar/qti:varequal", ns)]
        for cond in respconditions
    }
    assert scoring == {"cat_fruit": ["item_apple"], "cat_animal": ["item_dog"]}


def test_stimulus_item_keeps_text_only_metadata_and_has_no_scoring():
    quiz = Quiz(
        title="Stimulus",
        questions=[
            StimulusItem(
                qtype="STIMULUS",
                prompt="Read this passage.",
                layout="right",
                points=0.0,
                forced_ident="stim_item",
            )
        ],
    )

    root, ns = _root(build_assessment_xml(quiz))
    item = _item(root, ns, "stim_item")

    fields = _metadata_fields(item, ns)
    assert fields["question_type"] == "text_only_question"
    assert fields["points_possible"] == "0.0"
    assert item.find(".//qti:presentation/qti:response_lid", ns) is None
    assert item.find(".//qti:presentation/qti:response_str", ns) is None
    assert item.find(".//qti:resprocessing", ns) is None
