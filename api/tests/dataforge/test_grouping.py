import pytest

from api.dataforge.grouping import GroupingValidationError, build_grouping_proposal


GROUP_SET = {
    "category_id": "category-1",
    "groups": [
        {"id": "group-support", "name": "Support"},
        {"id": "group-core", "name": "Core"},
        {"id": "group-accelerate", "name": "Accelerate"},
        {"id": "group-extend", "name": "Extend"},
    ],
}

ROSTER = [
    {"id": "canvas-1", "name": "Synthetic One", "sis_user_id": "SIS-1"},
    {"id": "canvas-2", "name": "Synthetic Two", "sis_user_id": "SIS-2"},
    {"id": "canvas-3", "name": "Synthetic Three", "sis_user_id": "SIS-3"},
    {"id": "canvas-4", "name": "Synthetic Four", "sis_user_id": "SIS-4"},
    {"id": "canvas-5", "name": "Synthetic Five", "sis_user_id": "SIS-5"},
]

COVERAGE = {
    "rows": [
        {"pseudonym": "Student_001", "canvas_id": "canvas-1", "canvas_name": "Synthetic One", "status": "matched"},
        {"pseudonym": "Student_002", "canvas_id": "canvas-2", "canvas_name": "Synthetic Two", "status": "matched"},
        {"pseudonym": "Student_003", "canvas_id": "canvas-3", "canvas_name": "Synthetic Three", "status": "matched"},
        {"pseudonym": "Student_004", "canvas_id": "canvas-4", "canvas_name": "Synthetic Four", "status": "matched"},
    ]
}

SNAPSHOT = {
    "id": "synthetic-benchmark",
    "label": "Synthetic Benchmark",
    "students": [
        {"n": "Student_001", "pct": 42, "app": "n", "met": "n", "mas": "n"},
        {"n": "Student_002", "pct": 66, "app": "y", "met": "n", "mas": "n"},
        {"n": "Student_003", "pct": 82, "app": "y", "met": "y", "mas": "n"},
        {"n": "Student_004", "pct": 96, "app": "y", "met": "y", "mas": "y"},
    ],
}


def test_overall_proposal_covers_every_roster_student_and_requires_no_data_choice():
    proposal = build_grouping_proposal(
        SNAPSHOT,
        COVERAGE,
        ROSTER,
        GROUP_SET,
        no_data_group="Core",
    )

    assert [tier["name"] for tier in proposal["tiers"]] == ["Support", "Core", "Accelerate", "Extend"]
    assert [tier["student_count"] for tier in proposal["tiers"]] == [1, 2, 1, 1]
    assert proposal["no_data_count"] == 1
    assert {row["canvas_id"] for row in proposal["placements"]} == {row["id"] for row in ROSTER}
    assert proposal["proposal_digest"]

    with pytest.raises(GroupingValidationError, match="no-data"):
        build_grouping_proposal(SNAPSHOT, COVERAGE, ROSTER, GROUP_SET)


def test_staar_bands_use_highest_matching_band_and_quartiles_are_deterministic():
    staar = build_grouping_proposal(
        SNAPSHOT, COVERAGE, ROSTER, GROUP_SET,
        method="staar_bands", no_data_group="Support",
    )
    assert {row["canvas_id"]: row["group"] for row in staar["placements"]} == {
        "canvas-1": "Support", "canvas-2": "Core", "canvas-3": "Accelerate",
        "canvas-4": "Extend", "canvas-5": "Support",
    }

    quartiles = build_grouping_proposal(
        SNAPSHOT, COVERAGE, ROSTER, GROUP_SET,
        method="quartiles", no_data_group="Core",
    )
    assert {row["canvas_id"]: row["group"] for row in quartiles["placements"]} == {
        "canvas-1": "Support", "canvas-2": "Core", "canvas-3": "Accelerate",
        "canvas-4": "Extend", "canvas-5": "Core",
    }


def test_staar_bands_reject_a_snapshot_with_no_band_columns():
    """A breakdown export with no TX band columns places everyone in Support.
    Say that the method is wrong for this snapshot rather than reporting three
    empty tiers, which describes the symptom and not the cause."""
    no_bands = {
        **SNAPSHOT,
        "students": [
            {key: value for key, value in student.items() if key not in ("app", "met", "mas")}
            for student in SNAPSHOT["students"]
        ],
    }
    with pytest.raises(GroupingValidationError, match="no STAAR performance bands"):
        build_grouping_proposal(
            no_bands, COVERAGE, ROSTER, GROUP_SET,
            method="staar_bands", no_data_group="Support",
        )


def test_staar_bands_still_work_when_only_some_students_have_bands():
    """One band column anywhere means the snapshot carries band data; a student
    with none of them is a legitimate 'did not approach', not a missing column."""
    partial = {
        **SNAPSHOT,
        "students": [
            SNAPSHOT["students"][0],
            {"n": "Student_002", "pct": 66, "app": "y"},
            {"n": "Student_003", "pct": 82, "met": "y"},
            {"n": "Student_004", "pct": 96, "mas": "y"},
            *SNAPSHOT["students"][4:],
        ],
    }
    proposal = build_grouping_proposal(
        partial, COVERAGE, ROSTER, GROUP_SET,
        method="staar_bands", no_data_group="Support",
    )
    assert {row["canvas_id"]: row["group"] for row in proposal["placements"]} == {
        "canvas-1": "Support", "canvas-2": "Core", "canvas-3": "Accelerate",
        "canvas-4": "Extend", "canvas-5": "Support",
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"cutoffs": {"support": 75, "core": 60, "accelerate": 90}}, "strictly increasing"),
        ({"group_set": {"category_id": "category-1", "groups": [{"id": "one", "name": "Support"}]}}, "contain"),
    ],
)
def test_invalid_proposals_are_rejected(change, message):
    kwargs = {"no_data_group": "Core"}
    snapshot = SNAPSHOT
    coverage = COVERAGE
    roster = ROSTER
    group_set = GROUP_SET
    if "cutoffs" in change:
        kwargs["cutoffs"] = change["cutoffs"]
    else:
        group_set = change["group_set"]
    with pytest.raises(GroupingValidationError, match=message):
        build_grouping_proposal(snapshot, coverage, roster, group_set, **kwargs)
