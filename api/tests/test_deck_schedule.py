"""Tests for the ordered-meeting schedule model."""

import json
from pathlib import Path

from api.webui import deck_schedule
from api.webui.routes.calendar import _file_key


def _meeting(period_id, start, end, segment=""):
    return {"period_id": period_id, "start": start, "end": end, "segment": segment}


class TestParseBellSchedule:
    def test_valid_schedule(self):
        content = "period_id,start,end\n1,08:35,09:25\n2,09:29,10:21"
        meetings, problems = deck_schedule.parse_bell_schedule(content)
        assert meetings == [
            {"seq": 0, "period_id": "1", "start": "08:35", "end": "09:25", "segment": ""},
            {"seq": 1, "period_id": "2", "start": "09:29", "end": "10:21", "segment": ""},
        ]
        assert problems == []

    def test_optional_label_becomes_segment(self):
        content = "period_id,start,end,label\n1,08:35,09:25,Review"
        meetings, problems = deck_schedule.parse_bell_schedule(content)
        assert meetings[0]["segment"] == "Review"
        assert problems == []

    def test_duplicate_period_id_is_legal_and_sorted(self):
        content = (
            "period_id,start,end,label\n"
            "6,12:40,14:15,EXAM\n"
            "6,08:35,09:30,Review\n"
            "4,12:35,12:40,Study Hall\n"
        )
        meetings, problems = deck_schedule.parse_bell_schedule(content)
        assert meetings == [
            {"seq": 0, "period_id": "6", "start": "08:35", "end": "09:30", "segment": "Review"},
            {"seq": 1, "period_id": "4", "start": "12:35", "end": "12:40", "segment": "Study Hall"},
            {"seq": 2, "period_id": "6", "start": "12:40", "end": "14:15", "segment": "EXAM"},
        ]
        assert problems == []

    def test_empty_csv(self):
        meetings, problems = deck_schedule.parse_bell_schedule("period_id,start,end")
        assert meetings == []
        assert problems == []

    def test_invalid_time_format(self):
        meetings, problems = deck_schedule.parse_bell_schedule(
            "period_id,start,end\n1,8:35,09:25"
        )
        assert len(meetings) == 1
        assert "Invalid time format" in problems[0]

    def test_end_before_start_is_reported_and_kept(self):
        meetings, problems = deck_schedule.parse_bell_schedule(
            "period_id,start,end\n1,15:00,09:25"
        )
        assert meetings[0]["start"] == "15:00"
        assert meetings[0]["end"] == "09:25"
        assert "end time" in problems[0].lower()

    def test_named_periods_are_allowed(self):
        meetings, problems = deck_schedule.parse_bell_schedule(
            "period_id,start,end\nbobcat,12:11,13:13"
        )
        assert meetings[0]["period_id"] == "bobcat"
        assert meetings[0]["seq"] == 0
        assert problems == []


class TestParseDayCalendar:
    def test_valid_day_calendar(self):
        content = (
            "date,schedule_id\n"
            "2026-08-19,bell_schedule_example_day_a\n"
            "2026-08-20,bell_schedule_example_day_b"
        )
        mapping, problems = deck_schedule.parse_day_calendar(content)
        assert mapping == {
            "2026-08-19": "bell_schedule_example_day_a",
            "2026-08-20": "bell_schedule_example_day_b",
        }
        assert problems == []

    def test_mm_dd_yyyy_format(self):
        mapping, problems = deck_schedule.parse_day_calendar(
            "date,schedule_id\n08/19/2026,bell_schedule_example_day_a"
        )
        assert mapping == {"2026-08-19": "bell_schedule_example_day_a"}
        assert problems == []

    def test_invalid_date(self):
        _mapping, problems = deck_schedule.parse_day_calendar(
            "date,schedule_id\n2026-13-45,bell_schedule_example_day_a"
        )
        assert "Invalid date" in problems[0]

    def test_empty_day_calendar(self):
        mapping, problems = deck_schedule.parse_day_calendar("date,schedule_id")
        assert mapping == {}
        assert problems == []


