"""An ID cell must render as a stable string.

Historically a single blank cell anywhere in an otherwise-integer ID column
made the reader promote the whole column to float, turning 696969 into
696969.0 and silently re-keying the anonymizer. The current reader types cells
individually so that promotion cannot happen, but _clean_id() still normalizes
an integral float, because a caller can hand one in from anywhere.
"""

from api.dataforge.eduphoria_parser import _clean_id


def test_clean_id_normalizes_an_integral_float():
    assert _clean_id(696969.0) == "696969"
    assert _clean_id(123456.0) == "123456"


def test_clean_id_blank_and_none():
    assert _clean_id(None) == ""
    assert _clean_id(float("nan")) == ""


def test_clean_id_non_integral_float_kept():
    assert _clean_id(696969.5) == "696969.5"


def test_clean_id_plain_string_stripped():
    assert _clean_id("  ID-042  ") == "ID-042"


def test_clean_id_plain_int():
    assert _clean_id(696969) == "696969"
