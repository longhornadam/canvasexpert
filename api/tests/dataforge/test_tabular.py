"""The spreadsheet/CSV reader that replaced pandas.

Two of these behaviors are load-bearing for the parsers and were previously
inherited from pandas rather than chosen: blank normalization and trailing
trim. The third, per-cell typing, is a deliberate departure.
"""

import openpyxl
import pytest

from api.dataforge import tabular
from api.dataforge.eduphoria_parser import GenericTabularAssessmentParser


def _sheet(tmp_path, cells, name="g.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    for (r, c), v in cells.items():
        ws.cell(row=r, column=c, value=v)
    path = tmp_path / name
    wb.save(path)
    return path


# --- blank handling ------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   ", float("nan")])
def test_is_blank_covers_every_empty_form(value):
    assert tabular.is_blank(value)
    assert not tabular.not_blank(value)


@pytest.mark.parametrize("value", [0, 0.0, "0", "x", False])
def test_is_blank_does_not_swallow_real_values(value):
    """A zero score is data, not a missing cell."""
    assert not tabular.is_blank(value)


def test_empty_string_cell_reads_as_blank(tmp_path):
    p = _sheet(tmp_path, {(1, 1): "a", (1, 2): "", (1, 3): "c"})
    g = tabular.read_xlsx(p)
    assert g.iloc[0, 1] is None


# --- trimming ------------------------------------------------------------


def test_trailing_blank_rows_and_columns_are_trimmed(tmp_path):
    """The parsers derive positions from shape, so a sheet must report its
    content extent rather than whatever range the writer touched."""
    p = _sheet(tmp_path, {(1, 1): "a", (1, 2): "b", (4, 1): None, (1, 5): ""})
    assert tabular.read_xlsx(p).shape == (1, 2)


def test_interior_blanks_are_preserved(tmp_path):
    """Only trailing blanks go. A gap in the middle is meaningful."""
    p = _sheet(tmp_path, {(1, 1): "a", (3, 1): "c"})
    g = tabular.read_xlsx(p)
    assert g.shape == (3, 1)
    assert g.iloc[1, 0] is None


def test_leading_blank_columns_are_preserved(tmp_path):
    """Eduphoria puts its title in column F with A-E empty."""
    p = _sheet(tmp_path, {(1, 6): "Title"})
    g = tabular.read_xlsx(p)
    assert g.shape == (1, 6)
    assert g.iloc[0, 5] == "Title"


# --- shape / access ------------------------------------------------------


def test_out_of_range_raises_rather_than_returning_none(tmp_path):
    """A silent None would turn a layout mismatch into a plausible empty result."""
    p = _sheet(tmp_path, {(1, 1): "a"})
    g = tabular.read_xlsx(p)
    with pytest.raises(IndexError):
        g.iloc[5, 0]


def test_nrows_limits_the_read(tmp_path):
    p = _sheet(tmp_path, {(1, 1): "a", (2, 1): "b", (3, 1): "c", (4, 1): "d"})
    assert len(tabular.read_xlsx(p, nrows=2)) == 2


def test_header_mode_names_the_columns(tmp_path):
    p = _sheet(tmp_path, {(1, 1): "Student Name", (1, 2): "Local ID",
                          (2, 1): "Doe, Jane", (2, 2): 42})
    g = tabular.read_xlsx(p, header=0)
    assert g.columns == ["Student Name", "Local ID"]
    assert len(g) == 1
    assert list(g.iterrows())[0][1]["Local ID"] == 42


# --- per-cell typing, the deliberate departure ---------------------------


def test_leading_zero_ids_stay_text():
    """Losing the zero would change which student an ID refers to."""
    assert tabular.coerce("0012345") == "0012345"
    assert tabular.coerce("42") == 42
    assert tabular.coerce("3.5") == 3.5
    assert tabular.coerce("") is None
    assert tabular.coerce("D") == "D"


def test_blank_cell_does_not_retype_its_neighbours(tmp_path):
    """The bug this reader was built to avoid: one blank promoting a whole
    column to float and appending '.0' to every ID in it."""
    p = tmp_path / "ids.csv"
    p.write_text("Student Name,Local ID\nA,696969\nB,\nC,123456\n", encoding="utf-8")
    g = tabular.read_csv(p)
    values = [row["Local ID"] for _, row in g.iterrows()]
    assert values == [696969, None, 123456]


# --- the CSV path through the real parser --------------------------------


def test_generic_parser_reads_a_csv(tmp_path):
    p = tmp_path / "scores.csv"
    p.write_text(
        "Student Name,Local ID,Special Ed,Ethnicity,7.2(B),7.9(D),Percent Score\n"
        "Doe, Jane,696969,No,White,100,50,75\n".replace("Doe, Jane", '"Doe, Jane"'),
        encoding="utf-8",
    )
    data = GenericTabularAssessmentParser(str(p)).parse()
    assert len(data.students) == 1
    s = data.students[0]
    assert s.student_name == "Doe, Jane"
    assert s.local_id == "696969"
    assert s.missed_standards == {"7.9(D)": 0.5}
