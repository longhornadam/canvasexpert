"""Tests for the ordered-meeting schedule model."""

import json
from pathlib import Path

from api.webui import clock_time, day_schedule
from api.webui.deps import _file_key


def _meeting(period_id, start, end, segment=""):
    return {"period_id": period_id, "start": start, "end": end, "segment": segment}


class TestParseBellSchedule:
    def test_valid_schedule(self):
        content = "period_id,start,end\n1,8:35 AM,9:25 AM\n2,9:29 AM,10:21 AM"
        meetings, problems = day_schedule.parse_bell_schedule(content)
        assert meetings == [
            {"seq": 0, "period_id": "1", "start": "8:35 AM", "end": "9:25 AM", "segment": ""},
            {"seq": 1, "period_id": "2", "start": "9:29 AM", "end": "10:21 AM", "segment": ""},
        ]
        assert problems == []

    def test_optional_label_becomes_segment(self):
        content = "period_id,start,end,label\n1,8:35 AM,9:25 AM,Review"
        meetings, problems = day_schedule.parse_bell_schedule(content)
        assert meetings[0]["segment"] == "Review"
        assert problems == []

    def test_duplicate_period_id_is_legal_and_sorted(self):
        content = (
            "period_id,start,end,label\n"
            "6,12:40 PM,2:15 PM,EXAM\n"
            "6,8:35 AM,9:30 AM,Review\n"
            "4,12:35 PM,12:40 PM,Study Hall\n"
        )
        meetings, problems = day_schedule.parse_bell_schedule(content)
        assert meetings == [
            {"seq": 0, "period_id": "6", "start": "8:35 AM", "end": "9:30 AM", "segment": "Review"},
            {"seq": 1, "period_id": "4", "start": "12:35 PM", "end": "12:40 PM", "segment": "Study Hall"},
            {"seq": 2, "period_id": "6", "start": "12:40 PM", "end": "2:15 PM", "segment": "EXAM"},
        ]
        assert problems == []

    def test_empty_csv(self):
        meetings, problems = day_schedule.parse_bell_schedule("period_id,start,end")
        assert meetings == []
        assert problems == []

    def test_invalid_time_format(self):
        meetings, problems = day_schedule.parse_bell_schedule(
            "period_id,start,end\n1,8:35,9:25 AM"
        )
        assert len(meetings) == 1
        assert "Invalid time format" in problems[0]

    def test_twenty_four_hour_source_parses_and_renders_as_twelve_hour(self):
        """A Bell Schedule the teacher already had is written in 24-hour time.
        It must display in the canonical 12-hour form, not be refused for its
        spelling and echoed back raw."""
        meetings, problems = day_schedule.parse_bell_schedule(
            "period_id,start,end\n"
            "1,08:35,09:25\n"
            "4,11:19,12:09\n"
            "bobcat,12:11,13:13\n"
            "7,15:05,15:55\n"
        )
        assert problems == []
        assert [(m["period_id"], m["start"], m["end"]) for m in meetings] == [
            ("1", "8:35 AM", "9:25 AM"),
            ("4", "11:19 AM", "12:09 PM"),
            ("bobcat", "12:11 PM", "1:13 PM"),
            ("7", "3:05 PM", "3:55 PM"),
        ]

    def test_single_digit_hour_without_a_meridiem_stays_invalid(self):
        """"1:15" is 1:15 AM on a 24-hour clock and 1:15 PM to a teacher writing
        a bell schedule. Guessing would silently move an afternoon class to the
        middle of the night, so it has to surface as a problem instead."""
        meetings, problems = day_schedule.parse_bell_schedule(
            "period_id,start,end\n5,1:15,2:05\n"
        )
        assert len(meetings) == 1
        assert any("Invalid time format" in p and "1:15" in p for p in problems)

    def test_end_before_start_is_reported_and_kept(self):
        meetings, problems = day_schedule.parse_bell_schedule(
            "period_id,start,end\n1,3:00 PM,9:25 AM"
        )
        assert meetings[0]["start"] == "3:00 PM"
        assert meetings[0]["end"] == "9:25 AM"
        assert "end time" in problems[0].lower()

    def test_named_periods_are_allowed(self):
        meetings, problems = day_schedule.parse_bell_schedule(
            "period_id,start,end\nbobcat,12:11 PM,1:13 PM"
        )
        assert meetings[0]["period_id"] == "bobcat"
        assert meetings[0]["seq"] == 0
        assert problems == []


