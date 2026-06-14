from datetime import datetime

from api.webui import schooldays as sd


def test_add_school_days_skips_weekend():
    # Fri 2026-09-04 + 2 school days -> Tue 2026-09-08 (Sat/Sun skipped)
    due = datetime(2026, 9, 4, 23, 59)
    out = sd._add_school_days(due, 2, True, set())
    assert out.date().isoformat() == "2026-09-08"


def test_add_school_days_skips_holiday():
    # Mon +1, but Tue 2026-09-08 is a holiday -> Wed 2026-09-09
    start = datetime(2026, 9, 7, 23, 59)
    out = sd._add_school_days(start, 1, True, {"2026-09-08"})
    assert out.date().isoformat() == "2026-09-09"


def test_is_school_day():
    assert sd._is_school_day(datetime(2026, 9, 4).date(), True, set()) is True   # Fri
    assert sd._is_school_day(datetime(2026, 9, 5).date(), True, set()) is False  # Sat
    assert sd._is_school_day(datetime(2026, 9, 4).date(), True, {"2026-09-04"}) is False