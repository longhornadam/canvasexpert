"""Fix 1: F2 report-type routing is the root-cause fix - StudentResponsesParser
was permanently shadowed because looks_like_eduphoria() matched every known
Eduphoria export and was checked first. pick_parser() must route on the F2
label first, and only fall back to the legacy heuristics when F2 is
unrecognized.
"""

from api.dataforge.eduphoria_parser import (
    EducationDataParser,
    GenericTabularAssessmentParser,
    StudentResponsesParser,
    pick_parser,
)


def test_learning_standard_routes_to_education_parser(learning_standard_path):
    parser, label = pick_parser(learning_standard_path)
    assert isinstance(parser, EducationDataParser)
    assert parser.breakdown_type == "learning_standard"
    assert label == "Student Learning Standard Breakdown"


def test_reporting_category_routes_to_education_parser(reporting_category_path):
    parser, label = pick_parser(reporting_category_path)
    assert isinstance(parser, EducationDataParser)
    assert parser.breakdown_type == "reporting_category"
    assert label == "Student Reporting Category Breakdown"


def test_individual_responses_routes_to_student_responses_parser(individual_responses_path):
    parser, label = pick_parser(individual_responses_path)
    assert isinstance(parser, StudentResponsesParser)
    assert label == "Student Individual Responses"


def test_unrecognized_f2_falls_back_to_legacy_path_without_raising(unrecognized_f2_path):
    # Must not raise, and must not fall all the way through to the generic
    # parser when the file still shape-matches the legacy Eduphoria heuristic.
    parser, label = pick_parser(unrecognized_f2_path)
    assert isinstance(parser, (EducationDataParser, StudentResponsesParser, GenericTabularAssessmentParser))
    assert isinstance(parser, EducationDataParser)
    assert label == "Eduphoria standard breakdown"
