"""Fix 6: previously, finding zero standards only appended a warning to
validation_issues and kept going - which is how the Reporting Category file
used to emit a full set of artifacts claiming "All students mastered all
listed standards" and wrote a bogus growth snapshot. Zero standards must now
be a hard failure (ValueError), which webui.process() already catches
per-file so one bad file doesn't kill the whole run.
"""

import pytest

from api.dataforge.eduphoria_parser import pick_parser


def test_zero_standards_raises_value_error(zero_standards_path):
    parser, label = pick_parser(zero_standards_path)
    assert label == "Student Learning Standard Breakdown"
    with pytest.raises(ValueError):
        parser.parse()
