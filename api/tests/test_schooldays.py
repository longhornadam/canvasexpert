from datetime import datetime

from api.webui import schooldays as sd


def test_add_school_days_skips_weekend():
    # Fri 2026-09-04 + 2 school days -> Tue 2026-09-08 (Sat/Sun are no-count)
    due = datetime(2026, 9, 4, 23, 59)
    no_count = {"2026-09-05", "2026-09-06"}
    out = sd._add_school_days(due, 2, no_count)
    assert out.date().isoformat() == "2026-09-08"


def test_add_school_days_skips_holiday():
    # Mon +1, but Tue 2026-09-08 is a no-count day -> Wed 2026-09-09
    start = datetime(2026, 9, 7, 23, 59)
    out = sd._add_school_days(start, 1, {"2026-09-08"})
    assert out.date().isoformat() == "2026-09-09"


def test_is_school_day():
    assert sd._is_school_day(datetime(2026, 9, 4).date(), set()) is True   # Fri
    assert sd._is_school_day(datetime(2026, 9, 5).date(), {"2026-09-05"}) is False  # Sat, marked no-count
    assert sd._is_school_day(datetime(2026, 9, 4).date(), {"2026-09-04"}) is False