class TestClockTime:
    def test_canonical_twelve_hour_round_trips(self):
        for value in ("8:35 AM", "12:00 PM", "12:00 AM", "1:13 PM", "11:59 PM"):
            minutes = clock_time.parse_time(value)
            assert minutes is not None, value
            assert clock_time.format_time(minutes) == value

    def test_two_digit_hour_twenty_four_hour_values_normalize(self):
        assert clock_time.normalize_time("00:30") == "12:30 AM"
        assert clock_time.normalize_time("08:35") == "8:35 AM"
        assert clock_time.normalize_time("12:00") == "12:00 PM"
        assert clock_time.normalize_time("13:13") == "1:13 PM"
        assert clock_time.normalize_time("23:59") == "11:59 PM"

    def test_out_of_range_and_ambiguous_values_are_refused(self):
        for value in ("24:00", "25:00", "12:60", "1:15", "9:30", "835", "", "8:35 XM"):
            assert clock_time.parse_time(value) is None, value

    def test_normalize_returns_the_original_text_when_unparseable(self):
        assert clock_time.normalize_time("1:15") == "1:15"


class TestParseTeacherSchedule:
    def test_valid_teacher_schedule(self):
        data, problems = day_schedule.parse_teacher_schedule(
            '{"version":"1.0-json","blocks":[{"name":"1st","raw_periods":[1],"label":"ELA"}]}'
        )
        assert data["blocks"][0]["name"] == "1st"
        assert problems == []

    def test_legacy_weekdays_are_ignored(self):
        data, problems = day_schedule.parse_teacher_schedule(
            '{"blocks":[{"name":"1st","raw_periods":[1],"weekdays":[0]}]}'
        )
        assert data["blocks"][0]["weekdays"] == [0]
        assert problems == []

    def test_malformed_json(self):
        data, problems = day_schedule.parse_teacher_schedule("{invalid json")
        assert data == {}
        assert "invalid JSON" in problems[0]

    def test_empty_blocks(self):
        data, problems = day_schedule.parse_teacher_schedule('{"version":"1.0-json","blocks":[]}')
        assert data["blocks"] == []
        assert problems == []


