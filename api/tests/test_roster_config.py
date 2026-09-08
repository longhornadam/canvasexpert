"""Offline tests for Roster Console config helpers."""
import pytest

from api.platform_services import config


@pytest.fixture(autouse=True)
def isolated_roster_settings(monkeypatch):
    state = {"roster_student_settings": {}}

    def fake_synced_state():
        return state

    def fake_save_synced_key(key, value):
        state[key] = value

    def fake_modify_synced(mutator):
        updated = mutator(state)
        if updated is not None:
            state.clear()
            state.update(updated)
        return state

    monkeypatch.setattr(config._io, "_synced_state", fake_synced_state)
    monkeypatch.setattr(config._io, "_save_synced_key", fake_save_synced_key)
    monkeypatch.setattr(config._io, "_modify_synced", fake_modify_synced)


def test_get_returns_empty_for_unknown_course():
    result = config.get_roster_student_settings("99999")
    assert result == {}


def test_set_and_get_roundtrip():
    settings = {
        "101": {"tier": "Support"},
        "102": {"tier": "Core", "planned_group": {"category_id": "1", "group_id": "2"}},
    }
    config.set_roster_student_settings("100", settings)

    result = config.get_roster_student_settings("100")
    assert result == settings
    assert config.get_roster_student_settings("200") == {}


def test_update_patches_one_student():
    config.set_roster_student_settings("100", {
        "101": {"tier": "Support"},
        "102": {"tier": "Core"},
    })

    config.update_roster_student_settings("100", "101", {"tier": "Accelerate"})

    result = config.get_roster_student_settings("100")
    assert result["101"]["tier"] == "Accelerate"
    assert result["102"]["tier"] == "Core"


def test_update_adds_new_student():
    config.set_roster_student_settings("100", {"101": {"tier": "Support"}})

    config.update_roster_student_settings("100", "103", {"tier": "Extend"})

    result = config.get_roster_student_settings("100")
    assert result["101"]["tier"] == "Support"
    assert result["103"]["tier"] == "Extend"


def test_update_removes_key_when_none():
    config.set_roster_student_settings("100", {
        "101": {"tier": "Support", "planned_group": {"cat": "1"}},
    })

    config.update_roster_student_settings("100", "101", {"planned_group": None})

    result = config.get_roster_student_settings("100")
    assert "planned_group" not in result["101"]
    assert result["101"]["tier"] == "Support"


def test_classroom_profile_round_trip_and_clear_preserves_other_settings():
    profile = {
        "birthday": "09-08",
        "celebrations": [{
            "id": "celebration-1", "label": "Helpful teammate",
            "start": "2026-09-08", "end": "2026-09-12",
        }],
    }
    config.set_roster_student_settings("100", {"101": {"tier": "Support"}})
    config.update_roster_student_settings("100", "101", {"classroom_profile": profile})
    assert config.get_roster_student_settings("100")["101"]["classroom_profile"] == profile

    config.update_roster_student_settings("100", "101", {"classroom_profile": None})
    result = config.get_roster_student_settings("100")["101"]
    assert "classroom_profile" not in result
    assert result["tier"] == "Support"


@pytest.mark.parametrize("profile", [
    {"birthday": "2026-09-08", "celebrations": []},
    {"birthday": "02-30", "celebrations": []},
    {"birthday": "", "celebrations": [{"id": "x", "label": "<b>bad</b>", "start": "2026-09-08", "end": "2026-09-08"}]},
    {"birthday": "", "celebrations": [{"id": "x", "label": "Bad", "start": "2026-09-09", "end": "2026-09-08"}]},
    {"birthday": "", "celebrations": [{"id": "x", "label": "One", "start": "2026-09-08", "end": "2026-09-08"}, {"id": "x", "label": "Two", "start": "2026-09-09", "end": "2026-09-09"}]},
])
def test_classroom_profile_rejects_invalid_values(profile):
    with pytest.raises(ValueError):
        config.validate_classroom_profile(profile)


def test_score_matrix_round_trip_is_course_scoped():
    first = {
        "columns": [{"id": "score-writing", "label": "Writing"}],
        "values_by_section": {"section-a": {"student-a": {"score-writing": 12.5}}},
    }
    second = {
        "columns": [{"id": "score-reading", "label": "Reading"}],
        "values_by_section": {},
    }

    assert config.get_roster_score_matrix("missing") == config.ROSTER_SCORE_MATRIX_DEFAULT
    config.set_roster_score_matrix("course-a", first)
    config.set_roster_score_matrix("course-b", second)

    assert config.get_roster_score_matrix("course-a") == first
    assert config.get_roster_score_matrix("course-b") == second
    assert "roster_score_matrices" in config.SYNCED_KEYS


def test_relationships_round_trip_is_course_scoped():
    first = {"by_section": {"section-a": [{
        "student_a": "student-a", "student_b": "student-b",
        "type": "keep_apart", "reason": "private",
    }]}}
    second = {"by_section": {}}

    assert config.get_roster_relationships("missing") == config.ROSTER_RELATIONSHIPS_DEFAULT
    config.set_roster_relationships("course-a", first)
    config.set_roster_relationships("course-b", second)

    assert config.get_roster_relationships("course-a") == first
    assert config.get_roster_relationships("course-b") == second
    assert "roster_relationships" in config.SYNCED_KEYS


