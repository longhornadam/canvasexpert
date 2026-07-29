"""The no-school wrapper: parse the real shape, and never raise.

Every call into the academic calendar is monkeypatched here. Nothing in this
file reads or writes a workspace file, and the session-wide fixture in
`api/tests/conftest.py` already points the real config paths at a temp
location.
"""
from __future__ import annotations

from datetime import date

import pytest

from api.schedule import calendar

FROM = date(2027, 9, 13)
TO = date(2027, 9, 24)

# The shape api/webui/config/calendars.py actually returns.
REAL_SHAPE = {
    "no_count_dates": ["2027-09-16", "2027-09-17"],
    "grading_periods": [{"start": "2027-08-16", "end": "2027-10-15", "label": "Q1"}],
}


def _patch(monkeypatch, replacement):
    monkeypatch.setattr(
        "api.webui.config.get_combined_calendar_for_range", replacement
    )


def test_parses_the_real_return_shape(monkeypatch):
    _patch(monkeypatch, lambda **kwargs: REAL_SHAPE)

    assert calendar.no_school_dates(FROM, TO) == frozenset(
        {date(2027, 9, 16), date(2027, 9, 17)}
    )


def test_passes_the_range_as_iso_strings(monkeypatch):
    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"no_count_dates": [], "grading_periods": []}

    _patch(monkeypatch, fake)

    calendar.no_school_dates(FROM, TO)

    assert seen == {"date_from": "2027-09-13", "date_to": "2027-09-24"}


def test_empty_calendar_is_empty_not_an_error(monkeypatch):
    _patch(monkeypatch, lambda **kwargs: {"no_count_dates": [], "grading_periods": []})

    assert calendar.no_school_dates(FROM, TO) == frozenset()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"grading_periods": []},
        {"no_count_dates": None},
        {"no_count_dates": "2027-09-16"},
        None,
        "unconfigured",
    ],
)
def test_unexpected_payloads_degrade_to_empty(monkeypatch, payload):
    _patch(monkeypatch, lambda **kwargs: payload)

    assert calendar.no_school_dates(FROM, TO) == frozenset()


def test_a_failing_calendar_does_not_blank_the_screen(monkeypatch):
    def fake(**kwargs):
        raise RuntimeError("no calendar configured")

    _patch(monkeypatch, fake)

    assert calendar.no_school_dates(FROM, TO) == frozenset()


def test_a_call_signature_mismatch_degrades_rather_than_raising(monkeypatch):
    # Several existing tests replace this call with a no-argument lambda. A
    # projector should survive that rather than crash on a TypeError.
    _patch(monkeypatch, lambda: REAL_SHAPE)

    assert calendar.no_school_dates(FROM, TO) == frozenset()


def test_unparseable_entries_are_dropped_not_fatal(monkeypatch):
    _patch(monkeypatch, lambda **kwargs: {
        "no_count_dates": ["2027-09-16", "not a date", "", None, 20270917],
    })

    assert calendar.no_school_dates(FROM, TO) == frozenset({date(2027, 9, 16)})


def test_dates_outside_the_requested_range_are_ignored(monkeypatch):
    _patch(monkeypatch, lambda **kwargs: {
        "no_count_dates": ["2027-09-01", "2027-09-16", "2027-12-24"],
    })

    assert calendar.no_school_dates(FROM, TO) == frozenset({date(2027, 9, 16)})


def test_range_ends_are_inclusive(monkeypatch):
    _patch(monkeypatch, lambda **kwargs: {
        "no_count_dates": [FROM.isoformat(), TO.isoformat()],
    })

    assert calendar.no_school_dates(FROM, TO) == frozenset({FROM, TO})


def test_config_is_not_imported_at_module_level():
    """api/schedule must stay importable where keyring is not available."""
    assert "config" not in vars(calendar)
    assert not any(
        getattr(value, "__name__", "").startswith("api.webui")
        for value in vars(calendar).values()
    )
