"""Fix 4: _parse_max_points used a mistaken r"\\.\\d+" in its regex (a
literal backslash-dot, not an escaped decimal point), so "0 to 2.5" matched
digits "0", "2", "5" separately and returned 5.0 instead of 2.5.
"""

import pytest

from api.dataforge.eduphoria_parser import StudentResponsesParser

_max_points = StudentResponsesParser._parse_max_points


@pytest.mark.parametrize(
    "label, expected",
    [
        ("0 to 2.5", 2.5),          # the regression this fix targets
        ("Correct/Incorrect", 1.0),
        ("Partial (0-1-2)", 2.0),
        ("0 to 10", 10.0),
    ],
)
def test_parse_max_points(label, expected):
    assert _max_points(label) == expected
