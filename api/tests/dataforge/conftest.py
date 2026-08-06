"""Shared fixtures for the DataForge test suite.

CRITICAL: the repo .gitignore blocks *.xlsx unconditionally, so any
committed .xlsx fixture would be silently untracked. Every fixture below is
therefore built in code with openpyxl into pytest's tmp_path, never written
to the repo, and contains only obviously-synthetic data (fake names like
"Test Student One", made-up IDs).

Layout notes (Excel is 1-indexed; the reader indexes the same sheet from 0):

  Excel row 1 (row 0), col F: merged assessment title.
  Excel row 2 (row 1), col F: merged report-type label (the F2
      discriminator). Same row, columns after the standard codes: summary
      column headers (Raw Score, Scale Score, Percent Score, ...).
  Excel row 3 (row 2), col F+: standard/RC codes.
  Column A is merged from Excel row 2 down through the last header row
      (A2:A3 for the two breakdown-table layouts, A2:A6 for Individual
      Responses), which is exactly what dataforge.eduphoria_parser's
      _data_start_row() helper inspects to find where student rows begin.
"""

import json

import openpyxl
import pytest

from api.dataforge import identity
from api.feedback_vault import Vault
from api.platform_services import workspace


@pytest.fixture(autouse=True)
def _isolate_canvasexpert_workspace(tmp_path, monkeypatch):
    """Give path resolution a synthetic workspace for every DataForge test."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path / "CanvasExpert"))


def _touch(ws, row, col):
    """Write a placeholder value into a cell purely to force the reader to
    include that row. dataforge.tabular
    silently drops trailing rows whose only content is an empty string (they
    round-trip to all-NaN and get trimmed), so a *non-empty* marker value is
    required here - an empty string is not enough."""
    ws.cell(row=row, column=col, value="x")


def _save(wb, tmp_path, name):
    path = tmp_path / name
    wb.save(path)
    return path


def build_breakdown_workbook(
    tmp_path,
    filename,
    report_label,
    codes,
    student_scores,
    title="May 2026 STAAR Reading Language Arts, Grade 7",
):
    """Build a synthetic 'Learning Standard' or 'Reporting Category' export.

    codes: list of standard/RC code strings placed in the code row.
    student_scores: list of score lists (one list of floats per student,
        aligned with `codes`).
    """
    wb = openpyxl.Workbook()
    ws = wb.active

    ws.cell(row=1, column=6, value=title)
    ws.cell(row=2, column=6, value=report_label)

    for i, code in enumerate(codes):
        ws.cell(row=3, column=6 + i, value=code)

    summary_start = 6 + len(codes)
    summary_labels = [
        "Raw Score", "Scale Score", "Percent Score",
        "Approaches Grade Level (TX)", "Meets Grade Level (TX)", "Masters Grade Level (TX)",
    ]
    for i, label in enumerate(summary_labels):
        ws.cell(row=2, column=summary_start + i, value=label)

    # Column A merged across the header rows (A2:A3) -> data starts at
    # row 3 (Excel row 4).
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)

    for s_idx, scores in enumerate(student_scores):
        r = 4 + s_idx
        ws.cell(row=r, column=1, value=f"Test Student {s_idx + 1}")
        ws.cell(row=r, column=2, value=1001 + s_idx)
        ws.cell(row=r, column=3, value="N")
        ws.cell(row=r, column=4, value="N")
        ws.cell(row=r, column=5, value="H")
        for i, score in enumerate(scores):
            ws.cell(row=r, column=6 + i, value=score)
        raw = sum(1 for v in scores if v >= 1.0)
        pct = sum(scores) / len(scores) if scores else 0.0
        ws.cell(row=r, column=summary_start, value=raw)
        ws.cell(row=r, column=summary_start + 1, value=1600)
        ws.cell(row=r, column=summary_start + 2, value=round(pct, 4))
        ws.cell(row=r, column=summary_start + 3, value="Y" if pct >= 0.6 else "N")
        ws.cell(row=r, column=summary_start + 4, value="N")
        ws.cell(row=r, column=summary_start + 5, value="N")

    return _save(wb, tmp_path, filename)


@pytest.fixture
def learning_standard_path(tmp_path):
    return build_breakdown_workbook(
        tmp_path,
        "learning_standard.xlsx",
        "All Learning Standards",
        codes=["7.2(B) [R]", "7.3(A) [S]"],
        student_scores=[[1.0, 0.5]],
    )


@pytest.fixture
def reporting_category_path(tmp_path):
    return build_breakdown_workbook(
        tmp_path,
        "reporting_category.xlsx",
        "All RCs",
        codes=["R1", "R2"],
        student_scores=[[1.0, 0.88]],
    )


@pytest.fixture
def unrecognized_f2_path(tmp_path):
    """A file that looks like an Eduphoria export (title present, enough
    rows/cols) but whose F2 report-type label is not one DataForge knows
    about. detect_report_type() must return None and pick_parser() must
    fall back to the legacy looks_like_eduphoria() heuristic instead of
    raising."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=6, value="Some Assessment Title")
    ws.cell(row=2, column=6, value="Some Other Report Type")
    # A third row so looks_like_eduphoria()'s shape[0] >= 3 check passes.
    _touch(ws, 3, 6)
    return _save(wb, tmp_path, "unrecognized.xlsx")


