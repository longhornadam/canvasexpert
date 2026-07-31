"""Tests for the deck schedule parsing module."""
import pytest
from api.webui import deck_schedule


class TestParseBellSchedule:
    """Bell schedule CSV parsing."""

    def test_valid_schedule(self):
        """Parse a valid bell schedule."""
        csv = "period_id,start,end\n1,08:35,09:25\n2,09:29,10:21"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert len(periods) == 2
        assert periods[0] == {"period_id": "1", "start": "08:35", "end": "09:25"}
        assert periods[1] == {"period_id": "2", "start": "09:29", "end": "10:21"}
        assert problems == []

    def test_empty_csv(self):
        """Empty or header-only CSV returns empty list."""
        csv = "period_id,start,end"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert periods == []
        assert problems == []

    def test_invalid_time_format(self):
        """Invalid time format is reported in problems."""
        csv = "period_id,start,end\n1,8:35,09:25"  # "8:35" not "08:35"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert len(problems) > 0
        assert "Invalid time format" in problems[0]

    def test_end_before_start(self):
        """End time before start time is reported but row is kept."""
        csv = "period_id,start,end\n1,15:00,09:25"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert len(periods) == 1
        assert periods[0]["start"] == "15:00"
        assert periods[0]["end"] == "09:25"
        assert len(problems) > 0
        assert "end time" in problems[0].lower()

    def test_duplicate_period_id(self):
        """Last duplicate period_id wins."""
        csv = "period_id,start,end\n1,08:35,09:25\n1,08:40,09:30"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert len(periods) == 1
        assert periods[0] == {"period_id": "1", "start": "08:40", "end": "09:30"}
        assert len(problems) > 0
        assert "Duplicate" in problems[0]

    def test_named_periods(self):
        """Named periods like 'bobcat' or 'homeroom' are allowed."""
        csv = "period_id,start,end\nbobcat,12:11,13:13"
        periods, problems = deck_schedule.parse_bell_schedule(csv)
        assert len(periods) == 1
        assert periods[0]["period_id"] == "bobcat"
        assert problems == []


class TestParseDayCalendar:
    """Day calendar CSV parsing."""

    def test_valid_day_calendar(self):
        """Parse a valid day calendar."""
        csv = "date,schedule_id\n2026-08-19,bell_schedule_bobcat_hour\n2026-08-20,bell_schedule_bobcat_hour"
        mapping, problems = deck_schedule.parse_day_calendar(csv)
        assert mapping == {
            "2026-08-19": "bell_schedule_bobcat_hour",
            "2026-08-20": "bell_schedule_bobcat_hour",
        }
        assert problems == []

    def test_mm_dd_yyyy_format(self):
        """MM/DD/YYYY dates normalize to YYYY-MM-DD keys."""
        csv = "date,schedule_id\n08/19/2026,bell_schedule_bobcat_hour"
        mapping, problems = deck_schedule.parse_day_calendar(csv)
        assert "2026-08-19" in mapping
        assert mapping["2026-08-19"] == "bell_schedule_bobcat_hour"
        assert problems == []

    def test_invalid_date(self):
        """Invalid date is reported in problems."""
        csv = "date,schedule_id\n2026-13-45,bell_schedule_bobcat_hour"
        mapping, problems = deck_schedule.parse_day_calendar(csv)
        assert len(problems) > 0
        assert "Invalid date" in problems[0]

    def test_empty_day_calendar(self):
        """Empty day calendar returns empty mapping."""
        csv = "date,schedule_id"
        mapping, problems = deck_schedule.parse_day_calendar(csv)
        assert mapping == {}
        assert problems == []


class TestParseTeacherSchedule:
    """Teacher schedule JSON parsing."""

    def test_valid_teacher_schedule(self):
        """Parse a valid teacher schedule."""
        json_text = """{
            "version": "1.0-json",
            "blocks": [
                {"name": "1st Period", "raw_periods": [1], "label": "ELA"},
                {"name": "4th/5th", "raw_periods": [4, 5], "label": "Math"}
            ]
        }"""
        data, problems = deck_schedule.parse_teacher_schedule(json_text)
        assert data["version"] == "1.0-json"
        assert len(data["blocks"]) == 2
        assert data["blocks"][0]["name"] == "1st Period"
        assert problems == []

    def test_ignore_comment_key(self):
        """Top-level _comment key is silently ignored."""
        json_text = """{
            "_comment": "This is a comment",
            "version": "1.0-json",
            "blocks": []
        }"""
        data, problems = deck_schedule.parse_teacher_schedule(json_text)
        assert data["version"] == "1.0-json"
        assert "_comment" in data
        assert problems == []

    def test_malformed_json(self):
        """Malformed JSON returns error."""
        json_text = "{invalid json"
        data, problems = deck_schedule.parse_teacher_schedule(json_text)
        assert data == {}
        assert len(problems) > 0
        assert "invalid JSON" in problems[0]

    def test_empty_blocks(self):
        """Empty blocks list is valid."""
        json_text = '{"version": "1.0-json", "blocks": []}'
        data, problems = deck_schedule.parse_teacher_schedule(json_text)
        assert data["blocks"] == []
        assert problems == []


