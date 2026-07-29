"""Day plan schema: the shipped files, the budgets, and clamping.

Pure parsing and validation, so nothing here touches a workspace at all.
"""
from __future__ import annotations

import json
import os
from datetime import date

import pytest

from api.glass import schema
from api.webui import workspace

SHIPPED_DIR = os.path.join(workspace.DEFAULT_DOCS_DIR, "Glass")
SAMPLE_FILE = os.path.join(SHIPPED_DIR, "day-plan-sample.json")
TEMPLATE_FILE = os.path.join(SHIPPED_DIR, "day-plan-template.json")


def _read(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _plan_data(**overrides):
    data = {
        "format": schema.DAY_PLAN_FORMAT,
        "date": "2099-09-14",
        "day_type_override": None,
        "school_wide": {
            "events": [{"label": "Yearbook photos", "when": "Tue"}],
            "bobcat_hour_offerings": [{"label": "Robotics Club", "location": "Rm 214"}],
        },
        "teacher": {"bobcat_hour_here": {"label": "Essay retakes", "location": "Rm 108"}},
        "sections": {
            "p1": {
                "learning_goal": "Explain how point of view shapes what a reader knows",
                "success_criteria": ["Name the point of view"],
                "work": [{"name": "Point of view sort", "detail": "Finish page 2"}],
                "banner": ["Signed forms are due Friday"],
            },
        },
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------- shipped files


def test_shipped_sample_parses_and_fits():
    plan = schema.parse_day_plan(_read(SAMPLE_FILE))

    assert plan.date == date(2099, 9, 14)
    assert plan.is_sample is True
    assert plan.day_type_override is None
    assert len(plan.school_wide.events) == 2
    assert len(plan.school_wide.bobcat_hour_offerings) == 5
    assert plan.teacher_bobcat_hour.label == "Essay retakes"
    assert set(plan.sections) == {"p1", "p2", "p3", "p4", "p6"}
    assert schema.validate_day_plan(plan) == []


def test_shipped_sample_leaves_one_block_unplanned():
    plan = schema.parse_day_plan(_read(SAMPLE_FILE))

    # A block with no entry is normal: it shows an empty focus area, not an error.
    assert plan.section("p5") is None
    assert plan.section("p1").learning_goal


def test_shipped_template_is_blank_rather_than_wrong():
    data = _read(TEMPLATE_FILE)

    assert data["sections"] == {}
    assert data["school_wide"]["events"] == []
    assert data["school_wide"]["bobcat_hour_offerings"] == []
    assert data["teacher"]["bobcat_hour_here"]["label"] == ""


def test_shipped_template_says_what_to_fill_in_if_it_is_loaded_by_accident():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_read(TEMPLATE_FILE))

    assert "YYYY-MM-DD" in str(err.value)


# ----------------------------------------------------------------- budgets


def test_budgets_are_the_agreed_numbers_in_one_place():
    assert schema.CHARACTER_BUDGETS == {
        "learning_goal": 90,
        "success_criterion": 40,
        "work_name": 34,
        "work_detail": 44,
        "offering_label": 30,
        "offering_location": 12,
    }
    assert schema.BUDGET_LEARNING_GOAL == schema.CHARACTER_BUDGETS["learning_goal"]
    assert schema.BUDGET_SUCCESS_CRITERION == schema.CHARACTER_BUDGETS["success_criterion"]
    assert schema.BUDGET_WORK_NAME == schema.CHARACTER_BUDGETS["work_name"]
    assert schema.BUDGET_WORK_DETAIL == schema.CHARACTER_BUDGETS["work_detail"]
    assert schema.BUDGET_OFFERING_LABEL == schema.CHARACTER_BUDGETS["offering_label"]
    assert schema.BUDGET_OFFERING_LOCATION == schema.CHARACTER_BUDGETS["offering_location"]


def test_clamp_leaves_text_that_fits_alone():
    assert schema.clamp("Short goal", 40) == "Short goal"
    assert schema.clamp("x" * 40, 40) == "x" * 40


def test_clamp_never_exceeds_the_budget():
    for budget in list(schema.CHARACTER_BUDGETS.values()) + [0, 1, 2, 3]:
        for length in (0, 1, budget, budget + 1, budget + 200):
            assert len(schema.clamp("y" * length, budget)) <= budget


def test_clamp_ends_in_one_ellipsis_character():
    clamped = schema.clamp("z" * 100, 12)

    assert len(clamped) == 12
    assert clamped.endswith(schema.ELLIPSIS)
    assert clamped.count(schema.ELLIPSIS) == 1


def test_clamp_handles_a_zero_budget_and_empty_text():
    assert schema.clamp("anything", 0) == ""
    assert schema.clamp("", 40) == ""
    assert schema.clamp(None, 40) == ""


def test_every_over_budget_field_is_reported_by_name_with_both_lengths():
    plan = schema.parse_day_plan(_plan_data(
        school_wide={
            "events": [],
            "bobcat_hour_offerings": [{"label": "L" * 31, "location": "O" * 13}],
        },
        teacher={"bobcat_hour_here": {"label": "T" * 31, "location": "P" * 13}},
        sections={
            "p1": {
                "learning_goal": "G" * 91,
                "success_criteria": ["ok", "C" * 41],
                "work": [{"name": "N" * 35, "detail": "D" * 45}],
                "banner": ["fine"],
            },
        },
    ))

    problems = schema.validate_day_plan(plan)
    joined = "\n".join(problems)

    assert len(problems) == 8
    assert "Bobcat Hour offering 1 label" in joined
    assert "Bobcat Hour offering 1 location" in joined
    assert "your own Bobcat Hour label" in joined
    assert "your own Bobcat Hour location" in joined
    assert "block 'p1' learning goal is 91 characters and 90 fit" in joined
    assert "block 'p1' success criterion 2 is 41 characters and 40 fit" in joined
    assert "block 'p1' work item 1 name is 35 characters and 34 fit" in joined
    assert "block 'p1' work item 1 detail is 45 characters and 44 fit" in joined


def test_a_plan_that_fits_reports_nothing():
    assert schema.validate_day_plan(schema.parse_day_plan(_plan_data())) == []


# ------------------------------------------------------------- pure parsing


def test_unknown_format_is_rejected_by_name():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(format="canvasexpert.day_plan/2"))

    assert schema.DAY_PLAN_FORMAT in str(err.value)
    assert "canvasexpert.day_plan/2" in str(err.value)


