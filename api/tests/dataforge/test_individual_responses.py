"""Fix 1 + Fix 5 regression: Student Individual Responses used to yield 0
standards and 0 students because it was permanently shadowed by
looks_like_eduphoria() (fixed by F2 routing), and because of hardcoded row
offsets that don't hold once the file is actually parsed by the right class
(fixed by the merge-derived data_start_row helper).
"""

from api.dataforge.eduphoria_parser import pick_parser


def test_individual_responses_yields_standards_and_students(individual_responses_path):
    parser, _ = pick_parser(individual_responses_path)
    data = parser.parse()

    assert data.metadata["num_standards"] == 2
    assert set(data.metadata["standards"]) == {"7.2(B) [R]", "7.3(A) [S]"}
    assert len(data.students) == 1


def test_individual_responses_partial_credit_flows_through(individual_responses_path):
    parser, _ = pick_parser(individual_responses_path)
    data = parser.parse()

    student = data.students[0]
    # Item 1 ('+D', max 1) -> full credit -> mastered -> not in missed_standards.
    assert "7.2(B) [R]" not in student.missed_standards
    # Item 2 ('+1' out of max 2) -> 0.5 -> missed.
    assert student.missed_standards["7.3(A) [S]"] == 0.5
