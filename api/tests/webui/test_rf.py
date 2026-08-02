import copy
from pathlib import Path

from api.webui import rf


ROOT = Path(__file__).resolve().parents[3]
RUBRIC_DIR = ROOT / "api" / "rubrics"


def load(name):
    data, problems = rf.parse_file(str(RUBRIC_DIR / name))
    assert problems == []
    assert data is not None
    return data


def valid_dict():
    return {
        "version": "1.0-json",
        "type": "RUBRIC",
        "title": "Sample Rubric",
        "total_points": 5,
        "student_page": {"title": "Sample Student Page", "tagline": "", "reminder": ""},
        "criteria": [
            {
                "name": "Criterion 1",
                "student_label": "Criterion 1",
                "points": 5,
                "use_range": True,
                "core_question": "Question?",
                "consistency_thread": "Thread.",
                "ratings": [
                    {"label": "High", "points": 5, "description": "Desc 1", "student_description": "Student 1"},
                    {"label": "Low", "points": 0, "description": "Desc 0", "student_description": "Student 0"},
                ],
            }
        ],
        "scoring_guidance": {
            "design_principles": ["Principle"],
            "consistency_tips": ["Tip"],
            "scr_scaling": "Scale.",
            "output_template": {"scores": {}, "total": 0},
        },
    }


def test_library_files_parse_validate_and_totals():
    classroom = load("ELA7_Classroom_Writing_Rubric.txt")
    staar_ecr = load("ELA_STAAR_ECR_Rubric.txt")
    staar_scr = load("ELA_STAAR_SCR_Rubric.txt")
    district = load("ELA_District_ECR_Rubric.txt")

    assert rf.total_points(classroom) == 100
    assert rf.total_points(staar_ecr) == 5
    assert rf.total_points(staar_scr) == 2
    assert rf.total_points(district) == 10


def test_canvas_rubric_payload_shapes_and_range_flag():
    classroom = load("ELA7_Classroom_Writing_Rubric.txt")
    staar_ecr = load("ELA_STAAR_ECR_Rubric.txt")

    payload = rf.canvas_rubric_payload(classroom, 123)
    assert payload["rubric"]["criteria"]["0"]["criterion_use_range"] is True
    assert len(payload["rubric"]["criteria"]) == 5
    assert len(payload["rubric"]["criteria"]["0"]["ratings"]) == 5
    assert payload["rubric_association"]["association_id"] == 123

    payload2 = rf.canvas_rubric_payload(staar_ecr, 7)
    assert payload2["rubric"]["criteria"]["0"]["criterion_use_range"] is False


def test_student_page_html_and_scoring_prompt_use_file_content():
    classroom = load("ELA7_Classroom_Writing_Rubric.txt")
    html = rf.student_page_html(classroom)
    for criterion in classroom["criteria"]:
        for rating in criterion["ratings"]:
            assert rating["student_description"] in html

    prompt = rf.scoring_prompt(classroom)
    for criterion in classroom["criteria"]:
        for rating in criterion["ratings"]:
            assert rating["description"] in prompt
    for key in classroom["scoring_guidance"]["output_template"].keys():
        assert f'"{key}"' in prompt


def test_validate_flags_each_rule():
    base = valid_dict()

    cases = [
        ("version must be \"1.0-json\"", lambda d: d.__setitem__("version", "bad")),
        ("type must be RUBRIC", lambda d: d.__setitem__("type", "QUIZ")),
        ("title is required", lambda d: d.__setitem__("title", "")),
        ("student_page.title is required", lambda d: d["student_page"].__setitem__("title", "")),
        ("student_page.title must differ from title", lambda d: d["student_page"].__setitem__("title", d["title"])),
        ("criteria is required", lambda d: d.__setitem__("criteria", [])),
        ("points must be a number > 0", lambda d: d["criteria"][0].__setitem__("points", 0)),
        ("ratings must be a list with at least 2 entries", lambda d: d["criteria"][0].__setitem__("ratings", [d["criteria"][0]["ratings"][0]])),
        ("first rating points must equal criterion points", lambda d: d["criteria"][0]["ratings"][0].__setitem__("points", 4)),
        ("last rating points must be 0", lambda d: d["criteria"][0]["ratings"][1].__setitem__("points", 1)),
        ("student_description is required", lambda d: d["criteria"][0]["ratings"][1].__setitem__("student_description", "")),
        ("criteria points sum to", lambda d: d.__setitem__("total_points", 4)),
        ("rating labels must be unique", lambda d: d["criteria"][0]["ratings"][1].__setitem__("label", "High")),
    ]

    for expected, mutator in cases:
        data = copy.deepcopy(base)
        mutator(data)
        problems = rf.validate(data)
        assert any(expected in problem for problem in problems), (expected, problems)
