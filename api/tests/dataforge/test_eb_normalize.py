"""Fix 7: _normalize_eb() truncated "Other Non-Emergent Bilingual Student" to
the 6-char string "other " because no branch recognized "non-emergent"
before falling through to the generic 6-char fallback. A "non-emergent" /
"non emergent" check placed before the monitor/former checks fixes it while
keeping every existing mapping intact.
"""

import pytest

from api.dataforge.eduphoria_parser import EducationDataParser

_norm = EducationDataParser._normalize_eb


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Other Non-Emergent Bilingual Student", "n"),  # the regression this fix targets
        ("No", "n"),
        ("Yes", "y"),
        ("EB", "y"),
        ("Monitored 1st Year", "1st"),
        ("Monitored 2nd Year", "2nd"),
        ("Former EB", "fmr"),
        ("", "n"),
    ],
)
def test_normalize_eb(value, expected):
    assert _norm(value) == expected