class TestParseTeacherSchedule:
    def test_valid_teacher_schedule(self):
        data, problems = deck_schedule.parse_teacher_schedule(
            '{"version":"1.0-json","blocks":[{"name":"1st","raw_periods":[1],"label":"ELA"}]}'
        )
        assert data["blocks"][0]["name"] == "1st"
        assert problems == []

    def test_legacy_weekdays_are_ignored(self):
        data, problems = deck_schedule.parse_teacher_schedule(
            '{"blocks":[{"name":"1st","raw_periods":[1],"weekdays":[0]}]}'
        )
        assert data["blocks"][0]["weekdays"] == [0]
        assert problems == []

    def test_malformed_json(self):
        data, problems = deck_schedule.parse_teacher_schedule("{invalid json")
        assert data == {}
        assert "invalid JSON" in problems[0]

    def test_empty_blocks(self):
        data, problems = deck_schedule.parse_teacher_schedule('{"version":"1.0-json","blocks":[]}')
        assert data["blocks"] == []
        assert problems == []


class TestResolveDay:
    @staticmethod
    def resolve(periods, blocks, date="2026-08-19"):
        return deck_schedule.resolve_day(
            date,
            {date: "schedule"},
            {"schedule": periods},
            {"blocks": blocks},
        )

    def test_resolve_simple_block(self):
        blocks, problems = self.resolve(
            [_meeting("1", "08:35", "09:25")],
            [{"name": "1st Period", "raw_periods": [1], "label": "ELA"}],
        )
        assert blocks[0]["name"] == "1st Period"
        assert blocks[0]["start"] == "08:35"
        assert blocks[0]["end"] == "09:25"
        assert blocks[0]["period_ids"] == ["1"]
        assert blocks[0]["seq"] == 0
        assert problems == []

    def test_contiguous_periods_resolve_to_one_entry(self):
        blocks, problems = self.resolve(
            [
                _meeting("4", "11:19", "12:09"),
                _meeting("5", "13:17", "14:07"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5], "label": "Math"}],
        )
        assert len(blocks) == 1
        assert blocks[0]["start"] == "11:19"
        assert blocks[0]["end"] == "14:07"
        assert blocks[0]["period_ids"] == ["4", "5"]
        assert problems == []

    def test_non_contiguous_block_resolves_to_two_entries(self):
        blocks, problems = self.resolve(
            [
                _meeting("4", "11:19", "12:11"),
                _meeting("bobcat", "12:12", "13:13", "Bobcat Hour"),
                _meeting("5", "13:17", "14:11"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5]}],
        )
        assert [(block["start"], block["end"]) for block in blocks] == [
            ("11:19", "12:11"),
            ("13:17", "14:11"),
        ]
        assert problems == []

    def test_reordered_schedule_stays_chronological(self):
        blocks, problems = self.resolve(
            [
                _meeting("5", "10:50", "11:30"),
                _meeting("4", "11:35", "12:55"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5]}],
        )
        assert len(blocks) == 1
        assert blocks[0]["start"] == "10:50"
        assert blocks[0]["end"] == "12:55"
        assert blocks[0]["end"] >= blocks[0]["start"]
        assert blocks[0]["period_ids"] == ["5", "4"]
        assert problems == []

    def test_duplicate_period_id_preserves_both_runs_and_segments(self):
        blocks, problems = self.resolve(
            [
                _meeting("7", "08:35", "09:25", "Review"),
                _meeting("6", "09:30", "10:30", "Review"),
                _meeting("homeroom", "10:35", "12:35", "Homeroom"),
                _meeting("4", "12:35", "12:40", "Study Hall"),
                _meeting("6", "12:40", "14:15", "EXAM"),
                _meeting("7", "14:20", "15:55", "EXAM"),
            ],
            [{"name": "ELA 7", "raw_periods": [6, 7]}],
        )
        assert [(block["start"], block["end"]) for block in blocks] == [
            ("08:35", "10:30"),
            ("12:40", "15:55"),
        ]
        assert [block["segments"] for block in blocks] == [["Review", "Review"], ["EXAM", "EXAM"]]
        assert problems == []

    def test_absent_block_is_silent(self):
        blocks, problems = self.resolve(
            [_meeting("1", "08:35", "09:25")],
            [{"name": "Period 7", "raw_periods": [7]}],
        )
        assert blocks == []
        assert problems == []

    def test_legacy_weekday_does_not_filter_a_block(self):
        blocks, problems = self.resolve(
            [_meeting("1", "08:35", "09:25")],
            [{"name": "Every day", "raw_periods": [1], "weekdays": [0]}],
            date="2026-08-18",
        )
        assert [block["name"] for block in blocks] == ["Every day"]
        assert problems == []

    def test_date_not_in_calendar_is_reported(self):
        blocks, problems = deck_schedule.resolve_day("2026-08-19", {}, {}, {})
        assert blocks == []
        assert "2026-08-19" in problems[0]

    def test_schedule_id_not_found_is_reported(self):
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", {"2026-08-19": "missing"}, {"other": []}, {"blocks": []}
        )
        assert blocks == []
        assert "missing" in problems[0]

    def test_blocks_are_sorted_by_start_time(self):
        blocks, problems = self.resolve(
            [
                _meeting("6", "14:11", "15:01"),
                _meeting("1", "08:35", "09:25"),
                _meeting("2", "09:29", "10:21"),
            ],
            [
                {"name": "6th Period", "raw_periods": [6]},
                {"name": "1st Period", "raw_periods": [1]},
                {"name": "2nd Period", "raw_periods": [2]},
            ],
        )
        assert [block["name"] for block in blocks] == [
            "1st Period", "2nd Period", "6th Period"
        ]
        assert problems == []


