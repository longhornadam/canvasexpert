"""The fail-closed identity guardrails on DataForge's generated artifacts.

Every artifact is scanned before it is returned, not just the JSON: the teacher
report lists students under each missed standard and the parent narratives are
one block per student, so both carry more identity surface than the JSON.

These are the vault-backed versions of the checks the retired `NameAnonymizer`
carried. The map-file tests died with the map; the leak rules did not, because
`assert_no_leaks` still runs on every artifact and now receives a
`VaultIdentity`.
"""

import pytest

from api.dataforge.eduphoria_parser import (
    assert_no_leaks,
    convert_to_json,
    create_parent_narratives,
    create_teacher_report,
    pick_parser,
)

REAL_NAME = "Clauderino, Claude"
REAL_ID = "696969"


# --- leak detection ------------------------------------------------------


def test_detect_leaks_catches_reversed_name_order(vault_identity):
    """Eduphoria stores 'Last, First'. A report rendering 'First Last' is still
    a leak, and an exact check on the stored form misses it."""
    provider = vault_identity((REAL_NAME, REAL_ID, "Sparky McGee"))
    assert provider.detect_leaks("scores for Claude Clauderino follow")
    assert provider.detect_leaks("scores for Clauderino, Claude follow")


def test_detect_leaks_is_case_insensitive(vault_identity):
    provider = vault_identity((REAL_NAME, REAL_ID, "Sparky McGee"))
    assert provider.detect_leaks("CLAUDE CLAUDERINO")


def test_detect_leaks_ignores_short_ids(vault_identity):
    """A 2-3 digit local ID collides with ordinary report content such as a raw
    score, and a false positive blocks a legitimate run."""
    provider = vault_identity((REAL_NAME, "53", "Sparky McGee"))
    assert provider.detect_leaks("Raw Score: 53") == []


def test_detect_leaks_finds_long_ids_but_not_substrings(vault_identity):
    """The Local ID is the join key between the safe profile and a real student,
    so it must never survive into an artifact."""
    provider = vault_identity((REAL_NAME, REAL_ID, "Sparky McGee"))
    assert provider.detect_leaks("local id 696969 present")
    assert provider.detect_leaks("value 12696969000") == []


def test_detect_leaks_does_not_fire_on_a_clean_artifact(vault_identity):
    provider = vault_identity((REAL_NAME, REAL_ID, "Sparky McGee"))
    assert provider.detect_leaks("Sparky McGee scored 94.6%") == []


def test_detect_leaks_tolerates_a_short_name_fragment(vault_identity):
    """A vault name carrying a middle initial or a numeric suffix must not turn
    every standalone letter or digit in a report into a leak. `assert_no_leaks`
    raises rather than logs, so a false positive here stops the teacher's run
    with an error they cannot act on."""
    provider = vault_identity(("Ruiz, Ana J", "700001", "Sparky McGee"))
    assert provider.detect_leaks("Sparky McGee answered J and scored 1 point") == []
    assert provider.detect_leaks("scores for Ana J Ruiz follow")


# --- every artifact is checked, not just the JSON ------------------------


def _parsed(path, provider, poison_name=None):
    parser, _ = pick_parser(path)
    data = parser.parse()
    data.metadata["_anonymizer"] = provider
    data.metadata["_strip_demographics"] = True
    if poison_name:
        # The assessment name is echoed verbatim into every artifact header, so
        # it is a real path for an identity to reach an output unpseudonymized.
        data.metadata["assessment_name"] = f"Retest for {poison_name}"
    return data


@pytest.fixture
def enrolled(vault_identity):
    """A vault that knows the synthetic workbook's student and one other real
    identity, so a poisoned header is a detectable leak."""
    return vault_identity(
        ("Test Student 1", "1001", "Sparky McGee"),
        (REAL_NAME, REAL_ID, "Blaze Ottersmith"),
    )


def test_assert_no_leaks_is_a_noop_without_a_provider():
    assert assert_no_leaks(REAL_NAME, None, "x") == REAL_NAME


def test_teacher_report_is_leak_checked(learning_standard_path, enrolled):
    data = _parsed(learning_standard_path, enrolled, poison_name="Claude Clauderino")
    with pytest.raises(ValueError, match="teacher report"):
        create_teacher_report(data)


def test_parent_narratives_are_leak_checked(learning_standard_path, enrolled):
    data = _parsed(learning_standard_path, enrolled, poison_name="Claude Clauderino")
    with pytest.raises(ValueError, match="parent narratives"):
        create_parent_narratives(data)


def test_json_is_still_leak_checked(learning_standard_path, enrolled):
    data = _parsed(learning_standard_path, enrolled, poison_name="Claude Clauderino")
    with pytest.raises(ValueError, match="JSON"):
        convert_to_json(data)


def test_a_leaked_local_id_in_a_header_is_caught(learning_standard_path, enrolled):
    """Names are the obvious leak; the Local ID is the one that re-identifies."""
    data = _parsed(learning_standard_path, enrolled, poison_name=REAL_ID)
    with pytest.raises(ValueError, match="JSON"):
        convert_to_json(data)


def test_clean_run_produces_all_three_artifacts(learning_standard_path, enrolled):
    data = _parsed(learning_standard_path, enrolled)
    assert convert_to_json(data)
    assert create_teacher_report(data)
    assert create_parent_narratives(data)
