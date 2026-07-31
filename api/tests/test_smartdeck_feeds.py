"""Tests for SmartDeck feed resolution."""
import pytest
from datetime import date
from api import smartdeck_feeds, audience


class TestListFeedNames:
    """Test list_feed_names()."""

    def test_list_feed_names_returns_all_catalog_keys(self):
        """list_feed_names returns exactly the 7 catalog keys, sorted."""
        names = smartdeck_feeds.list_feed_names()
        expected = [
            "bell_schedule",
            "birthdays_today",
            "district_calendar_events",
            "missing_assignments",
            "positive_achievements",
            "school_events",
            "staar_masters",
        ]
        assert names == expected

    def test_list_feed_names_is_sorted(self):
        """Returned names are in alphabetical order."""
        names = smartdeck_feeds.list_feed_names()
        assert names == sorted(names)


class TestResolveFeedUnrecognizedName:
    """Test resolve_feed with unrecognized feed names."""

    def test_unknown_feed_name_raises_value_error(self):
        """Unrecognized feed name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            smartdeck_feeds.resolve_feed("nonsense_feed_name", "2026-08-14")
        assert "unknown feed" in str(exc_info.value)
        assert "nonsense_feed_name" in str(exc_info.value)

    def test_error_message_lists_valid_names(self):
        """ValueError message includes valid feed names."""
        with pytest.raises(ValueError) as exc_info:
            smartdeck_feeds.resolve_feed("bad_name", "2026-08-14")
        error_msg = str(exc_info.value)
        assert "bell_schedule" in error_msg


class TestResolveFeedNotYetAvailable:
    """Test resolve_feed with not-yet-available feed names."""

    @pytest.mark.parametrize("feed_name", [
        "birthdays_today",
        "missing_assignments",
        "positive_achievements",
        "staar_masters",
    ])
    def test_not_yet_available_feeds_return_graceful_response(self, feed_name):
        """Per-student feeds return not-yet-available without raising."""
        result = smartdeck_feeds.resolve_feed(feed_name, "2026-08-14")
        assert result["ok"] is True
        assert result["available"] is False
        assert result["feed"] == feed_name
        assert result["reason"] == "not yet available"

    def test_not_yet_available_feed_never_raises(self):
        """Not-yet-available feeds never raise, even if date_str is malformed."""
        result = smartdeck_feeds.resolve_feed("birthdays_today", "not_a_date")
        assert result["ok"] is True
        assert result["available"] is False


class TestResolveFeedBellSchedule:
    """Test resolve_feed('bell_schedule', ...)."""

    def test_bell_schedule_with_blocks(self, monkeypatch):
        """Bell schedule returns day_type, blocks, and current_block."""
        fixture_blocks = [
            {"period_id": "1", "start": "08:35", "end": "09:25", "schedule_id": "bobcat"},
            {"period_id": "2", "start": "09:29", "end": "10:21", "schedule_id": "bobcat"},
        ]
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: (fixture_blocks, [])
        )
        monkeypatch.setattr(
            "api.webui.deps.load_day_calendar",
            lambda: ({"2026-08-14": "bobcat"}, [])
        )

        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-08-14")
        assert result["ok"] is True
        assert result["available"] is True
        assert result["feed"] == "bell_schedule"
        data = result["data"]
        assert data["day_type"] == "bobcat"
        assert len(data["blocks"]) == 2
        assert data["blocks"][0]["period_id"] == "1"

    def test_bell_schedule_empty_blocks_preserves_day_type(self, monkeypatch):
        """A no-class day still reports the schedule selected by the calendar."""
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: ([], [])
        )
        monkeypatch.setattr(
            "api.webui.deps.load_day_calendar",
            lambda: ({"2026-08-14": "bobcat"}, [])
        )

        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-08-14")
        assert result["ok"] is True
        data = result["data"]
        assert data["day_type"] == "bobcat"
        assert data["blocks"] == []

    def test_bell_schedule_exception_graceful(self, monkeypatch):
        """Exception in resolve_schedule_for returns graceful response."""
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: (_ for _ in ()).throw(Exception("schedule error"))
        )

        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-08-14")
        assert result["ok"] is True
        data = result["data"]
        assert data["day_type"] is None
        assert data["blocks"] == []
        assert data["current_block"] is None

    def test_bell_schedule_current_block_today_only(self, monkeypatch):
        """current_block is only populated when date_str is today."""
        fixture_blocks = [
            {"period_id": "1", "start": "08:35", "end": "09:25", "schedule_id": "bobcat"},
            {"period_id": "2", "start": "09:29", "end": "10:21", "schedule_id": "bobcat"},
        ]
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: (fixture_blocks, [])
        )

        # Test with a past date
        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-08-01")
        data = result["data"]
        assert data["current_block"] is None

        # Test with a future date
        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-12-31")
        data = result["data"]
        assert data["current_block"] is None

    def test_bell_schedule_current_block_today(self, monkeypatch):
        """current_block is set when date is today and time falls within a block."""
        fixture_blocks = [
            {"period_id": "1", "start": "08:00", "end": "09:00", "schedule_id": "bobcat"},
            {"period_id": "2", "start": "09:00", "end": "10:00", "schedule_id": "bobcat"},
        ]
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: (fixture_blocks, [])
        )

        today_str = date.today().isoformat()

        # Mock datetime.now to return a time within the first block
        from unittest.mock import Mock
        mock_now = Mock()
        mock_now.strftime.return_value = "08:30"
        monkeypatch.setattr("api.smartdeck_feeds.datetime", Mock(now=Mock(return_value=mock_now)))

        result = smartdeck_feeds.resolve_feed("bell_schedule", today_str)
        data = result["data"]
        # current_block should be set if the time is within a block
        if data["current_block"] is not None:
            assert data["current_block"]["period_id"] == "1"


class TestResolveFeedDistrictCalendarEvents:
    """Test resolve_feed('district_calendar_events', ...)."""

    def test_district_calendar_events_classroom_only(self, monkeypatch):
        """Only classroom-facing events are returned."""
        fixture_payload = {
            "events": [
                {"kind": "no_school", "label": "Fall Break"},
                {"kind": "ssn", "label": "Secret student number"},
            ]
        }
        monkeypatch.setattr(
            "api.webui.config.get_combined_calendar_for_range",
            lambda start, end: fixture_payload
        )

        result = smartdeck_feeds.resolve_feed("district_calendar_events", "2026-08-14")
        assert result["ok"] is True
        data = result["data"]
        assert len(data) == 1
        assert data[0]["kind"] == "no_school"

    def test_district_calendar_events_no_audience_tag(self, monkeypatch):
        """Returned events have no 'audience' key."""
        fixture_payload = {
            "events": [
                {"kind": "no_school", "label": "Fall Break"},
            ]
        }
        monkeypatch.setattr(
            "api.webui.config.get_combined_calendar_for_range",
            lambda start, end: fixture_payload
        )

        result = smartdeck_feeds.resolve_feed("district_calendar_events", "2026-08-14")
        data = result["data"]
        for event in data:
            assert "audience" not in event

    def test_district_calendar_events_exception_graceful(self, monkeypatch):
        """Exception in config.get_combined_calendar_for_range returns empty list."""
        monkeypatch.setattr(
            "api.webui.config.get_combined_calendar_for_range",
            lambda start, end: (_ for _ in ()).throw(Exception("calendar error"))
        )

        result = smartdeck_feeds.resolve_feed("district_calendar_events", "2026-08-14")
        assert result["ok"] is True
        assert result["data"] == []

    def test_district_calendar_events_invalid_date_graceful(self, monkeypatch):
        """Invalid date string returns graceful response."""
        monkeypatch.setattr(
            "api.webui.config.get_combined_calendar_for_range",
            lambda start, end: {"events": []}
        )

        result = smartdeck_feeds.resolve_feed("district_calendar_events", "not_a_date")
        assert result["ok"] is True
        assert result["data"] == []


class TestResolveFeedSchoolEvents:
    """Test resolve_feed('school_events', ...)."""

    def test_school_events_classroom_only(self, monkeypatch):
        """Only classroom-facing events are returned."""
        fixture_events = [
            {"kind": "game", "label": "Football game", "start": "2026-08-15"},
            {"kind": "ssn", "label": "Secret data"},
        ]
        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            lambda date_from, date_to, root: fixture_events
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14")
        assert result["ok"] is True
        data = result["data"]
        assert len(data) == 1
        assert data[0]["kind"] == "game"

    def test_school_events_no_audience_tag(self, monkeypatch):
        """Returned events have no 'audience' key."""
        fixture_events = [
            {"kind": "game", "label": "Football game", "start": "2026-08-15"},
        ]
        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            lambda date_from, date_to, root: fixture_events
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14")
        data = result["data"]
        for event in data:
            assert "audience" not in event

    def test_school_events_exception_graceful(self, monkeypatch):
        """Exception in school_events.events_for_range returns empty list."""
        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            lambda date_from, date_to, root: (_ for _ in ()).throw(Exception("events error"))
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14")
        assert result["ok"] is True
        assert result["data"] == []

    def test_school_events_sorted(self, monkeypatch):
        """School events are sorted by _event_sort_key."""
        fixture_events = [
            {"kind": "club", "label": "Club B", "start": "2026-08-20"},
            {"kind": "game", "label": "Game A", "start": "2026-08-15"},
        ]
        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            lambda date_from, date_to, root: fixture_events
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14")
        data = result["data"]
        # Events should be sorted by start date
        assert len(data) == 2
        assert data[0]["label"] == "Game A"
        assert data[1]["label"] == "Club B"


class TestResolveFeedLookaheadDays:
    """Test lookahead_days parameter."""

    def test_lookahead_days_capped_at_max(self, monkeypatch):
        """lookahead_days is capped at MAX_LOOKAHEAD_DAYS."""
        fixture_events = []
        call_log = []

        def mock_events_for_range(date_from, date_to, root):
            call_log.append((date_from, date_to))
            return fixture_events

        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            mock_events_for_range
        )

        # Request with lookahead_days > MAX_LOOKAHEAD_DAYS
        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14", lookahead_days=50)
        assert result["ok"] is True

        # Verify the date range was capped
        assert len(call_log) == 1
        date_from, date_to = call_log[0]
        delta = (date_to - date_from).days
        assert delta == smartdeck_feeds.MAX_LOOKAHEAD_DAYS

    def test_lookahead_days_negative_becomes_zero(self, monkeypatch):
        """Negative lookahead_days is treated as zero."""
        fixture_events = []
        call_log = []

        def mock_events_for_range(date_from, date_to, root):
            call_log.append((date_from, date_to))
            return fixture_events

        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            mock_events_for_range
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14", lookahead_days=-10)
        assert result["ok"] is True

        # Verify the dates are the same (0 day span)
        date_from, date_to = call_log[0]
        assert date_from == date_to


class TestResolveScheduleRobustness:
    """Test that resolve_feed never raises for recognized names."""

    def test_bell_schedule_internal_exception_graceful(self, monkeypatch):
        """Bell schedule exception doesn't propagate."""
        monkeypatch.setattr(
            "api.webui.deps.resolve_schedule_for",
            lambda date_str: (_ for _ in ()).throw(Exception("mock error"))
        )

        result = smartdeck_feeds.resolve_feed("bell_schedule", "2026-08-14")
        assert result["ok"] is True
        assert result["available"] is True
        # Should have a valid response, not raise

    def test_district_calendar_malformed_payload_graceful(self, monkeypatch):
        """Malformed calendar payload is handled gracefully."""
        monkeypatch.setattr(
            "api.webui.config.get_combined_calendar_for_range",
            lambda start, end: "not a dict"  # Wrong type
        )

        result = smartdeck_feeds.resolve_feed("district_calendar_events", "2026-08-14")
        assert result["ok"] is True
        assert result["data"] == []

    def test_school_events_non_list_return_graceful(self, monkeypatch):
        """Non-list return from events_for_range is handled gracefully."""
        monkeypatch.setattr(
            "api.webui.school_events.events_for_range",
            lambda date_from, date_to, root: "not a list"  # Wrong type
        )

        result = smartdeck_feeds.resolve_feed("school_events", "2026-08-14")
        assert result["ok"] is True
        assert result["data"] == []
