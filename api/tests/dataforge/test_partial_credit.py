"""Fix 3: partial credit was being rounded up to full credit whenever the
'+'-prefixed payload wasn't a bare float (e.g. "+SCR 1/2" was scored 1.0
instead of 0.5), because float("SCR 1/2") raised and the except-branch
awarded max_points. The fixed resolution order is: explicit n/m fraction,
then bare-float-over-max_points, then non-numeric = full credit.
"""

import pytest

from api.dataforge.eduphoria_parser import StudentResponsesParser

_score = StudentResponsesParser._score_from_cell


@pytest.mark.parametrize(
    "cell, max_points, expected",
    [
        ("+SCR 2/2", 2, 1.0),
        ("+SCR 1/2", 2, 0.5),          # the regression this fix targets
        ("+Multiselect 1/2", 2, 0.5),  # same regression, different item type
        ("+10", 10, 1.0),
        ("+5", 10, 0.5),
        ("+D", 1, 1.0),
        ("F", 1, 0.0),                 # non-'+' cells always stay 0.0
    ],
)
def test_score_from_cell_matches_spec_table(cell, max_points, expected):
    assert _score(cell, max_points) == expected


def test_score_from_cell_clamps_to_unit_interval():
    # A fraction or bare number that somehow exceeds max_points must clamp.
    assert _score("+3/2", 1) == 1.0
    assert _score("+999", 10) == 1.0


def test_score_from_cell_guards_zero_denominator():
    assert _score("+SCR 1/0", 1) == 1.0


def test_score_from_cell_blank_and_missing():
    """An unanswered item is not a wrong answer, so a blank must stay None
    rather than collapsing to a zero score."""
    assert _score(None, 1) is None
    assert _score("", 1) is None
    assert _score("   ", 1) is None
    assert _score(float("nan"), 1) is None
