"""Fix 2: Reporting Category support, parameterized on EducationDataParser
rather than a new parser class. Verifies 2 standards are found (not 0), the
standard type is reported as "Reporting Category" (not Readiness/Supporting),
and canonical codes get the "RC:" prefix so they can never collide with a
TEKS code in the cross-assessment rollup.
"""

from api.dataforge.eduphoria_parser import pick_parser, create_teacher_report


def test_reporting_category_yields_two_standards(reporting_category_path):
    parser, _ = pick_parser(reporting_category_path)
    data = parser.parse()
    assert data.metadata["num_standards"] == 2
    assert set(data.metadata["standards"]) == {"R1", "R2"}


def test_reporting_category_std_type_and_canonical_prefix(reporting_category_path):
    parser, _ = pick_parser(reporting_category_path)
    data = parser.parse()
    by_code = {a.standard_code: a for a in data.standard_analysis}
    assert by_code["R1"].standard_type == "Reporting Category"
    assert by_code["R2"].standard_type == "Reporting Category"
    assert by_code["R1"].canonical_code == "RC:R1"
    assert by_code["R2"].canonical_code == "RC:R2"


def test_reporting_category_does_not_falsely_report_full_mastery(reporting_category_path):
    parser, _ = pick_parser(reporting_category_path)
    data = parser.parse()
    report = create_teacher_report(data)
    assert "All students mastered all listed standards." not in report
