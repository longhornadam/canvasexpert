"""Contract for the public PISD / Berry Miller 2026-27 Calendar seeds."""

import csv
import json
from pathlib import Path

from api.platform_services import workspace
from api.webui import deps, school_calendar


SEEDS = Path(__file__).resolve().parents[3] / "api" / "default_docs" / "Calendars"
BOBCAT = "bell_schedule_berry_miller_2026_27_bobcat_hour_mon_thu"
HOMEROOM = "bell_schedule_berry_miller_2026_27_homeroom"
SCHEDULE_ROWS = {
    "Bell Schedule - Berry Miller 2026-27 - Bobcat Hour Mon-Thu.csv": [
        ("1", "8:35 AM", "9:25 AM"), ("2", "9:29 AM", "10:21 AM"),
        ("3", "10:25 AM", "11:15 AM"), ("4", "11:19 AM", "12:09 PM"),
        ("bobcat_hour", "12:11 PM", "1:13 PM"), ("5", "1:17 PM", "2:07 PM"),
        ("6", "2:11 PM", "3:01 PM"), ("7", "3:05 PM", "3:55 PM"),
    ],
    "Bell Schedule - Berry Miller 2026-27 - Homeroom.csv": [
        ("1", "8:35 AM", "9:25 AM"), ("2", "9:29 AM", "10:19 AM"),
        ("homeroom", "10:23 AM", "10:53 AM"), ("3", "10:57 AM", "11:47 AM"),
        ("4", "11:51 AM", "1:13 PM"), ("5", "1:17 PM", "2:07 PM"),
        ("6", "2:11 PM", "3:01 PM"), ("7", "3:05 PM", "3:55 PM"),
    ],
    "Bell Schedule - Berry Miller 2026-27 - Homeroom First.csv": [
        ("homeroom", "8:35 AM", "9:05 AM"), ("1", "9:09 AM", "9:59 AM"),
        ("2", "10:03 AM", "10:53 AM"), ("3", "10:57 AM", "11:47 AM"),
        ("4", "11:51 AM", "1:13 PM"), ("5", "1:17 PM", "2:07 PM"),
        ("6", "2:11 PM", "3:01 PM"), ("7", "3:05 PM", "3:55 PM"),
    ],
    "Bell Schedule - Berry Miller 2026-27 - House Days (Homeroom Last).csv": [
        ("1", "8:35 AM", "9:15 AM"), ("2", "9:20 AM", "10:00 AM"),
        ("3", "10:05 AM", "10:45 AM"), ("5", "10:50 AM", "11:30 AM"),
        ("4", "11:35 AM", "12:55 PM"), ("6", "1:00 PM", "1:40 PM"),
        ("7", "1:45 PM", "2:25 PM"), ("homeroom", "2:30 PM", "3:55 PM"),
    ],
}


