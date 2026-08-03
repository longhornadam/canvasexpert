"""Fix 5: header depth is derived from the vertical merge on column A rather
than hardcoded row offsets. An A2:A6 merge (Individual Responses) means
student data starts at pandas row 6; an A2:A3 merge (the two breakdown
tables) means it starts at pandas row 3. No merge at all falls back to the
caller-supplied default.
"""

from api.dataforge.eduphoria_parser import _data_start_row


def test_data_start_row_a2_a6_merge(merge_a2_a6_path):
    assert _data_start_row(merge_a2_a6_path, default=999) == 6


def test_data_start_row_a2_a3_merge(merge_a2_a3_path):
    assert _data_start_row(merge_a2_a3_path, default=999) == 3


def test_data_start_row_falls_back_without_merge(no_merge_path):
    assert _data_start_row(no_merge_path, default=42) == 42


def test_data_start_row_falls_back_on_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.xlsx"
    assert _data_start_row(missing, default=7) == 7