def test_roster_baseline_round_trip_is_course_scoped():
    first = {"acknowledged_at": "2026-08-01T00:00:00", "students": {"101": ["44"]}}
    second = {"acknowledged_at": "2026-08-02T00:00:00", "students": {}}

    assert config.get_roster_baseline("missing") == config.ROSTER_BASELINE_DEFAULT
    config.set_roster_baseline("course-a", first)
    config.set_roster_baseline("course-b", second)

    assert config.get_roster_baseline("course-a") == first
    assert config.get_roster_baseline("course-b") == second
    assert "roster_baselines" in config.SYNCED_KEYS


def test_courses_are_independent():
    config.set_roster_student_settings("100", {"101": {"tier": "Support"}})
    config.set_roster_student_settings("200", {"201": {"tier": "Core"}})

    r1 = config.get_roster_student_settings("100")
    r2 = config.get_roster_student_settings("200")
    assert "201" not in r1
    assert "101" not in r2


def test_replace_overwrites_course():
    config.set_roster_student_settings("100", {"101": {"tier": "Support"}})
    config.set_roster_student_settings("100", {"102": {"tier": "Core"}})

    result = config.get_roster_student_settings("100")
    assert "101" not in result
    assert result["102"]["tier"] == "Core"


def test_valid_tier_names():
    assert "Support" in config.TIER_NAMES
    assert "Core" in config.TIER_NAMES
    assert "Accelerate" in config.TIER_NAMES
    assert "Extend" in config.TIER_NAMES
    assert "" not in config.TIER_NAMES
    assert len(config.TIER_NAMES) == 4


# --------------------------------------------------------------------------
# V2 Tier scheme tests
# --------------------------------------------------------------------------


def test_default_scheme_has_three_tiers():
    scheme = config.ROSTER_DEFAULT_TIER_SCHEME
    assert len(scheme) == 3
    ids = [t["id"] for t in scheme]
    assert ids == ["support", "core", "extend"]
    assert scheme[0]["alias"] == "Blue"
    assert scheme[1]["alias"] == "Red"
    assert scheme[2]["alias"] == "White"


def test_default_tier_scheme_returned_for_unknown_course():
    cid = "test_default_fallback"
    scheme = config.get_roster_tier_scheme(cid)
    assert len(scheme) == 3
    assert scheme[0]["id"] == "support"


def test_set_and_get_tier_scheme_roundtrip():
    cid = "roundtrip_course"
    custom = [
        {"id": "low", "teacher_label": "Low", "meaning": "below", "alias": "Gray", "order": 5, "active": True},
        {"id": "high", "teacher_label": "High", "meaning": "above", "alias": "Gold", "order": 25, "active": True},
    ]
    config.set_roster_tier_scheme(cid, custom)
    result = config.get_roster_tier_scheme(cid)
    assert len(result) == 2
    assert result[0]["id"] == "low"
    assert result[0]["alias"] == "Gray"
    assert result[1]["id"] == "high"


def test_tier_scheme_courses_are_independent():
    config.set_roster_tier_scheme("course_a", config.ROSTER_DEFAULT_TIER_SCHEME)
    config.set_roster_tier_scheme("course_b", [{"id": "x", "teacher_label": "X", "alias": "X", "order": 1, "active": True}])
    a = config.get_roster_tier_scheme("course_a")
    b = config.get_roster_tier_scheme("course_b")
    assert len(a) == 3
    assert len(b) == 1
    assert b[0]["id"] == "x"


def test_validate_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="Duplicate"):
        config.set_roster_tier_scheme("dup_test", [
            {"id": "a", "teacher_label": "A", "alias": "One", "order": 1, "active": True},
            {"id": "a", "teacher_label": "B", "alias": "Two", "order": 2, "active": True},
        ])


def test_validate_rejects_blank_alias():
    with pytest.raises(ValueError, match="blank"):
        config.set_roster_tier_scheme("alias_test", [
            {"id": "x", "teacher_label": "X", "alias": "", "order": 1, "active": True},
        ])


def test_validate_rejects_blank_label():
    with pytest.raises(ValueError, match="teacher_label"):
        config.set_roster_tier_scheme("label_test", [
            {"id": "x", "teacher_label": "", "alias": "X", "order": 1, "active": True},
        ])


def test_roster_tier_by_id():
    cid = "by_id_test"
    config.set_roster_tier_scheme(cid, [
        {"id": "a", "teacher_label": "A", "alias": "A1", "order": 1, "active": True},
        {"id": "b", "teacher_label": "B", "alias": "B1", "order": 2, "active": False},
    ])
    by_id = config.roster_tier_by_id(cid)
    assert by_id["a"]["alias"] == "A1"
    assert by_id["b"]["alias"] == "B1"
    assert by_id["b"]["active"] is False


def test_validate_requires_non_empty_scheme():
    with pytest.raises(ValueError, match="non-empty"):
        config.set_roster_tier_scheme("empty_test", [])