@pytest.fixture
def zero_standards_path(tmp_path):
    """Recognized as 'All Learning Standards' via F2, but the code row (Excel
    row 3) has no bracketed standard codes at all -> _extract_metadata must
    find zero standards and raise ValueError."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=6, value="Some Title")
    ws.cell(row=2, column=6, value="All Learning Standards")
    # Touch row 3 so it exists in the dataframe, but leave the code cell
    # (column F / index 5) blank -> zero standards detected.
    _touch(ws, 3, 6)
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)
    return _save(wb, tmp_path, "zero_standards.xlsx")


@pytest.fixture
def individual_responses_path(tmp_path):
    """Build a synthetic 'Student Individual Responses' export.

    Two items, each its own standard:
      col F (item 1): type 'Correct/Incorrect' (max 1), TEKS '7.2(B) [R]'
      col G (item 2): type '0 to 2' (max 2), TEKS '7.3(A) [S]'

    Column A merged A2:A6 -> data starts at row 6 (Excel row 7).
    One student: full credit on item 1 ('+D'), half credit on item 2
    ('+1' out of max 2), so '7.3(A) [S]' should show up as missed at 0.5
    and '7.2(B) [R]' should be mastered (absent from missed_standards).
    """
    wb = openpyxl.Workbook()
    ws = wb.active

    ws.cell(row=1, column=6, value="May 2026 STAAR Reading Language Arts, Grade 7")
    ws.cell(row=2, column=6, value="All Responses")

    # Item number row (row 2) - not read by the parser, kept for realism.
    ws.cell(row=3, column=6, value=1)
    ws.cell(row=3, column=7, value=2)

    # Item type / max-points row (row 3).
    ws.cell(row=4, column=6, value="Correct/Incorrect")
    ws.cell(row=4, column=7, value="0 to 2")

    # RC row (row 4) - not read by the parser, kept for realism.
    ws.cell(row=5, column=6, value="R1")
    ws.cell(row=5, column=7, value="R1")

    # TEKS row (row 5) - the last header row.
    ws.cell(row=6, column=6, value="7.2(B) [R]")
    ws.cell(row=6, column=7, value="7.3(A) [S]")

    ws.merge_cells(start_row=2, start_column=1, end_row=6, end_column=1)

    # Student row (Excel row 7 -> row 6).
    ws.cell(row=7, column=1, value="Test Student One")
    ws.cell(row=7, column=2, value=2002)
    ws.cell(row=7, column=3, value="N")
    ws.cell(row=7, column=4, value="N")
    ws.cell(row=7, column=5, value="H")
    ws.cell(row=7, column=6, value="+D")
    ws.cell(row=7, column=7, value="+1")

    return _save(wb, tmp_path, "individual_responses.xlsx")


@pytest.fixture
def merge_a2_a6_path(tmp_path):
    """A file whose ONLY relevant feature is a column-A merge A2:A6, for
    testing _data_start_row() in isolation."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=6, value="Title")
    ws.merge_cells(start_row=2, start_column=1, end_row=6, end_column=1)
    return _save(wb, tmp_path, "merge_a2_a6.xlsx")


@pytest.fixture
def merge_a2_a3_path(tmp_path):
    """A file whose ONLY relevant feature is a column-A merge A2:A3, for
    testing _data_start_row() in isolation."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=6, value="Title")
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)
    return _save(wb, tmp_path, "merge_a2_a3.xlsx")


@pytest.fixture
def no_merge_path(tmp_path):
    """A plain file with no column-A merge at all, for testing
    _data_start_row()'s fallback-to-default behavior."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=6, value="Title")
    return _save(wb, tmp_path, "no_merge.xlsx")


@pytest.fixture
def vault_identity(tmp_path):
    """Build a synthetic Identity Vault and its parser-facing provider.

    Call with (real_name, sis_id, pseudonym) triples. Written under tmp_path,
    never the repo, and every name is obviously fake. This is the only identity
    provider DataForge has after the vault migration, so tests that need a
    student to be pseudonymized go through here rather than building a map file.
    """
    def build(*students):
        entries = {}
        for index, (real_name, sis_id, pseudonym) in enumerate(students, start=1):
            first, _, last = str(pseudonym).partition(" ")
            entries[f"canvas-{index}"] = {
                "pseudonym": pseudonym,
                "pseudo_first": first,
                "pseudo_last": last,
                "real_name": real_name,
                "sis_id": str(sis_id),
                "nicknames": [],
            }
        path = tmp_path / "vault" / "vault.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"by_canvas_id": entries}), encoding="utf-8")
        return identity.VaultIdentity(Vault(str(path)))

    return build