class TestValidateTeacherSchedule:
    def test_valid_schedule_has_no_problems(self):
        assert deck_schedule.validate_teacher_schedule({
            "version": "1.0-json",
            "blocks": [
                {"name": "Algebra", "raw_periods": [1], "course_id": "9000001"},
                {"name": "Geometry", "raw_periods": [2], "label": "Math"},
            ],
        }) == []

    def test_duplicate_names_are_rejected(self):
        problems = deck_schedule.validate_teacher_schedule({
            "blocks": [
                {"name": "Shared", "raw_periods": [1]},
                {"name": "Shared", "raw_periods": [2]},
            ]
        })
        assert problems == ["block 'Shared' must be unique"]

    def test_duplicate_periods_across_blocks_are_rejected(self):
        problems = deck_schedule.validate_teacher_schedule({
            "blocks": [
                {"name": "Algebra", "raw_periods": [1]},
                {"name": "Geometry", "raw_periods": [1]},
            ]
        })
        assert problems == ["period '1' is claimed by both blocks 'Algebra' and 'Geometry'"]

    def test_weekdays_are_not_validated(self):
        assert deck_schedule.validate_teacher_schedule({
            "blocks": [{"name": "Algebra", "raw_periods": [1], "weekdays": "legacy"}]
        }) == []

    def test_course_id_must_be_a_string(self):
        assert deck_schedule.validate_teacher_schedule({
            "blocks": [{"name": "Algebra", "raw_periods": [1], "course_id": 9000001}]
        }) == ["block 'Algebra' course_id must be a string"]

    def test_blocks_must_be_a_list(self):
        assert deck_schedule.validate_teacher_schedule({"blocks": {}}) == [
            "blocks must be a list"
        ]

    def test_block_needs_a_name(self):
        problems = deck_schedule.validate_teacher_schedule({"blocks": [{"raw_periods": [1]}]})
        assert any("non-empty string name" in problem for problem in problems)

    def test_block_needs_raw_periods(self):
        problems = deck_schedule.validate_teacher_schedule({"blocks": [{"name": "Algebra"}]})
        assert any("raw_periods" in problem for problem in problems)

    def test_unknown_keys_and_version_are_allowed(self):
        assert deck_schedule.validate_teacher_schedule({
            "version": "future-format",
            "custom": {"source": "hand"},
            "blocks": [{"name": "Algebra", "raw_periods": [1], "custom": True}],
        }) == []


def test_default_resolved_runs_never_invert():
    root = Path(__file__).resolve().parents[1] / "default_docs" / "Calendars"
    teacher = json.loads(
        (root.parent / "SmartDecks" / "Teacher Schedule.template.json").read_text(
            encoding="utf-8"
        )
    )
    for path in sorted(root.glob("Bell Schedule*.csv")):
        meetings, problems = deck_schedule.parse_bell_schedule(path.read_text(encoding="utf-8"))
        assert not problems, f"{path.name}: {problems}"
        schedule_id = _file_key(path.name)
        blocks, resolve_problems = deck_schedule.resolve_day(
            "2026-08-19", {"2026-08-19": schedule_id}, {schedule_id: meetings}, teacher
        )
        assert resolve_problems == [], (path.name, resolve_problems)
        assert all(block["end"] >= block["start"] for block in blocks), path.name
