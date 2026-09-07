"""Teacher-facing local wall-clock values used by Calendar.

The authored/display contract is ``h:mm AM`` or ``h:mm PM``.  A small
minutes-since-midnight representation keeps comparisons independent of the
rendered spelling and avoids lexicographic bugs around 10 o'clock and noon.

Reads also accept an unambiguous two-digit-hour 24-hour value and normalize it,
so an existing file is displayed in the 12-hour form rather than refused.
"""

from __future__ import annotations

import re


_TIME_RE = re.compile(r"^(1[0-2]|[1-9]):([0-5][0-9])\s*(AM|PM)$", re.IGNORECASE)

# Read tolerance for 24-hour source values, so a Bell Schedule a teacher already
# had -- or typed off a district bell chart -- is not rejected for its spelling.
# The hour must be two digits: "08:35" and "13:13" mean exactly one time, but a
# bare "1:15" does not. Read as 24-hour it is the middle of the night, while a
# teacher writing a bell schedule means the afternoon, and guessing would put a
# class at 1 AM every day without ever looking wrong. Single-digit hours with no
# meridiem stay invalid so they surface as a repairable problem instead.
_TIME_24_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def parse_time(value: str | None) -> int | None:
    """Return local minutes after midnight for a canonical 12-hour value, or for
    an unambiguous two-digit-hour 24-hour value."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = _TIME_RE.fullmatch(text)
    if not match:
        match24 = _TIME_24_RE.fullmatch(text)
        if not match24:
            return None
        return int(match24.group(1)) * 60 + int(match24.group(2))
    hour = int(match.group(1))
    minute = int(match.group(2))
    if match.group(3).upper() == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return hour * 60 + minute


def format_time(minutes: int | None) -> str:
    """Format minutes after midnight as the canonical teacher-facing value."""
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 <= minutes < 24 * 60:
        return ""
    hour24, minute = divmod(minutes, 60)
    meridiem = "AM" if hour24 < 12 else "PM"
    hour12 = hour24 % 12 or 12
    return f"{hour12}:{minute:02d} {meridiem}"


def normalize_time(value: str | None) -> str:
    """Return canonical 12-hour text, or the original value when invalid."""
    minutes = parse_time(value)
    return format_time(minutes) if minutes is not None else str(value or "")
