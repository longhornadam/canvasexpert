"""Generative day-calendar write tests."""

from pathlib import Path

import pytest

from api.mcp_server import tools
from api.webui import deck_schedule, schedule_setup, workspace


@pytest.fixture
def isolated_schedule_workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    calendars = root / "Library" / "Calendars"
    calendars.mkdir(parents=True)
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(
        workspace, "library_folder", lambda name: str(root / "Library" / name)
    )
    monkeypatch.setattr(workspace, "system_folder", lambda name: str(root / "_System" / name))
    for filename, periods in (
        ("Bell Schedule Ordinary.csv", [("1", "08:00", "08:45"), ("2", "08:50", "09:35")]),
        ("Bell Schedule Short.csv", [("1", "09:00", "09:40"), ("2", "09:45", "10:25")]),
    ):
        lines = ["period_id,start,end"]
        lines.extend(",".join(row) for row in periods)
        (calendars / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root, calendars


def _ordinary_id():
    return "bell_schedule_ordinary"


def _short_id():
    return "bell_schedule_short"


def _read_day_calendar(path: Path):
    mapping, problems = deck_schedule.parse_day_calendar(path.read_text(encoding="utf-8"))
    assert problems == []
    return mapping


def test_save_day_calendar_excludes_weekends_and_uses_precedence(isolated_schedule_workspace):
    _root, calendars = isolated_schedule_workspace
    result, problems = schedule_setup.save_day_calendar(
        "Precedence",
        "2026-08-17",
        "2026-08-23",
        _ordinary_id(),
        weekday_schedules={0: _short_id()},
        date_schedules={"2026-08-18": _ordinary_id(), "2026-08-19": _short_id()},
        skip_dates=["2026-08-20"],
    )

    assert problems == []
    assert result["ok"] is True
    assert result["count"] == 4
    assert result["first"] == "2026-08-17"
    assert result["last"] == "2026-08-21"
    assert _read_day_calendar(calendars / "Day Calendar Precedence.csv") == {
        "2026-08-17": _short_id(),
        "2026-08-18": _ordinary_id(),
        "2026-08-19": _short_id(),
        "2026-08-21": _ordinary_id(),
    }


def test_save_day_calendar_unknown_schedule_refuses_without_writing(
    isolated_schedule_workspace,
):
    _root, calendars = isolated_schedule_workspace
    result, problems = schedule_setup.save_day_calendar(
        "Unknown",
        "2026-08-17",
        "2026-08-21",
        "missing_schedule",
    )

    assert result is None
    assert any("missing_schedule" in problem for problem in problems)
    assert any(_ordinary_id() in problem for problem in problems)
    assert not (calendars / "Day Calendar Unknown.csv").exists()


def test_save_day_calendar_refuses_out_of_range_skip_date(isolated_schedule_workspace):
    _root, calendars = isolated_schedule_workspace
    result, problems = schedule_setup.save_day_calendar(
        "Out of range",
        "2026-08-17",
        "2026-08-21",
        _ordinary_id(),
        skip_dates=["2026-08-22"],
    )

    assert result is None
    assert any("2026-08-22" in problem for problem in problems)
    assert not (calendars / "Day Calendar Out of range.csv").exists()


def test_save_day_calendar_refuses_existing_file_then_moves_it_on_replace(
    isolated_schedule_workspace,
):
    _root, calendars = isolated_schedule_workspace
    first, first_problems = schedule_setup.save_day_calendar(
        "Replace me", "2026-08-17", "2026-08-21", _ordinary_id()
    )
    target = calendars / "Day Calendar Replace me.csv"
    original_bytes = target.read_bytes()
    refused, refused_problems = schedule_setup.save_day_calendar(
        "Replace me", "2026-08-17", "2026-08-21", _short_id()
    )
    assert target.read_bytes() == original_bytes
    replaced, replace_problems = schedule_setup.save_day_calendar(
        "Replace me", "2026-08-17", "2026-08-21", _short_id(), replace=True
    )

    assert first_problems == [] and first["ok"] is True
    assert refused is None
    assert any("already exists" in problem for problem in refused_problems)
    assert replace_problems == [] and replaced["ok"] is True
    aside_files = list(calendars.glob("Day Calendar Replace me.csv.*.bak"))
    assert len(aside_files) == 1
    assert aside_files[0].read_bytes() == original_bytes
    assert _read_day_calendar(aside_files[0])


def test_save_day_calendar_reports_overlap_and_sorted_winner(
    isolated_schedule_workspace,
):
    _root, calendars = isolated_schedule_workspace
    (calendars / "Day Calendar Z.csv").write_text(
        "date,schedule_id\n2026-08-18," + _ordinary_id() + "\n", encoding="utf-8"
    )

    result, problems = schedule_setup.save_day_calendar(
        "A", "2026-08-17", "2026-08-19", _ordinary_id()
    )

    assert problems == []
    assert result["overlap"] == {"count": 1, "files": ["Day Calendar Z.csv"]}


def test_save_day_calendar_round_trips_and_mcp_response_is_token_lean(
    isolated_schedule_workspace,
):
    _root, calendars = isolated_schedule_workspace
    result = tools.save_day_calendar(
        "MCP",
        "2026-08-17",
        "2026-08-28",
        _ordinary_id(),
        skip_dates=["2026-08-21"],
    )

    assert result["ok"] is True
    assert "rows" not in result
    mapping = _read_day_calendar(calendars / "Day Calendar MCP.csv")
    assert len(mapping) == result["count"]
    assert "2026-08-21" not in mapping


def test_save_day_calendar_is_idempotent_with_replace(isolated_schedule_workspace):
    _root, calendars = isolated_schedule_workspace
    arguments = ("Idempotent", "2026-08-17", "2026-08-21", _ordinary_id())
    first, first_problems = schedule_setup.save_day_calendar(*arguments, replace=True)
    target = calendars / "Day Calendar Idempotent.csv"
    first_bytes = target.read_bytes()
    second, second_problems = schedule_setup.save_day_calendar(*arguments, replace=True)

    assert first_problems == [] and second_problems == []
    assert first["ok"] is True and second["ok"] is True
    assert target.read_bytes() == first_bytes


@pytest.mark.parametrize(
    "label",
    ["", "  ", "a/b", "a\\b", "Bell Schedule Ordinary"],
)
def test_save_day_calendar_rejects_unsafe_labels(isolated_schedule_workspace, label):
    _root, calendars = isolated_schedule_workspace
    result, problems = schedule_setup.save_day_calendar(
        label, "2026-08-17", "2026-08-21", _ordinary_id()
    )
    assert result is None
    assert problems
    assert not list(calendars.glob("Day Calendar *.csv"))


def test_save_day_calendar_refuses_empty_result(isolated_schedule_workspace):
    _root, calendars = isolated_schedule_workspace
    result, problems = schedule_setup.save_day_calendar(
        "Empty", "2026-08-22", "2026-08-23", _ordinary_id()
    )
    assert result is None
    assert any("no school days" in problem for problem in problems)
    assert not (calendars / "Day Calendar Empty.csv").exists()