def _csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_pisd_miller_calendar_seed_contract(tmp_path, monkeypatch):
    bell_files = {path.name for path in SEEDS.glob("Bell Schedule*.csv")}
    assert bell_files == set(SCHEDULE_ROWS)

    for filename, expected in SCHEDULE_ROWS.items():
        rows = _csv_rows(SEEDS / filename)
        assert [(row["period_id"], row["start"], row["end"]) for row in rows] == expected

    calendar_path = SEEDS / "School Calendar.json"
    raw_calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
    calendar, problems = school_calendar.parse_document(raw_calendar)
    assert problems == []
    assert calendar["revision"] == 1
    assert calendar["school_year"] == "2026-27"
    assert calendar["coverage"] == {"start": "2026-08-19", "end": "2027-05-27"}
    assert len(calendar["days"]) == 282

    schedule_ids = {deps._file_key(filename) for filename in bell_files}
    assert school_calendar._validate_known_schedules(calendar["days"], schedule_ids) == []
    opening_instructional_dates = (
        "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25",
        "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01",
        "2026-09-02", "2026-09-03", "2026-09-04",
    )
    assert all(calendar["days"][date_key]["schedule_id"] == HOMEROOM
               for date_key in opening_instructional_dates)
    assert calendar["days"]["2026-08-22"] == {
        "kind": "no_school", "schedule_id": None, "label": "Weekend"}
    assert calendar["days"]["2026-09-05"] == {
        "kind": "no_school", "schedule_id": None, "label": "Weekend"}
    assert calendar["days"]["2026-09-07"] == {
        "kind": "no_school", "schedule_id": None, "label": "Labor Day"}
    assert calendar["days"]["2026-09-08"]["schedule_id"] == BOBCAT
    assert calendar["days"]["2026-09-11"]["schedule_id"] == HOMEROOM
    assert calendar["days"]["2026-12-18"] == {
        "kind": "instructional", "schedule_id": HOMEROOM, "label": "Early Release"}
    assert calendar["days"]["2027-05-27"] == {
        "kind": "instructional", "schedule_id": BOBCAT, "label": "Early Release"}

    expected_no_school = {
        "2026-09-07": "Labor Day", "2026-09-21": "Staff Development",
        "2026-10-09": "Holiday for Students/Teachers", "2026-10-12": "Staff Development",
        "2026-11-09": "Staff Development", "2026-11-23": "Thanksgiving Break",
        "2026-11-27": "Thanksgiving Break", "2026-12-21": "Christmas Break",
        "2027-01-01": "Christmas Break", "2027-01-04": "Instructional Planning",
        "2027-01-05": "Staff Development", "2027-01-18": "MLK Jr. Day",
        "2027-02-15": "Staff Development", "2027-03-08": "Spring Break",
        "2027-03-12": "Spring Break", "2027-03-26": "Easter Break",
        "2027-03-29": "Easter Break",
    }
    for date_key, label in expected_no_school.items():
        assert calendar["days"][date_key] == {
            "kind": "no_school", "schedule_id": None, "label": label}

    assert calendar["grading_periods"] == [
        {"code": "T1", "name": "1st Grading Period", "start": "2026-08-19", "end": "2026-10-08", "report_issue_date": "2026-10-15"},
        {"code": "T2", "name": "2nd Grading Period", "start": "2026-10-13", "end": "2026-12-18", "report_issue_date": "2027-01-06"},
        {"code": "T3", "name": "3rd Grading Period", "start": "2027-01-06", "end": "2027-03-19", "report_issue_date": "2027-03-24"},
        {"code": "T4", "name": "4th Grading Period", "start": "2027-03-22", "end": "2027-05-27", "report_issue_date": "2027-06-04"},
    ]
    assert calendar["events"] == []

    district_rows = _csv_rows(SEEDS / "PISD 2026-27 District Calendar.csv")
    assert len(district_rows) == 22
    assert [row["report_issue_date"] for row in district_rows if row["row_type"] == "Academic Period"] == [
        "2026-10-15", "2027-01-06", "2027-03-24", "2027-06-04"]
    assert any(row["name"] == "Memorial Day" and row["start_date"] == "2027-05-31"
               for row in district_rows)
    source_text = (SEEDS / "PISD 2026-27 District Calendar.csv").read_text(encoding="utf-8")
    assert all(forbidden not in source_text for forbidden in ("STAAR", "TELPAS", "Pearland High School"))

    target = tmp_path / "Calendars"
    target.mkdir()
    teacher_file = target / next(iter(sorted(bell_files)))
    teacher_file.write_text("teacher-edited\n", encoding="utf-8")
    monkeypatch.setattr(workspace, "DEFAULT_DOCS_DIR", str(SEEDS.parent))
    workspace._seed_folder_if_missing(str(SEEDS), str(target))
    assert teacher_file.read_text(encoding="utf-8") == "teacher-edited\n"
    assert {path.name for path in target.iterdir()} == {path.name for path in SEEDS.iterdir()}