class TestResolveDay:
    """Schedule resolution for a specific date."""

    def test_resolve_simple_block(self):
        """Resolve a single-period block."""
        day_calendar = {"2026-08-19": "bobcat"}
        bell_schedules = {
            "bobcat": [
                {"period_id": "1", "start": "08:35", "end": "09:25"},
                {"period_id": "2", "start": "09:29", "end": "10:21"},
            ]
        }
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "1st Period", "raw_periods": [1], "label": "ELA"}
            ]
        }
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert len(blocks) == 1
        assert blocks[0]["name"] == "1st Period"
        assert blocks[0]["start"] == "08:35"
        assert blocks[0]["end"] == "09:25"
        assert problems == []

    def test_resolve_combined_block(self):
        """Resolve a combined block [4, 5] -> ONE entry, start of first, end of last."""
        day_calendar = {"2026-08-19": "schedule"}
        bell_schedules = {
            "schedule": [
                {"period_id": "4", "start": "11:19", "end": "12:09"},
                {"period_id": "5", "start": "13:17", "end": "14:07"},
            ]
        }
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "4th/5th", "raw_periods": [4, 5], "label": "Math"}
            ]
        }
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert len(blocks) == 1
        assert blocks[0]["name"] == "4th/5th"
        assert blocks[0]["start"] == "11:19"
        assert blocks[0]["end"] == "14:07"
        assert problems == []

    def test_resolve_combined_out_of_order(self):
        """Combined block whose raw_periods are not in chronological order.

        With raw_periods=[4, 5] where period 5 actually starts before period 4:
        start = first-in-list (period 4) start, end = last-in-list (period 5) end.
        This may result in end < start, which is allowed (not fixed/rejected).
        """
        day_calendar = {"2026-08-19": "pep_rally"}
        bell_schedules = {
            "pep_rally": [
                {"period_id": "4", "start": "11:35", "end": "12:55"},
                {"period_id": "5", "start": "10:50", "end": "11:30"},
            ]
        }
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "4th/5th", "raw_periods": [4, 5]}
            ]
        }
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert len(blocks) == 1
        assert blocks[0]["start"] == "11:35"  # first-in-list (period 4) start
        assert blocks[0]["end"] == "11:30"    # last-in-list (period 5) end
        assert blocks[0]["raw_periods"] == [4, 5]
        # Note: end < start is allowed and not reported as a problem

    def test_date_not_in_calendar(self):
        """Date absent from day calendar is reported."""
        day_calendar = {}
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, {}, {}
        )
        assert blocks == []
        assert len(problems) > 0
        assert "2026-08-19" in problems[0]

    def test_schedule_id_not_found(self):
        """Day calendar names schedule_id not in bell_schedules."""
        day_calendar = {"2026-08-19": "missing_schedule"}
        bell_schedules = {"other_schedule": []}
        teacher_schedule = {"version": "1.0-json", "blocks": []}
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert blocks == []
        assert len(problems) > 0
        assert "missing_schedule" in problems[0]

    def test_block_period_not_in_schedule(self):
        """Teacher block's period missing from today's schedule is omitted."""
        day_calendar = {"2026-08-19": "schedule"}
        bell_schedules = {
            "schedule": [
                {"period_id": "1", "start": "08:35", "end": "09:25"},
            ]
        }
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "Period 7", "raw_periods": [7], "label": "Homeroom"}
            ]
        }
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert blocks == []
        assert len(problems) > 0
        assert "7" in problems[0]

    def test_blocks_sorted_by_start_time(self):
        """Blocks are sorted by start time."""
        day_calendar = {"2026-08-19": "schedule"}
        bell_schedules = {
            "schedule": [
                {"period_id": "1", "start": "08:35", "end": "09:25"},
                {"period_id": "2", "start": "09:29", "end": "10:21"},
                {"period_id": "6", "start": "14:11", "end": "15:01"},
            ]
        }
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "6th Period", "raw_periods": [6]},
                {"name": "1st Period", "raw_periods": [1]},
                {"name": "2nd Period", "raw_periods": [2]},
            ]
        }
        blocks, problems = deck_schedule.resolve_day(
            "2026-08-19", day_calendar, bell_schedules, teacher_schedule
        )
        assert len(blocks) == 3
        assert blocks[0]["name"] == "1st Period"
        assert blocks[1]["name"] == "2nd Period"
        assert blocks[2]["name"] == "6th Period"

    def test_same_block_different_schedules(self):
        """Same block name resolves to different times on different days."""
        # Day 1: Monday with Bobcat Hour schedule
        day_calendar_1 = {"2026-08-19": "bobcat"}
        bell_schedules_1 = {
            "bobcat": [
                {"period_id": "4", "start": "11:19", "end": "12:09"},
                {"period_id": "5", "start": "13:17", "end": "14:07"},
            ]
        }

        # Day 2: Friday with different schedule (different times for period 4)
        day_calendar_2 = {"2026-08-21": "friday"}
        bell_schedules_2 = {
            "friday": [
                {"period_id": "4", "start": "11:30", "end": "12:44"},
                {"period_id": "5", "start": "12:48", "end": "13:38"},
            ]
        }

        # Same teacher schedule for both days
        teacher_schedule = {
            "version": "1.0-json",
            "blocks": [
                {"name": "4th/5th", "raw_periods": [4, 5], "label": "Math"}
            ]
        }

        # Resolve the same block on two different days
        blocks_1, _ = deck_schedule.resolve_day(
            "2026-08-19", day_calendar_1, bell_schedules_1, teacher_schedule
        )
        blocks_2, _ = deck_schedule.resolve_day(
            "2026-08-21", day_calendar_2, bell_schedules_2, teacher_schedule
        )

        # Same block name, different times
        assert blocks_1[0]["name"] == blocks_2[0]["name"]
        assert blocks_1[0]["start"] != blocks_2[0]["start"]
        assert blocks_1[0]["end"] != blocks_2[0]["end"]
        assert blocks_1[0]["schedule_id"] == "bobcat"
        assert blocks_2[0]["schedule_id"] == "friday"