class TestResolveDay:
    @staticmethod
    def resolve(periods, blocks):
        return day_schedule.resolve_day(
            "schedule",
            {"schedule": periods},
            {"blocks": blocks},
        )

    def test_resolve_simple_block(self):
        blocks, problems = self.resolve(
            [_meeting("1", "8:35 AM", "9:25 AM")],
            [{"name": "1st Period", "raw_periods": [1], "label": "ELA"}],
        )
        assert blocks[0]["name"] == "1st Period"
        assert blocks[0]["start"] == "8:35 AM"
        assert blocks[0]["end"] == "9:25 AM"
        assert blocks[0]["period_ids"] == ["1"]
        assert blocks[0]["seq"] == 0
        assert problems == []

    def test_contiguous_periods_resolve_to_one_entry(self):
        blocks, problems = self.resolve(
            [
                _meeting("4", "11:19 AM", "12:09 PM"),
                _meeting("5", "1:17 PM", "2:07 PM"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5], "label": "Math"}],
        )
        assert len(blocks) == 1
        assert blocks[0]["start"] == "11:19 AM"
        assert blocks[0]["end"] == "2:07 PM"
        assert blocks[0]["period_ids"] == ["4", "5"]
        assert problems == []

    def test_non_contiguous_block_resolves_to_two_entries(self):
        blocks, problems = self.resolve(
            [
                _meeting("4", "11:19 AM", "12:11 PM"),
                _meeting("bobcat", "12:12 PM", "1:13 PM", "Bobcat Hour"),
                _meeting("5", "1:17 PM", "2:11 PM"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5]}],
        )
        assert [(block["start"], block["end"]) for block in blocks] == [
            ("11:19 AM", "12:11 PM"),
            ("1:17 PM", "2:11 PM"),
        ]
        assert problems == []

    def test_reordered_schedule_stays_chronological(self):
        blocks, problems = self.resolve(
            [
                _meeting("5", "10:50 AM", "11:30 AM"),
                _meeting("4", "11:35 AM", "12:55 PM"),
            ],
            [{"name": "4th/5th", "raw_periods": [4, 5]}],
        )
        assert len(blocks) == 1
        assert blocks[0]["start"] == "10:50 AM"
        assert blocks[0]["end"] == "12:55 PM"
        assert blocks[0]["end"] >= blocks[0]["start"]
        assert blocks[0]["period_ids"] == ["5", "4"]
        assert problems == []

    def test_duplicate_period_id_preserves_both_runs_and_segments(self):
        blocks, problems = self.resolve(
            [
                _meeting("7", "8:35 AM", "9:25 AM", "Review"),
                _meeting("6", "9:30 AM", "10:30 AM", "Review"),
                _meeting("homeroom", "10:35 AM", "12:35 PM", "Homeroom"),
                _meeting("4", "12:35 PM", "12:40 PM", "Study Hall"),
                _meeting("6", "12:40 PM", "2:15 PM", "EXAM"),
                _meeting("7", "2:20 PM", "3:55 PM", "EXAM"),
            ],
            [{"name": "ELA 7", "raw_periods": [6, 7]}],
        )
        assert [(block["start"], block["end"]) for block in blocks] == [
            ("8:35 AM", "10:30 AM"),
            ("12:40 PM", "3:55 PM"),
        ]
        assert [block["segments"] for block in blocks] == [["Review", "Review"], ["EXAM", "EXAM"]]
        assert problems == []

    def test_absent_block_is_silent(self):
        blocks, problems = self.resolve(
            [_meeting("1", "8:35 AM", "9:25 AM")],
            [{"name": "Period 7", "raw_periods": [7]}],
        )
        assert blocks == []
        assert problems == []

    def test_legacy_weekday_does_not_filter_a_block(self):
        blocks, problems = self.resolve(
            [_meeting("1", "8:35 AM", "9:25 AM")],
            [{"name": "Every day", "raw_periods": [1], "weekdays": [0]}],
        )
        assert [block["name"] for block in blocks] == ["Every day"]
        assert problems == []

    def test_no_schedule_id_is_reported(self):
        blocks, problems = day_schedule.resolve_day(None, {}, {})
        assert blocks == []
        assert "no schedule" in problems[0]

    def test_schedule_id_not_found_is_reported(self):
        blocks, problems = day_schedule.resolve_day(
            "missing", {"other": []}, {"blocks": []}
        )
        assert blocks == []
        assert "missing" in problems[0]

    def test_blocks_are_sorted_by_start_time(self):
        blocks, problems = self.resolve(
            [
                _meeting("6", "2:11 PM", "3:01 PM"),
                _meeting("1", "8:35 AM", "9:25 AM"),
                _meeting("2", "9:29 AM", "10:21 AM"),
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
        assert day_schedule.validate_teacher_schedule({
            "version": "1.0-json",
            "blocks": [
                {"name": "Algebra", "raw_periods": [1], "course_id": "9000001"},
                {"name": "Geometry", "raw_periods": [2], "label": "Math"},
            ],
        }) == []

    def test_duplicate_names_are_rejected(self):
        problems = day_schedule.validate_teacher_schedule({
            "blocks": [
                {"name": "Shared", "raw_periods": [1]},
                {"name": "Shared", "raw_periods": [2]},
            ]
        })
        assert problems == ["block 'Shared' must be unique"]

    def test_duplicate_periods_across_blocks_are_rejected(self):
        problems = day_schedule.validate_teacher_schedule({
            "blocks": [
                {"name": "Algebra", "raw_periods": [1]},
                {"name": "Geometry", "raw_periods": [1]},
            ]
        })
        assert problems == ["period '1' is claimed by both blocks 'Algebra' and 'Geometry'"]

    def test_weekdays_are_not_validated(self):
        assert day_schedule.validate_teacher_schedule({
            "blocks": [{"name": "Algebra", "raw_periods": [1], "weekdays": "legacy"}]
        }) == []

    def test_course_id_must_be_a_string(self):
        assert day_schedule.validate_teacher_schedule({
            "blocks": [{"name": "Algebra", "raw_periods": [1], "course_id": 9000001}]
        }) == ["block 'Algebra' course_id must be a string"]

    def test_blocks_must_be_a_list(self):
        assert day_schedule.validate_teacher_schedule({"blocks": {}}) == [
            "blocks must be a list"
        ]

    def test_block_needs_a_name(self):
        problems = day_schedule.validate_teacher_schedule({"blocks": [{"raw_periods": [1]}]})
        assert any("non-empty string name" in problem for problem in problems)

    def test_block_needs_raw_periods(self):
        problems = day_schedule.validate_teacher_schedule({"blocks": [{"name": "Algebra"}]})
        assert any("raw_periods" in problem for problem in problems)

    def test_unknown_keys_and_version_are_allowed(self):
        assert day_schedule.validate_teacher_schedule({
            "version": "future-format",
            "custom": {"source": "hand"},
            "blocks": [{"name": "Algebra", "raw_periods": [1], "custom": True}],
        }) == []


def test_default_resolved_runs_never_invert():
    root = Path(__file__).resolve().parents[3] / "api" / "default_docs" / "Calendars"
    teacher = json.loads(
        (root.parent / "Calendars" / "Teacher Schedule.template.json").read_text(
            encoding="utf-8"
        )
    )
    for path in sorted(root.glob("Bell Schedule*.csv")):
        meetings, problems = day_schedule.parse_bell_schedule(path.read_text(encoding="utf-8"))
        assert not problems, f"{path.name}: {problems}"
        schedule_id = _file_key(path.name)
        blocks, resolve_problems = day_schedule.resolve_day(
            schedule_id, {schedule_id: meetings}, teacher
        )
        assert resolve_problems == [], (path.name, resolve_problems)
        assert all(clock_time.parse_time(block["end"]) >= clock_time.parse_time(block["start"])
                   for block in blocks), path.name