def test_same_day_override_is_read_from_the_plan():
    plan = schema.parse_day_plan(_plan_data(day_type_override="pep_rally"))

    assert plan.day_type_override == "pep_rally"


def test_a_bad_date_says_what_form_to_use():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(date="9/14/2099"))

    assert "9/14/2099" in str(err.value)
    assert "YYYY-MM-DD" in str(err.value)


def test_a_work_item_with_no_name_names_the_block_and_the_item():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(sections={
            "p2": {"work": [{"name": "Vocabulary check 3"}, {"detail": "no name here"}]},
        }))

    assert str(err.value).endswith("block 'p2' work item 2 has no name")


def test_an_offering_with_no_label_is_reported():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(school_wide={
            "bobcat_hour_offerings": [{"location": "Rm 214"}],
        }))

    assert "offering 1 has no label" in str(err.value)


def test_success_criteria_must_be_a_list():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(sections={
            "p1": {"success_criteria": "Name the point of view"},
        }))

    assert "success_criteria" in str(err.value)
    assert "block 'p1'" in str(err.value)


def test_sections_must_pair_a_block_id_with_a_plan():
    with pytest.raises(schema.DayPlanError) as err:
        schema.parse_day_plan(_plan_data(sections=["p1", "p2"]))

    assert "block id" in str(err.value)


def test_missing_optional_parts_default_to_empty():
    plan = schema.parse_day_plan({
        "format": schema.DAY_PLAN_FORMAT,
        "date": "2099-09-14",
    })

    assert plan.school_wide.events == ()
    assert plan.school_wide.bobcat_hour_offerings == ()
    assert plan.teacher_bobcat_hour is None
    assert plan.sections == {}
    assert plan.day_type_override is None
    assert plan.is_sample is False


def test_a_blank_teacher_label_means_nothing_is_happening_here():
    plan = schema.parse_day_plan(_plan_data(
        teacher={"bobcat_hour_here": {"label": "", "location": ""}},
    ))

    assert plan.teacher_bobcat_hour is None


def test_inline_comment_keys_are_documentation_not_data():
    plan = schema.parse_day_plan(_plan_data(**{
        "_comment": "explains the file",
        "sections": {
            "_comment_sections": "explains the sections",
            "p1": {"learning_goal": "Read the opening two pages"},
        },
    }))

    assert set(plan.sections) == {"p1"}
