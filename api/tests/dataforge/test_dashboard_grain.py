"""Fix 2 (dashboard grain guard): Reporting Category and Learning Standard
breakdowns are different grains and must never be compared in the same
cross-assessment rollup bucket (an RC average and a TEKS average are not the
same kind of number). The chosen minimal fix excludes reporting-category
assessments from the cross-standard rollup entirely, rather than reshaping
the dashboard template to add a second table.

This test builds fake per-assessment result dicts directly (the same shape
_process_file() returns) rather than real files, since _build_dashboard()
only needs that shape.
"""

from api.dataforge.views import _build_dashboard


def _fake_result(name, breakdown_type, grade, standards):
    return {
        "assessment_name": name,
        "descriptive": name,
        "grade": grade,
        "type": "STAAR",
        "total_students": 10,
        "avg_pct": 80.0,
        "approaches_pct": 80.0,
        "meets_pct": 60.0,
        "masters_pct": 30.0,
        "breakdown_type": breakdown_type,
        "standards": standards,
    }


def test_reporting_category_excluded_from_cross_standard_rollup():
    learning_standard_result = _fake_result(
        "Gr7 Learning Standards", "learning_standard", "7",
        [
            {"code": "7.2(B) [R]", "canonical": "2(B) [R]", "type": "Readiness", "avg": 90.0, "proficiency": 90.0, "total": 10},
        ],
    )
    reporting_category_result = _fake_result(
        "Gr7 Reporting Categories", "reporting_category", "7",
        [
            {"code": "R1", "canonical": "RC:R1", "type": "Reporting Category", "avg": 40.0, "proficiency": 40.0, "total": 10},
            {"code": "R2", "canonical": "RC:R2", "type": "Reporting Category", "avg": 30.0, "proficiency": 30.0, "total": 10},
        ],
    )

    dash = _build_dashboard([learning_standard_result, reporting_category_result])

    all_canonicals = {s["canonical"] for s in dash["cross"]} | {s["canonical"] for s in dash["single_weak"]}
    rc_codes = {s["canonical"] for s in all_canonicals if s.startswith("RC:")}

    assert rc_codes == set(), "reporting-category canonical codes must not appear in the cross-standard rollup"
    # The learning-standard entry is unaffected and still shows up.
    assert any(c == "2(B) [R]" for c in all_canonicals)


def test_dashboard_handles_all_reporting_category_batch():
    """A batch made entirely of RC assessments should not error, just yield
    an empty cross-standard rollup."""
    rc_only = _fake_result(
        "Gr7 Reporting Categories", "reporting_category", "7",
        [{"code": "R1", "canonical": "RC:R1", "type": "Reporting Category", "avg": 40.0, "proficiency": 40.0, "total": 10}],
    )
    dash = _build_dashboard([rc_only])
    assert dash["cross"] == []
    assert dash["single_weak"] == []
