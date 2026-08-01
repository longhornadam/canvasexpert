"""Today's bell schedule: the teacher's one-day correction.

A bell schedule changes for an assembly or a late start and the calendar does
not follow. That failure is silent -- panels resolve to the wrong class and
look healthy doing it -- so the correction path has to be reliable in the two
ways that matter: it must win over the generated calendar, and it must not
damage it.
"""

import pytest
from fastapi.testclient import TestClient

from api.webui import deps, schedule_setup, workspace
from api.webui.server import app


TODAY = "2026-08-17"
ORDINARY = "bell_schedule_ordinary"
SHORT = "bell_schedule_short"


@pytest.fixture
def calendars(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    cal_dir = root / "Library" / "Calendars"
    cal_dir.mkdir(parents=True)
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(root))
    monkeypatch.setattr(workspace, "library_folder",
                        lambda name: str(root / "Library" / name))
    for filename in ("Bell Schedule Ordinary.csv", "Bell Schedule Short.csv"):
        (cal_dir / filename).write_text(
            "period_id,start,end\n1,08:00,08:45\n2,08:50,09:35\n", encoding="utf-8")
    return cal_dir


def _district(cal_dir, filename, schedule_id=ORDINARY, day=TODAY):
    (cal_dir / filename).write_text(
        f"date,schedule_id\n{day},{schedule_id}\n", encoding="utf-8")


def test_a_correction_beats_the_generated_calendar(calendars):
    _district(calendars, "District 2026.csv", ORDINARY)

    saved, problems = schedule_setup.set_day_override(TODAY, SHORT)

    assert problems == []
    assert saved["schedule_id"] == SHORT
    assert deps.load_day_calendar()[0][TODAY] == SHORT


def test_precedence_is_by_name_not_alphabetical_luck(calendars):
    """load_day_calendar merges sorted(glob(...)) with dict.update, so whoever
    sorts last wins. A district file renamed past 'Day Overrides.csv' would
    silently start beating the teacher unless precedence is explicit."""
    _district(calendars, "ZZZ District Calendar.csv", ORDINARY)

    schedule_setup.set_day_override(TODAY, SHORT)

    assert "ZZZ District Calendar.csv" > schedule_setup.DAY_OVERRIDE_FILENAME
    assert deps.load_day_calendar()[0][TODAY] == SHORT


def test_the_generated_calendar_is_never_edited(calendars):
    """Corrections live in their own file so regenerating the district
    calendar cannot wipe them, and so a correction stays visibly a
    correction."""
    _district(calendars, "District 2026.csv", ORDINARY)
    before = (calendars / "District 2026.csv").read_text(encoding="utf-8")

    schedule_setup.set_day_override(TODAY, SHORT)

    assert (calendars / "District 2026.csv").read_text(encoding="utf-8") == before
    assert (calendars / schedule_setup.DAY_OVERRIDE_FILENAME).exists()


def test_clearing_a_correction_returns_to_the_calendar(calendars):
    _district(calendars, "District 2026.csv", ORDINARY)
    schedule_setup.set_day_override(TODAY, SHORT)

    saved, problems = schedule_setup.set_day_override(TODAY, "")

    assert problems == []
    assert saved["schedule_id"] == ""
    assert deps.load_day_calendar()[0][TODAY] == ORDINARY


def test_clearing_the_last_correction_removes_the_file(calendars):
    """A header-only file in the teacher's synced folder implies a correction
    that is not there."""
    schedule_setup.set_day_override(TODAY, SHORT)
    assert (calendars / schedule_setup.DAY_OVERRIDE_FILENAME).exists()

    schedule_setup.set_day_override(TODAY, "")

    assert not (calendars / schedule_setup.DAY_OVERRIDE_FILENAME).exists()


def test_clearing_one_of_two_corrections_keeps_the_file(calendars):
    schedule_setup.set_day_override(TODAY, SHORT)
    schedule_setup.set_day_override("2026-08-18", ORDINARY)

    schedule_setup.set_day_override(TODAY, "")

    overrides, _problems = schedule_setup.read_day_overrides()
    assert overrides == {"2026-08-18": ORDINARY}


def test_a_correction_works_when_the_calendar_has_no_entry(calendars):
    """The common case in practice: the calendar simply does not cover today."""
    schedule_setup.set_day_override(TODAY, SHORT)

    assert deps.load_day_calendar()[0][TODAY] == SHORT


def test_other_days_survive_a_correction(calendars):
    schedule_setup.set_day_override("2026-08-18", ORDINARY)
    schedule_setup.set_day_override(TODAY, SHORT)

    overrides, _problems = schedule_setup.read_day_overrides()
    assert overrides == {TODAY: SHORT, "2026-08-18": ORDINARY}


def test_an_unknown_schedule_is_refused(calendars):
    """An override naming a schedule nobody has resolves to an empty day,
    which on a projector is indistinguishable from a holiday."""
    saved, problems = schedule_setup.set_day_override(TODAY, "bell_schedule_ghost")

    assert saved is None
    assert any("unknown bell schedule" in p for p in problems)
    assert deps.load_day_calendar()[0].get(TODAY) is None


def test_a_bad_date_is_refused(calendars):
    saved, problems = schedule_setup.set_day_override("not-a-date", SHORT)

    assert saved is None
    assert problems


def test_the_override_file_is_not_also_read_as_a_district_calendar(calendars):
    """It is a date,schedule_id CSV in the same folder, so discovery would
    happily pick it up twice. Applied last means applied once."""
    schedule_setup.set_day_override(TODAY, SHORT)
    mapping, problems = deps.load_day_calendar()

    assert mapping[TODAY] == SHORT
    assert problems == []


def test_the_route_reports_todays_schedule_and_the_choices(calendars):
    client = TestClient(app, base_url="http://127.0.0.1:8765")

    body = client.get("/api/schedule/today").json()

    assert body["ok"] is True
    assert {option["schedule_id"] for option in body["options"]} == {ORDINARY, SHORT}
    assert body["corrected"] is False


def test_the_route_saves_and_then_reports_the_correction(calendars):
    client = TestClient(app, base_url="http://127.0.0.1:8765")

    saved = client.post("/api/schedule/today", data={"schedule_id": SHORT}).json()
    body = client.get("/api/schedule/today").json()

    assert saved["ok"] is True
    assert body["schedule_id"] == SHORT
    assert body["corrected"] is True
    assert body["label"]


def test_choice_labels_drop_the_prefix_every_file_shares(calendars):
    """Under a control labelled "Today's bell schedule", leading every option
    with "Bell Schedule" is the same five words in front of the one that
    tells them apart."""
    body = TestClient(app, base_url="http://127.0.0.1:8765").get(
        "/api/schedule/today").json()

    labels = sorted(option["label"] for option in body["options"])
    assert labels == ["Ordinary", "Short"]


def test_a_schedule_named_only_by_the_prefix_keeps_a_label(calendars):
    (calendars / "Bell Schedule.csv").write_text(
        "period_id,start,end\n1,08:00,08:45\n", encoding="utf-8")

    body = TestClient(app, base_url="http://127.0.0.1:8765").get(
        "/api/schedule/today").json()

    assert all(option["label"] for option in body["options"])


def test_the_route_refuses_an_unknown_schedule(calendars):
    client = TestClient(app, base_url="http://127.0.0.1:8765")

    result = client.post("/api/schedule/today", data={"schedule_id": "nope"}).json()

    assert result["ok"] is False
    assert result["problems"]
