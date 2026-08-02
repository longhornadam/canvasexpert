"""Focused validation coverage for PowerGrader's shared persona/pattern library."""

from api.webui.routes import feedback_library


def _pattern(**overrides):
    pattern = {
        "id": "custom_pattern", "name": "Custom pattern", "score_from_rubric": True,
        "glows": {"min": 1, "max": 2}, "grows": {"min": 1, "max": 2},
        "strategy_sentences": {"min": 1, "max": 2}, "sign_with_persona": True,
    }
    pattern.update(overrides)
    return pattern


def test_pattern_editor_reuses_library_validation():
    assert feedback_library._validate_patterns([_pattern()]) is None
    assert feedback_library._validate_patterns([_pattern(), _pattern()])
    assert feedback_library._validate_patterns([_pattern(glows={"min": 3, "max": 1})])
    assert feedback_library._validate_patterns([_pattern(id="Not Safe")])


def test_custom_persona_ids_are_constrained_to_config_safe_names():
    assert feedback_library._valid_persona_id("custom_sage_2") is True
    assert feedback_library._valid_persona_id("Custom Sage") is False
