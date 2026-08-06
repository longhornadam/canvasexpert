from api.webui import deps
from api.webui import school_calendar


def _calendar_dir(tmp_path):
    calendars = tmp_path / "Library" / "Calendars"
    calendars.mkdir(parents=True)
    return calendars


def _write_schedule(path, period_id="period-1"):
    path.write_text(
        "period_id,start,end\n"
        f"{period_id},8:00 AM,8:45 AM\n",
        encoding="utf-8",
    )


def test_conflict_copy_is_filtered_reported_and_left_untouched(tmp_path, monkeypatch):
    calendars = _calendar_dir(tmp_path)
    canonical = calendars / "Bell Schedule - A Day.csv"
    conflict = calendars / "Bell Schedule - A Day-LAPTOP-KD1OFHRJ.csv"
    _write_schedule(canonical, "canonical")
    conflict.write_text("conflict content\n", encoding="utf-8")
    original_bytes = conflict.read_bytes()
    monkeypatch.setattr(deps, "_calendars_dir", lambda: str(calendars))

    listed = deps.list_bell_schedule_files()
    schedules, problems = deps.load_bell_schedules()

    assert [entry["name"] for entry in listed] == [canonical.name]
    assert deps._file_key(conflict.name) not in schedules
    assert list(schedules) == [deps._file_key(canonical.name)]
    assert len(problems) == 1
    assert conflict.name in problems[0]
    assert canonical.name in problems[0]
    assert "delete" in problems[0].lower()
    assert conflict.exists()
    assert conflict.read_bytes() == original_bytes


def test_legitimate_descriptive_variant_remains_offered(tmp_path, monkeypatch):
    calendars = _calendar_dir(tmp_path)
    normal = calendars / "Bell Schedule - Friday.csv"
    early_release = calendars / "Bell Schedule - Friday Early Release.csv"
    _write_schedule(normal, "normal")
    _write_schedule(early_release, "early-release")
    monkeypatch.setattr(deps, "_calendars_dir", lambda: str(calendars))

    listed = deps.list_bell_schedule_files()
    schedules, problems = deps.load_bell_schedules()

    assert {entry["name"] for entry in listed} == {normal.name, early_release.name}
    assert set(schedules) == {deps._file_key(normal.name), deps._file_key(early_release.name)}
    assert problems == []


def test_numbered_and_dropbox_conflict_copies_are_filtered(tmp_path, monkeypatch):
    calendars = _calendar_dir(tmp_path)
    canonical = calendars / "Bell Schedule - A Day.csv"
    numbered = calendars / "Bell Schedule - A Day (1).csv"
    dropbox = calendars / "Bell Schedule - A Day (Teacher's conflicted copy 2026-08-04).csv"
    _write_schedule(canonical)
    numbered.write_text("numbered copy\n", encoding="utf-8")
    dropbox.write_text("dropbox copy\n", encoding="utf-8")
    monkeypatch.setattr(deps, "_calendars_dir", lambda: str(calendars))

    listed = deps.list_bell_schedule_files()
    schedules, problems = deps.load_bell_schedules()

    assert [entry["name"] for entry in listed] == [canonical.name]
    assert deps._file_key(numbered.name) not in schedules
    assert deps._file_key(dropbox.name) not in schedules
    assert len(problems) == 2
    assert all("delete" in problem.lower() for problem in problems)


def test_pinned_conflict_copy_resolves_to_existing_unknown_schedule_state(tmp_path, monkeypatch):
    calendars = _calendar_dir(tmp_path)
    canonical = calendars / "Bell Schedule - A Day.csv"
    conflict = calendars / "Bell Schedule - A Day-LAPTOP-KD1OFHRJ.csv"
    _write_schedule(canonical)
    _write_schedule(conflict, "conflict")
    monkeypatch.setattr(deps, "_calendars_dir", lambda: str(calendars))

    schedules, _problems = deps.load_bell_schedules()
    document, calendar_problems = school_calendar.create_school_year(
        school_year="2026-27",
        coverage_start="2026-08-17",
        coverage_end="2026-08-17",
        default_schedule_id=deps._file_key(conflict.name),
        root=str(tmp_path),
    )

    assert calendar_problems == []
    assert deps._file_key(conflict.name) not in schedules
    resolution = school_calendar.resolve_date(document, "2026-08-17", schedules)
    assert resolution["state"] == "unknown_schedule"
